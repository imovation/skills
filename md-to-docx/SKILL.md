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
- First-line indent: 2 chars (24pt) on body paragraphs (excludes address line, signature block, list items, image paragraphs)

```bash
python3 scripts/format_docx.py output.docx
```

The script requires `python-docx`. Install if needed: `pip install python-docx`.

### Step 4 (optional): Append an attachment section (附件册/证据册)

When the document needs scanned attachments appended (身份证、认定书、病历、票据、发票、凭证等), convert each PDF to images first, then run `scripts/build_attachments.py`:

```bash
# 1) PDF pages -> JPEG (150 dpi is fine for print)
pdftoppm -jpeg -r 150 -f 1 -l 9 住院病历.pdf bingli
pdftoppm -jpeg -r 150 认定书.pdf rending

# 2) Build manifest.json listing attachments (title prefix "附件N：" optional)
# {
#   "title": "附 件",
#   "attachments": [
#     {"title": "附件1：申请人身份证复印件", "files": ["idcard-1.jpg"]},
#     {"title": "附件4：住院病历关键页", "files": ["bingli-01.jpg", ...]}
#   ]
# }

# 3) Append attachment section — MUST run AFTER format_docx.py
python3 scripts/build_attachments.py output.docx manifest.json --align-signature
```

The script forces A4 (21×29.7 cm, margins 2.54/3.18 cm), scales images to max 5.7×9.2 in, sets image paragraphs to single spacing, adds a centered page footer "第 X 页", and optionally right-aligns the signature block. Known pitfalls and the PDF render check procedure: see `reference/troubleshooting.md` and `reference/rendering-check.md`.

## Dependencies

- `pandoc` (system package)
- `python-docx` (Python package)
- `Pillow` (Python package, for image dimension scaling)
- `poppler-utils` (pdftoppm/pdfinfo/pdftotext/pdfimages, for PDF->image and render checks)
- `libreoffice` (headless, for render verification)
