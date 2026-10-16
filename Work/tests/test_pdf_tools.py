"""Tests for the two PDF text-layer tools: pdf_to_paged_txt.py (a paged text
for TXT mode) and rebuild_from_pdf.py (docling lines rebuilt from the PDF),
with source_helpers.rebuilt_lines. The PDFs are drawn here with PyMuPDF.
Run from the project root:

    python -m unittest discover -s Work/tests
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import extract  # noqa: E402
import pdf_to_paged_txt as paged  # noqa: E402
import rebuild_from_pdf as rebuild  # noqa: E402
import source_helpers  # noqa: E402
from extract import RepairLog  # noqa: E402

FONTS = {}


def font(style):
    if style not in FONTS:
        FONTS[style] = pymupdf.Font("tiit" if style == "i" else "tiro")
    return FONTS[style]


def draw(page, x, y, segments, size=10.0):
    """Draw [(text, style)] from baseline (x, y).

    Styles: "r" roman, "i" italic, "s" superscript (smaller, raised), "a" a
    space glyph drawn over the end of the glyph before it (an artifact
    space, as some text layers have inside words).
    """
    tw = pymupdf.TextWriter(page.rect)
    for text, style in segments:
        if style == "s":
            tw.append((x, y - 0.35 * size), text, font=font("r"), fontsize=0.6 * size)
            x += font("r").text_length(text, fontsize=0.6 * size)
        elif style == "a":
            tw.append((x - font("r").text_length(" ", fontsize=size), y), " ", font=font("r"), fontsize=size)
        else:
            tw.append((x, y), text, font=font(style), fontsize=size)
            x += font(style).text_length(text, fontsize=size)
    tw.write_text(page)


def r(text):
    return [(text, "r")]


# Ada Penhale, The Grey Harbour, four pages: (x, baseline, size, segments) per
# line. Body 10 pt at 13 pt spacing from x 40, paragraphs indented to 52; a
# 16 pt heading; a quotation in 9 pt indented to 56; a footnote in 8 pt.
BOOK = [
    [(40, 70, 16, r("Chapter One")),
     (52, 100, 10, r("The boats came “home” at dawn—late, as the")),
     (40, 113, 10, [("offi", "r"), (" ", "a"), ("cial log of ", "r"), ("The Grey Harbour", "i"), (" shows. The", "r")]),
     (40, 126, 10, r("long-standing rule held: no boat left the quay—")),
     (40, 139, 10, r("and the boats waited for the tide to turn.")),
     (52, 152, 10, r("It was a slow life, and it con-")),
     (40, 165, 10, r("tinued so for years; the long-")),
     (40, 178, 10, r("standing quarrel with the board went on,"))],
    [(40, 100, 10, r("and no one could say when it would end. The")),
     (40, 113, 10, r("board wrote to Ada Penhale:")),
     (56, 130, 9, r("The quay is unsafe and must be closed until")),
     (56, 141.7, 9, r("the spring, when it will be rebuilt.")),
     (40, 160, 10, [("She kept the letter in ", "r"), ("Notes on the", "i")]),
     (40, 173, 10, [("Tide Tables", "i"), (" and wrote no reply.", "r"), ("1", "s")]),
     (52, 186, 10, r("Nothing more was heard of it, though the")),
     (40, 360, 8, r("1 Her reply, if any, is lost."))],
    [(40, 100, 10, r("board met again in May.")),
     (52, 113, 10, r("The tide tables, at least, were kept in good")),
     (40, 126, 10, r("order by the board."))],
    [(40, 100, 10, r("And so the story ends."))],
]
HEAD = "THE GREY HARBOUR"


def make_pdf(path, pages, head=HEAD):
    """A 300 x 420 pt PDF: each page's lines, a running head at y 30, and a folio at y 400."""
    doc = pymupdf.open()
    for no, lines in enumerate(pages, 1):
        page = doc.new_page(width=300, height=420)
        if head:
            draw(page, 110, 30, r(head), 8)
        for x, y, size, segments in lines:
            draw(page, x, y, segments, size)
        draw(page, 148, 400, r(str(no)), 8)
    doc.save(path)
    return path


# The same book as a docling export: quotation marks flattened, dashes as
# hyphens, italics lost, "The boats" run together, a line-end hyphen kept
# with a space, "long-standing" lost its hyphen, the paragraph that a
# footnote interrupts in the PDF joined, the note after it (out of the
# PDF's order), an image placeholder, and a line the PDF does not have.
BOOK_MD = "\n".join([
    "## Chapter One",                                                                       # 1
    "",
    "Theboats came 'home' at dawn-late, as the official log of The Grey Harbour shows. "
    "The longstanding rule held: no boat left the quay-and the boats waited for the tide to turn.",  # 3
    "",
    "It was a slow life, and it con- tinued so for years; the longstanding quarrel with the board went on,",  # 5
    "",
    "and no one could say when it would end. The board wrote to Ada Penhale:",             # 7
    "",
    "The quay is unsafe and must be closed until the spring, when it will be rebuilt.",    # 9
    "",
    "She kept the letter in Notes on the Tide Tables and wrote no reply. 1",               # 11
    "",
    "Nothing more was heard of it, though the board met again in May.",                    # 13
    "",
    "1 Her reply, if any, is lost.",                                                       # 15
    "",
    "<!-- image -->",                                                                      # 17
    "",
    "The tide tables, at least, were kept in good order by the board.",                    # 19
    "",
    "And so the story ends.",                                                              # 21
    "",
    "A line docling invented &amp; the PDF lacks.",                                         # 23
]) + "\n"

REBUILT = {
    3: "The boats came “home” at dawn—late, as the official log of *The Grey Harbour* shows. "
       "The long-standing rule held: no boat left the quay—and the boats waited for the tide to turn.",
    5: "It was a slow life, and it continued so for years; the long-standing quarrel with the board went on,",
    11: "She kept the letter in *Notes on the Tide Tables* and wrote no reply. 1",
}

PAGE_TEXTS = [
    "@@furniture THE GREY HARBOUR\nChapter One\n\n"
    "The boats came “home” at dawn—late, as the\n"
    "official log of *The Grey Harbour* shows. The\n"
    "long-standing rule held: no boat left the quay—and\n"
    "the boats waited for the tide to turn.\n\n"
    "It was a slow life, and it con-\ntinued so for years; the long-\nstanding quarrel with the board went on,\n"
    "@@furniture 1\n",
    "@@furniture THE GREY HARBOUR\nand no one could say when it would end. The\nboard wrote to Ada Penhale:\n\n"
    "The quay is unsafe and must be closed until\nthe spring, when it will be rebuilt.\n\n"
    "She kept the letter in *Notes on the\nTide Tables* and wrote no reply.1\n\n"
    "Nothing more was heard of it, though the\n\n1 Her reply, if any, is lost.\n@@furniture 2\n",
    "@@furniture THE GREY HARBOUR\nboard met again in May.\n\n"
    "The tide tables, at least, were kept in good\norder by the board.\n@@furniture 3\n",
    "@@furniture THE GREY HARBOUR\nAnd so the story ends.\n@@furniture 4\n",
]


def quiet(fn, *args, **kwargs):
    out = io.StringIO()
    with redirect_stdout(out):
        result = fn(*args, **kwargs)
    return result, out.getvalue()


class Book(unittest.TestCase):
    """A temporary folder holding the test book's PDF and its docling export."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        self.pdf = make_pdf(os.path.join(self.tmp, "book.pdf"), BOOK)
        self.md = os.path.join(self.tmp, "book.md")
        with open(self.md, "w", encoding="utf-8", newline="\n") as f:
            f.write(BOOK_MD)

    def path(self, name):
        return os.path.join(self.tmp, name)

    def pages(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read().split("\f")


class PagedTextTool(Book):
    """pdf_to_paged_txt: form feeds, blocks, furniture, italics, artifact spaces, closed dashes."""

    def test_pages_blocks_furniture_italics_and_dashes(self):
        summary = paged.write_paged_txt(self.pdf, self.path("paged.txt"), paged.Layout(header_ymax=40))
        self.assertEqual(self.pages(self.path("paged.txt")), PAGE_TEXTS + [""])
        self.assertEqual(extract.txt_page_texts(self.path("paged.txt")), PAGE_TEXTS)
        self.assertEqual(summary["pages"], 4)
        self.assertEqual(summary["furniture lines"], 8)
        self.assertEqual(summary["artifact spaces dropped"], 1)
        self.assertEqual(summary["dash joins"], 1)
        self.assertEqual(summary["italic runs"], 2)
        # p. 3 opens flush after a page ending in a footnote, p. 4 after "order by the board."
        self.assertEqual(summary["run-on pages"], [3, 4])
        self.assertEqual(summary["moved"], [])

    def test_move_run_on_moves_a_body_line_but_never_a_footnote(self):
        summary = paged.write_paged_txt(self.pdf, self.path("paged.txt"), paged.Layout(header_ymax=40), move_run_on=True)
        self.assertEqual(summary["moved"], [(3, "order by the board.")])
        pages = self.pages(self.path("paged.txt"))
        self.assertEqual(pages[1], PAGE_TEXTS[1])
        self.assertEqual(pages[2], "@@furniture THE GREY HARBOUR\nboard met again in May.\n\n"
                                   "The tide tables, at least, were kept in good\n@@furniture 3\n")
        self.assertEqual(pages[3], "@@furniture THE GREY HARBOUR\norder by the board.\nAnd so the story ends.\n"
                                   "@@furniture 4\n")

    def test_without_italics_or_header_cutoff(self):
        paged.write_paged_txt(self.pdf, self.path("plain.txt"), paged.Layout(italics=False))
        pages = self.pages(self.path("plain.txt"))
        self.assertNotIn("*", "".join(pages))
        self.assertIn("official log of The Grey Harbour shows.", pages[0])
        # No header_ymax: the running head is a body line; a bare folio is furniture all the same.
        self.assertTrue(pages[0].startswith("THE GREY HARBOUR\n\nChapter One\n"))
        self.assertTrue(pages[0].endswith("went on,\n@@furniture 1\n"))

    def test_italic_font_regex_and_superscript_size(self):
        with pymupdf.open(self.pdf) as doc:
            by_name = paged.PagedText(doc, paged.Layout(header_ymax=40, italic_font="Italic")).body_rows(2)
            none = paged.PagedText(doc, paged.Layout(header_ymax=40, italic_font="Oblique")).body_rows(2)
            line = paged.page_lines(doc[1], paged.Layout(superscript_max=6.5))[6]
            first_page = paged.page_lines(doc[0], paged.Layout())
        self.assertIn("She kept the letter in *Notes on the", by_name)
        self.assertIn("She kept the letter in Notes on the", none)
        self.assertEqual([g.c for g in line.glyphs if g.sup], ["1"])
        self.assertFalse(any(g.sup for ln in first_page for g in ln.glyphs))

    def test_superscript_from_shape(self):
        with pymupdf.open(self.pdf) as doc:
            line = paged.page_lines(doc[1], paged.Layout())[6]
        self.assertEqual(line.text(), "*Tide Tables* and wrote no reply.1")
        self.assertEqual([g.c for g in line.glyphs if g.sup], ["1"])

    def test_hanging_indent_pages(self):
        notes = [[(40, 100, 10, r("1. A note set with a hanging indent, which")),
                  (50, 113, 10, r("runs on to a second line.")),
                  (40, 126, 10, r("2. The next note."))]]
        pdf = make_pdf(self.path("notes.pdf"), notes, head=None)
        with pymupdf.open(pdf) as doc:
            usual = paged.PagedText(doc).body_rows(1)
            hanging = paged.PagedText(doc, hanging_pages={1}).body_rows(1)
        # Read as first-line indents, the run-on line starts a block and the next note joins it.
        self.assertEqual(usual, ["1. A note set with a hanging indent, which", "", "runs on to a second line.",
                                 "2. The next note."])
        self.assertEqual(hanging, ["1. A note set with a hanging indent, which", "runs on to a second line.",
                                   "", "2. The next note."])

    def test_lines_beside_a_drop_cap_continue_its_paragraph(self):
        cap = [[(40, 113, 30, r("T")),
                (62, 100, 10, r("he harbour lay quiet in the")),
                (62, 113, 10, r("winter, and the boats were")),
                (40, 126, 10, r("drawn up on the shingle.")),
                (52, 139, 10, r("A new paragraph."))]]
        pdf = make_pdf(self.path("cap.pdf"), cap, head=None)
        with pymupdf.open(pdf) as doc:
            rows = paged.PagedText(doc).body_rows(1)
        # The cap comes first (extract.join_drop_caps joins it to "he"), and no block starts beside it.
        self.assertEqual(rows, ["T", "he harbour lay quiet in the", "winter, and the boats were",
                                "drawn up on the shingle.", "", "A new paragraph."])
        md = self.path("cap.md")
        with open(md, "w", encoding="utf-8") as f:
            f.write("The harbour lay quiet in the winter, and the boats were drawn up on the shingle.\n")
        changed, report = rebuild.rebuild_lines(md, pdf, [1])
        self.assertEqual((changed, report["how"][1][0]), ({}, "found"))

    def test_layout_listing(self):
        _, out = quiet(paged.main, ["--pdf", self.pdf, "--layout", "2", "--header-ymax", "40"])
        self.assertIn("page 2 (300 x 420 pt)", out)
        self.assertIn("head  THE GREY HARBOUR  [NimbusRoman-Regular]", out)
        self.assertIn("size  9.00", out)
        self.assertIn("*Tide Tables* and wrote no reply.1  [NimbusRoman-Italic,NimbusRoman-Regular]", out)
        self.assertIn("foot  2", out)

    def test_cli_writes_the_file(self):
        _, out = quiet(paged.main, ["--pdf", self.pdf, "--out", self.path("cli.txt"), "--header-ymax", "40"])
        self.assertEqual(self.pages(self.path("cli.txt"))[:4], PAGE_TEXTS)
        self.assertIn("pages whose first line runs a paragraph on", out)


class PagedTextInTxtMode(Book):
    """The builder as a config's build_txt, extracted by extract.py in TXT mode."""

    def setUp(self):
        super().setUp()
        saved = (extract.SOURCES, extract.OUT, extract.RAW, extract.ROOT)
        self.addCleanup(lambda: setattr(extract, "SOURCES", saved[0]) or setattr(extract, "OUT", saved[1])
                        or setattr(extract, "RAW", saved[2]) or setattr(extract, "ROOT", saved[3]))
        extract.SOURCES = os.path.join(self.tmp, "Sources")
        extract.OUT = os.path.join(self.tmp, "Chapters")
        extract.RAW = os.path.join(self.tmp, "Raw")
        extract.ROOT = self.tmp

    def extract(self, **options):
        cfg = {"slug": "penhale-grey-harbour", "txt": "Work/Raw/penhale-grey-harbour/paged.txt",
               "build_txt": paged.paged_txt_builder(self.pdf, header_ymax=40, **options),
               "paragraphs": "blank_lines", "header_patterns": paged.FURNITURE_PATTERNS,
               "footer_patterns": paged.FURNITURE_PATTERNS, "hyphenates": True}
        _, out = quiet(extract.ensure_txt, cfg)
        log = RepairLog()
        ex = quiet(extract.make_txt_extractor, cfg, log)[0]
        paras = ex({"unit_id": "ch-01", "start": 1, "end": 4, "first_line": "The boats came"})
        return [extract.strip_comments(p) for p in paras], log, out

    def test_paragraphs_from_the_paged_text(self):
        paras, log, out = self.extract()
        self.assertIn("building", out)
        self.assertIn("ending a sentence (TXT mode starts a new paragraph unless move_run_on): 3, 4", out)
        self.assertEqual(paras, [
            "The boats came “home” at dawn—late, as the official log of *The Grey Harbour* shows. "
            "The long-standing rule held: no boat left the quay—and the boats waited for the tide to turn.",
            "It was a slow life, and it continued so for years; the long-standing quarrel with the board went on, "
            "and no one could say when it would end. The board wrote to Ada Penhale:",
            "The quay is unsafe and must be closed until the spring, when it will be rebuilt.",
            "She kept the letter in *Notes on the Tide Tables* and wrote no reply.1",
            "Nothing more was heard of it, though the",
            "1 Her reply, if any, is lost.",
            "board met again in May.",
            "The tide tables, at least, were kept in good order by the board.",
            "And so the story ends.",
        ])
        dropped = [row[3] for row in log.rows if row[2] == "furniture-dropped"]
        self.assertEqual(dropped, [s for no in range(1, 5) for s in ("@@furniture " + HEAD, "@@furniture %d" % no)])

    def test_moved_run_on_line_rejoins_its_paragraph(self):
        paras, _, out = self.extract(move_run_on=True)
        self.assertIn("moved from p. 3 to p. 4: order by the board.", out)
        self.assertEqual(paras[-1], "The tide tables, at least, were kept in good order by the board. "
                                    "And so the story ends.")


class RebuildTool(Book):
    """rebuild_from_pdf: docling lines rebuilt from the PDF, letters and digits unchanged."""

    def rebuild(self, lines="1-23", md=None, **layout):
        layout.setdefault("header_ymax", 40)
        return rebuild.rebuild_lines(md or self.md, self.pdf, rebuild.parse_ranges(lines),
                                     paged.Layout(**layout), hyphenates=True)

    def test_rebuilds_quotes_dashes_italics_spaces_and_hyphens(self):
        changed, report = self.rebuild()
        self.assertEqual(changed, REBUILT)
        for no, text in changed.items():
            self.assertEqual(source_helpers.skeleton(text), source_helpers.skeleton(BOOK_MD.split("\n")[no - 1]))
        self.assertEqual({no: how[0] for no, how in report["how"].items()},
                         {1: "found", 3: "found", 5: "found", 7: "found", 9: "found", 11: "found",
                          13: "in pieces", 15: "out of order", 19: "found", 21: "found"})
        self.assertEqual(report["how"][13], ("in pieces", [2, 3], 2))
        self.assertEqual([(no, why) for no, _, why in report["unmatched"]], [(23, "not found")])
        self.assertEqual(report["skipped"], {"blank": 11, "comment": 1})
        self.assertEqual([h[:4] for h in report["hyphens"]], [(5, "con", "tinued", False), (5, "long", "standing", True)])
        self.assertEqual(report["counts"]["curly quotation marks"], (0, 2))
        self.assertEqual(report["counts"]["em dashes"], (0, 2))
        self.assertEqual(report["counts"]["italic runs"], (0, 2))

    def test_report_text(self):
        _, report = self.rebuild()
        text = rebuild.format_report(report, "Work/Proof/penhale-grey-harbour.rebuilt.json")
        self.assertIn("23 in range, 12 skipped (blank 11, comment 1), 10 matched (found 8, in pieces 1, "
                      "out of order 1), 1 not matched, 3 changed -> Work/Proof/penhale-grey-harbour.rebuilt.json", text)
        self.assertIn("curly quotation marks          0 -> 2", text)
        self.assertIn("lines with changed quotation marks: 1 (2 gaps)", text)
        self.assertIn("lines with changed italics: 2", text)
        self.assertIn("MD 23: not found: A line docling invented &amp; the PDF lacks.", text)
        self.assertIn("MD 13: in pieces, PDF p. 2-3, 2 pieces", text)
        self.assertIn("MD 15: out of order, PDF p. 2", text)

    def test_hyphenation_detected_from_the_document(self):
        changed, report = rebuild.rebuild_lines(self.md, self.pdf, [5], paged.Layout(header_ymax=40))
        # Two line-end hyphens are too few to show that the book breaks words.
        self.assertFalse(report["hyphenates"])
        self.assertEqual(changed[5], "It was a slow life, and it con-tinued so for years; the long-standing quarrel "
                                     "with the board went on,")

    def test_note_number_spacing_and_an_export_without_note_numbers(self):
        md = self.path("notes.md")
        with open(md, "w", encoding="utf-8") as f:
            f.write("She kept the letter in Notes on the Tide Tables and wrote no reply 1\n\n"
                    "She kept the letter in Notes on the Tide Tables and wrote no reply.\n")
        changed, report = self.rebuild("1-3", md)
        self.assertEqual(changed[1], "She kept the letter in *Notes on the Tide Tables* and wrote no reply. 1")
        self.assertEqual(changed[3], "She kept the letter in *Notes on the Tide Tables* and wrote no reply.")
        self.assertEqual(report["how"][3][0], "out of order")

    def test_markdown_prefix_entities_and_no_italics(self):
        md = self.path("prefix.md")
        with open(md, "w", encoding="utf-8") as f:
            f.write("> Theboats came 'home' at dawn-late, as the official log of The Grey Harbour shows.\n")
        changed, _ = self.rebuild("1", md)
        self.assertEqual(changed[1], "> The boats came “home” at dawn—late, as the official log of "
                                     "*The Grey Harbour* shows.")
        changed, _ = self.rebuild("1", md, italics=False)
        self.assertNotIn("*", changed[1])

    def test_without_header_cutoff_the_running_head_is_skipped_in_pieces(self):
        changed, report = self.rebuild(header_ymax=None)
        self.assertEqual(changed, REBUILT)
        self.assertEqual(report["how"][13][0], "in pieces")

    def test_ranges_and_skips(self):
        self.assertEqual(rebuild.parse_ranges("3-5,1,9-9"), [1, 3, 4, 5, 9])
        with self.assertRaises(SystemExit):
            rebuild.parse_ranges("5-3")
        self.assertEqual(rebuild.skip_reasons(["", "| a |", "```", "x", "```", "<!-- page break -->", "--", "Text"]),
                         ["blank", "table", "fence", "fence", "fence", "comment", "no letters", None])
        with self.assertRaises(SystemExit) as cm:
            self.rebuild("20-30")
        self.assertIn("are not in the file (1-23)", str(cm.exception))

    def test_cli_writes_only_changed_lines(self):
        out_path = self.path("Proof/penhale-grey-harbour.rebuilt.json")
        _, out = quiet(rebuild.main, ["--md", self.md, "--pdf", self.pdf, "--lines", "1-23", "--header-ymax", "40",
                                      "--hyphenates", "yes", "--out", out_path, "--report"])
        with open(out_path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {str(k): v for k, v in REBUILT.items()})
        self.assertIn("3 changed -> " + out_path, out)
        _, out = quiet(rebuild.main, ["--md", self.md, "--pdf", self.pdf, "--lines", "1-23", "--header-ymax", "40",
                                      "--out", out_path])
        self.assertIn("lines changed -> " + out_path, out)


class RebuiltLines(Book):
    """source_helpers.rebuilt_lines feeds build_line_edits, which checks every line."""

    def setUp(self):
        super().setUp()
        saved = (source_helpers.SOURCES, source_helpers.PROOF)
        self.addCleanup(lambda: setattr(source_helpers, "SOURCES", saved[0]) or setattr(source_helpers, "PROOF", saved[1]))
        source_helpers.SOURCES = self.tmp
        source_helpers.PROOF = os.path.join(self.tmp, "Proof")
        changed, _ = rebuild.rebuild_lines(self.md, self.pdf, list(range(1, 24)), paged.Layout(header_ymax=40), True)
        self.json = os.path.join(self.tmp, "Proof", "penhale-grey-harbour.rebuilt.json")
        rebuild.write_rebuilt(self.json, changed)

    def test_rebuilt_lines_become_line_edits(self):
        lines = source_helpers.rebuilt_lines("penhale-grey-harbour")
        self.assertEqual(lines, REBUILT)
        self.assertEqual(source_helpers.build_line_edits("book.md", rebuilt=lines), REBUILT)

    def test_a_changed_word_stops_the_run(self):
        with open(self.json, encoding="utf-8") as f:
            data = json.load(f)
        data["5"] = data["5"].replace("continued", "went on")
        with open(self.json, "w", encoding="utf-8") as f:
            json.dump(data, f)
        with self.assertRaises(SystemExit) as cm:
            source_helpers.build_line_edits("book.md", rebuilt=source_helpers.rebuilt_lines("penhale-grey-harbour"))
        self.assertIn("book.md: line 5: rebuilt text changes letters or digits", str(cm.exception))

    def test_missing_file_stops_the_run(self):
        with self.assertRaises(SystemExit) as cm:
            source_helpers.rebuilt_lines("another-source")
        self.assertIn("another-source.rebuilt.json: not found", str(cm.exception))

    def test_entities_read_as_their_characters(self):
        with open(os.path.join(self.tmp, "e.md"), "w", encoding="utf-8") as f:
            f.write("Smith &amp; Sons &lt;1937&gt;\n")
        self.assertEqual(source_helpers.build_line_edits("e.md", rebuilt={1: "Smith & Sons <1937>"}),
                         {1: "Smith & Sons <1937>"})
        self.assertEqual(source_helpers.md_entities("a &amp; b &#8212; c & d"), "a & b — c & d")


if __name__ == "__main__":
    unittest.main()
