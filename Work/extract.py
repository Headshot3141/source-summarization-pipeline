import html
import os
import re
import sys
import zipfile
from collections import Counter
from html.parser import HTMLParser

import pymupdf
from spellchecker import SpellChecker

from common import PAGE_MARKER, ends_sentence, is_heading, strip_comments, yaml_value
from count_words import words_in_text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = os.path.join(ROOT, "Sources")
OUT = os.path.join(ROOT, "Work", "Chapters")
RAW = os.path.join(ROOT, "Work", "Raw")

sp = SpellChecker()

# Recurring page furniture that position alone cannot catch. Add one
# pattern per verified stamp. Example: page numbers printed as "-3-" or
# "-xii-" that can sit mid-page:
#     re.compile(r"^-\s*(?:\d{1,4}|[ivxlcdm]{1,7})\s*-$", re.I),
STAMP_PATTERNS = []
# Whole lines (normalized: lowercased, whitespace collapsed) that are
# watermarks or download stamps, such as a site name printed on every page.
JUNK_LINES = set()
DATE = re.compile(r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}$")
BARE_NUM = re.compile(r"^\d{1,4}$")
# A block of only punctuation carries no content (stray periods at chapter ends).
LONE_PUNCT = re.compile(r"^[.,;:!?\u2026'\"*\u00b7\u2022\u2013\u2014-]{1,3}$")
OVERLAP_THRESHOLD = 1.6
# Bare numbers and date stamps are page furniture only when they are the first
# or last block on the page and sit within this fraction of the page height
# from the top or bottom edge. Elsewhere they are content (table cells, years).
PAGE_NUM_ZONE = 0.12
# A chapter heading is looked for only in the first few blocks of its first page.
MAX_HEADING_BLOCKS = 4
WORD = re.compile(r"[A-Za-z][A-Za-z\u2019'-]*[A-Za-z]")
# Presentation-form ligatures (ff, fi, fl, ffi, ffl, st) are normalized to
# their letter sequences. The mapping is unambiguous, so no log is needed.
LIGATURES = {
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi",
    "\ufb04": "ffl", "\ufb05": "st", "\ufb06": "st",
}
LIGATURE_TABLE = str.maketrans(LIGATURES)
# A line-end hyphen after a known prefix is kept as a compound hyphen.
PREFIXES = {
    "anti", "auto", "bi", "bio", "co", "counter", "cross", "crypto", "de",
    "dis", "ex", "extra", "geo", "hyper", "il", "im", "in", "inter", "ir",
    "macro", "meta", "micro", "mid", "mis", "mono", "multi", "neo", "non",
    "over", "pan", "para", "post", "pre", "pro", "proto", "pseudo", "quasi",
    "re", "semi", "socio", "sub", "super", "techno", "trans", "ultra", "un",
    "under", "uni", "vice",
}
# A document "hyphenates" (breaks words at line ends) when at least this many
# line-end hyphens, and this share of those the document itself settles, are
# line-break hyphens. Otherwise every line-end hyphen is kept as real text.
# Set "hyphenates": True or False in a source's config to override detection.
HYPHENATION_MIN_BREAKS = 3
HYPHENATION_MIN_SHARE = 0.5
# A block starting with a list or note marker never continues the previous page.
LIST_MARKER = re.compile(r"^(\(?(\d{1,3}|[A-Za-z]|[ivxlcdm]{1,5})[.)]|[\u2022\u25aa\u25e6\u25cf\u25a0*]|\d{1,3}(?= +[A-Z\u201c\u2018\"']))\s")

# Block quotations are marked with a Markdown "> " prefix on each paragraph,
# so agents can tell quoted text from the author's own prose. A block
# quotation's citation follows its closing punctuation ("worthwhile. (Marlow
# 1986, 82)"); an in-text quotation's comes before the period.
BLOCK_QUOTE_PREFIX = "> "
BLOCK_CITATION = re.compile(r"[.?!…”’\]]\s*\([^()]*\d[^()]*\)$")
# An epigraph ends with its attribution after a dash: "... and the river
# kept its own counsel. —Ada Penhale 1937, 16".
EPIGRAPH = re.compile(r"[.?!…”’]\s+—\s?[A-Z][^—?!]{1,80}$")
# Verse ends with its citation standing alone: "(Penhale 1982, 133)".
CITATION_ONLY = re.compile(r"^\([^()]*\d[^()]*\)$")
# How many paragraphs after a lead-in are searched for the citation that
# ends a quotation (verse is often one paragraph per line).
BLOCK_QUOTE_WINDOW = 8

SOURCES_CONFIG = [
    {
        # PDF source.
        "slug": "",
        "pdf": "",
        "title": "",
        "part": 1,
        # Text above header_ymax or below footer_ymin (PDF points) is dropped.
        # 0 and 10000 turn the cutoffs off.
        "header_ymax": 0,
        "footer_ymin": 10000,
        # Optional "hyphenates": True/False overrides line-end hyphenation
        # detection. Set it when the detector disagrees with the page images.
        # Optional "space_repair": {font name: em factor}. Use when a text
        # layer drops the space glyph in some fonts, leaving only a gap; a
        # space is inserted where the gap exceeds factor * font size. Calibrate
        # the factor against known word gaps (0.08 worked on one serif face).
        "chapters": [
            # unit_id: stable and unique within this source (ch-01, appendix-a, ...).
            # slug: used in the filename. num: printed chapter label, or None if none.
            # start/end: one-based inclusive PDF pages.
            # Optional title_alt: extra heading spellings to strip, such as a
            # heading with an OCR error ("The Quiet Harhour").
            {"unit_id": "", "slug": "", "title": "", "start": 1, "end": 1, "num": None, "printed_pages": ""},
        ],
    },
    # EPUB source. Prefer an EPUB when the PDF text layer is damaged (wrong
    # ligature glyphs, missing spaces). Each chapter names its XHTML file in
    # the archive. Page markers come from print-page anchors whose id starts
    # with epub_page_anchor ("page_" for <a id="page_12"/>); without anchors
    # the chapter has no page markers. epub_heading_classes lists the class
    # attributes of the heading elements to drop (chapter number and title).
    # {
    #     "slug": "",
    #     "epub": "",
    #     "title": "",
    #     "part": 2,
    #     "epub_page_anchor": "page_",
    #     "epub_heading_classes": ["chno", "chtitle"],
    #     "chapters": [
    #         {"unit_id": "ch-01", "slug": "", "title": "", "num": 1, "file": "OEBPS/ch01.xhtml", "printed_pages": ""},
    #     ],
    # },
    # Paged .txt source: a pdftotext dump with a form feed per PDF page (piece
    # k = PDF page k). Use when only a text dump exists. Lines are cleaned per
    # page: running heads (header_patterns, footer_patterns), drop caps, and
    # junk lines are dropped; line_fixes replaces whole lines the dump mangled
    # (letter-spaced or two-line headings: "\nHeading\n" makes a block).
    # Set "dehyphenated": True if the dump joined hyphen-ended lines and
    # dropped the hyphen ("workingclass"); hyphen_fixes lists hand-checked
    # repairs. "kerning_spaces": True restores spaces lost after punctuation
    # before T, V, W, Y. "notes" attaches endnotes printed at the back to each
    # chapter (pages, and a heading pattern whose group is the chapter key).
    # "block_quotes": True marks block quotations with "> " (see
    # mark_block_quotes); block_quote_fixes holds hand-checked corrections,
    # and not_headings lists first lines the heading rule must skip.
    # Chapters give start/end PDF pages and a first_line (stop_line) prefix.
    # {
    #     "slug": "",
    #     "txt": "",
    #     "title": "",
    #     "part": 3,
    #     "header_patterns": [r"^[A-Z][A-Z'.,:&\- ]*$"],
    #     "dehyphenated": False,
    #     "kerning_spaces": False,
    #     "line_fixes": {},
    #     "notes": {"start": 300, "end": 310, "heading": r"^Chapter (\d+)$"},
    #     "block_quotes": True,
    #     "block_quote_fixes": {"join": [], "start": [], "end": [], "add": [], "remove": []},
    #     "not_headings": [],
    #     "chapters": [
    #         {"unit_id": "ch-01", "slug": "", "title": "", "num": 1, "start": 18, "end": 37,
    #          "printed_pages": "1-20", "first_line": "", "notes": 1},
    #     ],
    # },
    # Docling Markdown source: a .md file docling exported from a PDF (see
    # the Docling Markdown section below). The export is the source; the PDF
    # is for checking. A chapter starts at a docling heading line ("## 3 The
    # Long War"): by default one whose text, normalized for case, spacing,
    # and punctuation, is the title, the number and title, or a title_alt;
    # a bare number heading ("## 3", "## Chapter 3") just above it is taken
    # in, even across an image or formula placeholder, a comment, or a page
    # break, and also when docling made it a paragraph ("2"). "heading"
    # matches other heading text instead, and "first_line" (a line prefix)
    # starts at a body line, after the heading. "occurrence" picks a later
    # match when a table of contents repeats a heading; it counts matches
    # from just after the previous chapter's start (from the top of the file
    # for the first chapter), not from the top of the file. A chapter with
    # no body words (bare numbers, such as a contents page's page numbers,
    # do not count) is an error (usually a wrong occurrence): it stops the
    # run before any chapter file is written, and repairs.tsv is still
    # written. Another chapter's start heading inside a chapter is logged as
    # chapter-start-inside. A chapter ends at the next chapter's start, or
    # before the first line after its start beginning with stop_line; text
    # after a stop_line and before the next start (part titles, back
    # matter), and text before the first chapter, is left out and logged
    # as outside-chapters with its line range. A chapter that starts at
    # first_line needs stop_line on the chapter before it, or that chapter
    # keeps the heading. Chapters never set start/end pages.
    # page_break is docling's page_break_placeholder line: each one starts
    # the next PDF page, counted from first_page. skip_pages lists PDF pages
    # the export has no break for (blank or image-only pages), and last_page,
    # if set, is checked against the count. With no placeholders in the
    # file there are no page markers and pdf_pages is empty.
    # header_patterns (regexes searched in each paragraph and heading) and
    # junk_lines (whole normalized lines) drop running heads that leaked
    # into the text. They apply anywhere in the file, so make them specific.
    # footnote_pattern (a regex matched at the start of a paragraph) marks
    # footnotes: they move to a notes block at the chapter end, and a
    # paragraph they interrupted is rejoined. Footnotes docling exported as
    # a list block ("1. Minutes...", "2. ...", "* Not in...") count too
    # when every item matches the pattern: each item moves on its own,
    # logged as footnote-moved-from-list for review. Such a list stays in
    # the body (logged as footnote-candidate) when it reads as a body list:
    # the block before it ends with a colon, or the list before or after it
    # (across the page break) continues its numbering or bullets. With
    # page breaks, only footnotes at the end of a page move unless
    # footnotes_at_page_end is False; a page-end list that looks like notes
    # but does not match the pattern is logged as footnote-candidate.
    # Without page breaks (or with footnotes_at_page_end False) every body
    # paragraph matching the pattern is moved, with nothing to confirm it
    # is a note: each is logged as footnote-moved-no-page-evidence for
    # review. Each moved note follows a "<!-- footnote on page N -->"
    # comment; the notes block has no page marker of its own, so a part
    # holding only notes gets the body's last page in pdf_pages.
    # A paragraph or list interrupted on the same page (by a moved footnote,
    # a running head, or a placeholder) is rejoined by the same rules as
    # across a page break; an open-ended block left unjoined there, or a
    # paragraph a kept table splits from its continuation, is logged as
    # block-unjoined. not_headings lists heading-line prefixes that are
    # body text.
    # strip_emphasis removes *italic* and **bold** markers (default: kept).
    # hyphen_spaces: True rejoins "popu- lation", a line-end hyphen kept
    # with a space, by the hyphenation rules; False keeps and logs each.
    # line_fixes, char_map, hyphenates, block_quotes, and block_quote_fixes
    # work as for paged TXT.
    # {
    #     "slug": "",
    #     "md": "",
    #     "title": "",
    #     "part": 4,
    #     "page_break": "<!-- page break -->",
    #     "first_page": 1,
    #     "skip_pages": [],
    #     "last_page": None,
    #     "header_patterns": [r"^HARBOR TOWN HISTORY$"],
    #     "junk_lines": [],
    #     "footnote_pattern": r"^\d{1,3}\s",
    #     "footnotes_at_page_end": True,
    #     "not_headings": [],
    #     "strip_emphasis": False,
    #     "hyphen_spaces": False,
    #     "line_fixes": {},
    #     "block_quotes": True,
    #     "block_quote_fixes": {"join": [], "start": [], "end": [], "add": [], "remove": []},
    #     "chapters": [
    #         {"unit_id": "ch-01", "slug": "", "title": "", "num": 1, "printed_pages": "1-20"},
    #         {"unit_id": "ch-02", "slug": "", "title": "", "num": 2, "printed_pages": "21-40",
    #          "heading": "", "occurrence": 1, "first_line": "", "stop_line": ""},
    #     ],
    # },
]


def norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def headnorm(s):
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    s = re.sub(r"[^A-Za-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


class RepairLog:
    """Extraction decisions to check against the page image.

    Written to Work/Raw/{slug}/repairs.tsv. Kinds:
      heading-stripped, heading-not-found
      hyphen-removed, hyphen-kept         line-end hyphen before a lowercase letter
      page-join, page-join-midword        paragraph continued across a page break
      page-join-uncertain                 continued across a page break; check the page
      block-join, block-join-midword,     block continued by a lowercase block on the same page
      block-join-uncertain
      page-break-unjoined                 page ends without closing punctuation but was not joined
      furniture-dropped                   bare page number or date stamp in a margin zone
      url-join-uncertain                  URL line ends in a dot before a lowercase word; space kept
      blockquote                          block quotation marked: colon lead-in and closing citation
      blockquote-nocite, -multi,          block quotation marked on weaker evidence; review each
      blockquote-no-leadin, -epigraph
      blockquote-fixed                    marked or unmarked by the source's block_quote_fixes
    Docling Markdown sources also log (page is a PDF page, or "line N" of the
    .md file when the export has no page-break placeholders):
      no-page-markers                     the file has no page_break placeholders (once)
      page-count-mismatch                 page count differs from last_page
      chapter-start-ambiguous             the chapter's start heading recurs inside it
      chapter-start-inside                another chapter's start heading falls inside this one
                                          (check occurrence: a contents page may have matched)
      chapter-start-not-heading           start matched a paragraph, not a heading line
      chapter-end-of-file                 last chapter has no stop_line and runs to the end
      outside-chapters                    text in no chapter (front matter, part titles, text
                                          after a stop_line): line range, words, first words
      section-heading                     docling heading turned into a plain heading line
      heading-demoted                     heading line listed in not_headings, kept as text
      image-placeholder, formula-placeholder, comment-dropped
                                          placeholder dropped; check the page for content
      code-block                          fenced block kept verbatim
      furniture-dropped                   running head matched header_patterns or junk_lines
      furniture-candidate                 bare page-number paragraph kept
      footnote-moved                      moved to the notes block at the chapter end
      footnote-moved-no-page-evidence     moved with no page end to confirm it (no page
                                          breaks, or footnotes_at_page_end False); review
      footnote-moved-from-list            an item of a docling list block taken as a footnote
                                          and moved (the detail says when there was no page
                                          end to confirm it); review each
      footnote-candidate                  looks like a footnote but stayed in the body: matches
                                          footnote_pattern away from a page end, a matching list
                                          that reads as a body list (lead-in colon, numbering or
                                          bullets continuing), or a page-end list that looks
                                          like notes but does not match footnote_pattern
      footnote-open-ended                 moved footnote may continue on the next page
      page-break-joined, -midword,        paragraph rejoined across a page break or
      page-break-joined-uncertain         removed footnotes, running head, or placeholder
      list-page-joined, -midword,         last list item continued in lowercase after a page
      list-page-joined-uncertain          break or a removed block (same page or not), joined
      page-break-unjoined                 open-ended block (paragraph, list, quotation,
                                          code; a table followed by a table) not joined across
                                          a page break (or anywhere, when the export has none)
      block-unjoined                      the same, on one page: an open-ended block not joined
                                          across a removed block (footnote, running head,
                                          placeholder), or a paragraph split by a kept table
                                          from the paragraph it continues
      unescaped                           backslash removed before * # [ ] < > or &
      unescaped-underscores               one row per chapter: how many \\_ became _, where,
                                          and a few examples
      leading-markup-kept                 paragraph or heading would start with "#" or ">"
                                          after unescaping; a backslash is kept before it
      hyphen-space-kept                   "popu- lation": hyphen and space kept as exported
      blockquote-source                   paragraph the export already marked "> "
      emphasis-kept, emphasis-stripped    *italic* / **bold** spans in the chapter
      replacement-char, glyph-placeholder U+FFFD or docling "GLYPH<...>" left in the text
    """

    COLUMNS = ("unit_id", "pdf_page", "kind", "detail")

    def __init__(self):
        self.rows = []
        self.unit = ""

    def add(self, page, kind, detail):
        self.rows.append((self.unit, page, kind, detail))

    def kinds(self):
        return [row[2] for row in self.rows]

    def write(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\t".join(self.COLUMNS) + "\n")
            for row in self.rows:
                f.write("\t".join(re.sub(r"[\t\n]", " ", str(v)) for v in row) + "\n")


def _log(log, page, kind, detail):
    if log is not None:
        log.add(page, kind, detail)


def heading_forms(title, num=None, alt=None):
    """Normalized strings that count as a complete chapter heading."""
    t = headnorm(title or "")
    n = headnorm(str(num)) if num not in (None, "") else ""
    forms = set()
    if n:
        forms |= {n, "chapter " + n}
    if t:
        forms.add(t)
    if n and t:
        forms |= {n + " " + t, "chapter " + n + " " + t}
    for extra in (alt or []):
        e = headnorm(extra)
        if e:
            forms.add(e)
            if n:
                forms |= {n + " " + e, "chapter " + n + " " + e}
    return forms


def strip_chapter_heading(paras, title, num=None, log=None, page=None, alt=None):
    """Remove the chapter heading from the first blocks of a chapter's first page.

    Strips leading blocks that, alone or together, spell the chapter number or
    title (a title can be broken over several blocks). Stops at the first block
    that does not, so body text is never removed. alt lists extra heading
    spellings, such as a corrected title whose source heading has an OCR error.
    """
    forms = heading_forms(title, num, alt)
    if not forms:
        return list(paras)
    done, acc = 0, ""
    for i, para in enumerate(paras[:MAX_HEADING_BLOCKS]):
        pn = headnorm(para)
        if not pn:
            break
        # A note number can be set right after the heading text: "Title1".
        cands = [(acc + " " + x).strip() for x in {pn, re.sub(r"(?<=[a-z])\d{1,3}$", "", pn)}]
        if any(c in forms for c in cands):
            done, acc = i + 1, ""
        elif any(f.startswith(c + " ") for c in cands for f in forms):
            acc = next(c for c in cands if any(f.startswith(c + " ") for f in forms))
        else:
            break
    for para in paras[:done]:
        _log(log, page, "heading-stripped", para)
    if not done:
        _log(log, page, "heading-not-found", "first block: %s" % (paras[0][:80] if paras else ""))
    return list(paras[done:])


def is_known(word):
    for part in re.split(r"[-\u2019']", word):
        p = re.sub(r"[^A-Za-z]", "", part)
        if not p:
            continue
        if not sp.known([p.lower()]):
            return False
    return True


def ov(a, b):
    return min(a[2], b[2]) - max(a[0], b[0])


def line_text(spans, space_repair=None):
    """Join one line's characters into text.

    Artifact spaces (a space glyph overlapping a real glyph) are dropped.
    Some PDFs omit the space character at word boundaries, leaving only a
    horizontal gap; for a font listed in space_repair (font name -> em
    factor) a space is inserted when the gap before a character exceeds
    factor * font size and neither neighbour is already a space.
    """
    chars = [(c, s["font"], s["size"]) for s in spans for c in s["chars"]]
    out = []
    prev = None
    n = len(chars)
    for i, (c, font, size) in enumerate(chars):
        ch = c["c"]
        if ch == " ":
            artifact = False
            for j in range(n):
                if j == i or chars[j][0]["c"] == " ":
                    continue
                if ov(c["bbox"], chars[j][0]["bbox"]) > OVERLAP_THRESHOLD:
                    artifact = True
                    break
            if artifact:
                continue
            out.append(ch)
            prev = c
            continue
        factor = (space_repair or {}).get(font)
        if factor and prev is not None and prev["c"] != " ":
            if c["bbox"][0] - prev["bbox"][2] > factor * size:
                out.append(" ")
        out.append(ch)
        prev = c
    return "".join(out).translate(LIGATURE_TABLE)


def is_url(token):
    return "://" in token or token.startswith("www.") or "/" in token


class DocEvidence:
    """What the source document itself shows about spelling and hyphenation.

    forms: lowercased word forms that appear whole inside a line. A line-end
    break leaves only fragments, so these show how the source spells a word,
    e.g. "co-operate" versus "cooperate".
    hyphenates: whether the document breaks words at line ends at all. A
    reflowed ebook usually does not, so its line-end hyphens are real text.
    """

    def __init__(self, forms=(), hyphenates=True):
        self.forms = set(forms)
        self.hyphenates = hyphenates

    @classmethod
    def from_doc(cls, doc, hyphenates=None):
        lines = [ln for page in doc for ln in page.get_text("text").splitlines()]
        ev = cls(w.lower() for ln in lines for w in WORD.findall(ln))
        ev.breaks, ev.settled = 0, 0
        for a, b in zip(lines, lines[1:]):
            m = re.search(r"(\S*?)([A-Za-z]+)-\s*$", a)
            n = re.match(r"\s*([a-z]+)", b)
            if not (m and n) or is_url(m.group(1)):
                continue
            joined = (m.group(2) + n.group(1)).lower() in ev.forms
            hyphened = (m.group(2) + "-" + n.group(1)).lower() in ev.forms
            if joined != hyphened:
                ev.settled += 1
                ev.breaks += joined
        if hyphenates is None:
            hyphenates = ev.breaks >= HYPHENATION_MIN_BREAKS and ev.breaks >= HYPHENATION_MIN_SHARE * ev.settled
        ev.hyphenates = hyphenates
        return ev


NO_EVIDENCE = DocEvidence()


def hyphen_decision(stem, first, ev):
    """Return (separator, basis) for a word broken as stem- / first.

    Separator is "-" to keep the hyphen or "" to join the fragments into one
    word. Document evidence wins. A dictionary confirms a joined word. A
    known prefix, an acronym stem, or two known words keep the hyphen: a
    compound such as well- / known or poverty- / stricken must not lose it.
    Otherwise, in a document that hyphenates, an unverifiable line-end
    hyphen is taken as a word break and the fragments are joined.
    """
    if not ev.hyphenates:
        return "-", "document does not break words at line ends"
    joined, hyphened = (stem + first).lower(), (stem + "-" + first).lower()
    in_joined, in_hyphened = joined in ev.forms, hyphened in ev.forms
    if in_hyphened and not in_joined:
        return "-", "document"
    if in_joined and not in_hyphened:
        return "", "document"
    if in_joined and in_hyphened:
        return "-", "uncertain: document has both forms"
    stem_known, first_known = is_known(stem), is_known(first)
    if is_known(joined):
        if stem_known and first_known:
            return "", "uncertain: dictionary, but both parts are words"
        return "", "dictionary"
    if stem.isupper() and len(stem) >= 2:
        return "-", "acronym compound"
    if stem.lower() in PREFIXES:
        return "-", "prefix"
    if stem_known and first_known:
        return "-", "uncertain: both parts are words"
    return "", "uncertain: unverified, document hyphenates"


def join_hyphenated(left, right, ev=NO_EVIDENCE, log=None, page=None, marker=""):
    """Join text ending in a letter and hyphen to its continuation, with no space.

    Before a capital or digit, or after a digit, the hyphen belongs to the
    word (Anglo-Saxon, pre-1990, 55-member) and is kept, as it is inside a
    URL. Before a lowercase letter it may be a line-break hyphen; the
    decision and its basis are logged. marker, if given, goes at the seam.
    """
    m = re.match(r"[a-z]+", right)
    token = left.rsplit(None, 1)[-1]
    stem = re.search(r"([A-Za-z]*)-$", left).group(1)
    if not m or not stem or is_url(token):
        return left + marker + right
    first = m.group(0)
    sep, basis = hyphen_decision(stem, first, ev)
    word = stem + sep + first
    kind = "hyphen-kept" if sep == "-" else "hyphen-removed"
    _log(log, page, kind, "%s- / %s -> %s (%s)" % (stem, first, word, basis))
    return (left if sep == "-" else left[:-1]) + marker + right


URL_WRAP_CHARS = "/?&=#_~%"


def url_continues(left, right, log=None, page=None):
    """Whether right continues a URL that wrapped at the end of left.

    A URL broken after a slash or query character always continues. One
    broken after a dot continues only if left is a full URL and the next
    token also looks like URL text (com/path, example.org); otherwise the
    dot may end a sentence, so the space is kept and a lowercase
    continuation is logged for review.
    """
    token = left.rsplit(None, 1)[-1]
    if not is_url(token):
        return False
    if token[-1] in URL_WRAP_CHARS:
        return True
    if token[-1] != "." or not ("://" in token or token.startswith("www.")):
        return False
    head = re.sub(r"[.,;:!?)\]'\"]+$", "", right.split(None, 1)[0])
    if re.search(r"[/.?=#]", head):
        return True
    if right[:1].islower():
        _log(log, page, "url-join-uncertain", "%s / %s (kept space)" % (token, head))
    return False


def join_lines(lines, ev=NO_EVIDENCE, log=None, page=None):
    text = ""
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if not text:
            text = ln
        elif re.search(r"[A-Za-z0-9]-$", text):
            text = join_hyphenated(text, ln, ev, log, page)
        elif url_continues(text, ln, log, page):
            text = text + ln
        else:
            text = text + " " + ln
    return re.sub(r"\s+", " ", text).strip()


def in_margin_zone(bbox, page):
    r = page.rect
    zone = r.height * PAGE_NUM_ZONE
    return bbox[3] <= r.y0 + zone or bbox[1] >= r.y1 - zone


def block_paragraphs(page, header_ymax, footer_ymin, ev=NO_EVIDENCE, log=None, space_repair=None):
    page_no = page.number + 1
    blocks = []
    for b in page.get_text("rawdict")["blocks"]:
        if b.get("type", 0) != 0:
            continue
        y0, y1 = b["bbox"][1], b["bbox"][3]
        if header_ymax and y1 <= header_ymax:
            continue
        if footer_ymin and y0 >= footer_ymin:
            continue
        lines = []
        for l in b.get("lines", []):
            lines.append(line_text(l["spans"], space_repair))
        text = join_lines(lines, ev, log, page_no)
        if text:
            blocks.append((text, b["bbox"]))
    paras = []
    for i, (text, bbox) in enumerate(blocks):
        if norm(text) in JUNK_LINES or any(p.match(text) for p in STAMP_PATTERNS):
            continue
        if LONE_PUNCT.match(text):
            _log(log, page_no, "furniture-dropped", text)
            continue
        edge = i == 0 or i == len(blocks) - 1
        if (BARE_NUM.match(text) or DATE.match(text)) and edge and in_margin_zone(bbox, page):
            _log(log, page_no, "furniture-dropped", text)
            continue
        paras.append(text)
    return paras


# ---------------------------------------------------------------- EPUB

MARK = "\x00%d\x00"
MARK_RE = re.compile("\x00(\\d+)\x00")


DEFAULT_PAGE_ANCHOR = "page_"
# No default: heading markup differs between publishers. Set
# epub_heading_classes per source after opening one chapter file.
DEFAULT_HEADING_CLASSES = ()


class EpubText(HTMLParser):
    """Collect block texts from EPUB XHTML, with page anchors kept inline.

    Print page boundaries are anchored as elements whose id is the anchor
    prefix plus the page number (<a id="page_12"/> by default); they become
    sentinel markers that epub_paragraphs turns into <!-- page N -->.
    Elements whose class is in skip_classes are dropped with their content,
    except for any page anchors inside them.
    """

    BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "br", "tr", "blockquote"}
    VOID = {"br", "img", "hr", "meta", "link", "input", "col", "area", "base", "wbr", "source"}

    def __init__(self, anchor=DEFAULT_PAGE_ANCHOR, skip_classes=()):
        super().__init__(convert_charrefs=True)
        self.anchor = anchor
        self.skip_classes = set(skip_classes)
        self.blocks = []
        self.cur = ""
        self.skip = 0
        self.dropped = 0          # nesting depth inside a skipped heading element
        self.dropped_seen = 0     # skipped elements found
        self.first_anchor = None  # first page anchor inside a skipped element

    def page_of(self, attrs):
        ident = dict(attrs).get("id") or ""
        if self.anchor and ident.startswith(self.anchor):
            n = ident[len(self.anchor):]
            if n.isdigit():
                return int(n)
        return None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        page = self.page_of(attrs)
        if self.dropped:
            if tag not in self.VOID:
                self.dropped += 1
            if page is not None and self.first_anchor is None:
                self.first_anchor = page
            return
        classes = set((a.get("class") or "").split())
        if classes & self.skip_classes and tag not in self.VOID:
            self.flush()
            self.dropped = 1
            self.dropped_seen += 1
            if page is not None and self.first_anchor is None:
                self.first_anchor = page
            return
        if tag in ("script", "style", "head", "title"):
            self.skip += 1
        elif page is not None:
            self.cur += MARK % page
        elif tag in self.BLOCK:
            self.flush()

    def handle_startendtag(self, tag, attrs):
        page = self.page_of(attrs)
        if page is not None:
            if self.dropped:
                if self.first_anchor is None:
                    self.first_anchor = page
            else:
                self.cur += MARK % page
        elif not self.dropped and tag in self.BLOCK:
            self.flush()

    def handle_endtag(self, tag):
        if self.dropped:
            self.dropped -= 1
            return
        if tag in ("script", "style", "head", "title"):
            if self.skip:
                self.skip -= 1
        elif tag in self.BLOCK:
            self.flush()

    def handle_data(self, data):
        if not self.skip and not self.dropped:
            self.cur += data

    def flush(self):
        t = re.sub(r"\s+", " ", self.cur).strip()
        if t:
            self.blocks.append(t)
        self.cur = ""


def epub_paragraphs(raw, ch, log=None, anchor=DEFAULT_PAGE_ANCHOR, heading_classes=DEFAULT_HEADING_CLASSES):
    """Return block paragraphs for one EPUB chapter, with page markers.

    Heading elements whose class is in heading_classes are dropped (their
    text lives in the frontmatter); a page anchor inside one still marks the
    chapter's first page. A page anchor that opens a paragraph gets its
    marker on its own line; one inside a paragraph stays inline at the seam.
    """
    if log is not None:
        log.unit = ch["unit_id"]
    parser = EpubText(anchor, heading_classes)
    parser.feed(raw)
    parser.flush()
    paras = []
    for block in parser.blocks:
        text = MARK_RE.sub(lambda mm: PAGE_MARKER % int(mm.group(1)), block)
        text = re.sub(r"(<!-- page \d+ -->)\s*", r"\1 ", text)
        text = re.sub(r"^(<!-- page \d+ -->) ", r"\1\n", text).strip()
        if text:
            paras.append(text)
    if parser.first_anchor is not None:
        paras.insert(0, PAGE_MARKER % parser.first_anchor)
    if not parser.dropped_seen:
        _log(log, None, "heading-not-found", ch["title"])
    return paras


def make_epub_extractor(cfg, log=None):
    path = os.path.join(SOURCES, cfg["epub"])
    anchor = cfg.get("epub_page_anchor", DEFAULT_PAGE_ANCHOR)
    classes = cfg.get("epub_heading_classes", DEFAULT_HEADING_CLASSES)

    def extractor(ch):
        with zipfile.ZipFile(path) as z:
            raw = z.read(ch["file"]).decode("utf-8")
        return epub_paragraphs(raw, ch, log, anchor, classes)

    return extractor


def save_epub_raw(cfg):
    """Save each chapter file's text, before cleanup, to Work/Raw/{slug}/raw.txt."""
    folder = os.path.join(RAW, cfg["slug"])
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "raw.txt")
    with zipfile.ZipFile(os.path.join(SOURCES, cfg["epub"])) as z:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for ch in cfg["chapters"]:
                f.write("<!-- file %s -->\n\n" % ch["file"])
                parser = EpubText(cfg.get("epub_page_anchor", DEFAULT_PAGE_ANCHOR))
                parser.feed(z.read(ch["file"]).decode("utf-8"))
                parser.flush()
                blocks = [MARK_RE.sub(lambda m: PAGE_MARKER % int(m.group(1)), b) for b in parser.blocks]
                f.write("\n\n".join(blocks) + "\n")
    return path


# ---------------------------------------------------------------- paged text
#
# A plain-text dump of a PDF (pdftotext without -layout) with one form feed
# (U+000C) after each page, so piece k of the split is PDF page k. Lines are
# the PDF's lines; blank lines separate text blocks. Running heads, page
# numbers, and drop caps are still in the text and are removed per source.

PAGE_NUM_LINE = re.compile(r"^(?:\d{1,4}|[ivxlcdm]{1,7})$", re.I)
# A drop cap set on its own line: "I" / "n 1831 Edith Varga" -> "In 1831".
DROP_CAP = re.compile(r"^[A-Z]$")
DROP_CAP_REST = re.compile(r"^[a-z.’']")


def txt_page_texts(path):
    """Return the page texts of a paged .txt source, PDF page k at index k-1.

    The text after the last form feed is kept only if it has content.
    """
    with open(path, encoding="utf-8") as f:
        pages = f.read().split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    return pages


def clean_txt_line(line, cfg):
    """Normalize one line: ligatures, per-source character map, stray controls."""
    line = line.translate(LIGATURE_TABLE)
    for a, b in cfg.get("char_map", {}).items():
        line = line.replace(a, b)
    return re.sub(r"[\x00-\x08\x0b\x0e-\x1f]", "", line).rstrip()


def _matches(line, patterns):
    return any(p.search(line) for p in patterns)


def strip_txt_furniture(lines, cfg, log=None, page=None):
    """Drop running heads, page numbers, and junk lines from one page.

    Header lines are dropped from the top of the page while they match the
    source's header patterns (or are a bare page number), within the first
    header_scan non-blank lines; footer lines the same way from the bottom.
    JUNK_LINES and the source's junk_lines are dropped anywhere. Each dropped
    line is logged, so a heading taken for furniture can be found.
    """
    head = [re.compile(p) for p in cfg.get("header_patterns", [])] + [PAGE_NUM_LINE]
    foot = [re.compile(p) for p in cfg.get("footer_patterns", [])] + [PAGE_NUM_LINE]
    junk = JUNK_LINES | {norm(j) for j in cfg.get("junk_lines", [])}
    scan = cfg.get("header_scan", 8)
    lines = list(lines)

    def trim(indices, patterns):
        seen = 0
        for i in indices:
            s = lines[i].strip()
            if not s:
                continue
            seen += 1
            if seen > scan or not _matches(s, patterns):
                return
            _log(log, page, "furniture-dropped", s)
            lines[i] = ""

    trim(range(len(lines)), head)
    trim(range(len(lines) - 1, -1, -1), foot)
    out = []
    for ln in lines:
        s = ln.strip()
        if s and (norm(s) in junk or any(p.match(s) for p in STAMP_PATTERNS)):
            _log(log, page, "furniture-dropped", s)
            continue
        out.append(ln)
    return out


def join_drop_caps(lines, log=None, page=None):
    """Join a drop cap on its own line to the text that follows it.

    The cap joins the next line's first word ("I" / "n 1831" -> "In 1831",
    "U" / ".S." -> "U.S.") when that makes a known word or the rest starts
    with punctuation. Otherwise the cap is a word of its own ("I" /
    "initially" -> "I initially"). An opening quotation mark set alone on
    the line before the cap is joined too.
    """
    out = list(lines)
    for i, ln in enumerate(out):
        cap = ln.strip()
        if not DROP_CAP.match(cap):
            continue
        j = next((k for k in range(i + 1, len(out)) if out[k].strip()), None)
        if j is None or j - i > 2 or not DROP_CAP_REST.match(out[j].strip()):
            continue
        rest = out[j].strip()
        first = re.match(r"[A-Za-z]*", rest).group(0)
        joined = not first or is_known(cap + first)
        sep = "" if joined else " "
        p = next((k for k in range(i - 1, -1, -1) if out[k].strip()), None)
        quote = ""
        if p is not None and i - p <= 2 and out[p].strip() in ("“", "‘", '"', "'"):
            quote = out[p].strip()
            out[p] = ""
        _log(log, page, "dropcap-joined" if joined else "dropcap-word", "%s%s + %s" % (quote, cap, rest[:20]))
        out[j] = quote + cap + sep + rest
        out[i] = ""
    return out


def txt_line_width(pages):
    """Typical full line length in characters for a paged text source.

    The median of ordinary lines: those over 20 characters and not overlong
    (a dehyphenating dump joins a whole line onto the one before it).
    """
    lengths = sorted(len(ln.strip()) for p in pages for ln in p.splitlines() if len(ln.strip()) > 20)
    if not lengths:
        return 70
    med = lengths[len(lengths) // 2]
    ordinary = [n for n in lengths if n <= 1.3 * med]
    return ordinary[len(ordinary) // 2]


def restore_compound_hyphens(line, ev, width, log=None, page=None, fixes=None):
    """Put back compound hyphens a dehyphenating dump removed.

    Such a dump joins the next line onto a line ending in a hyphen and drops
    the hyphen, so a real compound broken at a line end comes out as one
    word ("workingclass"). A word the dictionary does not know gets its
    hyphen back when the document spells it hyphenated by a clear majority,
    or when the source config lists it (hyphen_fixes, checked by hand).
    Joins usually make an overlong line; doubtful words on such lines are
    left as printed and logged for review.
    """
    overlong = len(line) > 1.3 * width
    fixes = fixes or {}
    counts = getattr(ev, "counts", {})

    def fix(m):
        word = m.group(0)
        if is_known(word) or "-" in word:
            return word
        fixed = fixes.get(word)
        if fixed:
            _log(log, page, "compound-hyphen-restored", "%s -> %s (config, checked by coordinator)" % (word, fixed))
            return fixed
        n_joined = counts.get(word.lower(), 0)
        for i in range(2, len(word) - 1):
            cand = word[:i] + "-" + word[i:]
            n_hyph = counts.get(cand.lower(), 0)
            if not n_hyph:
                continue
            # The dump also makes the joined form wherever it rejoined a
            # break, so the joined count is inflated; the hyphenated form
            # only comes from the author. A clear majority settles it.
            if n_hyph >= 2 and n_hyph >= 3 * n_joined:
                _log(log, page, "compound-hyphen-restored", "%s -> %s (document: %d hyphenated, %d joined)" % (word, cand, n_hyph, n_joined))
                return cand
            if n_joined >= 3 * n_hyph or not overlong:
                return word
            _log(log, page, "compound-hyphen-uncertain", "%s or %s: document has %d joined, %d hyphenated (kept as printed)" % (word, cand, n_joined, n_hyph))
            return word
        if n_joined > 1 or not overlong:
            return word
        halves = [(word[:i], word[i:]) for i in range(3, len(word) - 2)]
        if any(is_known(a) and is_known(b) for a, b in halves):
            _log(log, page, "compound-hyphen-uncertain", "%s: not elsewhere in the document (kept as printed)" % word)
        return word

    return re.sub(r"[A-Za-zÀ-ɏ]{5,}", fix, line)


def txt_paragraphs(lines, cfg, ev, width, log=None, page=None, para_start=None):
    """Split one page's cleaned lines into paragraphs.

    Blank lines separate blocks. Inside a block a paragraph ends at a line
    that ends a sentence and falls well short of the full line width (for an
    overlong joined line, its last physical line is measured). The first line
    of a block is its own paragraph when it is short and reads as a heading.
    A short line ending in a colon ends a paragraph too: it introduces a
    block quotation, which the dump does not set off. para_start, if given,
    is a pattern for lines that always begin a paragraph (note numbers).
    not_headings lists line prefixes the heading rule must skip (a chapter's
    first line, shortened by a drop cap).

    With the source's block_quotes setting, a colon line of any length ends
    a paragraph when the next line starts with a capital or an opening
    quotation mark, and a line ending in a block citation ends one too, so
    a block quotation is a paragraph of its own (see mark_block_quotes).
    """
    bq = cfg.get("block_quotes", False)
    blocks, cur = [], []
    for ln in lines:
        if ln.strip():
            cur.append(ln.strip())
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    dehyph = cfg.get("dehyphenated", False)
    paras = []
    for block in blocks:
        if dehyph:
            fixes = cfg.get("hyphen_fixes", {})
            block = [restore_compound_hyphens(ln, ev, width, log, page, fixes) for ln in block]
        group = []
        for i, ln in enumerate(block):
            if para_start is not None and group and para_start.match(ln):
                paras.append(join_lines(group, ev, log, page))
                group = []
            if (i == 0 and len(block) > 1 and len(ln) < 0.7 * width and is_heading(ln) and block[1][:1].isupper()
                    and not any(ln.startswith(x) for x in cfg.get("not_headings", []))):
                paras.append(ln)
                continue
            group.append(ln.replace("­", "-") if ln.endswith("­") else ln)
            tail = len(ln) - width if len(ln) > 1.3 * width else len(ln)
            nxt = block[i + 1] if i + 1 < len(block) else ""
            if bq and (BLOCK_CITATION.search(ln) or (ln.endswith(":") and re.match(r"[A-Z“‘\"']", nxt))):
                paras.append(join_lines(group, ev, log, page))
                group = []
            elif (ends_sentence(ln) or ln.endswith(":")) and tail < 0.8 * width:
                paras.append(join_lines(group, ev, log, page))
                group = []
        if group:
            paras.append(join_lines(group, ev, log, page))
    return [p for p in paras if p]


# Some typesetting tightens the gap after punctuation before T, V, W, and Y
# (kerning pairs), and the dump then loses the space: "place.This".
KERNING_GAP = re.compile(r"(?<=[A-Za-z][.,;:?!])(?=[TVWY][a-z]|“)")


def apply_line_fixes(lines, cfg, log=None, page=None):
    """Apply a source's exact line replacements and kerning-gap repair.

    line_fixes maps a whole stripped line to its replacement, for text the
    dump mangled beyond rule-based repair (letter-spaced headings). A
    replacement may contain newlines: an empty line around a heading makes
    it a block of its own. kerning_spaces restores the space the dump lost
    after punctuation before T, V, W, Y, or an opening quotation mark.
    """
    fixes = cfg.get("line_fixes", {})
    out = []
    for ln in lines:
        s = ln.strip()
        if s in fixes:
            _log(log, page, "line-fixed", "%s -> %s" % (s, fixes[s].strip() or "(dropped)"))
            out.extend(fixes[s].split("\n") if fixes[s] else [])
            continue
        if cfg.get("kerning_spaces"):
            fixed = KERNING_GAP.sub(" ", ln)
            if fixed != ln:
                _log(log, page, "kerning-space", " | ".join(m.group(0) for m in re.finditer(r"\S*[.,;:?!](?:[TVWY][a-z]|“)\S*", ln)))
                ln = fixed
        out.append(ln)
    return out


def _cut_page(lines, first_line=None, stop_line=None, log=None, page=None):
    """Keep a page's lines from first_line on and before stop_line (prefix matches)."""
    lines = list(lines)
    if first_line:
        idx = next((i for i, ln in enumerate(lines) if ln.strip().startswith(first_line)), None)
        if idx is None:
            raise SystemExit("page %s: first_line %r not found" % (page, first_line))
        for ln in lines[:idx]:
            if ln.strip():
                _log(log, page, "heading-stripped", ln.strip())
        lines = lines[idx:]
    if stop_line:
        idx = next((i for i, ln in enumerate(lines) if ln.strip().startswith(stop_line)), None)
        if idx is None:
            raise SystemExit("page %s: stop_line %r not found" % (page, stop_line))
        lines = lines[:idx]
    return lines


class TxtSource:
    """A paged .txt source with its per-source cleanup settings."""

    def __init__(self, cfg, log=None):
        self.cfg = cfg
        self.log = log
        self.pages = txt_page_texts(os.path.join(SOURCES, cfg["txt"]))
        self.width = cfg.get("line_width") or txt_line_width(self.pages)
        # Spelling evidence comes from ordinary lines only: an overlong line in
        # a dehyphenating dump holds a join whose spelling is in question.
        lines = [clean_txt_line(ln, cfg) for p in self.pages for ln in p.splitlines()]
        counts = Counter(w.lower() for ln in lines for w in WORD.findall(ln))
        if cfg.get("dehyphenated"):
            lines = [ln for ln in lines if len(ln.strip()) <= 1.3 * self.width]
        ev = DocEvidence(w.lower() for ln in lines for w in WORD.findall(ln))
        ev.hyphenates = cfg.get("hyphenates", True)
        ev.counts = counts
        self.ev = ev

    def page_lines(self, no, first_line=None, stop_line=None):
        """Cleaned lines of PDF page no, cut to a unit's boundaries."""
        lines = [clean_txt_line(ln, self.cfg) for ln in self.pages[no - 1].splitlines()]
        lines = apply_line_fixes(lines, self.cfg, self.log, no)
        # Drop caps first: a lone capital would otherwise read as a running head.
        lines = join_drop_caps(lines, self.log, no)
        lines = strip_txt_furniture(lines, self.cfg, self.log, no)
        return _cut_page(lines, first_line, stop_line, self.log, no)

    def unit_pages(self, start, end, first_line=None, stop_line=None):
        pages = []
        for no in range(start, end + 1):
            lines = self.page_lines(no, first_line if no == start else None, stop_line if no == end else None)
            pages.append((no, txt_paragraphs(lines, self.cfg, self.ev, self.width, self.log, no)))
        return pages

    def notes_for(self, key):
        """Pages of the endnotes printed for one chapter, cut at the chapter headings."""
        notes = self.cfg["notes"]
        heading = re.compile(notes["heading"])
        out, active = [], False
        for no in range(notes["start"], notes["end"] + 1):
            lines = self.page_lines(no)
            kept = []
            for ln in lines:
                m = heading.match(ln.strip())
                if m:
                    active = m.group(1) == str(key)
                    continue
                if active:
                    kept.append(ln)
            if any(ln.strip() for ln in kept):
                start = re.compile(notes.get("para_start", r"^\d{1,3}\.\s"))
                out.append((no, txt_paragraphs(kept, self.cfg, self.ev, self.width, self.log, no, start)))
        return out


NOTES_LABEL = "Notes to this chapter (printed at the back of the book):"


def _prefix_quote(para):
    """Put the block-quote prefix before a paragraph's text, after leading marker lines."""
    m = re.match(r"(?:<!--[^\n]*?-->\n)*", para)
    return para[:m.end()] + BLOCK_QUOTE_PREFIX + para[m.end():]


def _restructure_for_quotes(paras, fixes, log=None, heads=()):
    """Apply the join, start, and end fixes of mark_block_quotes.

    Returns (paragraphs, indexes where a quotation starts, indexes where one
    ends, indexes of heads). Joins and splits change only paragraph breaks:
    a join puts back the single space the break replaced (a page marker on
    its own line moves inline), and a split replaces the space before or
    after the given text. heads (heading indexes) are carried through: a
    joined paragraph keeps the flag of its first part, a split one gives it
    to its first part.
    """
    paras = list(paras)
    head_at = [i in heads for i in range(len(paras))]
    for suffix in fixes.get("join", []):
        for i in range(len(paras) - 1):
            if strip_comments(paras[i]).rstrip().endswith(suffix):
                nxt = re.sub(r"^(<!-- page \d+ -->)\n", r"\1 ", paras[i + 1])
                _log(log, "", "blockquote-fixed", "join (config, checked by coordinator): %s" % suffix)
                paras[i:i + 2] = [paras[i] + " " + nxt]
                head_at[i:i + 2] = [head_at[i]]
                break
    # Flags per paragraph, kept in step with the list as splits insert items.
    start_at, end_at = [False] * len(paras), [False] * len(paras)
    for kind in ("start", "end"):
        for frag in fixes.get(kind, []):
            for i, p in enumerate(paras):
                pos = p.find(frag)
                if pos < 0:
                    continue
                cut = pos if kind == "start" else pos + len(frag)
                head, tail = p[:cut].rstrip(" "), p[cut:].lstrip(" ")
                if not head.strip() or not tail.strip():
                    raise SystemExit("block_quote_fixes %s: %r is at a paragraph edge; no split needed" % (kind, frag))
                paras[i:i + 1] = [head, tail]
                start_at[i:i + 1] = [start_at[i], kind == "start"]
                end_at[i:i + 1] = [kind == "end", end_at[i]]
                head_at[i:i + 1] = [head_at[i], False]
                _log(log, "", "blockquote-fixed", "%s (config, checked by coordinator): %s" % (kind, frag))
                break
    forced_start = {i for i, f in enumerate(start_at) if f}
    forced_end = {i for i, f in enumerate(end_at) if f}
    return paras, forced_start, forced_end, {i for i, f in enumerate(head_at) if f}


def mark_block_quotes(paras, log=None, fixes=None, item_start=None, heads=()):
    """Prefix the paragraphs of each block quotation with "> ".

    A quotation starts after a lead-in paragraph ending in a colon and runs
    to the first paragraph, within BLOCK_QUOTE_WINDOW, that ends in a block
    citation; with no citation in reach only the first paragraph is marked.
    A paragraph ending in a block citation with no lead-in is marked alone,
    and so is an epigraph (a paragraph ending in a dash and attribution).
    Scanning stops at a heading, a new lead-in, or an item_start paragraph
    (note numbers), which never starts a quotation. heads lists the indexes
    of paragraphs known to be headings (docling heading lines): they stop a
    quotation and are never quoted, whatever their text. Every quotation is
    logged; the kinds other than "blockquote" (lead-in and citation both
    found) need the coordinator's review.

    fixes, all set by hand after review; a string that matches nothing in
    this unit is ignored here and reported by check_block_quote_fixes:
      join    end of a colon lead-in that does not open a block quotation
              (the author's sentence runs on): the paragraph is joined to
              the next with a space, as printed.
      start   text where a block quotation begins inside a paragraph (a
              lead-in without a colon, or the dump lost the break): the
              paragraph is split before it, and the quotation runs from there
              like one after a colon lead-in.
      end     final text of a block quotation that runs on into the author's
              prose in the dump: the paragraph is split after it.
      add, remove   paragraph-text prefixes (page markers ignored) to mark or
              unmark. Each must match at most one paragraph.
    """
    fixes = fixes or {}
    paras, forced_start, forced_end, heads = _restructure_for_quotes(paras, fixes, log, set(heads))
    text = [strip_comments(p).strip() for p in paras]
    n = len(text)
    quoted = [False] * n
    pages, cur = [], None  # page each paragraph starts on, for the log
    for p in paras:
        m = re.match(r"<!-- page (\d+) -->", p)
        cur = int(m.group(1)) if m else cur
        pages.append(cur)
        marks = re.findall(r"<!-- page (\d+) -->", p)
        cur = int(marks[-1]) if marks else cur

    def item(k):
        return k in heads or item_start is not None and item_start.match(text[k])

    def stops(k):
        return is_heading(text[k]) or item(k) or text[k] == NOTES_LABEL

    for i in range(n):
        lead = text[i - 1] if i else ""
        led = lead.endswith(":") and lead != NOTES_LABEL
        # A short verse line after a lead-in reads as a heading; only a
        # note number or the notes label stops a quotation from starting.
        if quoted[i] or not (led or i in forced_start) or item(i) or text[i] == NOTES_LABEL:
            continue
        end = None
        for k in range(i, min(n, i + BLOCK_QUOTE_WINDOW)):
            if k > i and (stops(k) or text[k - 1].endswith(":") and k - 1 > i):
                break
            if BLOCK_CITATION.search(text[k]) or CITATION_ONLY.match(text[k]) or k in forced_end:
                end = k
                break
        if end is None:
            _log(log, pages[i], "blockquote-nocite", "%s | %s... | next: %s" % (lead[-40:], text[i][:50], text[i + 1][:40] if i + 1 < n else ""))
            end = i
        elif end > i:
            _log(log, pages[i], "blockquote-multi", "%d paragraphs: %s | %s ... %s" % (end - i + 1, lead[-40:], text[i][:40], text[end][-40:]))
        else:
            _log(log, pages[i], "blockquote", "%s | %s ... %s" % (lead[-40:], text[i][:40], text[i][-40:]))
        for k in range(i, end + 1):
            quoted[k] = True
    for i in range(n):
        if not quoted[i] and EPIGRAPH.search(text[i]) and not item(i):
            quoted[i] = True
            _log(log, pages[i], "blockquote-epigraph", "%s ... %s" % (text[i][:50], text[i][-50:]))
        if not quoted[i] and BLOCK_CITATION.search(text[i]) and not item(i):
            quoted[i] = True
            _log(log, pages[i], "blockquote-no-leadin", "prev: %s | %s ... %s" % (text[i - 1][-40:] if i else "", text[i][:50], text[i][-40:]))
    for kind, value in (("add", True), ("remove", False)):
        for prefix in fixes.get(kind, []):
            hits = [k for k in range(n) if text[k].startswith(prefix)]
            if len(hits) > 1:
                raise SystemExit("block_quote_fixes %s: %r matches %d paragraphs" % (kind, prefix, len(hits)))
            for k in hits:
                quoted[k] = value
                _log(log, pages[k], "blockquote-fixed", "%s (config, checked by coordinator): %s" % (kind, prefix))
    return [_prefix_quote(p) if q else p for p, q in zip(paras, quoted)]


def check_block_quote_fixes(cfg, folder):
    """Return the (kind, text) block_quote_fixes that match nothing in any chapter file.

    add and remove must start a paragraph; join, start, and end must occur
    somewhere in a chapter's text.
    """
    fixes = cfg.get("block_quote_fixes", {})
    bodies = []
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".md") or not os.path.isfile(os.path.join(folder, name)):
            continue  # skip parts/ and anything that is not a chapter file
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            bodies.append(f.read())
    paras = [strip_comments(p).strip().removeprefix(BLOCK_QUOTE_PREFIX) for b in bodies for p in b.split("\n\n")]
    missing = [(kind, p) for kind in ("add", "remove") for p in fixes.get(kind, [])
               if not any(q.startswith(p) for q in paras)]
    missing += [(kind, t) for kind in ("join", "start", "end") for t in fixes.get(kind, [])
                if not any(t in b for b in bodies)]
    return missing


def make_txt_extractor(cfg, log=None):
    src = TxtSource(cfg, log)
    print("%s: line width %d" % (cfg["txt"], src.width))

    def extractor(ch):
        if log is not None:
            log.unit = ch["unit_id"]
        paras = join_pages(src.unit_pages(ch["start"], ch["end"], ch.get("first_line"), ch.get("stop_line")), src.ev, log)
        bq = cfg.get("block_quotes", False)
        fixes = cfg.get("block_quote_fixes")
        if bq:
            paras = mark_block_quotes(paras, log, fixes)
        if ch.get("notes") is not None:
            notes = src.notes_for(ch["notes"])
            if not notes:
                raise SystemExit("%s: no notes found for chapter key %r" % (ch["unit_id"], ch["notes"]))
            note_paras = join_pages(notes, src.ev, log)
            if bq:
                start = re.compile(cfg["notes"].get("para_start", r"^\d{1,3}\.\s"))
                note_paras = mark_block_quotes(note_paras, log, fixes, start)
            note_paras[0] = re.sub(r"^(<!-- page \d+ -->\n)?", lambda m: (m.group(0) or "") + NOTES_LABEL + "\n\n", note_paras[0], count=1)
            paras += note_paras
        return paras

    return extractor


def save_txt_raw(cfg):
    """Save every page of a paged .txt source, before cleanup, with page markers."""
    folder = os.path.join(RAW, cfg["slug"])
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "raw.txt")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for i, page in enumerate(txt_page_texts(os.path.join(SOURCES, cfg["txt"])), 1):
            f.write(PAGE_MARKER % i + "\n" + page + "\n")
    return path


def last_alpha(text):
    m = re.search(r"([A-Za-z]+)[^A-Za-z]*$", text)
    return m.group(1) if m else ""


def first_alpha(text):
    m = re.match(r"[^A-Za-z]*([A-Za-z]+)", text)
    return m.group(1) if m else ""


def is_open_ended(block):
    """True if block stops without closing punctuation, so it may continue."""
    t = block.rstrip()
    return bool(t) and not ends_sentence(t) and t[-1] not in ":—-–"


def continues_across(a, b):
    """True if block a, ending one page, may run on into block b on the next.

    A short page-end fragment looks like a heading, so the heading test is
    applied only when b starts with a capital. A heading is never followed by
    a lowercase continuation or ends in a hyphen. A block that starts with a
    list or note marker is a new item.
    """
    # "(Marlow 1980," / "240) creates" is a citation running on, not a list item.
    # Legal "Harlan" / "v. Pell County" runs on too.
    citation = a.rstrip().endswith(",") and re.match(r"\d{1,4}\)", b)
    if LIST_MARKER.match(b) and not citation and not re.match(r"v\. [A-Z]", b):
        return False
    if re.search(r"[A-Za-z0-9]-$", a):
        return True
    if not is_open_ended(a):
        return False
    if b[:1].islower():
        return True
    return not is_heading(a) and not is_heading(b)


def continues_within(a, b):
    """True if block a runs on into the next block b on the same page.

    Only a lowercase start counts: a new paragraph or heading never starts in
    lowercase, while "...as follows" / "First, ..." stays two paragraphs.
    """
    if LIST_MARKER.match(b) or not b[:1].islower():
        return False
    return bool(re.search(r"[A-Za-z0-9]-$", a)) or is_open_ended(a)


def join_across(a, b, ev, log, where, kind="page-join", marker=""):
    """Join block a to its continuation b, with marker (if any) at the seam."""
    if re.search(r"[A-Za-z0-9]-$", a):
        return join_hyphenated(a, b, ev, log, where, marker)
    lw, fw = last_alpha(a), first_alpha(b)
    seam = "...%s | %s..." % (a[-30:], b[:30])
    lower = b[:1].islower()
    lw_known = is_known(lw)
    first_known = bool(fw) and is_known(fw)
    joined_known = bool(fw) and ((lw + fw).lower() in ev.forms or is_known(lw + fw))
    if lower and joined_known and not (lw_known and first_known):
        _log(log, where, kind + "-midword", "%s -> %s" % (seam, lw + fw))
        return a + marker + b
    # A word break needs a known last word and a lowercase continuation;
    # anything else (a possible new paragraph, an unknown word) needs a look.
    certain = lower and lw_known and not joined_known
    _log(log, where, kind if certain else kind + "-uncertain", seam)
    return a + " " + (marker + " " if marker else "") + b


def join_pages(pages, ev=NO_EVIDENCE, log=None):
    """Flatten [(pdf_page, paragraphs)] into one paragraph list with page markers.

    The last block of a page merges with the first block of the next page when
    the first does not end a sentence. On the same page, a block merges with
    the previous one only when it starts in lowercase. Each join is logged
    with its page numbers.

    Every page with text gets a marker: on its own line above a paragraph
    that starts the page, or inline at the seam where a paragraph runs on
    from the previous page.
    """
    out = []
    prev_page = None
    for page_no, paras in pages:
        marker = PAGE_MARKER % page_no
        for i, b in enumerate(paras):
            a = strip_comments(out[-1]) if out else ""
            if i == 0 and out and continues_across(a, b):
                out[-1] = join_across(out[-1], b, ev, log, "%s-%s" % (prev_page, page_no), marker=marker)
                continue
            if i > 0 and continues_within(a, b):
                out[-1] = join_across(out[-1], b, ev, log, page_no, "block-join")
                continue
            if i == 0 and out and is_open_ended(a):
                _log(log, "%s-%s" % (prev_page, page_no), "page-break-unjoined",
                     "...%s | %s..." % (a[-30:], b[:30]))
            out.append(marker + "\n" + b if i == 0 else b)
        if paras:
            prev_page = page_no
    return out


# ---------------------------------------------------------------- Docling Markdown
#
# A .md file docling exported from a PDF. Docling writes one block per layout
# item, separated by blank lines: section headers as "## " lines (the title
# sometimes "# "), paragraphs as single lines, tables as GitHub pipe tables,
# list items as "- " lines, and pictures and formulas as placeholder comments.
# Text is HTML-escaped (&amp; &lt; &gt;) and Markdown-escaped (\_). Running
# heads and page numbers are normally left out, and there are no page numbers
# unless the export used a page-break placeholder. Footnotes are ordinary
# paragraphs in reading order, usually at the end of their page, and a
# paragraph that runs across a page can come out as two.

DEFAULT_PAGE_BREAK = "<!-- page break -->"
MD_PLACEHOLDERS = {"<!-- image -->": "image", "<!-- formula-not-decoded -->": "formula"}
MD_HEADING = re.compile(r"^#{1,6}\s+(.*?)(?:\s+#+)?$")
MD_IMAGE_LINK = re.compile(r"^!\[[^\]]*\]\([^)]*\)$")
MD_COMMENT = re.compile(r"^<!--.*-->$")
MD_TABLE_ROW = re.compile(r"^\|.*\|$")
MD_LIST_ITEM = re.compile(r"^(?:[-*+]|\d{1,3}[.)])\s+\S")
# One pass, so an escaped entity (&amp;lt;) is unescaped once. Only the
# backslash escapes docling writes for ordinary text characters are undone:
# it escapes "_", and some exporters escape * # [ ] < > & too. Every other
# backslash is source text ("\d+\.\d+", "\\server\share") and stays.
MD_UNESCAPE = re.compile(r"\\([_*#\[\]<>&])|&(?:#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);")
MD_EMPHASIS = re.compile(r"(?<![\\*\w])(\*\*?)(?=\S)(.+?)(?<=[^\s\\])\1(?![*\w])")
GLYPH = re.compile(r"GLYPH<[^>]*>")
# A paragraph that looks like a footnote when no footnote_pattern is set.
MD_FOOTNOTE_HINT = re.compile(r"^(?:\d{1,3}(?!\d)[.)]?|[¹²³⁰-⁹]+|[*†‡])\s*[A-Z“‘\"'(]")
# A paragraph or heading that starts with "#" or ">" (after any page-marker
# lines) reads as a Markdown heading or block quotation downstream.
MD_LEADING_MARKUP = re.compile(r"(?:<!--[^\n]*?-->\n)*(?=[#>])")
# Tables, list items, and numbered items never start a block quotation.
MD_ITEM_START = re.compile(r"^(?:\||[-*+]\s|\d{1,3}[.)]\s)")
# "pre- and post-war": a suspended hyphen, not a line break.
HYPHEN_SPACE = re.compile(r"(?<![\w-])([A-Za-z]+)- ([a-z]+)")
SUSPENDED_NEXT = {"and", "or", "nor", "to", "und"}
MD_TEXT_KINDS = ("heading", "para", "quote", "list", "table", "code")
FOOTNOTES_LABEL = "Notes to this chapter (printed as footnotes in the source):"


def md_unescape(text, table=False, log=None, where=None, underscores=None):
    """Undo docling's HTML entities and its Markdown backslash escapes.

    Only the backslash escapes MD_UNESCAPE lists are removed, and each one
    is logged ("unescaped", with the original and some context) when a log
    is given. An escaped underscore is common enough to flood the log, so
    when an underscores list is given each "\\_" is added to it as (where,
    context) instead, for one unescaped-underscores row per chapter. In a
    table row an escaped pipe stays escaped (a backslash before "|" is
    never removed), so the row keeps its cells.
    """
    def sub(m):
        if m.group(1) is not None:
            a, b = max(0, m.start() - 20), m.end() + 20
            if m.group(1) == "_" and underscores is not None:
                underscores.append((where, text[a:b]))
            else:
                _log(log, where, "unescaped", "%s -> %s in: %s" % (m.group(0), m.group(1), text[a:b]))
            return m.group(1)
        ch = html.unescape(m.group(0))
        return m.group(0) if table and ch == "|" else ch
    return MD_UNESCAPE.sub(sub, text)


def md_keep_leading_markup(text, log=None, where=None, quoted=False):
    """Put a backslash before a "#" or ">" that starts a paragraph's text.

    After unescaping ("\\#", "&gt;") such a paragraph would read as a
    heading or a block quotation downstream (the word counter drops "#"
    lines; the splitter treats ">" as a quotation); the backslash keeps it
    prose. Page-marker lines before the text are skipped, and so is the
    "> " of quoted text.
    """
    m = MD_LEADING_MARKUP.match(text[len(BLOCK_QUOTE_PREFIX):] if quoted else text)
    if m is None:
        return text
    k = m.end() + (len(BLOCK_QUOTE_PREFIX) if quoted else 0)
    _log(log, where, "leading-markup-kept", "backslash kept before %r: %s" % (text[k], strip_comments(text)[:60]))
    return text[:k] + "\\" + text[k:]


def md_parse(lines, page_break=DEFAULT_PAGE_BREAK):
    """Group a docling export's (line number, line) pairs into blocks.

    Returns dicts with kind (heading, para, quote, list, table, code, page,
    image, formula, comment), lines, and line (number of the first line).
    Blank lines end a block. A heading, placeholder, or comment line is a
    block of its own; consecutive table rows, quote lines, list items (with
    indented continuation lines), or text lines make one block; a fenced
    code block is kept whole.
    """
    blocks, cur = [], None

    def flush():
        nonlocal cur
        if cur is not None:
            blocks.append(cur)
        cur = None

    for no, ln in lines:
        s = ln.strip()
        if cur is not None and cur["kind"] == "code":
            cur["lines"].append(ln)
            if s.startswith("```"):
                flush()
            continue
        if s.startswith("```"):
            flush()
            cur = {"kind": "code", "lines": [ln], "line": no}
            continue
        if not s:
            flush()
            continue
        single = None
        if page_break and s == page_break:
            single = "page"
        elif s in MD_PLACEHOLDERS:
            single = MD_PLACEHOLDERS[s]
        elif MD_IMAGE_LINK.match(s):
            single = "image"
        elif MD_COMMENT.match(s):
            single = "comment"
        elif MD_HEADING.match(s):
            single = "heading"
        if single:
            flush()
            blocks.append({"kind": single, "lines": [s], "line": no})
            continue
        if MD_TABLE_ROW.match(s):
            kind = "table"
        elif s.startswith(">"):
            kind = "quote"
        elif MD_LIST_ITEM.match(s) or (cur is not None and cur["kind"] == "list" and ln[:1].isspace()):
            kind = "list"
        else:
            kind = "para"
        if cur is None or cur["kind"] != kind:
            flush()
            cur = {"kind": kind, "lines": [], "line": no}
        cur["lines"].append(ln if kind == "list" else s)
    flush()
    return blocks


def md_hyphen_spaces(text, cfg, ev, log=None, where=None):
    """Handle "popu- lation": a line-end hyphen docling kept, followed by a space.

    With the source's hyphen_spaces setting the fragments are joined by the
    hyphenation rules (hyphen-removed or hyphen-kept is logged); otherwise
    the text is kept as exported and each case is logged. A suspended
    hyphen ("pre- and post-war") is left alone.
    """
    def fix(m):
        stem, first = m.group(1), m.group(2)
        if first in SUSPENDED_NEXT:
            return m.group(0)
        if not cfg.get("hyphen_spaces"):
            _log(log, where, "hyphen-space-kept", m.group(0))
            return m.group(0)
        sep, basis = hyphen_decision(stem, first, ev)
        if sep:
            # A kept hyphen keeps its space: "long- versus short-term" is
            # text as printed, so it stays exactly as exported.
            _log(log, where, "hyphen-kept", "%s (%s; space after hyphen kept)" % (m.group(0), basis))
            return m.group(0)
        _log(log, where, "hyphen-removed", "%s -> %s (%s; space after hyphen)" % (m.group(0), stem + first, basis))
        return stem + first
    return HYPHEN_SPACE.sub(fix, text)


def md_block_texts(block, cfg, ev=NO_EVIDENCE, log=None, where=None, stats=None, underscores=None):
    """Return the chapter-text paragraph(s) for one docling block.

    A heading becomes its plain text (no "#" marks). A paragraph's lines are
    unescaped and joined. A quote block becomes one "> " paragraph per
    quoted paragraph. Table, list, and code blocks keep their lines; table
    rows are unescaped but not reflowed. U+FFFD and docling GLYPH<...>
    placeholders are logged. stats counts emphasis spans kept or stripped;
    underscores collects unescaped "\\_" (see md_unescape).
    """
    stats = Counter() if stats is None else stats
    kind, lines = block["kind"], block["lines"]

    def inline(s):
        if cfg.get("strip_emphasis"):
            s, n = MD_EMPHASIS.subn(r"\2", s)
            stats["stripped"] += n
        else:
            stats["kept"] += len(MD_EMPHASIS.findall(s))
        return md_unescape(s, log=log, where=where, underscores=underscores)

    def prose(group):
        return md_hyphen_spaces(join_lines([inline(s) for s in group], ev, log, where), cfg, ev, log, where)

    if kind == "heading":
        out = [inline(MD_HEADING.match(lines[0]).group(1)).strip()]
    elif kind == "table":
        out = ["\n".join(md_unescape(s.strip(), True, log, where, underscores) for s in lines)]
    elif kind == "code":
        out = ["\n".join(lines)]
    elif kind == "list":
        out = ["\n".join(md_hyphen_spaces(inline(s), cfg, ev, log, where) for s in lines)]
    elif kind == "quote":
        groups, cur = [], []
        for s in lines:
            s = re.sub(r"^(?:>\s?)+", "", s)
            if s.strip():
                cur.append(s)
            elif cur:
                groups.append(cur)
                cur = []
        if cur:
            groups.append(cur)
        out = [BLOCK_QUOTE_PREFIX + prose(g) for g in groups]
    elif kind == "para":
        out = [prose(lines)]
    else:
        out = [lines[0]]
    out = [t for t in out if t.strip()]
    for t in out:
        if "�" in t:
            _log(log, where, "replacement-char", t[:80])
        for m in GLYPH.finditer(t):
            _log(log, where, "glyph-placeholder", m.group(0))
    return out


MD_LIST_MARK = re.compile(r"^([-*+]|\d{1,3}[.)])\s")


def md_list_items(text):
    """Split a list block's text into its top-level items.

    An item starts at an unindented line with a list marker; indented lines
    (continuations and nested items) stay with the item above them.
    """
    items = []
    for ln in text.split("\n"):
        if not items or (not ln[:1].isspace() and MD_LIST_MARK.match(ln)):
            items.append([ln])
        else:
            items[-1].append(ln)
    return ["\n".join(i) for i in items]


def md_list_continues(first, second):
    """True if list items with markers second continue a list whose markers are first.

    A numbered list continues at the next number with the same delimiter
    ("1." then "2."); a bulleted one continues with the same bullet.
    """
    if not first or not second:
        return False
    a, b = first[-1], second[0]
    na, nb = re.match(r"^(\d+)([.)])$", a), re.match(r"^(\d+)([.)])$", b)
    if na or nb:
        return bool(na and nb) and na.group(2) == nb.group(2) and int(nb.group(1)) == int(na.group(1)) + 1
    return a == b


class MdSource:
    """A docling Markdown source: parsed once, with each chapter's block range."""

    def __init__(self, cfg, log=None):
        self.cfg, self.log = cfg, log
        with open(os.path.join(SOURCES, cfg["md"]), encoding="utf-8-sig") as f:
            text = f.read()
        numbered = []
        for no, ln in enumerate(text.splitlines(), 1):
            for fixed in apply_line_fixes([clean_txt_line(ln, cfg)], cfg, log, "line %d" % no):
                numbered.append((no, fixed))
        self.blocks = md_parse(numbered, cfg.get("page_break", DEFAULT_PAGE_BREAK))
        self.paged = any(b["kind"] == "page" for b in self.blocks)
        self._number_pages()
        for b in self.blocks:
            if b["kind"] != "heading":
                continue
            s = MD_HEADING.match(b["lines"][0]).group(1)
            if any(s.startswith(x) or md_unescape(s).startswith(x) for x in cfg.get("not_headings", [])):
                _log(log, self.where(b), "heading-demoted", s)
                b["kind"], b["lines"] = "para", [s]
        counts = Counter(w.lower() for _, ln in numbered for w in WORD.findall(md_unescape(ln)))
        self.ev = DocEvidence(counts)
        self.ev.hyphenates = cfg.get("hyphenates", True)
        self.ev.counts = counts
        self._plain = {}
        self.bounds = self._find_bounds(cfg["chapters"])
        self._log_bounds(cfg["chapters"])
        self._check_empty(cfg["chapters"])

    def _number_pages(self):
        cfg = self.cfg
        skip = set(cfg.get("skip_pages", []))
        page = cfg.get("first_page", 1)
        while page in skip:
            page += 1
        for b in self.blocks:
            if b["kind"] == "page":
                page += 1
                while page in skip:
                    page += 1
            b["page"] = page if self.paged else None
        if not self.paged:
            _log(self.log, None, "no-page-markers", "%s: no %r placeholder lines; chapters get no page markers"
                 % (cfg["md"], cfg.get("page_break", DEFAULT_PAGE_BREAK)))
        elif cfg.get("last_page") not in (None, page):
            _log(self.log, None, "page-count-mismatch", "page breaks count to page %d, last_page is %d"
                 % (page, cfg["last_page"]))

    def where(self, block):
        return block["page"] if self.paged else "line %d" % block["line"]

    def plain(self, i):
        """Text of block i for matching chapter bounds (headings and paragraphs only)."""
        if i not in self._plain:
            b = self.blocks[i]
            texts = md_block_texts(b, self.cfg, self.ev) if b["kind"] in ("heading", "para") else []
            self._plain[i] = texts[0] if texts else ""
        return self._plain[i]

    def _starts(self, i, prefix):
        b = self.blocks[i]
        return b["kind"] in MD_TEXT_KINDS and (b["lines"][0].strip().startswith(prefix) or self.plain(i).startswith(prefix))

    def _is_form(self, i, forms):
        pn = headnorm(self.plain(i))
        return bool(pn) and (pn in forms or re.sub(r"(?<=[a-z])\d{1,3}$", "", pn) in forms)

    def _hits(self, ch, frm):
        """Blocks at or after frm that match ch's start: (indexes, description, matched a paragraph)."""
        n = len(self.blocks)
        if ch.get("first_line"):
            what = "first_line %r" % ch["first_line"]
            return [i for i in range(frm, n) if self._starts(i, ch["first_line"])], what, False
        if ch.get("heading"):
            what, forms = "heading %r" % ch["heading"], {headnorm(ch["heading"])}
        else:
            what = "heading %r" % ch["title"]
            full = heading_forms(ch["title"], ch.get("num"), ch.get("title_alt"))
            # A bare number heading starts a chapter only just above its title.
            forms = (full - heading_forms("", ch.get("num"))) or full
        hits = [i for i in range(frm, n) if self.blocks[i]["kind"] == "heading" and self._is_form(i, forms)]
        if hits:
            return hits, what, False
        return [i for i in range(frm, n) if self.blocks[i]["kind"] == "para" and self._is_form(i, forms)], what, True

    def _find_start(self, ch, frm):
        n = len(self.blocks)
        hits, what, para = self._hits(ch, frm)
        if hits and para:
            _log(self.log, self.where(self.blocks[hits[0]]), "chapter-start-not-heading",
                 "%s: %s matched a paragraph, not a heading line" % (ch["unit_id"], what))
        occ = ch.get("occurrence", 1)
        if len(hits) < occ:
            after = self.blocks[frm]["line"] if frm < n else "end"
            raise SystemExit("%s: %s (occurrence %d) not found at or after line %s of %s"
                             % (ch["unit_id"], what, occ, after, self.cfg["md"]))
        i = hits[occ - 1]
        if not ch.get("first_line"):
            # Take in a bare number ("## 2", or a "2" paragraph) above the
            # title, stepping over placeholders, comments, and page breaks.
            nums = heading_forms("", ch.get("num"))
            j = i - 1
            while j >= frm:
                kind = self.blocks[j]["kind"]
                if kind in ("heading", "para") and self._is_form(j, nums):
                    i = j
                elif kind not in ("image", "formula", "comment", "page"):
                    break
                j -= 1
        return i, [h for h in hits if h != hits[occ - 1]]

    def _find_bounds(self, chapters):
        starts, others, frm = [], [], 0
        for ch in chapters:
            i, rest = self._find_start(ch, frm)
            starts.append(i)
            others.append(rest)
            frm = i + 1
        # Every place each chapter's start matches, for chapter-start-inside.
        everywhere = [self._hits(ch, 0)[0] for ch in chapters]
        bounds = {}
        n = len(self.blocks)
        for k, ch in enumerate(chapters):
            a = starts[k]
            nxt = starts[k + 1] if k + 1 < len(chapters) else n
            if ch.get("stop_line"):
                b = next((i for i in range(a + 1, n) if self._starts(i, ch["stop_line"])), None)
                if b is None:
                    raise SystemExit("%s: stop_line %r not found after its start" % (ch["unit_id"], ch["stop_line"]))
                if b > nxt:
                    raise SystemExit("%s: stop_line %r falls after the next chapter's start" % (ch["unit_id"], ch["stop_line"]))
            else:
                b = nxt
            ambiguous = [self.blocks[i]["line"] for i in others[k] if a < i < b]
            inside = [(other["unit_id"], self.blocks[i]["line"]) for j, other in enumerate(chapters) if j != k
                      for i in everywhere[j] if a < i < b]
            bounds[ch["unit_id"]] = (a, b, ambiguous, k + 1 == len(chapters) and not ch.get("stop_line"), inside)
        self._log_outside([bounds[ch["unit_id"]][:2] for ch in chapters])
        return bounds

    def _log_outside(self, ranges):
        """Log each stretch of text that falls in no chapter (outside-chapters)."""
        gaps, pos = [], 0
        for a, b in sorted(ranges):
            if a > pos:
                gaps.append((pos, a))
            pos = max(pos, b)
        gaps.append((pos, len(self.blocks)))
        unit = self.log.unit if self.log is not None else ""
        if self.log is not None:
            self.log.unit = ""
        for a, b in gaps:
            texts = [t for blk in self.blocks[a:b] if blk["kind"] in MD_TEXT_KINDS
                     for t in md_block_texts(blk, self.cfg, self.ev)]
            # The project's word count: table pipes and separator rows are not words.
            words = words_in_text("\n\n".join(texts))
            if not words:
                continue
            last = self.blocks[b - 1]
            first = " ".join(" ".join(texts).split()[:12])
            span = "lines %d-%d" % (self.blocks[a]["line"], last["line"] + len(last["lines"]) - 1)
            if self.paged:
                span += " (pages %s-%s)" % (self.blocks[a]["page"], last["page"])
            _log(self.log, self.where(self.blocks[a]), "outside-chapters",
                 "%s, %d words left out: %s..." % (span, words, first))
        if self.log is not None:
            self.log.unit = unit

    def _log_bounds(self, chapters):
        """Log each chapter's bound warnings (ambiguous start, another start inside, runs to end of file).

        Logged once, when the source is read, so they are in the log even
        when an empty chapter stops the run before any chapter is written.
        """
        log = self.log
        unit = log.unit if log is not None else ""
        for ch in chapters:
            if log is not None:
                log.unit = ch["unit_id"]
            _, _, ambiguous, to_eof, inside = self.bounds[ch["unit_id"]]
            for line in ambiguous:
                _log(log, None, "chapter-start-ambiguous", "the start heading also matches line %d, inside this chapter" % line)
            for uid, line in inside:
                _log(log, None, "chapter-start-inside", "the start of %s also matches line %d, inside this chapter; "
                     "check occurrence (a contents page may have matched)" % (uid, line))
            if to_eof:
                _log(log, None, "chapter-end-of-file", "last chapter runs to the end of %s; set stop_line to leave out back matter" % self.cfg["md"])
        if log is not None:
            log.unit = unit

    def _check_empty(self, chapters):
        """Stop if any chapter has no body words, before any chapter file is written.

        Each chapter is assembled once without logging. Paragraphs that are
        only a bare number (a contents page's page numbers, "1" and "9", or
        other furniture candidates) do not count as body words. Moved
        footnotes do not count either.
        """
        saved, self.log = self.log, None
        empty = []
        try:
            for ch in chapters:
                paras = self._assemble(self._items(ch))
                body = paras[:paras.index(FOOTNOTES_LABEL)] if FOOTNOTES_LABEL in paras else paras
                texts = [strip_comments(p).strip() for p in body]
                if not words_in_text("\n\n".join(t for t in texts if not PAGE_NUM_LINE.match(t))):
                    a, b = self.bounds[ch["unit_id"]][:2]
                    end = self.blocks[b - 1]["line"] if b > a else self.blocks[a]["line"]
                    only = " (only bare numbers)" if words_in_text("\n\n".join(texts)) else ""
                    empty.append("%s: no body words%s between lines %d and %d of %s"
                                 % (ch["unit_id"], only, self.blocks[a]["line"], end, self.cfg["md"]))
        finally:
            self.log = saved
        if empty:
            raise SystemExit("\n".join(empty) + "\nThe start matched the wrong place (a contents page?) or the next "
                             "chapter starts too early. Check occurrence, which counts from just after the previous "
                             "chapter's start; the repair log's chapter-start-inside and outside-chapters rows show "
                             "where the headings matched. No chapter file was written.")

    def _is_furniture(self, it):
        if it["kind"] not in ("heading", "para"):
            return False
        t = it["text"]
        heads = [re.compile(p) for p in self.cfg.get("header_patterns", [])]
        junk = JUNK_LINES | {norm(j) for j in self.cfg.get("junk_lines", [])}
        return norm(t) in junk or _matches(t, heads) or any(p.match(t) for p in STAMP_PATTERNS)

    def _at_page_end(self, items, k, fpat):
        """True if only footnotes, furniture, and placeholders follow item k on its page."""
        for it in items[k + 1:]:
            if it["kind"] == "page":
                return True
            if it["kind"] in ("image", "formula", "comment") or it.get("note_list") or self._is_furniture(it):
                continue
            if it["kind"] == "para" and fpat is not None and fpat.match(it["text"]):
                continue
            return False
        return True

    def chapter(self, ch):
        """Paragraphs of one chapter, with page markers and a notes block of moved footnotes."""
        log = self.log
        if log is not None:
            log.unit = ch["unit_id"]
        stats, underscores = Counter(), []
        paras = self._assemble(self._items(ch, stats, underscores))
        if stats["kept"]:
            _log(log, None, "emphasis-kept", "%d *italic* or **bold** spans kept as Markdown (strip_emphasis removes them)" % stats["kept"])
        if stats["stripped"]:
            _log(log, None, "emphasis-stripped", "%d emphasis spans" % stats["stripped"])
        if underscores:
            places = [w for w, _ in underscores]
            span = places[0] if places[0] == places[-1] else "%s to %s" % (places[0], places[-1])
            _log(log, places[0], "unescaped-underscores", "%d \\_ -> _ (%s), e.g. in: %s" % (
                len(underscores), span, " | ".join(c for _, c in underscores[:3])))
        return paras

    def _items(self, ch, stats=None, underscores=None):
        """A chapter's blocks as items (kind, text, page, where), its heading stripped.

        A list block also carries its top-level items (list_items) and their
        markers (list_marks), so a block of list-style footnotes can be split.
        """
        cfg, log = self.cfg, self.log
        a, b = self.bounds[ch["unit_id"]][:2]
        items = []
        for blk in self.blocks[a:b]:
            where = self.where(blk)
            if blk["kind"] in MD_TEXT_KINDS:
                texts = md_block_texts(blk, cfg, self.ev, log, where, stats, underscores)
            else:
                texts = [blk["lines"][0]]
            for t in texts:
                it = {"kind": blk["kind"], "text": t, "page": blk["page"], "where": where}
                if blk["kind"] == "list":
                    it["list_items"] = md_list_items(t)
                    marks = [MD_LIST_MARK.match(x.lstrip()) for x in it["list_items"]]
                    it["list_marks"] = [m.group(1) if m else "" for m in marks]
                items.append(it)
        if not ch.get("first_line"):
            items = self._strip_heading(items, ch)
        return items

    def _strip_heading(self, items, ch):
        idx = [k for k, it in enumerate(items) if it["kind"] in ("heading", "para")][:MAX_HEADING_BLOCKS]
        if not idx:
            return items
        alt = list(ch.get("title_alt") or []) + ([ch["heading"]] if ch.get("heading") else [])
        kept = strip_chapter_heading([items[k]["text"] for k in idx], ch["title"], ch.get("num"),
                                     self.log, items[idx[0]]["where"], alt)
        drop = set(idx[:len(idx) - len(kept)])
        return [it for k, it in enumerate(items) if k not in drop]

    def _assemble(self, items):
        """Turn a chapter's items into paragraphs: drop, move, join, and mark pages.

        Placeholders, running heads, and footnotes (including list blocks of
        footnotes, split by _list_footnotes) are taken out of the body.
        Where any of them, or a page break, came between two body paragraphs,
        the paragraphs are joined by the page-break rules (continues_across);
        with nothing between them, only a lowercase continuation is joined
        (continues_within). Every page with body text gets a page marker, on
        its own line above a paragraph that starts the page or inline at the
        seam of a join. Moved footnotes follow the body under FOOTNOTES_LABEL,
        each after a comment naming its page. Across such a seam, blocks
        that are not both paragraphs go to _across_break, and so do a list
        and a lowercase paragraph right after it, or (in an export without
        page breaks) any such pair (_seamless_break); a paragraph that a
        kept table separates from the paragraph it continues is logged
        (_log_around_tables). An unjoined seam with no page break in it is
        logged as block-unjoined. Docling heading lines are passed to
        mark_block_quotes as heads, so they are never quoted.
        """
        cfg, log, ev = self.cfg, self.log, self.ev
        fpat = re.compile(cfg["footnote_pattern"]) if cfg.get("footnote_pattern") else None
        page_end_only = self.paged and cfg.get("footnotes_at_page_end", True)
        # List blocks of footnotes ("1. Minutes...", "* Not in...") become one
        # footnote paragraph per item, so they move and the paragraph they
        # interrupted can rejoin.
        items = self._list_footnotes(items, fpat, page_end_only)
        out, notes, seam, marked = [], [], [], None
        for k, it in enumerate(items):
            kind, text, where, page = it["kind"], it["text"], it["where"], it["page"]
            if kind == "page":
                seam.append("page break")
                continue
            if kind in ("image", "formula"):
                before = strip_comments(out[-1]["text"])[-50:] if out else ""
                _log(log, where, kind + "-placeholder", "%s after: ...%s" % (text, before))
                seam.append(kind)
                continue
            if kind == "comment":
                _log(log, where, "comment-dropped", text)
                continue
            if kind == "code":
                _log(log, where, "code-block", text[:80])
            if self._is_furniture(it):
                _log(log, where, "furniture-dropped", text)
                seam.append("running head")
                continue
            from_list = it.get("from_list", False)
            if kind == "para" and fpat is not None and (from_list or fpat.match(text)):
                if from_list or not page_end_only or self._at_page_end(items, k, fpat):
                    notes.append(dict(it, text=md_keep_leading_markup(text, log, where)))
                    no_evidence = "footnotes_at_page_end is False" if self.paged else "no page breaks"
                    if from_list:
                        _log(log, where, "footnote-moved-from-list", "%s (a docling list item%s; review)" % (
                            text[:80], "" if page_end_only else ", moved with no page end to confirm it: " + no_evidence))
                    elif page_end_only:
                        _log(log, where, "footnote-moved", text[:80])
                    else:
                        _log(log, where, "footnote-moved-no-page-evidence", "%s (%s; review)" % (text[:80], no_evidence))
                    if is_open_ended(text):
                        _log(log, where, "footnote-open-ended", "...%s" % text[-50:])
                    seam.append("footnote")
                    continue
                _log(log, where, "footnote-candidate", "matches footnote_pattern but is not at a page end (kept): %s" % text[:80])
            elif fpat is None and (kind == "para" or kind == "list" and len(it["list_items"]) == 1) and MD_FOOTNOTE_HINT.match(text):
                _log(log, where, "footnote-candidate", "set footnote_pattern if this is a note: %s" % text[:80])
            if kind == "para" and PAGE_NUM_LINE.match(text):
                _log(log, where, "furniture-candidate", "bare number kept: %s" % text)
            marker = PAGE_MARKER % page if self.paged and page != marked else ""
            prev = out[-1] if out else None
            at = "%s-%s" % (prev["end"], page) if prev is not None and self.paged and prev["end"] != page else where
            joined = None
            if kind == "para" and prev is not None and prev["kind"] == "para":
                a = strip_comments(prev["text"])
                if seam:
                    if continues_across(a, text):
                        joined = join_across(prev["text"], text, ev, log, at, "page-break-joined", marker)
                    elif is_open_ended(a):
                        _log(log, at, self._unjoined_kind(seam), "...%s | %s... (across %s)" % (a[-30:], text[:30], ", ".join(seam)))
                elif continues_within(a, text):
                    joined = join_across(prev["text"], text, ev, log, at, "block-join", marker)
                elif (not self.paged and is_open_ended(a) and not is_heading(a) and not is_heading(text)
                        and not LIST_MARKER.match(text)):
                    _log(log, at, "page-break-unjoined", "...%s | %s... (no page evidence)" % (a[-30:], text[:30]))
            elif prev is not None and (seam or self._seamless_break(prev, kind, text)):
                joined = self._across_break(prev, kind, text, at, marker, seam)
            if joined is None and kind == "para" and prev is not None and prev["kind"] == "table":
                self._log_around_tables(out, text, page, where)
            if joined is not None:
                prev["text"], prev["end"] = joined, page
                marked = page if marker else marked
                seam = []
                continue
            if kind == "heading":
                _log(log, where, "section-heading", text)
            if kind == "quote":
                _log(log, where, "blockquote-source", text[2:62])
            if kind in ("para", "heading", "quote"):
                text = md_keep_leading_markup(text, log, where, quoted=kind == "quote")
            out.append({"kind": kind, "text": (marker + "\n" if marker else "") + text, "end": page})
            marked = page if marker else marked
            seam = []
        bq, fixes = cfg.get("block_quotes", False), cfg.get("block_quote_fixes")
        paras = [o["text"] for o in out]
        if bq:
            heads = {k for k, o in enumerate(out) if o["kind"] == "heading"}
            paras = [_single_quote_prefix(p) for p in mark_block_quotes(paras, log, fixes, MD_ITEM_START, heads)]
        note_paras = [("<!-- footnote on page %d -->\n" % n["page"] if self.paged else "") + n["text"] for n in notes]
        if note_paras:
            if bq:
                note_paras = [_single_quote_prefix(p) for p in mark_block_quotes(note_paras, log, fixes, fpat)]
            paras += [FOOTNOTES_LABEL] + note_paras
        return paras

    def _seamless_break(self, prev, kind, text):
        """True if blocks with nothing between them, not both paragraphs, still go to _across_break.

        A list followed directly by a lowercase paragraph may be one item
        run on (in an export without page breaks, a list item split across
        a page looks exactly like this), so it goes there to be joined. In
        an export without page breaks, any other pair may also straddle a
        page, so it goes there to be logged as page-break-unjoined if the
        first is open-ended, as paragraph pairs are: not when the second is
        a heading, a list, or heading-like, or starts with a list marker.
        The heading-like test on the first block is made in _across_break.
        """
        if prev["kind"] == "list" and kind == "para" and text[:1].islower() and not LIST_MARKER.match(text):
            return True
        if self.paged or kind in ("heading", "list"):
            return False
        return kind == "table" or not (is_heading(text) or LIST_MARKER.match(text))

    def _unjoined_kind(self, seam):
        """page-break-unjoined across a page break (or where page breaks are unknown), else block-unjoined."""
        return "page-break-unjoined" if "page break" in seam or not self.paged else "block-unjoined"

    def _neighbor(self, items, k, step, fpat):
        """The nearest body item before (step -1) or after (step 1) item k.

        Page breaks, placeholders, comments, running heads, footnote
        paragraphs, and list blocks already taken as footnotes are skipped.
        """
        j = k + step
        while 0 <= j < len(items):
            x = items[j]
            skip = (x["kind"] in ("page", "image", "formula", "comment") or x.get("note_list")
                    or (x["kind"] == "para" and fpat is not None and fpat.match(x["text"]))
                    or self._is_furniture(x))
            if not skip:
                return x
            j += step
        return None

    def _body_list(self, items, k, fpat):
        """Why list item k reads as a body list rather than footnotes ("" if it does not).

        It does when it continues the list before it, the list after it
        (past any page break) continues it, the block before it is a
        lead-in ending with a colon, or its last item is open-ended and the
        next body block (past any page break) is a lowercase paragraph that
        continues it ("1. the board would meet and" / "vote on the dues.").
        That last test is skipped when the body block before the list is
        itself open-ended and also runs on into that paragraph: then the
        list more likely holds a note that interrupted a body paragraph,
        and the paragraph rejoins once the note moves. A real note that
        runs on to the next page is followed there by body text, which
        rarely starts in lowercase, so it still moves (footnote-open-ended).
        """
        it = items[k]
        prev, nxt = self._neighbor(items, k, -1, fpat), self._neighbor(items, k, 1, fpat)
        if prev is not None and prev["kind"] == "list" and md_list_continues(prev["list_marks"], it["list_marks"]):
            return "it continues the list before it"
        if nxt is not None and nxt["kind"] == "list" and md_list_continues(it["list_marks"], nxt["list_marks"]):
            return "the list continues after it"
        if prev is not None and strip_comments(prev["text"]).rstrip().endswith(":"):
            return "the block before it ends with a colon"
        if nxt is not None and nxt["kind"] == "para" and nxt["text"][:1].islower():
            last = strip_comments(it["list_items"][-1]).rstrip().split("\n")[-1].strip()
            if is_open_ended(last) and continues_across(last, nxt["text"]):
                before = strip_comments(prev["text"]).strip() if prev is not None and prev["kind"] == "para" else ""
                if not (before and continues_across(before, nxt["text"])):
                    return "the paragraph after it continues its last item"
        return ""

    def _list_footnotes(self, items, fpat, page_end_only):
        """Split list blocks of footnotes into one footnote paragraph per item.

        Docling often exports a page's footnotes ("1. Minutes...", "2. ...",
        or "* Not in...") as a list block. A list block whose every item
        matches footnote_pattern is taken as footnotes when it is at a page
        end (or, with no page evidence, anywhere), unless it reads as a body
        list (_body_list); each item becomes a paragraph marked from_list,
        which _assemble moves and logs as footnote-moved-from-list. A
        matching list that stays is logged as footnote-candidate, and so is
        a page-end list that does not match the pattern but looks like
        footnotes (MD_FOOTNOTE_HINT). Blocks are decided from the last to
        the first, so a footnote list counts as part of the page end for the
        blocks before it.
        """
        log, ev = self.log, self.ev
        items = [dict(it) for it in items]
        for k in range(len(items) - 1, -1, -1):
            it = items[k]
            if it["kind"] != "list":
                continue
            firsts = [e.split("\n")[0].strip() for e in it["list_items"]]
            at_end = self._at_page_end(items, k, fpat)
            if fpat is None or not all(fpat.match(f) for f in firsts):
                if (fpat is not None and page_end_only and at_end
                        and all(MD_FOOTNOTE_HINT.match(f) for f in firsts) and not self._body_list(items, k, fpat)):
                    _log(log, it["where"], "footnote-candidate", "list at a page end looks like footnotes but does "
                         "not match footnote_pattern (kept): %s" % it["text"][:80])
                continue
            if page_end_only and not at_end:
                _log(log, it["where"], "footnote-candidate", "list matches footnote_pattern but is not at a page "
                     "end (kept as a list): %s" % it["text"][:80])
                continue
            why = self._body_list(items, k, fpat)
            if why:
                _log(log, it["where"], "footnote-candidate", "list matches footnote_pattern but %s (kept as a "
                     "list): %s" % (why, it["text"][:80]))
                continue
            it["note_list"] = True
        out = []
        for it in items:
            if not it.get("note_list"):
                out.append(it)
                continue
            for entry in it["list_items"]:
                text = join_lines([ln.strip() for ln in entry.split("\n") if ln.strip()], ev, log, it["where"])
                out.append(dict(it, kind="para", text=text, from_list=True))
        return out

    def _log_around_tables(self, out, text, page, where):
        """Log a paragraph that a kept table (or tables) split from the paragraph it continues.

        The paragraphs are not joined, since that would move the table; the
        seam is logged as block-unjoined (page-break-unjoined if a page
        break also falls between them, or the export has no page breaks).
        """
        j = len(out) - 1
        while j >= 0 and out[j]["kind"] == "table":
            j -= 1
        if j < 0 or out[j]["kind"] != "para":
            return
        a = strip_comments(out[j]["text"])
        if not continues_across(a, text):
            return
        crossed = self.paged and out[j]["end"] != page
        at = "%s-%s" % (out[j]["end"], page) if crossed else where
        _log(self.log, at,self._unjoined_kind(["page break"] if crossed else []),
             "...%s | %s... (across a table)" % (a[-30:], text[:30]))

    def _across_break(self, prev, kind, text, at, marker, seam):
        """Join or log a seam between blocks that are not both paragraphs.

        A seam is a page break or anything removed between the blocks (a
        footnote, running head, or placeholder), on the same page or not.
        The seam may also be empty (_seamless_break): a list run on by a
        lowercase paragraph, or, in an export without page breaks, any
        pair that might straddle a page.
        A list whose last item is open-ended, followed by a lowercase
        paragraph, is joined (list-page-joined). Otherwise an open-ended
        block before the seam (a paragraph, list item, quotation, or code
        line; a table only when a table follows) is logged as
        page-break-unjoined, or block-unjoined when the seam has no page
        break. A heading is never open-ended here; with an empty seam,
        neither is a heading-like line. Returns the joined text, or None.
        """
        log, ev = self.log, self.ev
        body = strip_comments(prev["text"]).rstrip()
        lines = body.split("\n")
        if prev["kind"] == "code":
            lines = [ln for ln in lines if not ln.strip().startswith("```")] or [""]
        tail = lines[-1].strip()
        if prev["kind"] == "quote":
            tail = tail[len(BLOCK_QUOTE_PREFIX):] if tail.startswith(BLOCK_QUOTE_PREFIX) else tail
        hyphen = bool(re.search(r"[A-Za-z0-9]-$", tail))
        across = "across " + ", ".join(seam) if seam else "no page evidence"
        seam_text = "...%s | %s... (%s, then %s, %s)" % (tail[-30:], text[:30], prev["kind"], kind, across)
        if prev["kind"] == "table":
            if kind == "table":
                _log(log, at, self._unjoined_kind(seam), seam_text + "; a table may continue")
            return None
        if prev["kind"] == "heading" or not (hyphen or is_open_ended(tail)):
            return None
        if (prev["kind"] == "list" and kind == "para" and text[:1].islower()
                and not LIST_MARKER.match(text)):
            return join_across(prev["text"], text, ev, log, at, "list-page-joined", marker)
        if not seam and is_heading(tail):
            return None
        _log(log, at, self._unjoined_kind(seam), seam_text)
        return None


def _single_quote_prefix(para):
    """Collapse "> > " (a source quotation the detector marked again) to "> "."""
    return re.sub(r"^((?:<!--[^\n]*?-->\n)*)> > ", r"\1> ", para)


def make_md_extractor(cfg, log=None):
    src = MdSource(cfg, log)
    print("%s: %d blocks, %s" % (cfg["md"], len(src.blocks), "page breaks found" if src.paged else "no page breaks"))
    return src.chapter


def save_md_raw(cfg):
    """Save the docling export, before any cleanup, to Work/Raw/{slug}/raw.txt."""
    folder = os.path.join(RAW, cfg["slug"])
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "raw.txt")
    with open(os.path.join(SOURCES, cfg["md"]), encoding="utf-8-sig") as f:
        text = f.read()
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return path


def make_extractor(cfg, log=None):
    path = os.path.join(SOURCES, cfg["pdf"])
    with pymupdf.open(path) as doc:
        ev = DocEvidence.from_doc(doc, cfg.get("hyphenates"))
    print("%s: %d of %d settled line-end hyphens are word breaks; hyphenates=%s"
          % (cfg["pdf"], ev.breaks, ev.settled, ev.hyphenates))

    def extractor(ch):
        if log is not None:
            log.unit = ch["unit_id"]
        pages = []
        with pymupdf.open(path) as doc:
            for p in range(ch["start"] - 1, ch["end"]):
                paras = block_paragraphs(doc[p], cfg["header_ymax"], cfg["footer_ymin"], ev, log, cfg.get("space_repair"))
                pages.append((p + 1, paras))
        first = next((i for i, (_, paras) in enumerate(pages) if paras), None)
        if first is not None:
            no, paras = pages[first]
            pages[first] = (no, strip_chapter_heading(paras, ch["title"], ch.get("num"), log, no, ch.get("title_alt")))
        return join_pages(pages, ev, log)

    return extractor


def validate_config(cfg):
    errors = []
    src = cfg.get("slug") or cfg.get("pdf") or cfg.get("epub") or cfg.get("txt") or cfg.get("md")
    if not cfg.get("slug"):
        errors.append("source %r has no slug" % (cfg.get("pdf") or cfg.get("epub") or cfg.get("txt") or cfg.get("md")))
    epub = bool(cfg.get("epub"))
    md = bool(cfg.get("md"))
    seen = set()
    for ch in cfg["chapters"]:
        uid = ch.get("unit_id")
        if not uid:
            errors.append("%s: chapter %r has no unit_id" % (src, ch.get("title")))
        elif uid in seen:
            errors.append("%s: duplicate unit_id %r" % (src, uid))
        seen.add(uid)
        if not ch.get("slug"):
            errors.append("%s: chapter %r has no filename slug" % (src, uid))
        if epub:
            if not ch.get("file"):
                errors.append("%s: chapter %r has no EPUB file" % (src, uid))
        elif md:
            if "start" in ch or "end" in ch:
                errors.append("%s: chapter %r: Markdown chapters are bounded by heading, first_line, "
                              "and stop_line, not start/end pages" % (src, uid))
            if not (ch.get("title") or ch.get("heading") or ch.get("first_line") or ch.get("num") is not None):
                errors.append("%s: chapter %r has no title, heading, num, or first_line to find its start" % (src, uid))
        elif ch["end"] < ch["start"]:
            errors.append("%s: chapter %r ends before it starts" % (src, uid))
    return errors


def save_raw(cfg):
    """Save every page's text, before any cleanup, to Work/Raw/{slug}/raw.txt.

    Pages are separated by the same markers the chapter files use, so any
    repair can be checked against what the PDF text layer gave.
    """
    folder = os.path.join(RAW, cfg["slug"])
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "raw.txt")
    with pymupdf.open(os.path.join(SOURCES, cfg["pdf"])) as doc:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for page in doc:
                f.write(PAGE_MARKER % (page.number + 1) + "\n" + page.get_text("text") + "\n")
    return path


def build_markdown(src_title, part, chapters, extractor, slug, pdf=""):
    folder = os.path.join(OUT, slug)
    os.makedirs(folder, exist_ok=True)
    total_out = 0
    for idx, ch in enumerate(chapters, 1):
        paras = extractor(ch)
        body = "\n\n".join(paras) + "\n"
        wc = words_in_text(body)
        total_out += wc
        if "start" in ch:
            pages = "%d-%d" % (ch["start"], ch["end"])
        else:
            marks = [int(n) for n in re.findall(r"<!-- page (\d+) -->", body)]
            pages = "%d-%d" % (min(marks), max(marks)) if marks else ""
        fname = "%02d-%s.md" % (idx, ch["slug"])
        label = ch.get("num")
        fields = [
            ("source", src_title or pdf),
            ("source_slug", slug),
            ("unit_id", ch["unit_id"]),
            ("part", part),
            ("chapter", None if label is None else str(label)),
            ("title", ch["title"]),
            ("pdf_pages", pages),
            ("printed_pages", ch.get("printed_pages", "")),
            ("word_count", wc),
        ]
        front = "---\n" + "".join("%s: %s\n" % (k, yaml_value(v)) for k, v in fields) + "---\n\n"
        front += "# %s\n\n" % ch["title"]
        # newline="\n" keeps byte sizes identical on Windows and elsewhere.
        with open(os.path.join(folder, fname), "w", encoding="utf-8", newline="\n") as f:
            f.write(front + body)
        print("%-4s %-6d %s" % (part, wc, fname))
    print("TOTAL part %d: %d words" % (part, total_out))


def build_md_source(cfg):
    """Extract a docling Markdown source: raw copy, chapter files, and repairs.tsv.

    If reading the source stops the run (an empty chapter, a start heading
    not found), the repair log so far is still written, since its
    outside-chapters and chapter-start-inside rows explain the error.
    """
    print("raw text -> %s" % save_md_raw(cfg))
    log = RepairLog()
    log_path = os.path.join(RAW, cfg["slug"], "repairs.tsv")
    try:
        build_markdown(cfg["title"], cfg["part"], cfg["chapters"], make_md_extractor(cfg, log), cfg["slug"], cfg["md"])
    except SystemExit:
        log.write(log_path)
        print("repair log (run stopped): %d entries -> %s" % (len(log.rows), log_path))
        raise
    for kind, prefix in check_block_quote_fixes(cfg, os.path.join(OUT, cfg["slug"])):
        print("WARNING block_quote_fixes %s matches no paragraph: %r" % (kind, prefix))
    log.write(log_path)
    print("repair log: %d entries -> %s" % (len(log.rows), log_path))


if __name__ == "__main__":
    ran = False
    only = set(sys.argv[1:])  # optional: slugs to extract; default all
    for cfg in SOURCES_CONFIG:
        if only and cfg.get("slug") not in only:
            continue
        if cfg.get("txt"):
            if not cfg["chapters"]:
                continue
            problems = validate_config(cfg)
            if problems:
                raise SystemExit("SOURCES_CONFIG errors:\n  " + "\n  ".join(problems))
            ran = True
            print("raw text -> %s" % save_txt_raw(cfg))
            log = RepairLog()
            build_markdown(cfg["title"], cfg["part"], cfg["chapters"], make_txt_extractor(cfg, log), cfg["slug"], cfg["txt"])
            for kind, prefix in check_block_quote_fixes(cfg, os.path.join(OUT, cfg["slug"])):
                print("WARNING block_quote_fixes %s matches no paragraph: %r" % (kind, prefix))
            log_path = os.path.join(RAW, cfg["slug"], "repairs.tsv")
            log.write(log_path)
            print("repair log: %d entries -> %s" % (len(log.rows), log_path))
            continue
        if cfg.get("md"):
            if not cfg["chapters"]:
                continue
            problems = validate_config(cfg)
            if problems:
                raise SystemExit("SOURCES_CONFIG errors:\n  " + "\n  ".join(problems))
            ran = True
            build_md_source(cfg)
            continue
        if cfg.get("epub"):
            if not cfg["chapters"]:
                continue
            problems = validate_config(cfg)
            if problems:
                raise SystemExit("SOURCES_CONFIG errors:\n  " + "\n  ".join(problems))
            ran = True
            print("raw text -> %s" % save_epub_raw(cfg))
            log = RepairLog()
            build_markdown(cfg["title"], cfg["part"], cfg["chapters"], make_epub_extractor(cfg, log), cfg["slug"], cfg["epub"])
            log_path = os.path.join(RAW, cfg["slug"], "repairs.tsv")
            log.write(log_path)
            print("repair log: %d entries -> %s" % (len(log.rows), log_path))
            continue
        if not cfg["pdf"] or not cfg["chapters"]:
            continue
        problems = validate_config(cfg)
        if problems:
            raise SystemExit("SOURCES_CONFIG errors:\n  " + "\n  ".join(problems))
        ran = True
        print("raw text -> %s" % save_raw(cfg))
        log = RepairLog()
        build_markdown(cfg["title"], cfg["part"], cfg["chapters"], make_extractor(cfg, log), cfg["slug"], cfg["pdf"])
        log_path = os.path.join(RAW, cfg["slug"], "repairs.tsv")
        log.write(log_path)
        print("repair log: %d entries -> %s" % (len(log.rows), log_path))
    if not ran:
        print("no sources configured in SOURCES_CONFIG")
