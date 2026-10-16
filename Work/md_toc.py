"""Heading table of a docling Markdown file, for the Preflight inspection.

    python Work/md_toc.py <md file> [<output file>]

Prints the table, or writes it to the output file (UTF-8, LF line endings;
use this rather than a shell redirect, which on Windows may write another
encoding). The usual output is Work/Preflight/<md file stem>.toc.txt, which
the inspection agent reads before the Markdown itself
(passes/preflight-inspection.md).

The table starts with "#" lines: the file's total words (the project's
count, words_in_text) and heading count; counts of the placeholders and
characters that conversion damage shows up as (page-break, image, and
formula placeholders, U+FFFD, private-use characters, docling GLYPH<...>,
soft hyphens, HTML entities, straight against curly quotation marks,
dashes, " - ", and "x- y" line-end hyphens kept with a space); and the
running-head candidates, short paragraphs (8 words or fewer) that occur 3
times or more. Then one row per "#" heading line: its line number, the
words from it to the next heading, and the heading text. A "(start)" row
counts the words before the first heading.
"""
import re
import sys
from collections import Counter
from pathlib import Path

from common import utf8_output
from count_words import words_in_text

HEADING = re.compile(r"^#{1,6}\s")
COMMENT = re.compile(r"^<!--.*-->$")
PAGE_BREAK = "<!-- page break -->"
IMAGE = "<!-- image -->"
FORMULA = "<!-- formula-not-decoded -->"
IMAGE_LINK = re.compile(r"^!\[[^\]]*\]\([^)]*\)$")
ENTITY = re.compile(r"&(?:[A-Za-z][A-Za-z0-9]*|#\d+|#[xX][0-9a-fA-F]+);")
HYPHEN_SPACE = re.compile(r"[^\W\d_]- [^\W\d_]")
EMPHASIS = re.compile(r"(?<![\\*\w])(\*\*?)(?=\S)(.+?)(?<=[^\s\\])\1(?![*\w])")
# A running head is short and recurs; RUNNING_HEAD_WORDS and RUNNING_HEAD_MIN set "short" and "recurs".
RUNNING_HEAD_WORDS = 8
RUNNING_HEAD_MIN = 3


def blocks(lines):
    """(first line number, text) of each block of non-blank lines, comment lines left out."""
    out, cur, start = [], [], 0
    for no, ln in enumerate(lines + [""], 1):
        s = ln.strip()
        if s and not COMMENT.match(s):
            if not cur:
                start = no
            cur.append(s)
        elif cur:
            out.append((start, " ".join(cur)))
            cur = []
    return out


def toc(text, name):
    """The heading table of a Markdown file's text, as a list of lines."""
    lines = text.splitlines()
    heads = [i for i, ln in enumerate(lines) if HEADING.match(ln)]
    stripped = [ln.strip() for ln in lines]
    comments = Counter(s for s in stripped if COMMENT.match(s))
    other = {c: n for c, n in comments.items() if c not in (PAGE_BREAK, IMAGE, FORMULA)}
    images = comments[IMAGE] + sum(1 for s in stripped if IMAGE_LINK.match(s))
    repeated = Counter(t for _, t in blocks(lines) if len(t.split()) <= RUNNING_HEAD_WORDS)
    candidates = [(t, n) for t, n in repeated.most_common() if n >= RUNNING_HEAD_MIN]
    out = [
        "# %s: %d words, %d headings, %d lines" % (name, words_in_text(text), len(heads), len(lines)),
        "# placeholders: page break %d; image %d; formula %d; other comment lines: %s"
        % (comments[PAGE_BREAK], images, comments[FORMULA],
           "; ".join("%r x%d" % (c, n) for c, n in sorted(other.items(), key=lambda x: -x[1])) or "none"),
        "# characters: U+FFFD %d; private-use (U+E000-U+F8FF) %d; GLYPH< %d; soft hyphen %d; HTML entities %d"
        % (text.count("�"), len(re.findall("[-]", text)), text.count("GLYPH<"),
           text.count("­"), len(ENTITY.findall(text))),
        "# quotes: straight \" %d, ' %d; curly “ %d, ” %d, ‘ %d, ’ %d"
        % tuple(text.count(c) for c in "\"'“”‘’"),
        "# dashes: em — %d, en – %d; spaced hyphen \" - \" %d; hyphen-space \"x- y\" %d"
        % (text.count("—"), text.count("–"), text.count(" - "), len(HYPHEN_SPACE.findall(text))),
        "# emphasis spans (*x* or **x**): %d" % sum(len(EMPHASIS.findall(ln)) for ln in lines),
        "# repeated short paragraphs (running heads?): %s"
        % ("; ".join("%r x%d" % (t, n) for t, n in candidates) or "none"),
        "#   line   words  heading",
    ]
    bounds = [0] + heads + [len(lines)]
    for k in range(len(bounds) - 1):
        a, b = bounds[k], bounds[k + 1]
        if k == 0:
            # Words before the first heading (or in the whole file, if it has none).
            out.append("%6d %7d  (start)" % (0, words_in_text("\n".join(lines[a:b]))))
            continue
        out.append("%6d %7d  %s" % (a + 1, words_in_text("\n".join(lines[a + 1:b])), lines[a].strip()))
    return out


def main(argv):
    utf8_output()
    if len(argv) not in (1, 2):
        raise SystemExit("usage: python Work/md_toc.py <md file> [<output file>]")
    path = Path(argv[0])
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise SystemExit(str(exc))
    table = "\n".join(toc(text, path.name)) + "\n"
    if len(argv) == 2:
        Path(argv[1]).parent.mkdir(parents=True, exist_ok=True)
        with open(argv[1], "w", encoding="utf-8", newline="\n") as f:
            f.write(table)
        print("%s -> %s" % (path, argv[1]))
    else:
        sys.stdout.write(table)


if __name__ == "__main__":
    main(sys.argv[1:])
