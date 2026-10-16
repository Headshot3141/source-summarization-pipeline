import pathlib
import re
import sys

from common import parse_frontmatter, utf8_output


def words_in_text(text):
    """Count prose words in Markdown text.

    The shared counting function for this project. It splits text on
    whitespace and counts non-empty tokens (regex ``\\S+``), so a
    hyphenated compound such as "well-known" counts as one word and a
    number or date counts as one token. HTML comments (page markers such
    as ``<!-- page 12 -->`` and pipeline markers) are removed first,
    wherever they sit, so a marker inside a word or sentence changes
    nothing. Then lines starting with ``#`` (headings) are excluded, and
    the Markdown block-quote marker (``>`` at the start of a line) is
    removed, so a block quotation counts its words only. In a Markdown
    table (a line starting with ``|``), the separator row is skipped and
    the cell pipes are not counted, so a table counts its cell words only.
    YAML frontmatter is not stripped, so pass body text only (``words_of``
    strips it from a file).
    """
    kept = []
    for line in re.sub(r"<!--.*?-->", "", text, flags=re.S).splitlines():
        if line.startswith("#"):
            continue
        line = re.sub(r"^\s*(?:>\s?)+", "", line)
        if line.lstrip().startswith("|"):
            if re.fullmatch(r"[\s|:-]*", line):
                continue
            line = line.replace("\\|", " ").replace("|", " ")
        kept.append(line)
    return len(re.findall(r"\S+", "\n".join(kept)))


def words_of(path):
    """Count prose words in a file with ``words_in_text``, leaving out its YAML frontmatter.

    Reads with ``utf-8-sig`` so a UTF-8 byte order mark does not defeat
    the heading exclusion. Draft and summary files are summary Markdown
    only. A chapter source file starts with YAML frontmatter (a ``---``
    line, ``key: value`` lines, a closing ``---``), which is not prose:
    counted, it added 30 to 40 words to every chapter, so an agent's count
    disagreed with the ``word_count`` the file itself records. A leading
    frontmatter block is therefore dropped first; the ``# Title`` line after
    it is a heading and is not counted either, so on a chapter file this
    gives its ``word_count``.

    Run from the project root:

        python Work/count_words.py <file>

    Prints the measured prose word count for the file.
    """
    text = pathlib.Path(path).read_text(encoding="utf-8-sig")
    if text.startswith("---\n"):
        meta, rest = parse_frontmatter(text)
        if meta:
            text = rest
    return words_in_text(text)


if __name__ == "__main__":
    utf8_output()
    if len(sys.argv) != 2:
        raise SystemExit("usage: python Work/count_words.py <file>")
    try:
        count = words_of(sys.argv[1])
    except OSError as exc:
        raise SystemExit(str(exc))
    print(count)
