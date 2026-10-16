"""Tests for the PDF renderer's text escaping, the PDF text check, the
output name, Edge printing, and the EPUB build and its text check. Run from
the project root:

    python -m unittest discover -s Work/tests

Edge is not run here: the escaping is tested through Python-Markdown with
the renderer's configuration, the comparison on synthetic word lists and
PDFs drawn with PyMuPDF, and printing with a fake subprocess.run that
writes the PDF itself. The EPUB tests need ebooklib and are skipped
without it.
"""
import io
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from contextlib import redirect_stdout
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_pdf  # noqa: E402
import check_epub_text  # noqa: E402
import check_pdf_text as cpt  # noqa: E402
from build_pdf import markdown_source, markdown_to_html, output_name, parse_lines  # noqa: E402


class _Text(HTMLParser):
    """Collects text content and the tags seen."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.tags = [], []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.parts.append(data)


def render(md):
    """(text content with whitespace collapsed, [(tag, attrs)]) of the rendered HTML."""
    parser = _Text()
    parser.feed(markdown_to_html(md))
    parser.close()
    return " ".join("".join(parser.parts).split()), parser.tags


def squash(text):
    return " ".join(text.split())


def tag_names(tags):
    return [t for t, _ in tags]


class Escaping(unittest.TestCase):
    def assertProse(self, md):
        """md renders as plain paragraphs whose text is md itself."""
        text, tags = render(md)
        self.assertEqual(text, squash(md))
        self.assertEqual(set(tag_names(tags)), {"p"}, tags)

    def test_emphasis_characters_kept(self):
        self.assertProse("An _under_ word, **strong**, __dunder__, and snake_case_name.")
        self.assertProse("A star* after a word, a* b, 2 * 3, and one at the end*")

    def test_single_asterisk_spans_are_italics(self):
        text, tags = render("The *polis*, 100*C*+100*V*, and *Starts with a star* but ends with one*")
        self.assertEqual(text, "The polis, 100C+100V, and Starts with a star but ends with one*")
        self.assertEqual(tag_names(tags), ["p", "em", "em", "em", "em"])
        text, tags = render("A *word with <b> & _x_* stays escaped inside.")
        self.assertEqual(text, "A word with <b> & _x_ stays escaped inside.")
        self.assertEqual(tag_names(tags), ["p", "em"])

    def test_raw_angle_brackets_kept(self):
        self.assertProse("Text with <b>tags</b>, <http://example.com>, a <placeholder> and 3 < 4 > 2.")
        self.assertProse("<div>block-level html</div>")
        self.assertProse("<!-- a comment -->")

    def test_backslashes_and_entities_kept(self):
        self.assertProse(r"A \* star, a \\ pair, a C:\path\to\file and a trailing \ ")
        self.assertProse("AT&T, &amp; &lt;x&gt; &copy; &#169; and & alone.")

    def test_inline_markdown_kept(self):
        self.assertProse("`code` [link](http://x.org) ![img](y.png) [ref][1] {: .cls} a|b ~~~ [^1]")
        self.assertProse("[1]: http://example.com")
        self.assertProse("*[HTML]: Hyper Text")

    def test_number_period_paragraph_is_not_a_list(self):
        md = "1984. The year began badly.\n\nAnother paragraph."
        self.assertProse(md)

    def test_year_paragraphs_counting_up_are_not_a_list(self):
        self.assertProse("1984. The year began.\n\n1985. The next year.")

    def test_lone_bullet_paragraphs_are_not_lists(self):
        self.assertProse("- Lone dash paragraph.")
        self.assertProse("+ Lone plus paragraph.")
        self.assertProse("* Lone star paragraph.")
        self.assertProse("- Dash paragraph.\n\n+ Plus paragraph.")
        self.assertProse("1. A lone numbered paragraph.")

    def test_block_level_markers_kept(self):
        for md in ("Setext\n===", "Setext\n---", "---", "* * *", "___",
                   "    indented code", "Term\n: definition", "a | b\n--|--\nc | d",
                   "```\nfence\n```", "~~~\nfence\n~~~", "Hard  \nbreak",
                   "#hashtag at start", "#### Too deep for a heading"):
            with self.subTest(md=md):
                self.assertProse(md)

    def test_typography_untouched(self):
        md = "\u201cCurly\u201d \u2018quotes\u2019, it\u2019s\u2026 an en \u2013 and em \u2014 dash, \"straight\" 'quotes' -- and ... too."
        self.assertProse(md)
        self.assertIn("\u201cCurly\u201d", markdown_to_html(md))

    def test_bullet_list_kept(self):
        md = "Intro:\n\n- first *a*\n- second <b>\n- third"
        text, tags = render(md)
        self.assertEqual(text, squash("Intro: first a second <b> third"))
        self.assertEqual(tag_names(tags), ["p", "ul", "li", "em", "li", "li"])

    def test_loose_bullet_list_kept(self):
        text, tags = render("- one\n\n- two")
        self.assertEqual(text, "one two")
        self.assertEqual(tag_names(tags).count("li"), 2)

    def test_numbered_list_kept(self):
        text, tags = render("1. alpha\n2. beta\n3. gamma")
        self.assertEqual(text, "alpha beta gamma")
        self.assertEqual(tag_names(tags), ["ol", "li", "li", "li"])
        self.assertEqual(tags[0][1], {})

    def test_numbered_list_from_later_start_needs_adjacent_items(self):
        text, tags = render("4. delta\n5. epsilon")
        self.assertEqual(text, "delta epsilon")
        self.assertEqual(tags[0], ("ol", {"start": "4"}))
        self.assertProse("4. delta\n\n5. epsilon")

    def test_numbered_list_skipping_a_number_stops(self):
        md = "1. alpha\n2. beta\n\n7. gamma"
        text, tags = render(md)
        self.assertEqual(text, "alpha beta 7. gamma")
        self.assertEqual(tag_names(tags), ["ol", "li", "li", "p"])

    def test_wrong_number_inside_list_stays_text(self):
        text, tags = render("1. alpha\n2. beta\n1984. gamma")
        self.assertEqual(text, "alpha beta 1984. gamma")
        self.assertEqual(tag_names(tags).count("li"), 2)

    def test_adjacent_lists_are_not_joined(self):
        text, tags = render("1984. a\n1985. b\n\n9. c\n10. d\n\n- e\n- f\n\n* g\n* h")
        self.assertEqual(text, "a b c d e f g h")
        self.assertEqual([t for t in tags if t[0] in ("ol", "ul")],
                         [("ol", {"start": "1984"}), ("ol", {"start": "9"}), ("ul", {}), ("ul", {})])
        words = cpt.markdown_words("1984. a\n1985. b\n\n9. c\n10. d")[0]
        self.assertEqual(words, ["1984.", "a", "1985.", "b", "9.", "c", "10.", "d"])

    def test_leading_zero_is_not_a_list(self):
        self.assertProse("01. alpha\n02. beta")

    def test_block_quote_kept_and_escaped(self):
        md = "Lead-in:\n\n> Quoted *text* with 1984. and <tag> and \\ and _x_.\n>\n> - not a list\n>\n> # not a heading"
        text, tags = render(md)
        self.assertEqual(text, squash("Lead-in: Quoted text with 1984. and <tag> and \\ and _x_. "
                                      "- not a list # not a heading"))
        self.assertEqual(tag_names(tags), ["p", "blockquote", "p", "em", "p", "p"])
        self.assertTrue(markdown_source(md).splitlines()[2].startswith("> Quoted"))

    def test_list_inside_block_quote_kept(self):
        text, tags = render("> - one\n> - two")
        self.assertEqual(text, "one two")
        self.assertEqual(tag_names(tags), ["blockquote", "ul", "li", "li"])

    def test_nested_quote_marker_stays_text(self):
        text, tags = render("> > inner")
        self.assertEqual(text, "> inner")
        self.assertEqual(tag_names(tags), ["blockquote", "p"])

    def test_headings_kept(self):
        md = "# Part 1: *Title* by A_Author\n\n## Chapter #2 ##\n\n### Sub <x>\n\nBody."
        text, tags = render(md)
        self.assertEqual(text, squash("Part 1: Title by A_Author Chapter #2 ## Sub <x> Body."))
        self.assertEqual(tag_names(tags), ["h1", "em", "h2", "h3", "p"])

    def test_heading_line_inside_block(self):
        text, tags = render("Para\n## Heading\nMore")
        self.assertEqual(text, "Para Heading More")
        self.assertEqual(tag_names(tags), ["p", "h2", "p"])

    def test_summary_shaped_document(self):
        md = ("# Introduction\n\nThis covers *one* source.\n\n# Part 1: A Book by A. Writer\n\n"
              "## Chapter One\n\n1984. The year it began.\n\nAs one witness put it:\n\n"
              "> \u201cWe saw *nothing*\u2026\u201d\n>\n> 2. said she.\n\nThe list:\n\n"
              "1. one\n2. two\n\n### After\n\nEnd \u2014 fin.\n")
        text, tags = render(md)
        self.assertEqual(text, squash(
            "Introduction This covers one source. Part 1: A Book by A. Writer Chapter One "
            "1984. The year it began. As one witness put it: \u201cWe saw nothing\u2026\u201d "
            "2. said she. The list: one two After End \u2014 fin."))
        self.assertEqual(tag_names(tags), ["h1", "p", "em", "h1", "h2", "p", "p", "blockquote", "p", "em",
                                           "p", "p", "ol", "li", "li", "h3", "p"])


class ParseLines(unittest.TestCase):
    def test_line_numbers_and_kinds(self):
        lines = parse_lines("# H\n\n- a\n- b\n> q")
        self.assertEqual([(l.lineno, l.kind, l.quote) for l in lines],
                         [(1, "heading", False), (2, "blank", False), (3, "item", False),
                          (4, "item", False), (5, "prose", True)])


class Words(unittest.TestCase):
    def test_markdown_words_strip_markup_but_keep_list_numbers(self):
        words, where, headings = cpt.markdown_words("## Ch\n\n> Quoted *x*\n\n- a\n- b\n\n3. c\n4. d\n\n1984. e")
        self.assertEqual(words, ["Ch", "Quoted", "x", "a", "b", "3.", "c", "4.", "d", "1984.", "e"])
        self.assertEqual(where, [1, 3, 3, 5, 6, 8, 8, 9, 9, 11, 11])
        self.assertEqual(headings, [(1, "##", ["Ch"])])

    def test_markdown_words_without_list_numbers(self):
        # The EPUB check: an e-reader draws an <ol>'s numbers, so they are not in the text.
        words = cpt.markdown_words("3. c\n4. d\n\n1984. e", list_numbers=False)[0]
        self.assertEqual(words, ["c", "d", "1984.", "e"])

    def test_tokens_split_where_lines_may_break(self):
        self.assertEqual(cpt.tokens("self-evident and/or here\u2014there"),
                         ["self-", "evident", "and/", "or", "here", "\u2014", "there"])

    def test_clean(self):
        self.assertEqual(cpt.clean("\ufb01ne evi\u00addent zero\u200bwidth"), "fine evident zerowidth")

    def test_layout_hyphen_joined_real_hyphen_kept(self):
        md = "an evident and self-evident truth"
        lines = [(1, "an evi-"), (1, "dent and self-"), (2, "evident truth")]
        words, pages = cpt.pdf_words(lines, md)
        self.assertEqual(words, cpt.markdown_words(md)[0])
        # "self-evident" is joined onto the line where it starts.
        self.assertEqual(pages, [1, 1, 1, 1, 1, 2])

    def test_hyphen_kept_when_both_forms_unknown(self):
        words, _ = cpt.pdf_words([(1, "a well-"), (1, "made b")], "a well-made b")
        self.assertEqual(words, ["a", "well-", "made", "b"])
        words, _ = cpt.pdf_words([(1, "a co-"), (1, "op b")], "a coop b")
        self.assertEqual(words, ["a", "coop", "b"])

    def test_break_without_space_joined(self):
        md = "see [x](y) and the cat"
        words, _ = cpt.pdf_words([(1, "see [x]"), (1, "(y) and the"), (1, "cat")], md)
        self.assertEqual(words, cpt.markdown_words(md)[0])

    def test_soft_hyphen_at_line_end_joined(self):
        words, _ = cpt.pdf_words([(1, "evi\u00ad"), (1, "dent")], "evi\u00addent")
        self.assertEqual(words, ["evident"])


class Compare(unittest.TestCase):
    def test_equal(self):
        words = "a b c d e f g h".split()
        self.assertEqual(cpt.compare(words, list(words)), [])

    def test_changed_word(self):
        a = "one two three four five six seven eight nine ten".split()
        b = "one two THREE four five six seven eight nine ten".split()
        self.assertEqual(cpt.compare(a, b), [(2, 3, 2, 3)])

    def test_missing_and_extra_words(self):
        a = "w0 w1 w2 w3 w4 w5 w6 w7 w8 w9 w10 w11 w12 w13 w14 w15".split()
        b = "w0 w1 w4 w5 w6 w7 w8 w9 X Y w10 w11 w12 w13 w14 w15".split()
        self.assertEqual(cpt.compare(a, b), [(2, 4, 2, 2), (10, 10, 8, 10)])

    def test_difference_at_end(self):
        a = "a b c d".split()
        self.assertEqual(cpt.compare(a, a[:3]), [(3, 4, 3, 3)])
        self.assertEqual(cpt.compare(a[:3], a), [(3, 3, 3, 4)])

    def test_repeated_words_do_not_confuse_alignment(self):
        a = ("the cat and the dog and the bird " * 5).split()
        b = list(a)
        del b[17]
        diffs = cpt.compare(a, b)
        self.assertEqual(len(diffs), 1)
        i0, i1, j0, j1 = diffs[0]
        self.assertEqual((i1 - i0, j1 - j0), (1, 0))
        self.assertEqual(a[:i0] + a[i1:], b)

    def test_describe_gives_line_page_and_context(self):
        a = "one two three four".split()
        b = "one two 3 four".split()
        d = cpt.compare(a, b)[0]
        text = cpt.describe(d, a, [1, 1, 2, 2], b, [1, 1, 1, 1])
        self.assertIn("Summary.md line 2, PDF page 1", text)
        self.assertIn("Markdown: [three]", text)
        self.assertIn("PDF:      [3]", text)
        self.assertIn("one two [...] four", text)
        text = cpt.describe(d, a, [1, 1, 2, 2], b, ["a.xhtml"] * 4, found="EPUB", unit="file")
        self.assertIn("Summary.md line 2, EPUB file a.xhtml", text)
        self.assertIn("EPUB:     [3]", text)


class CheckPdf(unittest.TestCase):
    """check() on small PDFs drawn with PyMuPDF (no browser)."""

    MD = "# Introduction\n\nOne *two* three.\n\n## Chapter\n\n1984. Four five six seven.\n"

    def run_check(self, pages, md=MD):
        import pymupdf
        with tempfile.TemporaryDirectory() as tmp:
            md_path, pdf_path = os.path.join(tmp, "s.md"), os.path.join(tmp, "s.pdf")
            with open(md_path, "w", encoding="utf-8") as fh:
                fh.write(md)
            doc = pymupdf.open()
            for n, lines in enumerate(pages, 1):
                page = doc.new_page(width=612, height=792)
                for k, line in enumerate(lines):
                    page.insert_text((72, 90 + 16 * k), line, fontname="helv", fontsize=11)
                page.insert_text((303, 750), str(n), fontname="helv", fontsize=10)
            doc.save(pdf_path)
            doc.close()
            out = io.StringIO()
            with redirect_stdout(out):
                ok = cpt.check(md_path, pdf_path)
        return ok, out.getvalue()

    def test_matching_pdf_passes(self):
        # The Markdown's *two* is printed in italics, without its asterisks.
        ok, out = self.run_check([["Introduction", "One two three."],
                                  ["Chapter", "1984. Four five six", "seven."]])
        self.assertTrue(ok, out)
        self.assertIn("OK", out)

    def test_changed_text_fails_with_context(self):
        ok, out = self.run_check([["Introduction", "One too three."],
                                  ["Chapter", "1984. Four five six seven."]])
        self.assertFalse(ok)
        self.assertIn("Markdown: [two]", out)
        self.assertIn("PDF:      [too]", out)
        self.assertIn("Summary.md line 3, PDF page 1", out)

    def test_missing_heading_and_blank_page_fail(self):
        ok, out = self.run_check([["Introduction", "One *two* three."], [],
                                  ["1984. Four five six seven."]])
        self.assertFalse(ok)
        self.assertIn("page 2 is blank", out)
        self.assertIn("heading missing from the PDF (Summary.md line 5): ## Chapter", out)

    def test_spacing_only_difference_is_a_warning(self):
        ok, out = self.run_check([["Introduction", "One two three."],
                                  ["Chapter", "1984. Four fivesix seven."]])
        self.assertTrue(ok, out)
        self.assertIn("warning: spacing differs", out)

    def test_literal_asterisks_are_a_warning(self):
        # **bold** copied from a source is not an italic span: it prints, and matches, literally.
        md = "# Introduction\n\nOne **two** three, 2 * 3.\n"
        ok, out = self.run_check([["Introduction", "One **two** three, 2 * 3."]], md)
        self.assertTrue(ok, out)
        self.assertIn("warning: 5 literal asterisk(s) in the PDF text", out)
        ok, out = self.run_check([["Introduction", "One two three, 2 3."]], md)
        self.assertFalse(ok)
        self.assertNotIn("literal asterisk", out)


class OutputName(unittest.TestCase):
    def test_default_title(self):
        self.assertEqual(output_name("Summary"), "Summary")
        self.assertEqual(os.path.basename(build_pdf.PDF), build_pdf.OUTPUT_NAME + ".pdf")
        self.assertEqual(os.path.basename(check_epub_text.EPUB), build_pdf.OUTPUT_NAME + ".epub")

    def test_punctuation_separates_words(self):
        self.assertEqual(output_name("The Grey Harbour: Essays"), "The-Grey-Harbour-Essays")
        self.assertEqual(output_name(" The Grey Harbour \u2014 Essays, 1890\u20131910 "),
                         "The-Grey-Harbour-Essays-1890-1910")
        self.assertEqual(output_name("Harbour\u2014Essays"), "Harbour-Essays")

    def test_apostrophes_dropped(self):
        self.assertEqual(output_name("Ada Penhale's Harbour"), "Ada-Penhales-Harbour")
        self.assertEqual(output_name("Ada Penhale\u2019s Harbour"), "Ada-Penhales-Harbour")

    def test_accented_letters_folded(self):
        self.assertEqual(output_name("\u00c9conomie du Caf\u00e9"), "Economie-du-Cafe")
        self.assertEqual(output_name("S\u00f8ren\u2019s Stra\u00dfe, \u0141\u00f3d\u017a"),
                         "Sorens-Strasse-Lodz")

    def test_title_without_ascii_letters_gives_summary(self):
        self.assertEqual(output_name(": \u2014 ?!"), "Summary")
        self.assertEqual(output_name(""), "Summary")


COMPLETE_PDF = b"%PDF-1.4\n% test\ntrailer\n<<>>\n%%EOF\n"


def write_later(path, data, delay, mode="wb"):
    """Start a timer that writes data to path after delay seconds, as Edge has been seen to; return it."""
    def write():
        with open(path, mode) as fh:
            fh.write(data)
    timer = threading.Timer(delay, write)
    timer.start()
    return timer


class WaitForPdf(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = os.path.join(tmp.name, "out.pdf")

    def test_file_written_late_is_found(self):
        timer = write_later(self.path, COMPLETE_PDF, 0.3)
        self.addCleanup(timer.cancel)
        self.assertTrue(build_pdf._wait_for_pdf(self.path, timeout=10))

    def test_partly_written_file_is_waited_for(self):
        # No %%EOF yet: the file is not taken until its end is written.
        first = write_later(self.path, COMPLETE_PDF[:-6], 0.1)
        rest = write_later(self.path, COMPLETE_PDF[-6:], 1.3, "ab")
        self.addCleanup(first.cancel)
        self.addCleanup(rest.cancel)
        start = time.monotonic()
        self.assertTrue(build_pdf._wait_for_pdf(self.path, timeout=10))
        self.assertGreaterEqual(time.monotonic() - start, 1.3)
        with open(self.path, "rb") as fh:
            self.assertEqual(fh.read(), COMPLETE_PDF)

    def test_no_file_times_out(self):
        start = time.monotonic()
        with mock.patch.object(build_pdf, "PDF_WAIT", 0.6):
            self.assertFalse(build_pdf._wait_for_pdf(self.path))
        self.assertLess(time.monotonic() - start, 5)


class PrintPdf(unittest.TestCase):
    """print_pdf with subprocess.run and the DevTools route faked: no Edge is launched."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp_pdf = os.path.join(tmp.name, "printed.pdf")
        self.html = os.path.join(tmp.name, "summary.html")
        self.calls, self.timers = [], []
        self.addCleanup(lambda: [t.cancel() for t in self.timers])

    def fake_run(self, outcomes):
        """A subprocess.run stand-in. outcomes, one per call: "late" (exit 0, then write the
        PDF 0.5 s later), "none" (exit 0, no PDF), or "hang" (time out)."""
        outcomes = list(outcomes)

        def run(cmd, **kwargs):
            self.calls.append(cmd)
            outcome = outcomes.pop(0)
            if outcome == "hang":
                raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))
            if outcome == "late":
                out = next(a.split("=", 1)[1] for a in cmd if a.startswith("--print-to-pdf="))
                self.timers.append(write_later(out, COMPLETE_PDF, 0.5))
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return run

    def print_pdf(self, outcomes, wait, devtools):
        with mock.patch.object(build_pdf.subprocess, "run", self.fake_run(outcomes)), \
                mock.patch.object(build_pdf, "PDF_WAIT", wait), \
                mock.patch.object(build_pdf, "print_pdf_devtools", devtools):
            return build_pdf.print_pdf("msedge", self.tmp_pdf, self.html)

    def test_pdf_written_after_edge_returns_is_used(self):
        devtools = mock.Mock()
        route = self.print_pdf(["late"], 10, devtools)
        self.assertEqual(route, "--print-to-pdf --headless=new")
        self.assertEqual(len(self.calls), 1)
        devtools.assert_not_called()
        with open(self.tmp_pdf, "rb") as fh:
            self.assertEqual(fh.read(), COMPLETE_PDF)

    def test_timeout_moves_on_to_the_next_mode(self):
        route = self.print_pdf(["hang", "late"], 10, mock.Mock())
        self.assertEqual(route, "--print-to-pdf --headless")
        self.assertIn("--headless=new", self.calls[0])
        self.assertIn("--headless", self.calls[1])

    def test_every_route_failing_names_all_three(self):
        devtools = mock.Mock(side_effect=RuntimeError("no Edge here"))
        with self.assertRaises(SystemExit) as cm:
            self.print_pdf(["none", "none"], 0.6, devtools)
        message = str(cm.exception)
        self.assertEqual(len(self.calls), 2)
        self.assertIn("--headless=new: exit 0, no complete PDF", message)
        self.assertIn("--headless: exit 0, no complete PDF", message)
        self.assertIn("DevTools Page.printToPDF: no Edge here", message)
        devtools.assert_called_once()
        self.assertFalse(os.path.exists(self.tmp_pdf))


class EpubText(unittest.TestCase):
    def test_body_text_spaces_block_elements_not_inline_ones(self):
        text, headings, ems = check_epub_text.body_text(
            "<?xml version='1.0' encoding='utf-8'?>\n<!DOCTYPE html>\n<html><head><title>Head *x*</title>"
            "</head><body><h1>A <em>b</em>c</h1><p>d&amp;e</p><ol><li>f</li><li>g<br/>h</li></ol>"
            "<h2>i</h2></body></html>")
        self.assertEqual(text.split(), ["A", "bc", "d&e", "f", "g", "h", "i"])
        self.assertEqual([(tag, t.strip()) for tag, t in headings], [("h1", "A bc"), ("h2", "i")])
        self.assertEqual(ems, 1)


try:
    import build_epub
except ImportError:  # ebooklib is optional (requirements.txt)
    build_epub = None


@unittest.skipIf(build_epub is None, "ebooklib is not installed")
class Epub(unittest.TestCase):
    """build_epub.main() on a small Summary.md in a temporary directory, then check_epub_text."""

    MD = ("# Introduction\n\nThis covers *one* source.\n\n"
          "# Part 1: *The Grey Harbour* by Ada Penhale\n\nWhat the part holds.\n\n"
          "## Chapter One: *Tides*\n\nThe list:\n\n1. first\n2. second\n\n"
          "> Quoted <b> & _x_, 100*C*+100*V*.\n\n"
          "## Chapter Two\n\nA **bold** claim and a self-evident one.\n")

    def build(self, tmp):
        md, out = Path(tmp) / "Summary.md", Path(tmp) / "Test.epub"
        md.write_text(self.MD, encoding="utf-8")
        log = io.StringIO()
        with mock.patch.object(build_epub, "MD", md), mock.patch.object(build_epub, "EPUB", out), \
                redirect_stdout(log):
            build_epub.main()
        return md, out, log.getvalue()

    def test_build_passes_the_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            md, out, log = self.build(tmp)
            self.assertIn("wrote Test.epub: 2 sections, 2 chapters", log)
            # one, The Grey Harbour, Tides, C, V
            self.assertIn("5 italic spans (<em>)", log)
            self.assertIn("warning: 4 literal asterisk(s) in the EPUB text", log)
            self.assertIn("check_epub_text: OK", log)
            docs = dict(check_epub_text.spine_documents(out))
            self.assertEqual(list(docs), ["part00.xhtml", "part01.xhtml", "part01_ch01.xhtml",
                                          "part01_ch02.xhtml"])
            self.assertIn("<em>The Grey Harbour</em>", docs["part01.xhtml"])
            self.assertEqual(docs["part01.xhtml"].count("<h1"), 1)

    def test_table_of_contents_has_no_asterisks(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, out, _ = self.build(tmp)
            with zipfile.ZipFile(out) as z:
                for name in ("nav.xhtml", "toc.ncx"):
                    toc = next(z.read(n).decode("utf-8") for n in z.namelist() if n.endswith(name))
                    self.assertIn("Part 1: The Grey Harbour by Ada Penhale", toc)
                    self.assertIn("Chapter One: Tides", toc)
                    self.assertNotIn("*", toc)

    def test_check_fails_after_a_word_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            md, out, _ = self.build(tmp)
            md.write_text(self.MD.replace("second", "secnod"), encoding="utf-8")
            log = io.StringIO()
            with redirect_stdout(log):
                ok = check_epub_text.check(md, out)
            log = log.getvalue()
            self.assertFalse(ok)
            self.assertIn("1 text difference(s)", log)
            self.assertIn("EPUB file part01_ch01.xhtml", log)
            self.assertIn("Markdown: [secnod]", log)
            self.assertIn("EPUB:     [second]", log)

    def test_build_exits_1_when_the_check_fails(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(check_epub_text, "check", return_value=False):
            with self.assertRaises(SystemExit) as cm:
                self.build(tmp)
            self.assertEqual(cm.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
