"""Shared helpers for the pipeline scripts: paths, frontmatter, and text checks."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARD_CAP = 32_000  # bytes, UTF-8, complete file

OWNED_START = "<!-- begin owned text -->\n"
OWNED_END = "\n<!-- end owned text -->"

_FM_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_TITLE_RE = re.compile(r"\A\n*#[^\n]*\n\n*")


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
    """True if text ends with terminal punctuation, allowing a footnote number."""
    t = text.rstrip()
    return bool(t) and bool(re.search(r"[.!?…”)\"]\d{0,3}$", t))


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
