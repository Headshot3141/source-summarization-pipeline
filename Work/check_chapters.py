"""Scan chapter source files for extraction damage, and print each chapter's boundaries.

    python Work/check_chapters.py [slug ...]

Reads every chapter file in Work/Chapters/<slug>/ (every source when no slug
is given; parts/ is not read). Run it after each extraction (plan.md Step
2). Exit status 1 if any file holds a forbidden character or sequence,
which extraction must never leave; repair it in the source's config and
re-extract, never in the chapter file:

  U+FFFD                 replacement character: a character the conversion lost
  U+E000-U+F8FF          private-use character: a glyph the text layer did not
                         map (old-style figures, small capitals); map it with
                         the config's char_map once the page image shows it
  U+00AD                 soft hyphen
  &name; &#123;          an HTML entity left escaped
  U+FB00-U+FB06          presentation-form ligature
  GLYPH<                 docling's placeholder for a glyph it could not read
  @@                     a marker a build_txt script or config left behind

Warnings, each to check against the page image (they do not change the exit
status): a double space; a space before punctuation; "x- y", a line-end
hyphen kept with a space; a letter, quotation mark, and letter run together
("Polish'spring", a lost space that a word check reads as one name); a body
paragraph that does not end a sentence (a split paragraph, or a chapter cut
mid-sentence; a colon or semicolon ending, and a short line that reads as a
section heading, pass); and a frontmatter word_count that differs from a
recount.

Then each chapter's first and last body paragraph (the notes block is not
body), for a boundary read against the original.
"""
import re
import sys
from html.entities import html5

from common import NOTES_LABELS, ROOT, chapter_body, ends_sentence, is_heading, strip_comments, utf8_output
from count_words import words_in_text

CHAPTERS = ROOT / "Work" / "Chapters"

ENTITY = re.compile(r"&(?:[A-Za-z][A-Za-z0-9]*|#\d+|#[xX][0-9a-fA-F]+);")


class _Entities:
    """Finds HTML entities: numeric ones, and named ones HTML defines ("&amp;", not "AT&T;")."""

    @staticmethod
    def finditer(line):
        return [m for m in ENTITY.finditer(line) if m.group(0)[1] == "#" or m.group(0)[1:] in html5]


FORBIDDEN = [
    ("U+FFFD replacement character", re.compile("�")),
    ("private-use character (map it with char_map)", re.compile("[-]")),
    ("soft hyphen U+00AD", re.compile("­")),
    ("HTML entity", _Entities),
    ("presentation-form ligature", re.compile("[ﬀ-ﬆ]")),
    ("docling GLYPH< placeholder", re.compile("GLYPH<")),
    ("leftover @@ marker", re.compile("@@")),
]
LETTER = r"[^\W\d_]"
# A quotation mark between letters: a double or opening single mark never sits
# inside a word. An apostrophe does ("don't", "Penhale's", "o'clock", and
# romanized names such as "Ch'en" or "Dong'an"), so it counts only with three
# letters or more on each side and not before a contraction's ending:
# "Polish'spring", not "Polish's".
RUN_TOGETHER = re.compile(r"%s[\"“”‘]%s|\b%s{3,}['’](?!(?:s|t|d|ll|re|ve|m)\b)%s{3,}"
                          % (LETTER, LETTER, LETTER, LETTER))
WARNINGS = [
    ("double space", re.compile(r"\S {2,}\S")),
    # A spaced ellipsis (". . .") is printed that way and is not flagged.
    ("space before punctuation", re.compile(r"(?<=\w) [,;:?!)]|(?<=\w) \.(?! ?\.)")),
    # "pre- and post-war" is a suspended hyphen, not a line break.
    ("hyphen-space (x- y)", re.compile(r"(?<![\w-])%s+- (?!(?:and|or|nor|to)\b)%s" % (LETTER, LETTER))),
    ("letter, quotation mark, letter run together", RUN_TOGETHER),
]
LIST_ITEM = re.compile(r"^(?:[-*+]|\d{1,3}[.)])\s")
# How much of a paragraph or line is shown.
CONTEXT = 30
BOUNDARY_CHARS = 300


def _context(text, m):
    a, b = max(0, m.start() - CONTEXT), m.end() + CONTEXT
    return ("..." if a else "") + text[a:b] + ("..." if b < len(text) else "")


def _paragraphs(body, first_line):
    """(first line number, text) of each paragraph of body, whose first line is line first_line."""
    out, cur, start = [], [], first_line
    for no, ln in enumerate(body.split("\n"), first_line):
        if ln.strip():
            if not cur:
                start = no
            cur.append(ln)
        elif cur:
            out.append((start, "\n".join(cur)))
            cur = []
    if cur:
        out.append((start, "\n".join(cur)))
    return out


def _plain(paragraph):
    """A paragraph's text: comments (page markers) and block-quotation markers removed."""
    lines = [re.sub(r"^\s*(?:>\s?)+", "", ln) for ln in strip_comments(paragraph).split("\n")]
    return "\n".join(lines).strip()


def scan(raw):
    """Check one chapter file's text: {"errors", "warnings": [(line, message)], "first", "last"}."""
    errors, warnings = [], []
    for no, line in enumerate(raw.split("\n"), 1):
        for label, pat in FORBIDDEN:
            hits = list(pat.finditer(line))
            if hits:
                errors.append((no, "%s x%d: %s" % (label, len(hits), _context(line, hits[0]))))
    meta, body = chapter_body(raw)
    first_line = raw[:len(raw) - len(body)].count("\n") + 1
    in_code = False
    for no, line in enumerate(body.split("\n"), first_line):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        text = strip_comments(line)
        if in_code or text.lstrip().startswith("|"):
            continue
        for label, pat in WARNINGS:
            m = pat.search(text)
            if m:
                warnings.append((no, "%s: %s" % (label, _context(text, m))))
    paragraphs, in_notes = [], False
    for no, p in _paragraphs(body, first_line):
        text = _plain(p)
        if not text:
            continue
        if text in NOTES_LABELS:
            in_notes = True
        if in_notes:
            continue
        paragraphs.append(text)
        lines = text.split("\n")
        # A lead-in ends in a colon, and an item of a printed series (the clauses
        # of a resolution) in a semicolon; a short line reads as a section heading.
        if (text.startswith(("|", "```")) or LIST_ITEM.match(lines[0]) or is_heading(text)
                or ends_sentence(text) or text.endswith((":", ";"))):
            continue
        warnings.append((no, "paragraph does not end a sentence: ...%s" % text[-2 * CONTEXT:]))
    recount = words_in_text(body)
    if meta.get("word_count") != recount:
        warnings.append((1, "word_count %r in the frontmatter, %d on a recount" % (meta.get("word_count"), recount)))
    warnings.sort(key=lambda w: w[0])
    first = paragraphs[0] if paragraphs else ""
    last = paragraphs[-1] if paragraphs else ""
    return {"errors": errors, "warnings": warnings,
            "first": first if len(first) <= BOUNDARY_CHARS else first[:BOUNDARY_CHARS] + "...",
            "last": last if len(last) <= BOUNDARY_CHARS else "..." + last[-BOUNDARY_CHARS:]}


def chapter_files(slugs):
    """The chapter files of the named sources (all sources when none is named), in order."""
    if not CHAPTERS.is_dir():
        return []
    folders = [CHAPTERS / s for s in slugs] if slugs else sorted(p for p in CHAPTERS.iterdir() if p.is_dir())
    missing = [f.name for f in folders if not f.is_dir()]
    if missing:
        raise SystemExit("no chapter folder Work/Chapters/%s" % ", Work/Chapters/".join(missing))
    return [p for f in folders for p in sorted(f.glob("*.md")) if p.is_file()]


def main(argv):
    utf8_output()
    files = chapter_files(argv)
    if not files:
        print("no chapter files in Work/Chapters")
        return 0
    with_errors = warned = 0
    for path in files:
        result = scan(path.read_text(encoding="utf-8"))
        print(path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path))
        for no, message in result["errors"]:
            print("  ERROR line %d: %s" % (no, message))
        for no, message in result["warnings"]:
            print("  WARNING line %d: %s" % (no, message))
        print("  first: %s" % result["first"].replace("\n", " / "))
        print("  last:  %s" % result["last"].replace("\n", " / "))
        with_errors += bool(result["errors"])
        warned += len(result["warnings"])
    print("%d chapter file(s): %d with forbidden characters, %d warning(s)" % (len(files), with_errors, warned))
    return 1 if with_errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
