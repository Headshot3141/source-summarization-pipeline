# Source configs

One Python file per source, so sources can be configured in parallel (one extraction agent per source) without editing a shared file.

- **Name:** `<slug with underscores>.py`, for example `penhale_grey_harbour.py` for the slug `penhale-grey-harbour`. A test checks every file's name against its slug.
- **Contents:** a dict `CONFIG` in the format of a `SOURCES_CONFIG` entry in `Work/extract.py`. The commented examples there (PDF, EPUB, paged TXT, docling Markdown) list every key; copy the one for your source type. Start the file with a docstring that records what the source is, which text layer it is extracted from and why, and each repair decision with its evidence (page or line), so the next reader need not reconstruct them. `_example_md.py` is a worked example.
- **Files whose name starts with `_` are ignored** by `extract.py` (examples, notes).

## Never read a file at import

A config file is imported every time `extract.py` runs, for every source, and on a checkout without `Sources/` (which git ignores). So a config never opens a file when it is imported. Anything built from the source file goes in a zero-argument callable, which `extract.py` calls only for the sources it extracts, just before it validates the config (`resolve_config`). `line_fixes` and `line_edits` may be such a callable:

```python
from source_helpers import build_line_edits

MD = "penhale-grey-harbour.md"

CONFIG = {
    ...
    "line_edits": lambda: build_line_edits(MD, quotes=[212, 214], drops={301: "Translator's note"}),
}
```

A paged TXT source's `build_txt` is a callable too: it takes the path of the paged text (a path starting `Work/`, from the project root) and writes it from the PDF. It runs when the file is missing, and on every run with `--rebuild-txt`.

## Repairs live in the config, never in a chapter file

`extract.py` rewrites every chapter file on each run, so a hand edit to `Work/Chapters/` is lost at the next extraction. Every repair, removal, block-quotation mark, and figure or table transcription goes in the config:

- `line_fixes` `{whole line text: replacement}` (TXT and Markdown): for a line that is damaged the same way wherever it occurs. A key that matches no line is logged as `line-fix-unused` and printed as a warning.
- `line_edits` `{line number: text}` (Markdown): for a repair at one place. Build it with `source_helpers.build_line_edits(md_name, rebuilt=, replace=, edits=, swaps=, joins=, moves=, drops=, quotes=)`, which checks each edit against the line it changes (its docstring lists the operations and checks). Lines rebuilt from the PDF come in through `rebuilt=rebuilt_lines(slug)` (below). A proofreading pass against the page images (`passes/proofread.md`) comes in through `replace=proof_fixes(slug, md_name)`, which stops the run if the proofread lines have changed since.
- `char_map` `{from: to}`: encoding faults only, never the author's text. For example a font's private-use old-style figures, `{chr(0xF730 + i): str(i) for i in range(10)}`.
- Figures and tables: a transcription goes in at its place in the text (`line_edits` or `line_fixes`), opening "[Visual transcription of Figure N (p. X): ...]". A table can be written as Markdown pipe rows.

## Text from the PDF's text layer

Two tools read the PDF with PyMuPDF character by character (font, size, position) for what a docling export or a plain text dump loses. Both take the same reading settings: `header_ymax` and `footer_ymin` (running heads and footers, in PDF points), `italic_font` (a regex on the font name; by default the font flags mark italics), `superscript_max` (the type size of note references; by default a smaller, raised character is one), and `artifact_gap` (a space glyph closer than this to its neighbours is not a word space; default 0.3 pt). To choose them, `python Work/pdf_to_paged_txt.py --pdf <file> --layout 12-14` prints each line's position, type size, share of italics, and text. Lines are read top to bottom, so a two-column page needs its own handling.

**Rebuilt lines for a docling Markdown source** (`Work/rebuild_from_pdf.py`). When the export flattened quotation marks, dashes, or italics, ran words together, or mishandled line-end hyphens, but its words and structure are sound, rebuild the damaged lines rather than repairing them one by one:

```text
python Work/rebuild_from_pdf.py --md penhale-grey-harbour.md --pdf penhale-grey-harbour.pdf --lines 95-293,435-603 --header-ymax 52 --out Work/Proof/penhale-grey-harbour.rebuilt.json --report
```

Each line is found in the PDF by its letters and digits, searching on from the last line found. Its letters and digits stay exactly as docling has them; everything between them comes from the PDF. Italics are marked `*...*`, docling's spacing is kept next to a superscript note number ("Penhale. 1 The"), and each PDF line-end hyphen is kept or dropped by the book's own mid-line usage, then the dictionary, then a known prefix, then the rule that a break between two known words keeps its hyphen. Only changed lines are written. The config applies them before its other edits:

```python
from source_helpers import build_line_edits, rebuilt_lines

"line_edits": lambda: build_line_edits(MD, rebuilt=rebuilt_lines(SLUG), joins=[(288, 290)], quotes=[212, 214]),
```

`build_line_edits` stops the run if a rebuilt line changes a letter or digit of the line it replaces (a re-exported file), and `rebuilt_lines` stops it if the JSON is missing. `--report` lists the lines not found (left as exported); the lines matched in pieces (a paragraph a footnote interrupts), out of order, or without their note numbers, to check against the page; the uncertain hyphen decisions; and how many quotation marks, dashes, and italics differ between the export and the PDF, which is also the evidence for "Extract from" in Preflight. Table rows, code fences, and placeholders are not rebuilt. `--no-italics` follows a typography policy without italics; `--hyphenates yes|no` overrides the detection of whether the book breaks words at line ends. Rerun the script after a re-export.

**A paged text for TXT mode** (`Work/pdf_to_paged_txt.py`). When the text layer is the better text but units start and end mid-page, write a paged text from it with `build_txt` and extract in TXT mode:

```python
from pdf_to_paged_txt import FURNITURE_PATTERNS, paged_txt_builder

CONFIG = {
    ...
    "txt": "Work/Raw/penhale-grey-harbour/paged.txt",
    "build_txt": paged_txt_builder("penhale-grey-harbour.pdf", header_ymax=52, footer_ymin=600),
    "paragraphs": "blank_lines",
    "header_patterns": FURNITURE_PATTERNS,
    "footer_patterns": FURNITURE_PATTERNS,
}
```

The file has one form feed per PDF page. A blank line starts each block: a line set further right than the one before (a first-line indent, an indented quotation), one set further left than the rest of its block (the end of an indented quotation), a change of type size, or a vertical gap wider than `gap_factor` (default 1.2) line spacings. Lines beside a drop cap continue its paragraph. Running heads, footers, sideways text, and bare folios are prefixed `@@furniture `, so the patterns drop each one and log it as `furniture-dropped`; raise `header_scan` if a page has more than 8 of them at one end. Italics are marked `*...*` (`italics=False` for none), artifact spaces are dropped, and a line ending in a closed dash ("quay—") takes the next line's first word. Line-end hyphens are left for TXT mode to decide. Other settings: `indent` (points that start a block; default half the type size), `hanging_pages` (pages set with a hanging indent, such as endnotes, where a block starts at a line further left), and `move_run_on`. The build prints a summary that lists the pages whose first line runs a paragraph on after a page ending a sentence. TXT mode starts a new paragraph there unless `move_run_on=True` moves that last line to the next page (a footnote ending the page is never moved). Footnotes at a page foot stay there as paragraphs.

## Keys

A short index; the commented examples in `Work/extract.py` give the details and defaults.

`register` (set in Preflight) goes into each chapter file's frontmatter and reaches the agents as REGISTER: `"modern"` for English from before 1950 (or a later translation that reads as antiquated), summarized in plain modern English; `"source"` for English from 1950 on. A chapter's own `register` overrides the source's (an edited collection mixing old and new texts). Without it, extraction uses `"source"` and warns.

| Source type | Source keys | Chapter keys |
|---|---|---|
| All | `slug`, `title`, `part`, `register`, `chapters`, and one of `pdf`, `epub`, `txt`, `md` | `unit_id`, `slug`, `title`, `num`, `printed_pages`, optional `file_no` (pins the file's NN prefix), optional `register` |
| PDF | `header_ymax`, `footer_ymin`, `hyphenates`, `space_repair`, `char_map` | `start`, `end` (PDF pages), `first_line`, `stop_line` (cut the first and last pages), `title_alt` |
| EPUB | `epub_page_anchor`, `epub_heading_classes`, `epub_skip_classes`, `char_map` | `file`, or `files` for a chapter in several archive files |
| Paged TXT | `build_txt`, `paragraphs` (`"blank_lines"`), `line_width`, `header_patterns`, `footer_patterns`, `header_scan`, `junk_lines`, `char_map`, `line_fixes`, `hyphenates`, `dehyphenated`, `hyphen_fixes`, `kerning_spaces`, `not_headings`, `notes` (`start`, `end`, `heading`, `para_start`), `block_quotes`, `block_quote_fixes` | `start`, `end`, `first_line`, `stop_line`, `notes` (the key its endnotes are filed under) |
| Docling Markdown | `page_break`, `first_page`, `skip_pages`, `last_page`, `header_patterns`, `junk_lines`, `footnote_pattern`, `footnotes_at_page_end`, `not_headings`, `strip_emphasis`, `hyphen_spaces`, `hyphenates`, `char_map`, `line_edits`, `line_fixes`, `block_quotes`, `block_quote_fixes` | `title`, `title_alt`, `heading`, `occurrence`, `first_line`, `stop_line` |

## Running

- `python Work/extract.py` extracts every source; `python Work/extract.py <slug> [<slug> ...]` only the named ones. A slug that names no source is an error.
- `python Work/extract.py --check [<slug> ...]` re-extracts into temporary folders and compares the chapter files byte for byte with `Work/Chapters/` (exit 1 on any difference). Run it after a config change meant to touch one chapter, and after any change to `extract.py`.
- `python Work/check_chapters.py [<slug> ...]` scans the chapter files for forbidden characters (exit 1) and suspicious spacing, and prints each chapter's first and last paragraph for a boundary read.
- A file that fails to import (the message names the line), has no `CONFIG` dict or slug, or reuses another source's slug stops the run with a message naming the file. So does an error inside a callable, naming the source and the key.
