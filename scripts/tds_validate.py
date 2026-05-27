#!/usr/bin/env python3
"""
tds_validate.py — Validate an HPDF TDS Markdown document.

Usage:
    python3 tds_validate.py <TDS_FILE.md> [--check <validator,...>]

Runs all registered validators by default.  Pass --check to run a subset.

Built-in validators
  mermaid   Render every ```mermaid block through mmdc (catches grammar errors
            that only manifest at render time).
  images    Verify every engineer-authored PNG reference exists on disk.

Adding a new validator
  1. Subclass Validator and implement run().
  2. Append an instance to _ALL_VALIDATORS below the class definition.
  That's it — the CLI picks it up automatically.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


# ── Result types ───────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    """Outcome of a single check within a validator run."""
    label:   str        # human-readable identifier, e.g. "fig_01" or "diagrams/foo.png"
    ok:      bool
    message: str = ""   # error detail; empty when ok is True


@dataclass
class ValidatorReport:
    """Aggregated results for one validator."""
    name:    str
    results: List[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.ok for r in self.results)

    @property
    def failures(self) -> List[CheckResult]:
        return [r for r in self.results if not r.ok]


# ── Validator base class ───────────────────────────────────────────────────────

class Validator(ABC):
    """
    Base class for all TDS validators.

    Subclass this, set `name` and `description`, implement `run()`, and
    append an instance to _ALL_VALIDATORS at module level.
    """
    name:        str = ""
    description: str = ""

    @abstractmethod
    def run(self, content: str, doc_dir: Path) -> ValidatorReport:
        """
        Validate the document and return a ValidatorReport.

        Args:
            content: Full text of the TDS Markdown file.
            doc_dir: Directory containing the file (used for resolving
                     relative paths such as image references).
        """


# ── Built-in validators ────────────────────────────────────────────────────────

class MermaidValidator(Validator):
    """
    Render every ```mermaid block through mmdc.

    mmdc parses the diagram and produces a PNG; any grammar error surfaces
    here rather than at full render time.  The temporary PNG is discarded.
    """
    name        = "mermaid"
    description = "Render every Mermaid block through mmdc to catch syntax errors"

    _BLOCK_RE = re.compile(r'```mermaid\n(.*?)\n```', re.DOTALL)

    def _find_blocks(self, content: str) -> List[str]:
        return [m.group(1) for m in self._BLOCK_RE.finditer(content)]

    def _validate_one(self, source: str) -> tuple:   # (ok: bool, stderr: str)
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.mmd', delete=False, encoding='utf-8'
        ) as f:
            f.write(source)
            tmp_in = f.name
        tmp_out = tmp_in.replace('.mmd', '.png')
        try:
            r = subprocess.run(
                ['mmdc', '-i', tmp_in, '-o', tmp_out, '-t', 'neutral'],
                capture_output=True,
                text=True,
            )
            return r.returncode == 0, r.stderr.strip()
        finally:
            for p in (tmp_in, tmp_out):
                try:
                    os.unlink(p)
                except FileNotFoundError:
                    pass

    def run(self, content: str, doc_dir: Path) -> ValidatorReport:
        report = ValidatorReport(name=self.name)
        blocks = self._find_blocks(content)
        for i, source in enumerate(blocks, 1):
            ok, msg = self._validate_one(source)
            report.results.append(CheckResult(
                label=f"fig_{i:02d}", ok=ok, message=msg,
            ))
        return report


class ImageValidator(Validator):
    """
    Verify every engineer-authored PNG reference exists on disk.

    Mirrors the pre-flight check in tds_render.py so problems are caught
    before a full render is attempted.
    """
    name        = "images"
    description = "Verify all engineer-authored PNG image references exist on disk"

    _COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)
    _FENCE_RE   = re.compile(r'```[^\n]*\n.*?```', re.DOTALL)
    _IMG_RE     = re.compile(r'!\[[^\]]*\]\(\s*"?([^")>\s]+)"?\s*\)')

    def _find_refs(self, content: str) -> List[str]:
        # Strip HTML comments (template guidance) and fenced blocks (examples)
        stripped = self._COMMENT_RE.sub('', content)
        stripped = self._FENCE_RE.sub('', stripped)
        refs = self._IMG_RE.findall(stripped)
        return [r for r in refs if not re.match(r'https?://', r)]

    def run(self, content: str, doc_dir: Path) -> ValidatorReport:
        report = ValidatorReport(name=self.name)
        for ref in self._find_refs(content):
            exists = (doc_dir / ref).resolve().exists()
            report.results.append(CheckResult(
                label=ref,
                ok=exists,
                message="" if exists else f"file not found: {ref}",
            ))
        return report


# ── Validator registry ─────────────────────────────────────────────────────────
# Add new validator instances here; the CLI discovers them automatically.

_ALL_VALIDATORS: List[Validator] = [
    MermaidValidator(),
    ImageValidator(),
]

REGISTRY: dict = {v.name: v for v in _ALL_VALIDATORS}


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Validate an HPDF TDS Markdown file.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(
            f"  {v.name:<12} {v.description}" for v in _ALL_VALIDATORS
        ),
    )
    parser.add_argument(
        'input',
        help='TDS Markdown file to validate (e.g. HPDF_TDS_0003_iam.md)',
    )
    parser.add_argument(
        '--check',
        metavar='VALIDATORS',
        default=None,
        help=(
            'Comma-separated list of validators to run '
            f'(default: all). Available: {", ".join(REGISTRY)}'
        ),
    )
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"Error: file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    content = input_path.read_text(encoding='utf-8')
    doc_dir = input_path.parent

    # Resolve which validators to run
    if args.check:
        names = [n.strip() for n in args.check.split(',')]
        unknown = [n for n in names if n not in REGISTRY]
        if unknown:
            print(
                f"Error: unknown validator(s): {', '.join(unknown)}\n"
                f"Available: {', '.join(REGISTRY)}",
                file=sys.stderr,
            )
            sys.exit(1)
        validators = [REGISTRY[n] for n in names]
    else:
        validators = list(REGISTRY.values())

    print(f"Validating: {input_path.name}")

    total_failures = 0

    for validator in validators:
        report = validator.run(content, doc_dir)

        if not report.results:
            continue  # validator had nothing to check (e.g. no Mermaid blocks)

        print(f"\n  [{validator.name}]")
        for result in report.results:
            print(f"    {result.label} ... {'ok' if result.ok else 'FAILED'}")
            if not result.ok and result.message:
                for line in result.message.splitlines():
                    print(f"      {line}", file=sys.stderr)

        total_failures += len(report.failures)

    if total_failures:
        print(
            f"\n{total_failures} check(s) failed — fix errors above before rendering.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("\nAll checks passed.")


if __name__ == '__main__':
    main()
