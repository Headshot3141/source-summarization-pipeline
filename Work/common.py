"""Shared helpers for the pipeline scripts: paths, frontmatter, and text checks."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARD_CAP = 32_000  # bytes, UTF-8, complete file

# Compression targets (plan.md, Goal). The summarizer drafts each unit to
# DRAFT_RATIO of its retained source words (the budget tables' Target), within
# RANGE_PCT. Review and later passes may grow a unit by up to REVIEW_ALLOWANCE
# of its source words where clarity or fidelity needs it (the unit's ceiling).
# Units may run shorter or longer; the document as a whole aims at DOC_TARGET
# and must not exceed DOC_MAX.
DRAFT_RATIO = 0.40
RANGE_PCT = 0.15
REVIEW_ALLOWANCE = 0.10
DOC_TARGET = 0.50
DOC_MAX = 0.55

# Register (writing-rules.md, "Register"): "modern" for English from before 1950,
# written up in plain modern English; "source" for later English. Set per source
# in its extraction config and carried in each chapter's frontmatter.
REGISTERS = ("modern", "source")
DEFAULT_REGISTER = "source"


def draft_range(budget):
    """(lower, upper) word range a draft should land in."""
    return round(budget * (1 - RANGE_PCT)), round(budget * (1 + RANGE_PCT))


def review_ceiling(budget, source_words):
    """Words a reviewed unit may reach without a recorded preservation reason."""
    return budget + round(source_words * REVIEW_ALLOWANCE)

OWNED_START = "<!-- begin owned text -->\n"
OWNED_END = "\n<!-- end owned text -->"

# Chapter text keeps a marker for each PDF page (one-based), for evidence
# lookup. It sits on its own line above the first paragraph that starts on
# the page, or inline where a paragraph runs on from the previous page.
PAGE_MARKER = "<!-- page %d -->"
PAGE_MARKER_RE = re.compile(r"<!-- page (\d+) -->")
_COMMENT_RE = re.compile(r"<!--.*?-->[ \t]*\n?", re.S)

_FM_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_TITLE_RE = re.compile(r"\A\n*#[^\n]*\n\n*")


def strip_comments(text):
    """Text with HTML comments (page and pipeline markers) removed."""
    return _COMMENT_RE.sub("", text)


def rel(path):
    """Project-root-relative path with forward slashes."""
    return Path(path).resolve().relative_to(ROOT).as_posix()


def yaml_value(value):
    """Format a frontmatter value. JSON strings are valid YAML scalars."""
    if value is None:
        return "null"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def parse_frontmatter(raw):
    """Return (meta, rest). Values are JSON-decoded where possible."""
    m = _FM_RE.match(raw)
    if not m:
        return {}, raw
    meta = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        try:
            meta[key.strip()] = json.loads(value)
        except ValueError:
            meta[key.strip()] = value
    return meta, raw[m.end():]


def chapter_body(raw):
    """Return (meta, body) for a chapter source file.

    The body is everything after the frontmatter and the leading `# Title`
    heading, byte for byte. Parts own exact slices of this string.
    """
    meta, rest = parse_frontmatter(raw)
    m = _TITLE_RE.match(rest)
    return meta, rest[m.end():] if m else rest.lstrip("\n")


def owned_text(raw):
    """Return the owned slice stored in a part file, exactly."""
    if raw.count(OWNED_START) != 1 or raw.count(OWNED_END) != 1:
        raise ValueError("part file must contain exactly one owned-text block")
    start = raw.index(OWNED_START) + len(OWNED_START)
    end = raw.index(OWNED_END)
    if end < start:
        raise ValueError("owned-text markers are out of order")
    return raw[start:end]


# Words that end in a period without ending a sentence (titles, initials
# aside). split_parts.py does not cut an over-long paragraph after them, and
# check_fidelity.py does not end a sentence there.
ABBREVIATIONS = {
    "dr", "mr", "mrs", "ms", "st", "jr", "sr", "prof", "vs", "cf", "eg", "ie",
    "no", "vol", "pp", "p", "ch", "fig", "ed", "eds", "al", "gen", "col", "rev",
}
# Abbreviations that stand before a number in a reference ("see p. 12",
# "vol. 3"). ends_sentence reads "p. 12" at the end of a block as a reference
# cut off by a page break, not as a sentence end followed by a note number.
REFERENCE_ABBREVIATIONS = {
    "p", "pp", "no", "nos", "vol", "vols", "ch", "chap", "art", "fig", "sec", "para", "n", "nn", "cf", "ed",
}

# The labels Work/extract.py puts above a chapter's notes block: one for
# footnotes it moved there, one for endnotes printed at the back of the book.
# split_parts.py finds the notes block by them.
NOTES_LABELS = (
    "Notes to this chapter (printed as footnotes in the source):",
    "Notes to this chapter (printed at the back of the book):",
)

_SENTENCE_END_RE = re.compile(r"([.!?…”)\"]|[.!?…][’'\]]+)(\d{1,3}| \d{1,3})?$")


def ends_sentence(text):
    """True if text ends with terminal punctuation, allowing a footnote number.

    Closing quotes and brackets after the punctuation are allowed: .’ .]
    The note number may follow a space, as docling prints it: "world. 7".
    Without that, a paragraph ending in a note reference looks open-ended, so
    extraction joins it to the next paragraph across a page break and the
    splitter never cuts a part there. "see p. 12" (a reference abbreviation
    before the spaced number) still reads as open: the sentence goes on.
    """
    t = text.rstrip()
    m = _SENTENCE_END_RE.search(t) if t else None
    if not m:
        return False
    if m.group(2) and m.group(2).startswith(" ") and m.group(1) == ".":
        word = re.search(r"([A-Za-z]+)$", t[:m.start(1)])
        if word and word.group(1).lower() in REFERENCE_ABBREVIATIONS:
            return False
    return True


def is_heading(block):
    t = block.strip()
    if "\n" in t or len(t) < 2 or len(t) > 70:
        return False
    if t.endswith((".", ",", ";", ":", "—", "…", '"', "”")):
        return False
    if "..." in t or re.search(r"\. \. \.", t):
        return False
    if not (t[0].isupper() or t[0] in "“'"):
        return False
    if not 1 <= len(t.split()) <= 10:
        return False
    return any(c.isalpha() for c in t)


def utf8_output():
    """Write UTF-8 to stdout and stderr, whatever the console or pipe defaults to.

    Call it first in every script's main(). On Windows a piped stdout defaults
    to cp1252, so a reason or name with a character outside it (U+2212, a
    Polish or Chinese name) either crashes the script or reaches the agent as
    a replacement character. backslashreplace keeps any character it still
    cannot write visible. Streams without reconfigure (test StringIO) are left
    alone.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")


_LIST_ITEM_RE = re.compile(r"^[ ]{0,3}(?:[-*+]|\d{1,9}\.)[ \t]+\S")
_HEADING_LINE_RE = re.compile(r"^#{1,3}[ \t]+\S")


def paragraph_break_problems(text):
    """(line number, message) for each pair of adjacent lines that Markdown will run together.

    In a summary every paragraph, heading, and block quotation is set off by
    a blank line. A lost blank line is invisible to a word diff and to the
    PDF text check (the words are the same), but it merges two paragraphs,
    pulls a heading into the text, or swallows the next paragraph into a
    block quotation. Two list items, two lines of one block quotation, and
    two rows of one Markdown table may sit on adjacent lines.
    """
    problems = []
    lines = text.replace("\r\n", "\n").split("\n")
    for n in range(1, len(lines)):
        a, b = lines[n - 1], lines[n]
        if not a.strip() or not b.strip():
            continue
        if _LIST_ITEM_RE.match(a) and _LIST_ITEM_RE.match(b):
            continue
        if a.lstrip().startswith("|") and b.lstrip().startswith("|"):
            continue
        qa, qb = a.lstrip().startswith(">"), b.lstrip().startswith(">")
        if qa and qb:
            continue
        if _HEADING_LINE_RE.match(a) or _HEADING_LINE_RE.match(b):
            message = "heading without a blank line around it"
        elif qa or qb:
            message = ("block quotation and text without a blank line between them "
                       "(they render as one quotation)")
        else:
            message = ("two text lines without a blank line between them "
                       "(they render as one paragraph)")
        problems.append((n + 1, message))
    return problems
