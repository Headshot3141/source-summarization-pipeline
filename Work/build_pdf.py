"""Render Summary.md to Summary.pdf, then check the PDF text against it.

Summary.md -> styled HTML (Python-Markdown + Jinja2, written to
Work/summary.html) -> PDF (headless Microsoft Edge) -> page numbers
(PyMuPDF) -> text check (Work/check_pdf_text.py). Run from the project root:

    python Work/build_pdf.py

It exits nonzero if the build fails or the PDF text does not match the
Markdown. To rerun only the check on an existing PDF:

    python Work/check_pdf_text.py

Text fidelity. The summary reproduces source text exactly, so the renderer
must not change a character. Python-Markdown would: `*x*`, `_x_` and `**x**`
become emphasis, `<...>` becomes raw HTML, `\\` escapes vanish, `[x](y)`
becomes a link, a line of `===` or `---` becomes a heading, and so on.
markdown_source() therefore keeps only the structure the pipeline writes
and turns every other Markdown-significant ASCII character (ESCAPE_CHARS)
into a numeric character reference, which Python-Markdown passes through
untouched and the browser shows as the original character. Typographic
quotes, apostrophes, dashes, and ellipses are not ASCII and pass through;
no extension that rewrites them (such as smarty) is enabled.

Structure kept (parse_lines()):
- A line `# `, `## ` or `### ` followed by text is a heading. Deeper levels
  are not part of the pipeline's format and stay literal text.
- A line starting `>` (up to three spaces before it, one optional space
  after it) is a block quotation line. Its content is escaped like prose,
  and genuine lists inside a quotation are kept; headings and nested `>`
  inside a quotation stay literal text.
- Genuine lists. A list can only start at the beginning of a block (after
  a blank line, heading, or quotation), as in Python-Markdown. An item line
  is `- `, `* ` or `+ ` (bullet) or digits and `. ` (numbered, no leading
  zero) followed by text. A run of items is the item lines of one kind
  (numbered, or the same bullet character) that follow one another, on adjacent lines or in blocks separated only
  by blank lines; numbered items must count up by one. A run is a list
  only if it has at least two items, and a numbered run must also either
  start at 1 or have two items on adjacent lines. Everything else that
  looks like a list marker is escaped: a lone paragraph starting "1984. ",
  "- " or "+ ", or blank-line-separated paragraphs starting "1984. " and
  "1985. ". Inside a list, a line that is not a valid next item is a
  continuation of the item above it, escaped. Two lists separated only by
  blank lines get an empty HTML comment between them, because
  Python-Markdown would otherwise join and renumber them.
- Blank lines (paragraph breaks) are kept. Leading and trailing spaces on
  a line are dropped (HTML collapses them anyway, and they would otherwise
  make indented code blocks or hard line breaks).
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import markdown
import pymupdf
from jinja2 import Template

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD = os.path.join(ROOT, "Summary.md")
HTML = os.path.join(ROOT, "Work", "summary.html")
PDF = os.path.join(ROOT, "Summary.pdf")
TITLE = "Summary"

# Python-Markdown configuration shared with Work/build_epub.py. Do not add
# smarty or any extension that rewrites characters.
MD_EXTENSIONS = ["extra", "sane_lists"]

# Every ASCII character with meaning to Python-Markdown or its extra
# extensions (emphasis, code, links, raw HTML, entities, headings, lists,
# quotations, tables, definition lists, abbreviations, attribute lists,
# fenced code, setext headings, rules). Escaped everywhere in text.
ESCAPE_CHARS = "\\`*_{}[]()#+-.!:|=~<>&"
_ESCAPE_TABLE = {ord(c): "&#%d;" % ord(c) for c in ESCAPE_CHARS}

HEADING_RE = re.compile(r"^(#{1,3})[ \t]+(\S.*?)[ \t]*$")
QUOTE_RE = re.compile(r"^[ ]{0,3}>[ ]?(.*)$")
BULLET_RE = re.compile(r"^[ ]{0,3}([-*+])[ \t]+(\S.*?)[ \t]*$")
NUMBER_RE = re.compile(r"^[ ]{0,3}(0|[1-9]\d{0,8})\.[ \t]+(\S.*?)[ \t]*$")

EDGE = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ title }}</title>
<style>
@page { size: Letter; margin: 1in; }
body {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 11pt;
  line-height: 1.5;
  color: #111;
  margin: 0;
}
h1 {
  font-size: 18pt;
  line-height: 1.3;
  margin: 1.6em 0 0.4em;
  page-break-after: avoid;
}
h1:first-child { margin-top: 0; }
h2 {
  font-size: 14pt;
  line-height: 1.35;
  margin: 1.5em 0 0.4em;
  page-break-after: avoid;
}
h3 {
  font-size: 11.5pt;
  font-style: italic;
  margin: 1.2em 0 0.3em;
  page-break-after: avoid;
}
p { margin: 0 0 0.65em; text-align: justify; }
blockquote {
  margin: 0 2em 0.65em;
  font-size: 10.5pt;
}
blockquote p { text-align: left; }
ul, ol { margin: 0 0 0.65em; padding-left: 2.5em; }
/* Room for long markers such as "1984. ": the browser clips what overflows the page. */
ol[start] { padding-left: 3.5em; }
li { margin: 0 0 0.3em; }
</style>
</head>
<body>
{{ body }}
</body>
</html>
"""


def escape_text(text):
    """Text with every Markdown-significant ASCII character as a character reference."""
    return text.translate(_ESCAPE_TABLE)


@dataclass
class Line:
    """One Summary.md line split into structure and literal text.

    kind is "blank", "heading", "prose", "item", or "separator" (an empty
    HTML comment that keeps two adjacent lists apart). marker is the Markdown
    marker kept for a heading or list item ("##", "-", "3."); number is the
    number the browser prints for a numbered item. text is the literal text.
    """
    lineno: int
    kind: str
    text: str = ""
    marker: str = ""
    quote: bool = False
    number: int = None

    def markdown(self):
        prefix = ">" if self.quote else ""
        if self.kind == "blank":
            return prefix
        if self.kind == "separator":
            return (prefix + " " if prefix else "") + "<!-- -->"
        if prefix:
            prefix += " "
        if self.kind in ("heading", "item"):
            prefix += self.marker + " "
        return prefix + escape_text(self.text)


def _item(line):
    """(kind, marker, number, text) for a list-item line, else None.

    kind is "number", or "bullet" plus the bullet character: a change of
    bullet character does not continue a list.
    """
    m = BULLET_RE.match(line)
    if m:
        return "bullet" + m.group(1), m.group(1), None, m.group(2)
    m = NUMBER_RE.match(line)
    if m:
        return "number", m.group(1) + ".", int(m.group(1)), m.group(2)
    return None


def _prose(lineno, line, quote):
    return Line(lineno, "prose", line.strip(), quote=quote)


def _list_run(units, k):
    """Find the list run starting at units[k], a block whose first line is an item.

    Returns (items, end): items maps (unit index, line index) to the parsed
    item for every line that is a list item, and end is the index of the
    first unit after the run (blank units between the run's blocks belong
    to it; trailing blank units do not). Returns (None, k + 1) when the run
    is not a genuine list.
    """
    kind, _, first, _ = _item(units[k][1][0][1])
    items, expected, tight = {}, first, False
    m, end = k, k
    while m < len(units):
        if units[m][0] == "blank":
            m += 1
            continue
        if units[m][0] != "block":
            break
        lines = units[m][1]
        head = _item(lines[0][1])
        if not head or head[0] != kind or (kind == "number" and head[2] != expected):
            break
        prev_item = False
        for li, (_, text) in enumerate(lines):
            it = _item(text)
            if it and it[0] == kind and (kind != "number" or it[2] == expected):
                items[(m, li)] = it
                if prev_item:
                    tight = True
                prev_item = True
                if kind == "number":
                    expected += 1
            else:
                prev_item = False
        m += 1
        end = m
    if len(items) < 2 or (kind == "number" and first != 1 and not tight):
        return None, k + 1
    return items, end


def _parse_plain(numbered, headings, quote):
    """Parse a stretch of lines with no quotation lines in it."""
    # Units: ("blank", lineno), ("heading", (lineno, text, marker)), ("block", [(lineno, text)]).
    units, block = [], []
    for lineno, text in numbered:
        h = HEADING_RE.match(text) if headings else None
        if not text.strip() or h:
            if block:
                units.append(("block", block))
                block = []
            if h:
                units.append(("heading", (lineno, h.group(2), h.group(1))))
            else:
                units.append(("blank", lineno))
        else:
            block.append((lineno, text))
    if block:
        units.append(("block", block))

    out = []
    k = 0
    last_list = None  # "ol" or "ul" when the last thing emitted (blank lines aside) was a list
    while k < len(units):
        kind, value = units[k]
        if kind == "blank":
            out.append(Line(value, "blank", quote=quote))
            k += 1
            continue
        if kind == "heading":
            lineno, text, marker = value
            out.append(Line(lineno, "heading", text, marker, quote=quote))
            last_list = None
            k += 1
            continue
        items, end = _list_run(units, k) if _item(value[0][1]) else (None, k + 1)
        tag = ("ol" if _item(value[0][1])[0] == "number" else "ul") if items else None
        if tag and tag == last_list:
            # Python-Markdown would continue the previous list (renumbering it).
            out.append(Line(value[0][0], "separator", quote=quote))
            out.append(Line(value[0][0], "blank", quote=quote))
        last_list = tag
        for m in range(k, end):
            ukind, uvalue = units[m]
            if ukind == "blank":
                out.append(Line(uvalue, "blank", quote=quote))
                continue
            for li, (lineno, text) in enumerate(uvalue):
                it = items.get((m, li)) if items else None
                if it:
                    out.append(Line(lineno, "item", it[3], it[1], quote=quote, number=it[2]))
                else:
                    out.append(_prose(lineno, text, quote))
        k = end
    return out


def parse_lines(text, headings=True, first_lineno=1):
    """Split Markdown text into Line records (see the module docstring for the rules)."""
    raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    numbered = list(enumerate(raw, first_lineno))
    out, plain, i = [], [], 0
    while i < len(numbered):
        if not QUOTE_RE.match(numbered[i][1]):
            plain.append(numbered[i])
            i += 1
            continue
        out.extend(_parse_plain(plain, headings, False))
        plain = []
        j = i
        while j < len(numbered) and QUOTE_RE.match(numbered[j][1]):
            j += 1
        inner = [(n, QUOTE_RE.match(t).group(1)) for n, t in numbered[i:j]]
        out.extend(_parse_plain(inner, False, True))
        i = j
    out.extend(_parse_plain(plain, headings, False))
    return out


def markdown_source(text):
    """Summary.md text rewritten so Python-Markdown keeps every character."""
    return "\n".join(line.markdown() for line in parse_lines(text)) + "\n"


def markdown_to_html(text):
    """HTML for Markdown text, with the text rendered exactly as written."""
    return markdown.markdown(markdown_source(text), extensions=MD_EXTENSIONS)


def find_edge():
    on_path = shutil.which("msedge")
    if on_path:
        return on_path
    for path in EDGE:
        if os.path.exists(path):
            return path
    raise SystemExit("Microsoft Edge not found on PATH or in: " + ", ".join(EDGE))


def render_html(md_path=MD, html_path=HTML):
    with open(md_path, "r", encoding="utf-8") as fh:
        text = fh.read()
    html = Template(TEMPLATE).render(body=markdown_to_html(text), title=TITLE)
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html)


def print_pdf(edge, tmp_pdf, html_path=HTML):
    url = Path(html_path).resolve().as_uri()
    failures = []
    # A separate profile keeps an open Edge window from taking over the print job.
    with tempfile.TemporaryDirectory(prefix="edge-profile-") as profile:
        base = [edge, "--no-first-run", "--no-default-browser-check",
                "--user-data-dir=" + profile,
                "--disable-gpu", "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=10000",
                "--no-pdf-header-footer", "--print-to-pdf-no-header"]
        for mode in ("--headless=new", "--headless"):
            if os.path.exists(tmp_pdf):
                os.remove(tmp_pdf)
            cmd = base + [mode, "--print-to-pdf=" + tmp_pdf, url]
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    errors="replace", timeout=180)
            produced = os.path.exists(tmp_pdf) and os.path.getsize(tmp_pdf) > 0
            if result.returncode == 0 and produced:
                return
            failures.append("%s: exit %d%s\n%s" % (
                mode, result.returncode, "" if produced else ", no PDF",
                result.stderr.strip() or "(no stderr)"))
    raise SystemExit("Edge failed to produce a PDF\n" + "\n".join(failures))


def add_page_numbers(tmp_pdf, pdf_path=PDF):
    doc = pymupdf.open(tmp_pdf)
    count = doc.page_count
    for i, page in enumerate(doc):
        rect = page.rect
        label = str(i + 1)
        width = pymupdf.get_text_length(label, fontname="helv", fontsize=10)
        page.insert_text(
            (rect.width / 2 - width / 2, rect.height - 42),
            label,
            fontname="helv",
            fontsize=10,
        )
    doc.save(pdf_path, garbage=4, deflate=True)
    doc.close()
    return count


def build(md_path=MD, html_path=HTML, pdf_path=PDF):
    """Render md_path to pdf_path; return the page count."""
    render_html(md_path, html_path)
    edge = find_edge()
    fd, tmp_pdf = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        print_pdf(edge, tmp_pdf, html_path)
        pages = add_page_numbers(tmp_pdf, pdf_path)
    finally:
        if os.path.exists(tmp_pdf):
            os.remove(tmp_pdf)
    return pages


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")  # report any character on any console
    pages = build(MD, HTML, PDF)
    print("wrote %s: %d pages" % (PDF, pages))
    import check_pdf_text  # imports this module, so load it only when needed
    if not check_pdf_text.check(MD, PDF):
        sys.exit(1)


if __name__ == "__main__":
    main()
