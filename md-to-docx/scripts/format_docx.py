#!/usr/bin/env python3
"""Post-process a pandoc-generated docx for Chinese legal document formatting.

Applies: 宋体 font (12pt), 1.5x line spacing, zero paragraph spacing.
"""
import sys
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
from docx.enum.text import WD_LINE_SPACING


def process_docx(path: str) -> None:
    doc = Document(path)

    # Process all paragraphs
    for para in doc.paragraphs:
        fmt = para.paragraph_format
        fmt.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
        fmt.space_before = Pt(0)
        fmt.space_after = Pt(0)
        for run in para.runs:
            run.font.name = '宋体'
            r = run._element
            rPr = r.get_or_add_rPr()
            rFonts = rPr.find(qn('w:rFonts'))
            if rFonts is None:
                rFonts = rPr.makeelement(qn('w:rFonts'), {})
                rPr.insert(0, rFonts)
            rFonts.set(qn('w:ascii'), '宋体')
            rFonts.set(qn('w:hAnsi'), '宋体')
            rFonts.set(qn('w:eastAsia'), '宋体')
            rFonts.set(qn('w:cs'), '宋体')

    # Process all tables
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    fmt = para.paragraph_format
                    fmt.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
                    fmt.space_before = Pt(0)
                    fmt.space_after = Pt(0)
                    for run in para.runs:
                        run.font.name = '宋体'
                        r = run._element
                        rPr = r.get_or_add_rPr()
                        rFonts = rPr.find(qn('w:rFonts'))
                        if rFonts is None:
                            rFonts = rPr.makeelement(qn('w:rFonts'), {})
                            rPr.insert(0, rFonts)
                        rFonts.set(qn('w:ascii'), '宋体')
                        rFonts.set(qn('w:hAnsi'), '宋体')
                        rFonts.set(qn('w:eastAsia'), '宋体')
                        rFonts.set(qn('w:cs'), '宋体')

    # Set default style
    style = doc.styles['Normal']
    style.font.name = '宋体'
    style.font.size = Pt(12)
    rPr = style.element.get_or_add_rPr()
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = rPr.makeelement(qn('w:rFonts'), {})
        rPr.insert(0, rFonts)
    rFonts.set(qn('w:ascii'), '宋体')
    rFonts.set(qn('w:hAnsi'), '宋体')
    rFonts.set(qn('w:eastAsia'), '宋体')
    rFonts.set(qn('w:cs'), '宋体')

    doc.save(path)
    print(f'Formatted: {path}')


if __name__ == '__main__':
    process_docx(sys.argv[1])
