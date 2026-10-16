"""Worked example of a source config (invented source; extract.py skips files starting with "_").

Ada Penhale, The Grey Harbour (1937; reissued 1982; 212
PDF pages, printed page = PDF page - 8). Selected: chapters 1-3 and the
Afterword. The editor's Foreword (pp. ix-xiv) is not Penhale's text and is
left out (outside-chapters).

Extracted from the docling Markdown (Sources/penhale-grey-harbour.md),
checked against the PDF beside it; see the Preflight report,
Work/Preflight/penhale-grey-harbour.report.md. The export has page-break
placeholders, so chapters carry page markers. Repairs, each checked against
the page image:

- the running head "THE GREY HARBOUR" leaks into the text on 40 pages
  (header_patterns);
- footnotes are paragraphs starting with the note number and a space, at
  the foot of their page (footnote_pattern);
- MD 212 and 214 are a block quotation from a harbour-board report set in
  smaller type and indented (p. 31), which the export did not mark;
- MD 301 is a translator's note inside chapter 2 (not Penhale's text);
- MD 288/290 is one paragraph the export split at the page break (pp.
  40-41; the continuation is not indented);
- MD 455 "Tbe tide" is an OCR misreading of "The tide" (p. 63);
- chapter 3's opening pages were proofread against the images
  (passes/proofread.md; Work/Proof/penhale-grey-harbour.*.json).

Kept as printed: "harbor" and "harbour" both occur (pp. 12, 57).
"""
from source_helpers import build_line_edits, proof_fixes

SLUG = "penhale-grey-harbour"
MD = "penhale-grey-harbour.md"


def _line_edits():
    """Line-numbered repairs, checked against the lines they change (see the docstring)."""
    return build_line_edits(
        MD,
        replace=proof_fixes(SLUG, MD),
        edits={455: [("Tbe tide", "The tide")]},
        joins=[(288, 290)],
        drops={301: "Translator's note"},
        quotes=[212, 214],
    )


CONFIG = {
    "slug": SLUG,
    "md": MD,
    "title": "The Grey Harbour",
    "part": 1,
    # Penhale's English is from 1937 (the 1982 reissue reprints it unrevised),
    # so the summary is written in plain modern English (plan.md, Preflight).
    "register": "modern",
    "page_break": "<!-- page break -->",
    "first_page": 1,
    "header_patterns": [r"^THE GREY HARBOUR$"],
    "footnote_pattern": r"^\d{1,2} [A-Z“]",
    "hyphen_spaces": True,
    # A callable: the Markdown file is read only when this source is extracted.
    "line_edits": _line_edits,
    "block_quotes": True,
    "block_quote_fixes": {"join": [], "start": [], "end": [], "add": [], "remove": []},
    "chapters": [
        {"unit_id": "ch-01", "slug": "the-quay", "title": "The Quay", "num": 1, "printed_pages": "1-24"},
        {"unit_id": "ch-02", "slug": "the-tide-tables", "title": "The Tide Tables", "num": 2,
         "printed_pages": "25-48"},
        {"unit_id": "ch-03", "slug": "winter-moorings", "title": "Winter Moorings", "num": 3,
         "printed_pages": "49-77", "stop_line": "## Part Two"},
        {"unit_id": "afterword", "slug": "afterword", "title": "Afterword", "num": None,
         "printed_pages": "201-204", "stop_line": "## Index"},
    ],
}
