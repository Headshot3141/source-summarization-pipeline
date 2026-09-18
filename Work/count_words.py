import pathlib
import re
import sys


def words_in_text(text):
    """Count prose words in Markdown text.

    The shared counting function for this project. It splits text on
    whitespace and counts non-empty tokens (regex ``\\S+``), so a
    hyphenated compound such as "well-known" counts as one word and a
    number or date counts as one token. Lines starting with ``#``
    (headings) are excluded, and so are lines that consist only of an
    HTML comment (page markers and pipeline markers such as
    ``<!-- page 12 -->``). YAML frontmatter is not stripped, so pass
    body text only.
    """
    kept = []
    for line in text.splitlines():
        s = line.strip()
        if line.startswith("#"):
            continue
        if s.startswith("<!--") and s.endswith("-->"):
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
