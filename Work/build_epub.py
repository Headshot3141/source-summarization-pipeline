"""Build Summary.epub from Summary.md (optional deliverable).

Each `# ` heading (the introduction and each source part) becomes a section
page, and each `## ` chapter becomes its own EPUB page listed under its part
in the table of contents. The title comes from TITLE in Work/build_pdf.py.

Markdown is converted with Work/build_pdf.py's markdown_to_html, so the
text appears exactly as written (see that module's docstring for the rules).

Requires ebooklib (see requirements.txt). Run from the project root:

    python Work/build_epub.py
"""
import html
import re
import uuid

from ebooklib import epub

from build_pdf import TITLE, markdown_to_html
from common import ROOT

MD = ROOT / "Summary.md"
EPUB = ROOT / "Summary.epub"
LANGUAGE = "en"
# A stable identifier lets readers treat a rebuilt file as the same book.
IDENTIFIER = "urn:uuid:%s" % uuid.uuid5(uuid.NAMESPACE_URL, "summary:" + TITLE)

CSS = """
body { font-family: Georgia, "Times New Roman", serif; line-height: 1.5; margin: 0 0.5em; }
h1 { font-size: 1.6em; line-height: 1.3; margin: 2em 0 0.6em; text-align: center; }
h2 { font-size: 1.3em; line-height: 1.35; margin: 1em 0 0.6em; }
h3 { font-size: 1.05em; font-style: italic; margin: 1.2em 0 0.3em; }
blockquote { margin: 0 2em 0.65em; font-size: 0.95em; }
p { margin: 0 0 0.65em; text-align: justify; }
"""


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


def page(book, css, file_name, title, html):
    item = epub.EpubHtml(title=title, file_name=file_name, lang=LANGUAGE)
    item.content = html
    item.add_item(css)
    book.add_item(item)
    return item


def main():
    text = MD.read_text(encoding="utf-8")

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
        head = page(book, css, "part%02d.xhtml" % p_idx, p_title,
                    "<h1>%s</h1>\n%s" % (html.escape(p_title, quote=False), to_html(preamble)))
        spine.append(head)
        links = []
        for c_idx, (c_title, body) in enumerate(chapters, 1):
            item = page(book, css, "part%02d_ch%02d.xhtml" % (p_idx, c_idx), c_title,
                        to_html("## %s\n%s" % (c_title, body)))
            spine.append(item)
            links.append(item)
            chapter_count += 1
        if links:
            toc.append((epub.Section(p_title, href=head.file_name), links))
        else:
            toc.append(head)

    book.toc = toc
    book.spine = spine
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(EPUB), book)
    print("wrote %s: %d sections, %d chapters" % (EPUB.name, len(toc), chapter_count))


if __name__ == "__main__":
    main()
