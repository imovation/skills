---
name: docx-to-md
description: >
  Convert .docx (Word) documents to Markdown format. Use this skill whenever the user asks to
  convert a Word document to Markdown, extract text from .docx, read a Word file's contents,
  or turn a docx into readable plain text. Also use when the user mentions needing to edit,
  search, or analyze the content of a .docx file — since .docx is binary, conversion to
  Markdown is the necessary first step. This skill is especially suited for Chinese legal
  and formal documents with numbered headings (一、二、三...) and structured formatting.
---

# Docx to Markdown Converter

Convert `.docx` files to `.md` using `python-docx`. The script extracts text, tables, and
detects heading hierarchy from both Word styles and Chinese numbering patterns.

## Workflow

### Step 1: Run the conversion script

```bash
python3 scripts/docx_to_md.py input.docx output.md
```

If `output.md` is omitted, the output file name defaults to the same as the input with `.md` extension.

### Step 2: Review and polish the output

The script does a **structural first pass** — it extracts text, identifies headings, and
converts tables into Markdown table syntax. However, it is **not a full semantic converter**.

After running, review the output for:

1. **Heading levels** — Paragraphs with Word `Heading` styles are converted as-is.
   Chinese numbering patterns (`一、` → `#`, `（一）` → `##`, `1.` → `##`) are auto-detected
   and may conflict with Word styles. Adjust `#` depth as needed for the document's hierarchy.

2. **Inline formatting** — Bold, italic, underline, and other inline styles are
   **not preserved**. The script extracts plain text from each paragraph. If the document
   contains important bold/italic emphasis, restore it manually in the Markdown output.

3. **Block quotes** — The script does not convert indented passages to `>` block quotes.
   Identify and mark up quoted sections (e.g., quoted legal provisions, quoted statements)
   manually.

4. **Lists** — If the original Word document uses automatic list numbering, the rendered
   text may appear as flat paragraphs (numbers as literal text) rather than Markdown lists.
   Review and add `-` or `1.` list markers where appropriate.

5. **Tables** — Tables are converted to Markdown table syntax. Verify column alignment
   and cell content integrity.

### Step 3: Clean up artifacts

The script collapses 4+ consecutive blank lines to 3. If the output still has excessive
whitespace, run:

```bash
python3 -c "
import re
text = open('output.md').read()
text = re.sub(r'\n{3,}', '\n\n', text)
open('output.md', 'w').write(text)
"
```

## Dependencies

- `python-docx` (Python package) — install with `pip install python-docx`

The script path is relative to the skill directory. Use the full path:

```bash
python3 ~/.config/opencode/skills/docx-to-md/scripts/docx_to_md.py ...
```

## Limitations

This is an extraction-first tool. It does not reproduce the exact visual formatting of the
Word document. Key differences from a visual-perfect conversion:

- Fonts, colors, sizes are ignored (only semantic structure is captured)
- Images are not extracted
- Headers, footers, and footnotes are not included
- Track changes / comments are ignored
- Inline formatting (bold, italic) is lost

For documents that require **perfect visual fidelity**, use pandoc instead
(`pandoc input.docx -o output.md`). Use this skill when `pandoc` is unavailable or when
structural extraction with Chinese heading patterns is the priority.
