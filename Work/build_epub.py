"""Build the EPUB from Summary.md (optional deliverable), then check its text.

Each `# ` heading (the introduction and each source part) becomes a section
page, and each `## ` chapter becomes its own EPUB page listed under its part
in the table of contents. The title comes from TITLE in Work/build_pdf.py,
and so does the file name (build_pdf.OUTPUT_NAME): "The Grey Harbour:
Essays" is written to The-Grey-Harbour-Essays.epub at the project root, and
the default TITLE gives Summary.epub.

Markdown is converted with Work/build_pdf.py's markdown_to_html, so the
text appears exactly as written (see that module's docstring for the rules),
and a single-asterisk span is set in italics, in the part headings too. The
table of contents shows the titles without those asterisks.

After writing the file, the build runs Work/check_epub_text.py, which
compares the EPUB's text with Summary.md word for word, and exits 1 if it
fails. Requires ebooklib (see requirements.txt). Run from the project root:

    python Work/build_epub.py
"""
import re
import sys
import uuid

from ebooklib import epub

import check_epub_text
from build_pdf import OUTPUT_NAME, TITLE, markdown_to_html, strip_emphasis
from common import ROOT, utf8_output

MD = ROOT / "Summary.md"
# Named like the PDF, after the title (build_pdf.OUTPUT_NAME).
EPUB = ROOT / (OUTPUT_NAME + ".epub")
LANGUAGE = "en"
# A stable identifier lets readers treat a rebuilt file as the same book.
IDENTIFIER = "urn:uuid:%s" % uuid.uuid5(uuid.NAMESPACE_URL, "summary:" + TITLE)

CSS = """
body { font-family: Georgia, "Times New Roman", serif; line-height: 1.5; margin: 0 0.5em; }
h1 { font-size: 1.6em; line-height: 1.3; margin: 2em 0 0.6em; text-align: center; }
h2 { font-size: 1.3em; line-height: 1.35; margin: 1em 0 0.6em; }
h3 { font-size: 1.05em; font-style: italic; margin: 1.2em 0 0.3em; }
/* Italics inside a heading already set in italics show upright. */
h3 em { font-style: normal; }
blockquote { margin: 0 2em 0.65em; font-size: 0.95em; }
p { margin: 0 0 0.65em; text-align: justify; }
"""

_H1_RE = re.compile(r"<h1[\s>]")


def to_html(text):
    return markdown_to_html(text)


def split_book(text):
    """Return a list of parts: (h1 title, preamble markdown, [(h2 title, body markdown)])."""
    parts = []
    for block in re.split(r"(?m)^# ", text)[1:]:
        title, _, rest = block.partition("\n")
        chunks = re.split(r"(?m)^## ", rest)
        chapters = []
        for chunk in chunks[1:]:
            ch_title, _, body = chunk.partition("\n")
            chapters.append((ch_title.strip(), body))
        parts.append((title.strip(), chunks[0], chapters))
    return parts


def part_html(p_title, preamble):
    """HTML for a part's section page: its heading and the text before its first chapter.

    The heading goes through the renderer like any other line, so an italic
    span in a part title (a book title) prints as italics, not asterisks.
    """
    body = to_html("# %s\n\n%s" % (p_title, preamble))
    if len(_H1_RE.findall(body)) != 1:
        raise SystemExit("part %r does not render to exactly one <h1>" % p_title)
    return body


def page(book, css, file_name, title, html):
    # The table of contents shows the title as text, so it drops the italics' asterisks.
    item = epub.EpubHtml(title=strip_emphasis(title), file_name=file_name, lang=LANGUAGE)
    item.content = html
    item.add_item(css)
    book.add_item(item)
    return item


def build(md_path, epub_path):
    """Write the EPUB for md_path to epub_path; return (sections, chapters)."""
    text = md_path.read_text(encoding="utf-8")

    book = epub.EpubBook()
    book.set_identifier(IDENTIFIER)
    book.set_title(TITLE)
    book.set_language(LANGUAGE)

    css = epub.EpubItem(uid="style", file_name="style/main.css",
                        media_type="text/css", content=CSS)
    book.add_item(css)

    spine, toc = ["nav"], []
    chapter_count = 0
    for p_idx, (p_title, preamble, chapters) in enumerate(split_book(text)):
        head = page(book, css, "part%02d.xhtml" % p_idx, p_title, part_html(p_title, preamble))
        spine.append(head)
        links = []
        for c_idx, (c_title, body) in enumerate(chapters, 1):
            item = page(book, css, "part%02d_ch%02d.xhtml" % (p_idx, c_idx), c_title,
                        to_html("## %s\n%s" % (c_title, body)))
            spine.append(item)
            links.append(item)
            chapter_count += 1
        if links:
            toc.append((epub.Section(strip_emphasis(p_title), href=head.file_name), links))
        else:
            toc.append(head)

    book.toc = toc
    book.spine = spine
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(epub_path), book)
    return len(toc), chapter_count


def main():
    utf8_output()
    sections, chapters = build(MD, EPUB)
    print("wrote %s: %d sections, %d chapters" % (EPUB.name, sections, chapters))
    if not check_epub_text.check(MD, EPUB):
        sys.exit(1)


if __name__ == "__main__":
    main()
