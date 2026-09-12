#!/usr/bin/env python3
"""Convert a .docx file to Markdown, preserving Chinese document structure."""

import sys
import re
from pathlib import Path
from docx import Document


HEADING_PATTERNS = [
    (re.compile(r'^第[一二三四五六七八九十百千]+[章节篇条]'), 1),
    (re.compile(r'^[一二三四五六七八九十]+[、，]'), 1),
    (re.compile(r'^（[一二三四五六七八九十]+）'), 2),
    (re.compile(r'^\([一二三四五六七八九十]+\)'), 2),
    (re.compile(r'^\d+[\.、]'), 2),
    (re.compile(r'^[（\(]\d+[）\)]'), 3),
]

LIST_PATTERN = re.compile(r'^\d+[\.\)、]\s')


def detect_heading_level(text: str) -> int:
    """Detect heading level from Chinese numbering patterns."""
    if not text:
        return 0
    for pattern, level in HEADING_PATTERNS:
        if pattern.match(text.strip()):
            return level
    return 0


def build_paragraphs(doc):
    """Yield paragraph-like objects from body text and tables."""
    for para in doc.paragraphs:
        yield para

    for table in doc.tables:
        if not table.rows:
            continue
        header_cells = [cell.text.strip() for cell in table.rows[0].cells]
        yield _make_virtual('| ' + ' | '.join(header_cells) + ' |')
        yield _make_virtual('|' + '|'.join(' --- ' for _ in header_cells) + '|')
        for row in table.rows[1:]:
            cells = [cell.text.strip().replace('\n', ' ') for cell in row.cells]
            yield _make_virtual('| ' + ' | '.join(cells) + ' |')
        yield _make_virtual('')


def _make_virtual(text: str):
    """Create a paragraph-like object with minimal attributes."""
    return type('VPara', (), {
        'text': text,
        'style': type('Style', (), {'name': 'Normal'})(),
        'runs': [],
    })()


def para_to_markdown(para) -> str:
    """Convert a single paragraph to a Markdown line."""
    text = para.text.strip()
    if not text:
        return ''

    style_name = para.style.name if para.style else ''

    if style_name.startswith('Heading'):
        try:
            level = int(style_name.replace('Heading', '').strip())
        except ValueError:
            level = 1
        return f"{'#' * level} {text}"

    h_level = detect_heading_level(text)
    if h_level > 0:
        return f"{'#' * h_level} {text}"

    is_all_bold = para.runs and all(
        run.bold for run in para.runs if run.text.strip()
    )
    if is_all_bold and len(text) < 80 and not text.startswith(('-', '*', '|')):
        return f"**{text}**"

    if text.startswith(('* ', '- ', '+ ')):
        return text

    if LIST_PATTERN.match(text):
        return text

    if text.startswith('>'):
        return text

    return text


def convert_docx_to_md(input_path: str, output_path: str | None = None) -> str:
    """Convert a .docx file to Markdown. Returns the markdown string."""
    doc = Document(input_path)
    lines = [para_to_markdown(p) for p in build_paragraphs(doc)]
    markdown = '\n\n'.join(filter(None, lines))
    # Collapse excessive blank lines
    markdown = re.sub(r'\n{4,}', '\n\n\n', markdown)

    if output_path:
        Path(output_path).write_text(markdown, encoding='utf-8')
        print(f"Converted: {input_path} → {output_path}")
        return output_path
    return markdown


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 docx_to_md.py <input.docx> [output.md]")
        sys.exit(1)
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else Path(input_file).with_suffix('.md')
    convert_docx_to_md(input_file, str(output_file))
