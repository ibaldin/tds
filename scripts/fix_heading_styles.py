#!/usr/bin/env python3
"""
fix_heading_styles.py — Post-process a docx-js-generated DOCX so that
heading styles are recognised by pandoc 2.9+ during DOCX → Markdown
conversion.

What pandoc requires (confirmed against its source and test cases):
  • A paragraph style with w:default="1" named "Normal" must exist.
    docx-js omits this; without it pandoc's style-chain resolver can't
    anchor the heading styles and treats every heading as a plain Para.
  • A character style with w:default="1" named "Default Paragraph Font".
  • w:name w:val must be lowercase "heading 1" … "heading 6"
    (docx-js writes "Heading 1" with a capital H, which pandoc ignores)
  • w:link w:val pointing to a character style (Heading1Char … Heading6Char)
  • w:uiPriority w:val="9" (marks the style as built-in/important)

This script also adds the six matching HeadingNChar character styles if
they are absent, because Word itself expects them to be linked.

Usage:
    python3 fix_heading_styles.py input.docx output.docx
    python3 fix_heading_styles.py inout.docx          # in-place
"""

import io
import sys
import zipfile
from pathlib import Path

from lxml import etree

# ── Namespaces ────────────────────────────────────────────────────────────────

W_URI  = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
W      = f'{{{W_URI}}}'
NSMAP  = {'w': W_URI}

# ── Per-level metadata ────────────────────────────────────────────────────────

HEADING_LEVELS = [
    # (styleId,   lower_name,  char_style_id, ui_priority)
    ('Heading1', 'heading 1', 'Heading1Char', '9'),
    ('Heading2', 'heading 2', 'Heading2Char', '9'),
    ('Heading3', 'heading 3', 'Heading3Char', '9'),
    ('Heading4', 'heading 4', 'Heading4Char', '9'),
    ('Heading5', 'heading 5', 'Heading5Char', '9'),
    ('Heading6', 'heading 6', 'Heading6Char', '9'),
]

# Display names for the linked character styles (used in w:name)
CHAR_STYLE_DISPLAY = {
    'Heading1Char': 'Heading 1 Char',
    'Heading2Char': 'Heading 2 Char',
    'Heading3Char': 'Heading 3 Char',
    'Heading4Char': 'Heading 4 Char',
    'Heading5Char': 'Heading 5 Char',
    'Heading6Char': 'Heading 6 Char',
}


# ── XML helpers ───────────────────────────────────────────────────────────────

def _w(tag):
    return f'{W}{tag}'


def _get_or_insert(parent, tag, insert_after_tags=None, position=None):
    """
    Return an existing child element with *tag*, or create and insert one.
    If *insert_after_tags* is given, the new element is inserted immediately
    after the last child whose tag is in that set.  Otherwise it is appended.
    """
    existing = parent.find(tag)
    if existing is not None:
        return existing, False   # (element, was_created)
    elem = etree.Element(tag)
    if insert_after_tags:
        idx = -1
        for i, child in enumerate(parent):
            if child.tag in insert_after_tags:
                idx = i
        if idx >= 0:
            parent.insert(idx + 1, elem)
            return elem, True
    if position is not None:
        parent.insert(position, elem)
    else:
        parent.append(elem)
    return elem, True


# ── Base-style injection ──────────────────────────────────────────────────────

def _ensure_base_styles(root, existing_ids: set) -> None:
    """
    docx-js omits the two default root styles that pandoc's DOCX reader
    requires to anchor the style-inheritance chain:

      • Normal           — default paragraph style (w:type="paragraph" w:default="1")
      • DefaultParagraphFont — default character style (w:type="character" w:default="1")

    Without Normal, pandoc cannot resolve the heading styles' basedOn chain
    and emits every heading paragraph as a plain Para instead of a Header.
    """

    if 'Normal' not in existing_ids:
        existing_ids.add('Normal')
        normal = etree.Element(_w('style'))
        normal.set(_w('type'),    'paragraph')
        normal.set(_w('default'), '1')
        normal.set(_w('styleId'), 'Normal')
        name_e = etree.SubElement(normal, _w('name'))
        name_e.set(_w('val'), 'Normal')
        etree.SubElement(normal, _w('qFormat'))
        root.insert(0, normal)

    if 'DefaultParagraphFont' not in existing_ids:
        existing_ids.add('DefaultParagraphFont')
        dpf = etree.Element(_w('style'))
        dpf.set(_w('type'),    'character')
        dpf.set(_w('default'), '1')
        dpf.set(_w('styleId'), 'DefaultParagraphFont')
        name_e = etree.SubElement(dpf, _w('name'))
        name_e.set(_w('val'), 'Default Paragraph Font')
        ui_e = etree.SubElement(dpf, _w('uiPriority'))
        ui_e.set(_w('val'), '1')
        etree.SubElement(dpf, _w('semiHidden'))
        etree.SubElement(dpf, _w('unhideWhenUsed'))
        # Insert right after Normal (position 1) or at position 0
        normal_idx = next(
            (i for i, c in enumerate(root) if c.get(_w('styleId')) == 'Normal'),
            -1,
        )
        root.insert(normal_idx + 1, dpf)


# ── Core fixer ────────────────────────────────────────────────────────────────

def fix_styles_xml(xml_bytes: bytes) -> bytes:
    """
    Parse word/styles.xml and apply all heading-compatibility fixes.
    Returns the patched XML bytes.
    """
    root = etree.fromstring(xml_bytes)

    # Index existing styles for fast lookup
    existing_ids = {
        s.get(_w('styleId'))
        for s in root.findall(_w('style'))
    }

    # Step 0: ensure Normal and DefaultParagraphFont exist
    _ensure_base_styles(root, existing_ids)

    for style_id, lower_name, char_id, priority in HEADING_LEVELS:

        # ── Fix the paragraph heading style ──────────────────────────────────
        para_style = root.find(
            f'{_w("style")}[@{_w("styleId")}="{style_id}"]'
        )
        if para_style is None:
            print(f'  Warning: style {style_id} not found — skipping',
                  file=sys.stderr)
            continue

        # 1. Lowercase the name
        name_elem = para_style.find(_w('name'))
        if name_elem is not None:
            name_elem.set(_w('val'), lower_name)

        # 2. Add w:link → character style
        after_tags = {_w('name'), _w('basedOn'), _w('next')}
        link_elem, _ = _get_or_insert(
            para_style, _w('link'), insert_after_tags=after_tags)
        link_elem.set(_w('val'), char_id)

        # 3. Add w:uiPriority
        after_tags2 = after_tags | {_w('link')}
        ui_elem, _ = _get_or_insert(
            para_style, _w('uiPriority'), insert_after_tags=after_tags2)
        ui_elem.set(_w('val'), priority)

        # ── Ensure the matching character style exists ────────────────────────
        if char_id not in existing_ids:
            existing_ids.add(char_id)
            char_style = etree.SubElement(root, _w('style'))
            char_style.set(_w('type'),    'character')
            char_style.set(_w('styleId'), char_id)

            name_c = etree.SubElement(char_style, _w('name'))
            name_c.set(_w('val'), CHAR_STYLE_DISPLAY[char_id])

            based_c = etree.SubElement(char_style, _w('basedOn'))
            based_c.set(_w('val'), 'DefaultParagraphFont')

            link_c = etree.SubElement(char_style, _w('link'))
            link_c.set(_w('val'), style_id)

            ui_c = etree.SubElement(char_style, _w('uiPriority'))
            ui_c.set(_w('val'), priority)

    return etree.tostring(root, xml_declaration=True, encoding='UTF-8',
                          standalone=True)


# ── DOCX patcher ─────────────────────────────────────────────────────────────

def patch_docx(input_path: Path, output_path: Path) -> None:
    """
    Copy *input_path* to *output_path*, replacing word/styles.xml with the
    patched version.
    """
    # Read all entries
    with zipfile.ZipFile(input_path, 'r') as zin:
        entries = {name: zin.read(name) for name in zin.namelist()}

    if 'word/styles.xml' not in entries:
        raise FileNotFoundError("word/styles.xml not found in DOCX")

    original_xml = entries['word/styles.xml']
    patched_xml  = fix_styles_xml(original_xml)
    entries['word/styles.xml'] = patched_xml

    # Write output preserving compression
    with zipfile.ZipFile(output_path, 'w',
                         compression=zipfile.ZIP_DEFLATED) as zout:
        for name, data in entries.items():
            zout.writestr(name, data)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if not args or len(args) > 2:
        print(
            f'Usage: {sys.argv[0]} input.docx [output.docx]\n'
            '  If output.docx is omitted the file is patched in place.',
            file=sys.stderr,
        )
        sys.exit(1)

    input_path  = Path(args[0]).resolve()
    output_path = Path(args[1]).resolve() if len(args) == 2 else input_path

    if not input_path.exists():
        print(f'Error: {input_path} not found', file=sys.stderr)
        sys.exit(1)

    in_place = (output_path == input_path)
    work_path = input_path.with_suffix('.tmp.docx') if in_place else output_path

    print(f'Patching {input_path.name} …')
    patch_docx(input_path, work_path)
    print('  Normal + DefaultParagraphFont base styles ensured')
    print('  Heading style names lowercased (heading 1 … heading 6)')
    print('  w:link and w:uiPriority added to Heading1–Heading6')
    print('  Heading1Char–Heading6Char character styles ensured')

    if in_place:
        work_path.replace(input_path)

    print(f'Written: {output_path}')


if __name__ == '__main__':
    main()
