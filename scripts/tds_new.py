#!/usr/bin/env python3
"""
tds_new.py — Create a new HPDF TDS document from the template.

Usage:
    python3 tds_new.py <title>
                       [--owner <name>]
                       [--component <name>]
                       [--id <NNNN>]
                       [--slug <slug>]

Steps:
  1. Read TDS_REGISTRY.md to determine the next available doc ID.
  2. Read TDS_TEMPLATE.md from the working directory.
  3. Substitute all placeholder values (doc_id, title, owner, dates).
  4. Write HPDF_TDS_NNNN_<slug>.md to the working directory.
  5. Append a new row to TDS_REGISTRY.md and update its "Last updated" line.
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path


# These paths are relative to /workspace (the user's TDS directory,
# mounted by the `tds` wrapper script at runtime).
TEMPLATE_FILE = Path("TDS_TEMPLATE.md")
REGISTRY_FILE = Path("TDS_REGISTRY.md")


# ── Helpers ────────────────────────────────────────────────────────────────────

def slugify(text: str, max_len: int = 40) -> str:
    """
    Convert a title to a filename-safe slug.
    e.g. "Transfer Engine: Hub Design" → "transfer-engine-hub-design"
    """
    slug = text.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)   # non-alphanumeric → hyphen
    slug = slug.strip('-')                      # trim leading/trailing hyphens
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip('-')       # truncate cleanly
    return slug


def next_doc_id(registry_path: Path, override: str | None = None) -> str:
    """
    Scan TDS_REGISTRY.md for the highest HPDF_TDS_NNNN ID and return the next one.
    If --id NNNN was given, validate it and return that instead.
    """
    if override is not None:
        try:
            n = int(override)
        except ValueError:
            print(f"Error: --id must be a number, got: {override!r}", file=sys.stderr)
            sys.exit(1)
        return f"HPDF_TDS_{n:04d}"

    if not registry_path.exists():
        print(
            f"Error: {registry_path} not found.\n"
            "Run 'tds init' to initialise a TDS working directory.",
            file=sys.stderr,
        )
        sys.exit(1)

    content = registry_path.read_text(encoding='utf-8')
    ids = re.findall(r'HPDF_TDS_(\d{4})', content)
    if not ids:
        return "HPDF_TDS_0001"
    return f"HPDF_TDS_{max(int(n) for n in ids) + 1:04d}"


# ── Template substitution ──────────────────────────────────────────────────────

def _sub(pattern: str, replacement: str, text: str, **kwargs) -> str:
    """re.sub wrapper that asserts the pattern matched at least once."""
    result, n = re.subn(pattern, replacement, text, **kwargs)
    if n == 0:
        print(
            f"Warning: substitution pattern not found in template:\n  {pattern}",
            file=sys.stderr,
        )
    return result


def substitute_template(content: str, doc_id: str, title: str,
                         owner: str, today: str) -> str:
    """Apply all placeholder substitutions to the template content."""

    num = doc_id.split('_')[-1]   # '0001'

    # ── YAML frontmatter ──────────────────────────────────────────────────────

    content = _sub(
        r'^(doc_id:\s*)"HPDF_TDS_XXXX"',
        lambda m: f'{m.group(1)}"{doc_id}"',
        content, flags=re.MULTILINE,
    )
    content = _sub(
        r'^(title:\s*)"<Component or Feature Name>"',
        lambda m: f'{m.group(1)}"{title}"',
        content, flags=re.MULTILINE,
    )
    # owner: "<Name>"   # comment
    content = _sub(
        r'^(owner:\s*)"<Name>"([ \t]*#[^\n]*)?',
        lambda m: (
            f'{m.group(1)}"{owner}"'
            + ('  ' + m.group(2).strip() if m.group(2) else '')
        ),
        content, flags=re.MULTILINE,
    )
    # Both 'created' and 'last_updated' share the YYYY-MM-DD placeholder
    content = _sub(
        r'^((?:created|last_updated):\s*)"YYYY-MM-DD"',
        lambda m: f'{m.group(1)}"{today}"',
        content, flags=re.MULTILINE,
    )

    # ── Markdown heading ──────────────────────────────────────────────────────

    # Template: # HPDF_TDS_XXXX — \<Title\>
    content = _sub(
        r'^# HPDF_TDS_XXXX — \\<Title\\>',
        f'# {doc_id} — {title}',
        content, flags=re.MULTILINE,
    )

    # ── Markdown header table ─────────────────────────────────────────────────

    content = _sub(
        r'(\|\s*\*\*Document ID\*\*\s*\|\s*)HPDF_TDS_XXXX(\s*\|)',
        lambda m: f'{m.group(1)}{doc_id}{m.group(2)}',
        content,
    )
    # Template value is "Architecture of something"
    content = _sub(
        r'(\|\s*\*\*Title\*\*\s*\|\s*)Architecture of something(\s*\|)',
        lambda m: f'{m.group(1)}{title}{m.group(2)}',
        content,
    )
    # Template value is \<Name \>  (backslash-escaped angle brackets)
    content = _sub(
        r'(\|\s*\*\*Owner\*\*\s*\|\s*)\\<Name \\>(\s*\|)',
        lambda m: f'{m.group(1)}{owner}{m.group(2)}',
        content,
    )
    # Both Created and Last Updated rows share the YYYY-MM-DD placeholder
    content = _sub(
        r'(\|\s*\*\*(?:Created|Last Updated)\*\*\s*\|\s*)YYYY-MM-DD(\s*\|)',
        lambda m: f'{m.group(1)}{today}{m.group(2)}',
        content,
    )

    # ── Render-hint comment: update the example command with the real filename ──

    slug = slugify(title)
    new_filename = f"HPDF_TDS_{num}_{slug}.md"
    content = re.sub(
        r'(#\s+python3 scripts/tds_render\.py\s+)HPDF_TDS_XXXX_<slug>\.md',
        lambda m: f'{m.group(1)}{new_filename}',
        content,
    )

    return content


# ── Registry update ────────────────────────────────────────────────────────────

def append_registry_row(registry_path: Path, doc_id: str, title: str,
                         owner: str, component: str, filename: str,
                         today: str) -> None:
    """
    Append a new row to the TDS_REGISTRY.md table and update the
    "Last updated" footer line.
    """
    content = registry_path.read_text(encoding='utf-8')
    lines   = content.splitlines(keepends=True)

    new_row = (
        f"| {doc_id} | {title} | {owner} | {component} | DRAFT | {filename} |\n"
    )

    # Find the last line that starts a pipe-table row (i.e. the last data row).
    # We skip separator rows (lines whose non-pipe content is only - : and spaces).
    last_pipe_idx = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('|'):
            last_pipe_idx = i

    if last_pipe_idx >= 0:
        lines.insert(last_pipe_idx + 1, new_row)
    else:
        print(
            "Warning: could not locate the registry table — appending row at end.",
            file=sys.stderr,
        )
        lines.append(new_row)

    updated = ''.join(lines)
    updated = re.sub(
        r'\*Last updated:.*?\*',
        f'*Last updated: {today}*',
        updated,
    )
    registry_path.write_text(updated, encoding='utf-8')


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Create a new HPDF TDS document from the template.',
    )
    parser.add_argument(
        'title',
        help='Document title, e.g. "Transfer Engine Design"',
    )
    parser.add_argument(
        '--owner',
        default='',
        metavar='NAME',
        help='Owner name, e.g. "I. Baldin"',
    )
    parser.add_argument(
        '--component',
        default='',
        metavar='NAME',
        help='Short component label for the registry, e.g. "Data Transfer"',
    )
    parser.add_argument(
        '--id',
        default=None,
        metavar='NNNN',
        help='Override the auto-assigned document number (4-digit integer)',
    )
    parser.add_argument(
        '--slug',
        default=None,
        metavar='SLUG',
        help='Override the auto-derived filename slug, e.g. "transfer-engine"',
    )
    args = parser.parse_args()

    today = date.today().isoformat()

    # ── Validate inputs ───────────────────────────────────────────────────────

    if not TEMPLATE_FILE.exists():
        print(
            f"Error: {TEMPLATE_FILE} not found.\n"
            "Run 'tds init' to download the template files.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── Derive ID, slug, and filename ─────────────────────────────────────────

    doc_id   = next_doc_id(REGISTRY_FILE, override=args.id)
    num      = doc_id.split('_')[-1]                           # e.g. '0042'
    slug     = args.slug if args.slug else slugify(args.title)
    filename = f"HPDF_TDS_{num}_{slug}.md"
    out_path = Path(filename)

    if out_path.exists():
        print(
            f"Error: {filename} already exists.\n"
            "Use --slug or --id to produce a different filename.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── Read, substitute, write ───────────────────────────────────────────────

    template = TEMPLATE_FILE.read_text(encoding='utf-8')
    doc      = substitute_template(template, doc_id, args.title, args.owner, today)
    out_path.write_text(doc, encoding='utf-8')

    # ── Update registry ───────────────────────────────────────────────────────

    append_registry_row(
        REGISTRY_FILE,
        doc_id    = doc_id,
        title     = args.title,
        owner     = args.owner,
        component = args.component,
        filename  = filename,
        today     = today,
    )

    # ── Summary ───────────────────────────────────────────────────────────────

    print(f"Created  : {filename}")
    print(f"Doc ID   : {doc_id}")
    print(f"Registry : TDS_REGISTRY.md updated")
    print()
    print("Next steps:")
    print(f"  1. Fill in §1 Overview & Objectives and §2 Background")
    print(f"  2. Draft §3 Architecture with your team or LLM assistance")
    print(f"  3. When ready: tds render {filename}")


if __name__ == '__main__':
    main()
