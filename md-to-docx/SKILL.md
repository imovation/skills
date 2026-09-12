---
name: md-to-docx
description: >
  Convert Markdown documents to properly formatted .docx files with Chinese legal document styling.
  Use this skill whenever the user asks to convert a .md file to Word (.docx) format, export to Word,
  generate a .docx from markdown, or mentions needing a Word version of a document.
  Also use when the user reports issues with Word document formatting such as wrong fonts,
  incorrect line spacing, or misdirected Chinese quotation marks in .docx files.
---

# Markdown to Docx Converter

Convert Markdown to .docx with proper Chinese legal document formatting.

## Workflow

### Step 1: Fix Chinese quotation marks in Markdown

Pandoc's smart quote conversion gets Chinese quotation mark direction wrong (opening quotes become closing quotes). Fix this in the source Markdown before conversion. Replace all straight double quotes (`"`) with proper Chinese curly quotes:

- Opening: `\u201c` (`"`)
- Closing: `\u201d` (`"`)

Use a simple alternating approach — every odd `"` becomes opening, every even `"` becomes closing. This reliably produces correct paired quotes for Chinese legal documents where quotes don't span paragraphs.

### Step 2: Convert to docx with Pandoc

Use `--from=markdown-smart` to prevent Pandoc from re-processing the already-correct quotes:

```bash
pandoc input.md -o output.docx --from=markdown-smart
```

### Step 3: Apply formatting with the bundled script

Run `scripts/format_docx.py` on the generated .docx to apply:
- Font: 宋体, 12pt (all text including Western characters and digits)
- Line spacing: 1.5x
- Paragraph spacing: 0 before, 0 after

```bash
python3 scripts/format_docx.py output.docx
```

The script requires `python-docx`. Install if needed: `pip install python-docx`.

## Dependencies

- `pandoc` (system package)
- `python-docx` (Python package)
