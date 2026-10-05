"""Shared helpers for the pipeline scripts: paths, frontmatter, and text checks."""
import json
import re
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


def ends_sentence(text):
    """True if text ends with terminal punctuation, allowing a footnote number.

    Closing quotes and brackets after the punctuation are allowed: .’ .]
    """
    t = text.rstrip()
    return bool(t) and bool(re.search(r"([.!?…”)\"]|[.!?…][’'\]]+)\d{0,3}$", t))


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
