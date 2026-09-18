import pathlib
import re
import sys


def words_in_text(text):
    """Count prose words in Markdown text.

    The shared counting function for this project. It splits text on
    whitespace and counts non-empty tokens (regex ``\\S+``), so a
    hyphenated compound such as "well-known" counts as one word and a
    number or date counts as one token. HTML comments (page markers such
    as ``<!-- page 12 -->`` and pipeline markers) are removed first,
    wherever they sit, so a marker inside a word or sentence changes
    nothing. Then lines starting with ``#`` (headings) are excluded. YAML
    frontmatter is not stripped, so pass body text only.
    """
    kept = []
    for line in re.sub(r"<!--.*?-->", "", text, flags=re.S).splitlines():
        if line.startswith("#"):
            continue
        kept.append(line)
    return len(re.findall(r"\S+", "\n".join(kept)))


def words_of(path):
    """Count prose words in a draft or summary file with ``words_in_text``.

    Reads with ``utf-8-sig`` so a UTF-8 byte order mark does not defeat
    the heading exclusion. Intended for draft and summary files, which
    contain summary Markdown only, with no YAML frontmatter.

    Run from the project root:

        python Work/count_words.py <file>

    Prints the measured prose word count for the file.
    """
    return words_in_text(pathlib.Path(path).read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python Work/count_words.py <file>")
    try:
        count = words_of(sys.argv[1])
    except OSError as exc:
        raise SystemExit(str(exc))
    print(count)
