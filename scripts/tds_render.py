#!/usr/bin/env python3
"""
tds_render.py — Convert an HPDF TDS Markdown document to DOCX.

Usage:
    python3 tds_render.py <TDS_FILE.md> [--reference-doc <hpdf-reference.docx>]
                                        [--output <output.docx>]

Steps:
  1. Parse YAML frontmatter to extract doc_id and derive slug from filename.
  2. Pre-flight check: verify all engineer-authored PNG references exist on disk.
  3. Scan the document for Mermaid fenced blocks.
  4. Render each block to PNG via mmdc, saved to diagrams/ as
     HPDF_TDS_<id>_<slug>_fig_NN.png.
  5. Build a temporary render copy of the MD with Mermaid blocks replaced
     by standard image references.
  6. Run pandoc on the render copy to produce the DOCX.
  7. Delete all temporary files (render copy + generated PNGs).
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Cover-page post-processor (same directory as this script)
sys.path.insert(0, str(Path(__file__).parent))
_COVER_AVAILABLE = False
_COVER_IMPORT_ERROR = None
try:
    from tds_cover import (
        prepend_cover as _prepend_cover,
        add_table_borders as _add_table_borders,
        strip_bookmarks as _strip_bookmarks,
    )
    _COVER_AVAILABLE = True
except ImportError as _e:
    _COVER_IMPORT_ERROR = _e


# ── Helpers ────────────────────────────────────────────────────────────────────

def find_tool(name):
    """Return the absolute path to a CLI tool, or None if not on PATH."""
    return shutil.which(name)


def parse_last_updated(content):
    """
    Extract the last_updated value from the YAML frontmatter block.
    Returns the string value or None if not found.
    """
    fm_match = re.search(r'\A---\s*\n(.*?)\n---', content, re.DOTALL)
    if not fm_match:
        return None
    date_match = re.search(
        r'^last_updated:\s*["\']?([0-9]{4}-[0-9]{2}-[0-9]{2})["\']?',
        fm_match.group(1),
        re.MULTILINE,
    )
    return date_match.group(1).strip() if date_match else None


def parse_doc_id(content):
    """
    Extract the doc_id value from the YAML frontmatter block.
    Returns the string value or None if not found.
    """
    fm_match = re.search(r'\A---\s*\n(.*?)\n---', content, re.DOTALL)
    if not fm_match:
        return None
    id_match = re.search(
        r'^doc_id:\s*["\']?([A-Za-z0-9_\-]+)["\']?',
        fm_match.group(1),
        re.MULTILINE,
    )
    return id_match.group(1).strip() if id_match else None


def numeric_id_from_doc_id(doc_id):
    """
    Extract the 4-digit numeric portion from a doc_id.
    e.g. 'HPDF_TDS_0001' -> '0001'
    Falls back to the full doc_id if no 4-digit run is found.
    """
    m = re.search(r'(\d{4})', doc_id)
    return m.group(1) if m else doc_id


def slug_from_filename(filepath):
    """
    Derive the slug from the TDS filename.
    e.g. 'HPDF_TDS_0001_example.md' -> 'example'
         'HPDF_TDS_0042_transfer-engine.md' -> 'transfer-engine'
    Falls back to the full stem if the expected prefix pattern is absent.
    """
    stem = Path(filepath).stem
    m = re.match(r'^HPDF_TDS_\d{4}_(.+)$', stem)
    return m.group(1) if m else stem


def find_engineer_image_refs(content):
    """
    Find all ![alt](path) image references in the document body,
    ignoring those inside HTML comments or fenced code blocks (which are
    typically template examples, not real assets).
    Returns a list of path strings. HTTP/S URLs are excluded.
    """
    # Strip HTML comments (<!-- ... -->) — template guidance lives here
    stripped = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
    # Strip fenced code blocks (``` ... ```) — examples and ASCII art live here
    stripped = re.sub(r'```[^\n]*\n.*?```', '', stripped, flags=re.DOTALL)
    # Match ![alt](path) where path may be optionally quoted
    refs = re.findall(r'!\[[^\]]*\]\(\s*"?([^")>\s]+)"?\s*\)', stripped)
    # Drop URLs — only local paths are checked
    return [r for r in refs if not re.match(r'https?://', r)]


def check_engineer_images(content, doc_dir):
    """
    Verify that every engineer-authored image reference in the document
    resolves to an existing file on the filesystem.
    Returns a list of ref strings for any that are missing.
    """
    missing = []
    for ref in find_engineer_image_refs(content):
        if not (doc_dir / ref).resolve().exists():
            missing.append(ref)
    return missing


def find_mermaid_blocks(content):
    """
    Return all ```mermaid ... ``` blocks as a list of
    (start_char, end_char, diagram_source) tuples.
    Positions span the full fenced block including the back-ticks.
    """
    pattern = re.compile(r'```mermaid\n(.*?)\n```', re.DOTALL)
    return [(m.start(), m.end(), m.group(1)) for m in pattern.finditer(content)]


def render_mermaid_block(mmd_source, png_path, mmdc_path):
    """
    Write mmd_source to a temp .mmd file, run mmdc to produce png_path.
    Returns True on success, False on failure (stderr is printed).
    """
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.mmd', delete=False, encoding='utf-8'
    ) as f:
        f.write(mmd_source)
        tmp_mmd = f.name

    try:
        result = subprocess.run(
            [mmdc_path, '-i', tmp_mmd, '-o', str(png_path), '-t', 'neutral'],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"    mmdc stderr:\n{result.stderr.strip()}", file=sys.stderr)
            return False
        return True
    finally:
        os.unlink(tmp_mmd)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Render an HPDF TDS Markdown file to DOCX.'
    )
    parser.add_argument(
        'input',
        help='Input TDS Markdown file (e.g. HPDF_TDS_0001_example.md)',
    )
    parser.add_argument(
        '--reference-doc',
        default=None,
        metavar='DOCX',
        help=(
            'Pandoc reference DOCX for HPDF styling. '
            'Defaults to resources/HPDF_TDS_Template.docx next to the scripts/ directory. '
            'Pass an explicit path to override, or --no-reference-doc to disable.'
        ),
    )
    parser.add_argument(
        '--no-reference-doc',
        action='store_true',
        default=False,
        help='Skip the reference DOCX entirely (pandoc default styles only).',
    )
    parser.add_argument(
        '--output',
        default=None,
        metavar='DOCX',
        help='Output DOCX path (default: same name as input with .docx extension)',
    )
    parser.add_argument(
        '--no-cover',
        action='store_true',
        default=False,
        help='Skip cover page and DOE disclaimer (useful for quick review renders)',
    )
    parser.add_argument(
        '--ascii-art-font-size',
        default=9.0,
        type=float,
        metavar='PT',
        help='Font size in points for untagged code blocks / ASCII art (default: 9)',
    )
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    doc_dir = input_path.parent
    diagrams_dir = doc_dir / 'diagrams'
    diagrams_dir.mkdir(exist_ok=True)

    output_path = Path(args.output).resolve() if args.output \
        else input_path.with_suffix('.docx')

    # ── Check required tools ──────────────────────────────────────────────────

    mmdc = find_tool('mmdc')
    if not mmdc:
        print(
            "Error: mmdc not found.\n"
            "Install with: npm install -g @mermaid-js/mermaid-cli",
            file=sys.stderr,
        )
        sys.exit(1)

    pandoc = find_tool('pandoc')
    if not pandoc:
        print(
            "Error: pandoc not found.\n"
            "Install from: https://pandoc.org/installing.html",
            file=sys.stderr,
        )
        sys.exit(1)

    lua_filter = Path(__file__).parent / 'ascii_art_font.lua'
    if not lua_filter.exists():
        print(
            f"Warning: Lua filter not found: {lua_filter}\n"
            "ASCII art blocks will use pandoc's default code font size.",
            file=sys.stderr,
        )

    if not _COVER_AVAILABLE:
        if not args.no_cover:
            print(
                "Error: python-docx is required to generate the cover page, table borders,\n"
                "and bookmark stripping.\n"
                "Install it with:\n"
                "    pip3 install python-docx\n"
                f"(Import error was: {_COVER_IMPORT_ERROR})\n"
                "To render without a cover page or post-processing, pass --no-cover.",
                file=sys.stderr,
            )
            sys.exit(1)
        else:
            print(
                "Warning: python-docx not available — table borders and bookmark "
                "stripping will be skipped.",
                file=sys.stderr,
            )

    # ── Parse document ────────────────────────────────────────────────────────

    content = input_path.read_text(encoding='utf-8')

    doc_id = parse_doc_id(content)
    if not doc_id:
        print(
            "Error: could not find doc_id in YAML frontmatter.\n"
            "Ensure the document starts with a --- block containing: doc_id: \"HPDF_TDS_NNNN\"",
            file=sys.stderr,
        )
        sys.exit(1)

    num_id       = numeric_id_from_doc_id(doc_id)
    slug         = slug_from_filename(input_path)
    last_updated = parse_last_updated(content)

    print(f"Input    : {input_path.name}")
    print(f"Doc ID   : {doc_id}  (numeric: {num_id})")
    print(f"Slug     : {slug}")
    print(f"Output   : {output_path.name}")

    # ── Pre-flight: check engineer-authored images exist ──────────────────────

    missing_images = check_engineer_images(content, doc_dir)
    if missing_images:
        print(
            f"\nError: {len(missing_images)} engineer-authored image(s) referenced "
            f"in the document were not found on the filesystem:",
            file=sys.stderr,
        )
        for ref in missing_images:
            print(f"  missing: {ref}", file=sys.stderr)
        print(
            "\nEnsure all PNG files are present in the diagrams/ directory "
            "before rendering.",
            file=sys.stderr,
        )
        sys.exit(1)

    image_refs = find_engineer_image_refs(content)
    print(f"\nEngineer images checked: {len(image_refs)} found, all present.")

    # ── Find and render Mermaid blocks ────────────────────────────────────────

    blocks = find_mermaid_blocks(content)
    print(f"\nMermaid blocks found: {len(blocks)}")

    # Artifacts written this run.  Kept on success; cleaned up on any failure.
    generated_artifacts = []
    replacements        = []   # (start, end, image_markdown) — applied in reverse

    for i, (start, end, mmd_source) in enumerate(blocks, start=1):
        base_name = f"mmdc-{slug}-{i:02d}"
        mmd_path  = diagrams_dir / f"{base_name}.mmd"
        png_path  = diagrams_dir / f"{base_name}.png"
        rel_ref   = f"diagrams/{base_name}.png"

        print(f"  [fig_{i:02d}] Rendering → {rel_ref} ... ", end='', flush=True)
        if not render_mermaid_block(mmd_source, png_path, mmdc):
            print("FAILED")
            # Clean up any artifacts already written before exiting
            for p in generated_artifacts:
                p.unlink(missing_ok=True)
            sys.exit(1)

        # Persist Mermaid source as sidecar so tds_unconvert can restore blocks
        mmd_path.write_text(mmd_source, encoding='utf-8')
        print("ok")

        generated_artifacts.extend([png_path, mmd_path])
        replacements.append((start, end, f"![Figure {i}]({rel_ref})"))

    # ── Build render copy ─────────────────────────────────────────────────────

    render_content = content
    for start, end, image_md in reversed(replacements):
        render_content = render_content[:start] + image_md + render_content[end:]

    tmp_render = tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.md',
        dir=doc_dir,
        prefix=f'_render_{input_path.stem}_',
        delete=False,
        encoding='utf-8',
    )
    tmp_render.write(render_content)
    tmp_render.close()
    tmp_render_path = Path(tmp_render.name)

    print(f"\nRender copy : {tmp_render_path.name}")

    # ── Run pandoc ────────────────────────────────────────────────────────────

    pandoc_cmd = [
        pandoc,
        str(tmp_render_path),
        '-o', str(output_path),
        '--toc',
        '-f', 'markdown+yaml_metadata_block',
    ]

    # Resolve reference doc: explicit arg → auto-discover → skip
    _default_ref = Path(__file__).parent.parent / 'resources' / 'HPDF_TDS_Template.docx'
    if args.no_reference_doc:
        ref_path = None
    elif args.reference_doc:
        ref_path = Path(args.reference_doc).resolve()
        if not ref_path.exists():
            print(
                f"Warning: --reference-doc not found: {ref_path}\n"
                "Falling back to auto-discovered template.",
                file=sys.stderr,
            )
            ref_path = _default_ref if _default_ref.exists() else None
    else:
        ref_path = _default_ref if _default_ref.exists() else None

    if ref_path and ref_path.exists():
        pandoc_cmd += ['--reference-doc', str(ref_path)]
        print(f"Reference doc: {ref_path.name}")
    elif not args.no_reference_doc:
        print(
            f"Warning: HPDF_TDS_Template.docx not found at {_default_ref}\n"
            "Rendering with pandoc default styles. "
            "Place HPDF_TDS_Template.docx in the resources/ directory for HPDF formatting.",
            file=sys.stderr,
        )

    if lua_filter.exists():
        pandoc_cmd += [
            '--lua-filter', str(lua_filter),
            '--metadata', f'ascii-art-font-pt={args.ascii_art_font_size}',
        ]

    print(f"Running pandoc  ... ", end='', flush=True)
    result = subprocess.run(pandoc_cmd, capture_output=True, text=True)

    # ── Clean up temporary files ──────────────────────────────────────────────
    # The render copy is always temporary.
    # generated_artifacts (PNGs + MMDs) are permanent sidecars — kept on success,
    # cleaned up only if pandoc fails so we don't leave a partial set.

    tmp_render_path.unlink(missing_ok=True)

    if result.returncode != 0:
        print("FAILED")
        print(result.stderr.strip(), file=sys.stderr)
        for p in generated_artifacts:
            p.unlink(missing_ok=True)
        sys.exit(1)

    print("ok")

    # ── Prepend cover page and DOE disclaimer ─────────────────────────────────

    if not args.no_cover:
        # Locate HPDF logo: resources/hpdf-logo.png relative to scripts/
        logo_path = Path(__file__).parent.parent / 'resources' / 'hpdf-logo.png'
        if not logo_path.exists():
            print(
                f"\nWarning: HPDF logo not found at {logo_path}\n"
                "Cover page will be generated without the logo.\n"
                "Place hpdf-logo.png in the resources/ directory to include it.",
                file=sys.stderr,
            )
            logo_path = None

        print("Prepending cover page ... ", end='', flush=True)
        try:
            _prepend_cover(
                docx_path=output_path,
                doc_id=doc_id,
                slug=slug,
                last_updated=last_updated or '',
                logo_path=logo_path,
            )
            print("ok")
        except Exception as exc:
            print(f"\nError: cover page generation failed: {exc}", file=sys.stderr)
            raise

    # ── Post-process: table borders and bookmark stripping ────────────────────
    # Both steps run regardless of --no-cover as long as python-docx is available.

    if _COVER_AVAILABLE:
        print("Adding table borders    ... ", end='', flush=True)
        try:
            _add_table_borders(output_path)
            print("ok")
        except Exception as exc:
            print(f"\nError: table border processing failed: {exc}", file=sys.stderr)
            raise

        print("Stripping bookmarks     ... ", end='', flush=True)
        try:
            _strip_bookmarks(output_path)
            print("ok")
        except Exception as exc:
            print(f"\nError: bookmark stripping failed: {exc}", file=sys.stderr)
            raise

    print(f"\nDone → {output_path}")


if __name__ == '__main__':
    main()
