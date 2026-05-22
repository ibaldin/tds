#!/usr/bin/env python3
"""
tds_unconvert.py — Convert a reviewed HPDF TDS DOCX back to its source
Markdown file, stripping the cover page and DOE disclaimer prepended by
tds_render.py and restoring Mermaid blocks from their saved .mmd sources.

Assumptions:
  • The DOCX has no tracked changes or comments (it is a clean review copy).
  • The original .md file is in the same directory (used to source the YAML
    frontmatter and to locate any .mmd sidecar files for Mermaid restoration).
  • Mermaid sidecar files are in diagrams/ as HPDF_TDS_<num>_<slug>_fig_NN.mmd
    (produced automatically by tds_render.py when a block is rendered).

Usage:
    python3 tds_unconvert.py <DOCX_FILE> [--output <output.md>]
                                         [--original <original.md>]
                                         [--no-mermaid-restore]

Steps:
  1. Parse YAML frontmatter from the original .md (same dir, same stem).
  2. Strip cover/disclaimer elements from the DOCX body using python-docx
     (Title/Subtitle block, doc-number, date, page breaks, disclaimer table,
     and the first w:sdt TOC — identical to what tds_cover.py inserted).
  3. Run pandoc on the stripped DOCX to produce raw Markdown.
  4. Clean up pandoc artefacts (setext headings → ATX, spurious blank lines,
     image captions, page-break paragraphs, etc.).
  5. Restore Mermaid blocks: replace ![Figure N](diagrams/…_fig_NN.png)
     references with the original ```mermaid … ``` source from the .mmd files.
  6. Prepend the original YAML frontmatter block.
  7. Write output (default: same path as input with .md extension).
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

# Auto-apply heading style fix (works on old and new DOCXes alike)
sys.path.insert(0, str(Path(__file__).parent))
try:
    from fix_heading_styles import patch_docx as _patch_heading_styles
    _HEADING_FIX_AVAILABLE = True
except ImportError:
    _HEADING_FIX_AVAILABLE = False


# ── DOCX stripping ─────────────────────────────────────────────────────────────

def _style_val(para_elem):
    """Return the pStyle value for an lxml paragraph element, or ''."""
    ps = para_elem.find('.//' + qn('w:pStyle'))
    return ps.get(qn('w:val'), '') if ps is not None else ''


def _is_page_break(elem):
    """Return True if elem is a paragraph containing only a page-break run."""
    tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
    if tag != 'p':
        return False
    br = elem.find('.//' + qn('w:br'))
    if br is None:
        return False
    return br.get(qn('w:type'), '') == 'page'


def _has_picture(elem):
    """Return True if the element contains an inline image (w:drawing)."""
    return elem.find('.//' + qn('w:drawing')) is not None


def _text_of(elem):
    """Concatenate all w:t text in *elem*."""
    return ''.join(
        t.text or '' for t in elem.findall('.//' + qn('w:t'))
    )


def strip_cover_and_toc(docx_path: Path) -> Path:
    """
    Remove the cover page, DOE disclaimer, and TOC from *docx_path*.
    Returns the path to a new temporary DOCX containing only the body.

    Elements removed (in order from the top of body):
      • Logo paragraph (Title style, contains a picture)
      • Title paragraph  (style Title)
      • Subtitle paragraph (style Subtitle)
      • Doc-number paragraph (gray text with doc ID)
      • Date paragraph (gray text)
      • Page-break paragraph  (end of cover page 1)
      • Attribution paragraph (DOE attribution sentence)
      • Contract number paragraph (centred DE-AC05-…)
      • Blank paragraph
      • Disclaimer table (w:tbl)
      • Page-break paragraph  (end of disclaimer page 2)
      • TOC (w:sdt)
      • Page-break paragraph  (after TOC, inserted by tds_cover.py)
    """
    doc  = Document(str(docx_path))
    body = doc.element.body

    to_remove = []
    state     = 'cover'   # cover → disclaimer → toc → done

    for child in list(body):
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag

        if state == 'done':
            break

        # ── Cover page ────────────────────────────────────────────────────────
        if state == 'cover':
            if tag == 'p':
                sval = _style_val(child)
                if sval in ('Title', 'Subtitle'):
                    to_remove.append(child)
                    continue
                if _has_picture(child):
                    to_remove.append(child)
                    continue
                if _is_page_break(child):
                    to_remove.append(child)
                    state = 'disclaimer'
                    continue
                # Doc-number / date paragraphs are Normal style with gray text
                txt = _text_of(child).strip()
                if txt and not _style_val(child):
                    to_remove.append(child)
                    continue
                if _style_val(child) in ('', 'Normal', 'BodyText',
                                         'FirstParagraph'):
                    to_remove.append(child)
                    continue
            else:
                # Non-paragraph before page break → remove (shouldn't happen)
                to_remove.append(child)

        # ── Disclaimer page ───────────────────────────────────────────────────
        elif state == 'disclaimer':
            if tag == 'tbl':
                to_remove.append(child)
                continue
            if tag == 'p':
                if _is_page_break(child):
                    to_remove.append(child)
                    state = 'toc'
                    continue
                to_remove.append(child)

        # ── TOC ───────────────────────────────────────────────────────────────
        elif state == 'toc':
            if tag == 'sdt':
                to_remove.append(child)
                state = 'post_toc'
                continue
            # Blank paragraphs between disclaimer pb and TOC
            if tag == 'p' and not _text_of(child).strip():
                to_remove.append(child)

        # ── Page break immediately after TOC ──────────────────────────────────
        elif state == 'post_toc':
            if tag == 'p' and _is_page_break(child):
                to_remove.append(child)
            state = 'done'

    for elem in to_remove:
        body.remove(elem)

    tmp = Path(tempfile.mktemp(suffix='_stripped.docx'))
    doc.save(str(tmp))
    return tmp


# ── ASCII-art block reassembly ─────────────────────────────────────────────────

def _is_ascii_art_para(elem) -> bool:
    """
    Return True if *elem* looks like a paragraph emitted by ascii_art_font.lua:
      • at least one run font set to Courier New (required in all cases)
      • AND one of:
          - no explicit paragraph style / Normal (old Lua filter: no pStyle emitted)
          - pStyle "Source Code" (new Lua filter: pStyle added but style undefined
            in the DOCX, so pandoc's style lookup silently fails)

    Both cases need intervention before pandoc can round-trip them as code blocks.
    """
    tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
    if tag != 'p':
        return False
    # Require Courier New on at least one run
    fonts = elem.findall('.//' + qn('w:rFonts'))
    has_courier = any(
        f.get(qn('w:ascii'), '').lower() == 'courier new'
        for f in fonts
    )
    if not has_courier:
        return False
    # Accept: no pStyle, Normal, or "Source Code" (with or without definition)
    ps = elem.find('.//' + qn('w:pStyle'))
    if ps is None:
        return True
    return ps.get(qn('w:val'), '').lower() in ('', 'normal', 'source code', 'sourcecode')


def reassemble_ascii_art_blocks(docx_path: Path) -> Path:
    """
    Prepare ASCII-art code-block paragraphs for pandoc round-trip:

    1. Ensure every matching paragraph has <w:pStyle w:val="Source Code"/>.
       Old Lua filter output has no pStyle; new output already has it but the
       style is not defined in the DOCX, so pandoc's lookup silently fails.

    2. Inject a minimal "Source Code" style definition into the DOCX styles
       part so pandoc can resolve the pStyle ID to the name "Source Code" and
       emit a fenced code block.

    Returns the path to a new temporary DOCX, or the original path unchanged
    if no matching paragraphs were found.
    """
    doc  = Document(str(docx_path))
    body = doc.element.body

    # ── Step 1: ensure every ASCII-art paragraph has the right pStyle ─────────
    changed = 0
    for child in body:
        if not _is_ascii_art_para(child):
            continue
        pPr = child.find(qn('w:pPr'))
        if pPr is None:
            pPr = OxmlElement('w:pPr')
            child.insert(0, pPr)
        pStyle = pPr.find(qn('w:pStyle'))
        if pStyle is None:
            pStyle = OxmlElement('w:pStyle')
            pPr.insert(0, pStyle)
        pStyle.set(qn('w:val'), 'SourceCode')
        changed += 1

    if changed == 0:
        return docx_path   # nothing to do — return original path unchanged

    # No style definition injection needed: pandoc 2.9.x recognises the
    # 'SourceCode' styleId as a code block directly, without a definition.

    tmp = Path(tempfile.mktemp(suffix='_ascii_fixed.docx'))
    doc.save(str(tmp))
    return tmp


# ── Pandoc conversion ──────────────────────────────────────────────────────────

def docx_to_markdown(docx_path: Path) -> str:
    """Run pandoc on *docx_path* and return raw Markdown text."""
    pandoc = shutil.which('pandoc')
    if not pandoc:
        print("Error: pandoc not found.", file=sys.stderr)
        sys.exit(1)

    result = subprocess.run(
        [
            pandoc, str(docx_path),
            # Use pipe tables; disable grid/simple/multiline table formats so
            # all tables come back as clean pipe-delimited Markdown.
            '--to=markdown+pipe_tables-grid_tables-simple_tables-multiline_tables',
            '--wrap=none',
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Error: pandoc failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout


# ── Markdown cleanup ───────────────────────────────────────────────────────────

_SETEXT_H1 = re.compile(r'^(.+)\n={3,}\s*$', re.MULTILINE)
_SETEXT_H2 = re.compile(r'^(.+)\n-{3,}\s*$', re.MULTILINE)

def _setext_to_atx(md: str) -> str:
    """Convert setext headings (underline style) to ATX (# prefix)."""
    md = _SETEXT_H1.sub(r'# \1', md)
    md = _SETEXT_H2.sub(r'## \1', md)
    return md


def _unescape_markdown(md: str) -> str:
    """
    Remove pandoc's backslash-escaping of characters that are safe
    unescaped in our source Markdown (underscores, brackets, dots in
    numbered headings, angle brackets inside normal text).

    Pandoc adds these to prevent accidental interpretation, but our
    source files already use them unescaped in prose and heading text.
    """
    # \_ inside inline text → _   (e.g. HPDF\_TDS\_0001 → HPDF_TDS_0001)
    md = re.sub(r'(?<!\\)\\_', '_', md)
    # \[ and \] in inline text → [ and ]
    md = re.sub(r'\\\[', '[', md)
    md = re.sub(r'\\\]', ']', md)
    # \. after a digit (numbered list items in headings) → .
    md = re.sub(r'(\d)\\\.', r'\1.', md)
    # \< and \> in inline text → < and >
    md = re.sub(r'\\<', '<', md)
    md = re.sub(r'\\>', '>', md)
    # \# in inline text → #  (pandoc escapes # in table cells and headings)
    md = re.sub(r'\\#', '#', md)
    # \* in inline text → *  (rare, but pandoc escapes lone asterisks)
    md = re.sub(r'\\\*', '*', md)
    return md


_TABLE_SEP_LINE = re.compile(r'^\|[\s\-:|]+\|[\s\-:|]*$')

def _fix_dashes(md: str) -> str:
    """
    Pandoc encodes Unicode dashes as ASCII sequences in Markdown output:
      • em-dash (U+2014) — → ---  (three hyphens, possibly with spaces)
      • en-dash (U+2013) – → --   (two hyphens)

    Restore them on a line-by-line basis, skipping:
      • YAML front-matter delimiters (lines that are exactly `---`)
      • Markdown horizontal rules (lines that are only hyphens/spaces)
      • Table separator rows  (lines like |---|---|)
    """
    result = []
    for line in md.splitlines():
        stripped = line.strip()
        # Skip table separator rows and standalone hr/delimiter lines
        if _TABLE_SEP_LINE.match(stripped):
            result.append(line)
            continue
        if re.match(r'^-{3,}$', stripped):
            result.append(line)
            continue
        # em-dash: restore   word --- word  →  word — word  (with spaces)
        # Handle cases: word---word, word ---word, word--- word, word --- word
        line = re.sub(r' ?---+ ?', ' — ', line)
        # en-dash: restore  word--word  →  word–word  (no spaces, typographic)
        # Only when flanked by word chars (avoid ---  being caught as --)
        line = re.sub(r'(?<=\w)--(?=\w)', '–', line)
        result.append(line)
    return '\n'.join(result)


# Figure image reference pattern produced by tds_render.py:
#   ![Figure N](diagrams/HPDF_TDS_<num>_<slug>_fig_NN.png)
_FIG_REF = re.compile(
    r'!\[Figure (\d+)\]\(diagrams/([^)]+\.png)\)'
)

# Pattern pandoc emits for embedded images extracted from DOCX:
#   ![alt text](media/rIdXX.png){width=… height=…}
_MEDIA_REF = re.compile(
    r'!\[([^\]]*)\]\(media/([^)]+)\)(?:\{[^}]*\})?'
)


def _build_alt_to_path_map(original_md: Path) -> dict:
    """
    Parse the original .md file and return a dict mapping each image's
    alt text to its original path.
    e.g. {'Test environment topology': 'diagrams/HPDF_TDS_0001_example-diagram.png'}
    Mermaid blocks have no image reference in the source, so they don't appear here.
    """
    if not original_md.exists():
        return {}
    content = original_md.read_text(encoding='utf-8')
    # Strip fenced code blocks (don't match image refs inside examples)
    content = re.sub(r'```[^\n]*\n.*?```', '', content, flags=re.DOTALL)
    # Match ![alt](path)
    refs = re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', content)
    return {alt: path for alt, path in refs if alt}


def _strip_pandoc_image_attrs(md: str, alt_to_path: dict | None = None) -> str:
    """
    1. Strip pandoc's {width=… height=…} attribute blocks after image references.
    2. Replace  ![alt](media/rIdXX.png)  with  ![alt](original_path)  using
       *alt_to_path* (built from the original MD).
    3. Strip the bare caption paragraph pandoc emits after each image
       (a line containing only the alt text).
    """
    # Step 1: strip inline attrs
    md = re.sub(r'(\!\[[^\]]*\]\([^)]+\))\{[^}]*\}', r'\1', md)

    # Step 2: restore original image paths using alt text
    if alt_to_path:
        def _restore_path(m):
            alt  = m.group(1)
            orig = alt_to_path.get(alt)
            if orig:
                return f'![{alt}]({orig})'
            return m.group(0)   # leave unchanged
        md = _MEDIA_REF.sub(_restore_path, md)

    # Step 3: strip auto-generated caption paragraphs
    # Pandoc emits a bare paragraph containing only the alt text after images.
    # Match:  \n\n<alt text>\n  where alt text is any non-empty, non-heading line.
    # We iterate over known alt texts (plus generic Figure N pattern).
    if alt_to_path:
        for alt in alt_to_path:
            if alt:
                escaped_alt = re.escape(alt)
                md = re.sub(rf'\n\n{escaped_alt}\n', '\n\n', md)
    # Generic Figure N captions
    md = re.sub(r'\n\nFigure \d+\n', '\n\n', md)
    md = re.sub(r'\n\n\*Figure \d+\*\n', '\n\n', md)

    return md


def _indented_to_fenced_code_blocks(md: str) -> str:
    """
    Convert Markdown indented code blocks (≥4-space prefix) to ```text fenced
    blocks.  Pandoc 2.9.x emits indented-style blocks for 'SourceCode'-styled
    DOCX paragraphs; the HPDF convention is ```text fenced blocks so the
    ascii_art_font.lua filter applies the correct font on the next render.

    Detection rule: a line starting with ≥4 spaces, preceded by a blank line
    (or document start), begins a candidate block.  The candidate is only
    converted if it contains NO list-item lines (numbered or bulleted) — those
    are indented list continuations that must be left alone.  Exactly 4 leading
    spaces are stripped from each content line.
    """
    # Matches indented list items: "    1. ", "    - ", "    * ", "    + "
    _list_item = re.compile(r'    (\d+[.)]\s|\s*[-*+]\s)')

    lines = md.split('\n')
    out   = []
    i     = 0

    while i < len(lines):
        # Candidate: ≥4-space line after a blank line (or document start)
        if lines[i].startswith('    ') and (not out or out[-1].strip() == ''):
            # Collect all lines belonging to this candidate block
            candidate = []
            j = i
            while j < len(lines):
                if lines[j].startswith('    '):
                    candidate.append(lines[j])
                    j += 1
                elif lines[j] == '' and j + 1 < len(lines) and lines[j + 1].startswith('    '):
                    candidate.append(lines[j])   # blank line within block
                    j += 1
                else:
                    break

            # Skip if any line looks like a list item — it's a list continuation
            if any(_list_item.match(l) for l in candidate if l):
                out.append(lines[i])
                i += 1
                continue

            # Genuine code block: strip 4-space indent and wrap in fences
            block = [l[4:] if l else '' for l in candidate]
            while block and block[-1] == '':
                block.pop()
            if block:
                out.append('```text')
                out.extend(block)
                out.append('```')
                i = j
                continue

        out.append(lines[i])
        i += 1

    return '\n'.join(out)


def _merge_consecutive_code_blocks(md: str) -> str:
    """
    Merge consecutive untagged fenced code blocks into one.

    When pandoc reads back a DOCX where each line of an ASCII-art block is a
    separate 'Source Code' paragraph, it may emit one ``` ... ``` block per
    line.  This pass collapses adjacent untagged blocks (separated by at most
    one blank line) back into a single block, restoring the original structure.

    Applied repeatedly until stable so runs of 3+ blocks are fully merged.
    """
    prev = None
    while prev != md:
        prev = md
        # ``` (close)  +  0-or-more blank lines  +  ``` (open, no language tag)
        md = re.sub(r'\n```\n\n*```\n', '\n', md)
    return md


def _clean_markdown(md: str, alt_to_path: dict | None = None) -> str:
    """Apply all post-pandoc cleanup passes."""
    md = _setext_to_atx(md)
    # Note: do NOT call _remove_title_block — the Title-style paragraph was
    # already stripped from the DOCX; the first heading in pandoc's output is
    # genuine body content that must be preserved.
    md = _unescape_markdown(md)
    md = _fix_dashes(md)
    md = _strip_pandoc_image_attrs(md, alt_to_path=alt_to_path)
    md = _indented_to_fenced_code_blocks(md)
    md = _merge_consecutive_code_blocks(md)
    # Remove trailing whitespace on every line
    md = '\n'.join(line.rstrip() for line in md.splitlines())
    # Collapse 3+ consecutive blank lines to 2
    md = re.sub(r'\n{4,}', '\n\n\n', md)
    # Ensure single trailing newline
    md = md.rstrip('\n') + '\n'
    return md


# ── Mermaid restoration ────────────────────────────────────────────────────────

def restore_mermaid(md: str, doc_dir: Path) -> str:
    """
    Replace each ![Figure N](diagrams/HPDF_TDS_…_fig_NN.png) reference with
    the original ```mermaid block from the matching .mmd sidecar file.

    If the .mmd file does not exist (e.g. the figure is an engineer-authored
    PNG, not a Mermaid diagram), the image reference is left unchanged.
    """
    def _replace(m):
        png_path_str = m.group(2)                   # e.g. diagrams/…_fig_01.png
        mmd_path = (doc_dir / png_path_str).with_suffix('.mmd')
        if not mmd_path.exists():
            return m.group(0)                        # leave as-is
        source = mmd_path.read_text(encoding='utf-8').strip()
        return f'```mermaid\n{source}\n```'

    return _FIG_REF.sub(_replace, md)


# ── YAML frontmatter ───────────────────────────────────────────────────────────

_FM_RE = re.compile(r'\A---\s*\n.*?\n---\s*\n', re.DOTALL)

def extract_frontmatter(original_md: Path) -> str:
    """Return the YAML frontmatter block (including --- delimiters) from
    the original .md file, or '' if not found."""
    if not original_md.exists():
        return ''
    content = original_md.read_text(encoding='utf-8')
    m = _FM_RE.match(content)
    return m.group(0) if m else ''


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Convert a reviewed HPDF TDS DOCX back to Markdown.'
    )
    parser.add_argument(
        'input',
        help='Input DOCX file (e.g. HPDF_TDS_0001_example.docx)',
    )
    parser.add_argument(
        '--output',
        default=None,
        metavar='MD',
        help='Output Markdown path (default: same name as input with .md extension)',
    )
    parser.add_argument(
        '--original',
        default=None,
        metavar='MD',
        help=(
            'Original .md file to source YAML frontmatter from. '
            'Defaults to the same directory as the DOCX with the same stem.'
        ),
    )
    parser.add_argument(
        '--no-mermaid-restore',
        action='store_true',
        default=False,
        help='Skip Mermaid block restoration (leave diagram references as PNG images).',
    )
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    doc_dir     = input_path.parent
    output_path = Path(args.output).resolve() if args.output \
        else input_path.with_suffix('.md')
    original_md = Path(args.original).resolve() if args.original \
        else input_path.with_suffix('.md')

    # Don't clobber the original if output == original
    if output_path == original_md and original_md.exists():
        backup = original_md.with_suffix('.md.bak')
        print(f"Warning: output path matches original; saving backup → {backup.name}",
              file=sys.stderr)
        import shutil as _shutil
        _shutil.copy2(original_md, backup)

    print(f"Input    : {input_path.name}")
    print(f"Output   : {output_path.name}")
    print(f"Original : {original_md.name if original_md.exists() else '(not found)'}")

    # ── Step 1: extract YAML frontmatter + alt→path image map ───────────────
    frontmatter = extract_frontmatter(original_md)
    if frontmatter:
        print("Frontmatter: found in original .md")
    else:
        print("Warning: original .md not found — output will have no YAML frontmatter",
              file=sys.stderr)

    # Build alt-text → original-path map for image reference recovery
    alt_to_path = _build_alt_to_path_map(original_md)
    if alt_to_path:
        print(f"Image map   : {len(alt_to_path)} reference(s) from original .md")

    # ── Step 1b: ensure heading styles are pandoc-compatible ─────────────────
    # Patch the input DOCX (to a temp file) so headings have lowercase
    # w:name values that pandoc's reader recognises.  This is a no-op if the
    # styles are already correct, so it is safe to run unconditionally.
    work_input = input_path
    if _HEADING_FIX_AVAILABLE:
        patched_input = Path(tempfile.mktemp(suffix='_headings.docx'))
        _patch_heading_styles(input_path, patched_input)
        work_input = patched_input

    # ── Step 2: strip cover / disclaimer / TOC ───────────────────────────────
    print("Stripping cover page, disclaimer, TOC … ", end='', flush=True)
    stripped_docx = strip_cover_and_toc(work_input)
    if work_input != input_path:
        work_input.unlink(missing_ok=True)
    print("ok")

    # ── Step 2b: reassemble ASCII-art code blocks ─────────────────────────────
    # ascii_art_font.lua renders untagged code blocks as raw Courier New
    # paragraphs (one per line, no paragraph style).  Pandoc cannot identify
    # these as code on the return trip; we restyle them as 'Source Code' here
    # so pandoc converts them back to fenced blocks.
    fixed_docx = reassemble_ascii_art_blocks(stripped_docx)
    if fixed_docx != stripped_docx:
        stripped_docx.unlink(missing_ok=True)
        stripped_docx = fixed_docx
        print("ASCII art blocks restyled for round-trip.")

    # ── Step 3: pandoc DOCX → Markdown ───────────────────────────────────────
    print("Running pandoc … ", end='', flush=True)
    raw_md = docx_to_markdown(stripped_docx)
    stripped_docx.unlink(missing_ok=True)
    print("ok")

    # ── Step 4: clean up pandoc output ───────────────────────────────────────
    md = _clean_markdown(raw_md, alt_to_path=alt_to_path)

    # ── Step 5: restore Mermaid blocks ───────────────────────────────────────
    if not args.no_mermaid_restore:
        before = md
        md = restore_mermaid(md, doc_dir)
        n_restored = len(re.findall(r'```mermaid', md)) - \
                     len(re.findall(r'```mermaid', before))
        if n_restored:
            print(f"Mermaid blocks restored: {n_restored}")
        else:
            # Count remaining media/ references (no .mmd sidecar found)
            n_refs = len(re.findall(r'!\[[^\]]*\]\(media/', md))
            if n_refs:
                print(
                    f"Note: {n_refs} figure reference(s) left as embedded media "
                    "(no matching .mmd sidecar found — review manually)",
                    file=sys.stderr,
                )

    # ── Step 6: prepend YAML frontmatter ─────────────────────────────────────
    if frontmatter:
        md = frontmatter + md.lstrip('\n')

    # ── Step 7: write output ──────────────────────────────────────────────────
    output_path.write_text(md, encoding='utf-8')
    print(f"\nDone → {output_path}")


if __name__ == '__main__':
    main()
