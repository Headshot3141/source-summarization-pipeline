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
- `line_edits` `{line number: text}` (Markdown): for a repair at one place. Build it with `source_helpers.build_line_edits(md_name, rebuilt=, replace=, edits=, swaps=, joins=, moves=, drops=, quotes=)`, which checks each edit against the line it changes (its docstring lists the operations and checks). A proofreading pass against the page images (`passes/proofread.md`) comes in through `replace=proof_fixes(slug, md_name)`, which stops the run if the proofread lines have changed since.
- `char_map` `{from: to}`: encoding faults only, never the author's text. For example a font's private-use old-style figures, `{chr(0xF730 + i): str(i) for i in range(10)}`.
- Figures and tables: a transcription goes in at its place in the text (`line_edits` or `line_fixes`), opening "[Visual transcription of Figure N (p. X): ...]". A table can be written as Markdown pipe rows.

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
