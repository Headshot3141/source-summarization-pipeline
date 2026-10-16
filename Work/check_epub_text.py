"""Check that the EPUB (named from TITLE, like the PDF) shows exactly the text of Summary.md.

Run from the project root (Work/build_epub.py also runs it after every build):

    python Work/check_epub_text.py [--md Summary.md] [--epub <OUTPUT_NAME>.epub]

The EPUB is read with the standard library, not ebooklib, so the check does
not share the builder's view of the file: META-INF/container.xml names the
package (OPF) file, whose spine lists the content documents in reading
order. The navigation document (the table of contents) is skipped. A
document's text is the text of its <body>, with a space at the start and end
of each block element (paragraph, heading, list, list item, quotation,
division, line break) and none at an inline element such as <em>.

Text check. The Markdown's words, read as Work/check_pdf_text.py reads them
(markdown_words: heading, quotation, and list markup and the asterisks of
italic spans removed), must equal the EPUB's words, in order. The numbers of
a numbered list are left out on both sides: an e-reader draws them from the
<ol>, so they are not in the text. There is no page layout, so no line-break
joins and no spacing tolerance: every difference fails, and is reported with
the words around it, its Summary.md line, and its spine file.

Structural checks: U+FFFD characters, and every `#` and `##` heading present
as an <h1> or <h2> with the same words. The number of <em> spans must equal
the number of italic spans in the Markdown (build_pdf.EMPHASIS_RE). As in
the PDF check, any asterisk left in the text is a warning: an unmatched
italic span, or `**bold**` copied from a source, prints literally.

Exits 1 on any difference or failed check.
"""
import argparse
import os
import posixpath
import re
import sys
import zipfile
from html.parser import HTMLParser
from urllib.parse import unquote
from xml.etree import ElementTree

from build_pdf import EMPHASIS_RE, MD, OUTPUT_NAME, ROOT, parse_lines
from check_pdf_text import clean, compare, describe, markdown_words, tokens
from common import utf8_output

# The file Work/build_epub.py writes.
EPUB = os.path.join(ROOT, OUTPUT_NAME + ".epub")

BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "div", "br", "ol", "ul"}


class _BodyText(HTMLParser):
    """Text of an XHTML document outside <head>, with the <h1>/<h2> texts and the <em> count."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.headings, self.ems = [], [], 0
        self._head = 0          # depth inside <head>
        self._heading = None    # (tag, index into parts) inside an <h1> or <h2>

    def handle_starttag(self, tag, attrs):
        if tag == "head":
            self._head += 1
        if self._head:
            return
        if tag in BLOCK_TAGS:
            self.parts.append(" ")
        if tag == "em":
            self.ems += 1
        if tag in ("h1", "h2"):
            self._heading = (tag, len(self.parts))

    def handle_endtag(self, tag):
        if tag == "head":
            self._head = max(0, self._head - 1)
            return
        if self._head:
            return
        if self._heading and self._heading[0] == tag:
            self.headings.append((tag, "".join(self.parts[self._heading[1]:])))
            self._heading = None
        if tag in BLOCK_TAGS:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self._head:
            self.parts.append(data)

    def text(self):
        return "".join(self.parts)


def body_text(xhtml):
    """(text, [(heading tag, heading text)], number of <em> elements) of an XHTML document."""
    parser = _BodyText()
    parser.feed(xhtml)
    parser.close()
    return parser.text(), parser.headings, parser.ems


def spine_documents(epub_path):
    """[(href, XHTML text)] for the spine's documents in reading order, without the nav document.

    href is the manifest's path, relative to the package file. Bytes that are
    not UTF-8 become U+FFFD, which the check reports.
    """
    with zipfile.ZipFile(epub_path) as z:
        container = ElementTree.fromstring(z.read("META-INF/container.xml"))
        rootfile = container.find(".//{*}rootfile")
        if rootfile is None:
            raise ValueError("META-INF/container.xml names no package file")
        opf_path = rootfile.get("full-path")
        opf = ElementTree.fromstring(z.read(opf_path))
        manifest = {item.get("id"): (item.get("href"), (item.get("properties") or "").split())
                    for item in opf.iterfind("{*}manifest/{*}item")}
        docs = []
        for ref in opf.iterfind("{*}spine/{*}itemref"):
            if ref.get("idref") not in manifest:
                raise ValueError("spine item %r is not in the manifest" % ref.get("idref"))
            href, properties = manifest[ref.get("idref")]
            if "nav" in properties:
                continue
            name = posixpath.normpath(posixpath.join(posixpath.dirname(opf_path), unquote(href)))
            docs.append((href, z.read(name).decode("utf-8", errors="replace")))
    return docs


def check(md_path=MD, epub_path=EPUB):
    """Run every check, print the results, and return True if all pass."""
    with open(md_path, "r", encoding="utf-8") as fh:
        md_text = fh.read()
    try:
        docs = spine_documents(epub_path)
    except (OSError, KeyError, ValueError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        print("check_epub_text: FAILED, cannot read %s: %s" % (epub_path, exc))
        return False

    problems, warnings = [], []
    epub_wds, epub_files, epub_headings, texts, ems = [], [], set(), [], 0
    for href, xhtml in docs:
        text, headings, n_em = body_text(xhtml)
        toks = tokens(clean(text))
        epub_wds.extend(toks)
        epub_files.extend([href] * len(toks))
        epub_headings.update((tag, tuple(tokens(clean(t)))) for tag, t in headings)
        texts.append(text)
        ems += n_em
        if "\ufffd" in xhtml:
            problems.append("%d U+FFFD replacement character(s) in %s" % (xhtml.count("\ufffd"), href))

    md_wds, md_lines, headings = markdown_words(md_text, list_numbers=False)
    for lineno, marker, words in headings:
        tag = "h1" if marker == "#" else "h2"
        if (tag, tuple(words)) not in epub_headings:
            problems.append("heading missing from the EPUB as an <%s> (Summary.md line %d): %s %s"
                            % (tag, lineno, marker, " ".join(words)))
    md_ems = sum(len(EMPHASIS_RE.findall(line.text)) for line in parse_lines(md_text))
    if ems != md_ems:
        problems.append("%d <em> span(s) in the EPUB, %d italic span(s) in the Markdown" % (ems, md_ems))
    flat = " ".join(" ".join(t.split()) for t in texts)
    stars = [m.start() for m in re.finditer(r"\*+", flat)]  # one context per run of asterisks
    if stars:
        shown = ", ".join(repr(flat[max(0, i - 30):i + 30]) for i in stars[:5])
        warnings.append("%d literal asterisk(s) in the EPUB text (an unmatched italic span, or "
                        "Markdown bold?): %s" % (flat.count("*"), shown))

    diffs = compare(md_wds, epub_wds)
    for d in diffs:
        problems.append("text differs at " + describe(d, md_wds, md_lines, epub_wds, epub_files,
                                                      found="EPUB", unit="file"))

    print("check_epub_text: %s: %d documents, %d words (Markdown: %d words), %d italic spans (<em>)"
          % (epub_path, len(docs), len(epub_wds), len(md_wds), ems))
    for w in warnings:
        print("  warning: %s" % w)
    if problems:
        print("check_epub_text: FAILED, %d problem(s), %d text difference(s):" % (len(problems), len(diffs)))
        for p in problems:
            print("  " + p)
        return False
    print("check_epub_text: OK: the EPUB text matches the Markdown word for word")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--md", default=MD, help="Markdown file (default: Summary.md)")
    parser.add_argument("--epub", default=EPUB, help="EPUB file (default: %(default)s)")
    args = parser.parse_args(argv)
    utf8_output()
    if not check(args.md, args.epub):
        sys.exit(1)


if __name__ == "__main__":
    main()
