"""Regression tests for Work/extract.py. Run from the project root:

    python -m unittest discover -s Work/tests
"""
import os
import sys
import tempfile
import unittest

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import extract  # noqa: E402
from common import ends_sentence, strip_comments  # noqa: E402
from extract import DocEvidence, RepairLog, join_lines, join_pages, strip_chapter_heading  # noqa: E402


def plain_pages(*args, **kwargs):
    """join_pages output with page markers removed."""
    return [strip_comments(p) for p in join_pages(*args, **kwargs)]


class PageMarkers(unittest.TestCase):
    def test_marker_above_paragraph_that_starts_a_page(self):
        paras = join_pages([(4, ["First.", "Second."]), (5, ["Third."])])
        self.assertEqual(paras, ["<!-- page 4 -->\nFirst.", "Second.", "<!-- page 5 -->\nThird."])

    def test_marker_inline_where_paragraph_runs_on(self):
        paras = join_pages([(4, ["The treaty was"]), (5, ["signed in 1919."])])
        self.assertEqual(paras, ["<!-- page 4 -->\nThe treaty was <!-- page 5 --> signed in 1919."])

    def test_marker_inside_hyphenated_word(self):
        paras = join_pages([(4, ["the popu-"]), (5, ["lation grew."])])
        self.assertEqual(paras, ["<!-- page 4 -->\nthe popu<!-- page 5 -->lation grew."])

    def test_markers_do_not_change_word_count(self):
        from count_words import words_in_text
        body = "\n\n".join(join_pages([(4, ["The treaty was"]), (5, ["signed. The popu-"]), (6, ["lation grew."])]))
        self.assertEqual(words_in_text(body), 7)
        self.assertEqual(strip_comments(body), "The treaty was signed. The population grew.")


class StripChapterHeading(unittest.TestCase):
    def test_short_title_keeps_body_containing_title(self):
        paras = ["War", "The war began in the spring.", "It ended in autumn."]
        self.assertEqual(strip_chapter_heading(paras, "War"), paras[1:])

    def test_body_paragraph_equal_to_part_of_title_is_kept(self):
        paras = ["The war began in the spring.", "War", "More text."]
        self.assertEqual(strip_chapter_heading(paras, "War"), paras)

    def test_empty_title_strips_nothing(self):
        paras = ["One.", "Two.", "Three.", "Four.", "Five."]
        self.assertEqual(strip_chapter_heading(paras, ""), paras)

    def test_empty_title_strips_chapter_number_only(self):
        paras = ["3", "Body text."]
        self.assertEqual(strip_chapter_heading(paras, "", 3), ["Body text."])

    def test_number_and_title_split_over_blocks(self):
        paras = ["Chapter 3", "The Long", "War", "Body text.", "More."]
        self.assertEqual(strip_chapter_heading(paras, "The Long War", 3), ["Body text.", "More."])

    def test_partial_title_followed_by_body_is_kept(self):
        paras = ["The Long", "Road ahead was clear."]
        self.assertEqual(strip_chapter_heading(paras, "The Long War"), paras)

    def test_missing_heading_is_logged(self):
        log = RepairLog()
        strip_chapter_heading(["Body text."], "War", log=log, page=5)
        self.assertEqual(log.kinds(), ["heading-not-found"])


class JoinPages(unittest.TestCase):
    def test_unpunctuated_paragraph_within_page_is_not_merged(self):
        pages = [(1, ["The rules are as follows", "First, arrive on time."])]
        self.assertEqual(plain_pages(pages), ["The rules are as follows", "First, arrive on time."])

    def test_paragraph_continues_across_page_break(self):
        log = RepairLog()
        pages = [(1, ["Intro.", "The treaty was"]), (2, ["signed in 1919.", "Next paragraph."])]
        self.assertEqual(plain_pages(pages, log=log), ["Intro.", "The treaty was signed in 1919.", "Next paragraph."])
        self.assertEqual(log.rows[0][1:3], ("1-2", "page-join"))

    def test_lowercase_block_within_page_joins(self):
        log = RepairLog()
        pages = [(3, ["Each party shall never develop, produce or", "stockpile such weapons.", "(b) Transfer them."])]
        self.assertEqual(plain_pages(pages, log=log),
                         ["Each party shall never develop, produce or stockpile such weapons.", "(b) Transfer them."])
        self.assertEqual(log.rows[0][1:3], (3, "block-join"))

    def test_only_first_block_of_next_page_joins(self):
        pages = [(1, ["The treaty was"]), (2, ["signed.", "and this stays separate"])]
        self.assertEqual(plain_pages(pages), ["The treaty was signed.", "and this stays separate"])

    def test_heading_shaped_page_end_is_flagged_not_joined(self):
        log = RepairLog()
        paras = plain_pages([(1, ["The rules are as follows"]), (2, ["First, arrive on time."])], log=log)
        self.assertEqual(paras, ["The rules are as follows", "First, arrive on time."])
        self.assertEqual(log.kinds(), ["page-break-unjoined"])

    def test_capitalized_continuation_is_joined_and_flagged(self):
        log = RepairLog()
        a = "Delegates from every member state travelled to the conference held at"
        paras = plain_pages([(1, [a]), (2, ["Northbridge in the summer of 1919."])], log=log)
        self.assertEqual(paras, [a + " Northbridge in the summer of 1919."])
        self.assertEqual(log.kinds(), ["page-join-uncertain"])

    def test_sentence_end_does_not_join(self):
        pages = [(1, ["Done."]), (2, ["and more."])]
        self.assertEqual(plain_pages(pages), ["Done.", "and more."])

    def test_hyphen_across_page_break(self):
        pages = [(1, ["They agreed to co-"]), (2, ["operate fully."])]
        self.assertEqual(plain_pages(pages, DocEvidence({"co-operate"})), ["They agreed to co-operate fully."])


class JoinLines(unittest.TestCase):
    def test_hyphen_before_capital_has_no_space(self):
        self.assertEqual(join_lines(["the Anglo-", "Saxon kings"]), "the Anglo-Saxon kings")

    def test_hyphen_before_digit_has_no_space(self):
        self.assertEqual(join_lines(["in the pre-", "1990 era"]), "in the pre-1990 era")

    def test_hyphen_after_digit_has_no_space(self):
        self.assertEqual(join_lines(["a 12-", "member council"]), "a 12-member council")

    def test_document_spelling_wins_over_dictionary(self):
        log = RepairLog()
        self.assertEqual(join_lines(["to co-", "operate"], DocEvidence({"co-operate"}), log=log), "to co-operate")
        self.assertEqual(log.kinds(), ["hyphen-kept"])
        self.assertIn("(document)", log.rows[0][3])

    def test_dictionary_repair_is_logged(self):
        log = RepairLog()
        self.assertEqual(join_lines(["the popu-", "lation"], log=log, page=7), "the population")
        self.assertEqual(log.rows, [("", 7, "hyphen-removed", "popu- / lation -> population (dictionary)")])

    def test_compound_of_two_known_words_keeps_hyphen_and_is_logged(self):
        log = RepairLog()
        self.assertEqual(join_lines(["a well-", "known fact"], log=log), "a well-known fact")
        self.assertEqual(log.kinds(), ["hyphen-kept"])
        self.assertIn("uncertain", log.rows[0][3])
        self.assertEqual(join_lines(["poverty-", "stricken towns"]), "poverty-stricken towns")

    def test_known_prefix_keeps_hyphen(self):
        log = RepairLog()
        self.assertEqual(join_lines(["a non-", "antagonistic view"], log=log), "a non-antagonistic view")
        self.assertIn("(prefix)", log.rows[0][3])

    def test_acronym_stem_keeps_hyphen(self):
        self.assertEqual(join_lines(["the NATO-", "led force"]), "the NATO-led force")

    def test_unverifiable_break_in_hyphenating_document_joins_and_is_logged(self):
        log = RepairLog()
        self.assertEqual(join_lines(["the Zwor-", "kowski estate"], log=log), "the Zworkowski estate")
        self.assertEqual(log.kinds(), ["hyphen-removed"])
        self.assertIn("uncertain", log.rows[0][3])

    def test_compound_of_two_words_is_flagged(self):
        log = RepairLog()
        self.assertEqual(join_lines(["it was point-", "less"], log=log), "it was pointless")
        self.assertIn("uncertain", log.rows[0][3])

    def test_document_without_word_breaks_keeps_hyphens(self):
        ev = DocEvidence(hyphenates=False)
        self.assertEqual(join_lines(["a life-", "saving drug"], ev), "a life-saving drug")
        self.assertEqual(join_lines(["the non-", "military aid"], ev), "the non-military aid")
        ev.forms.add("takeover")
        self.assertEqual(join_lines(["the take-", "over"], ev), "the take-over")

    def test_hyphen_in_url_is_kept_without_logging(self):
        log = RepairLog()
        self.assertEqual(join_lines(["see https://example.org/u-", "s-report.html."], log=log),
                         "see https://example.org/u-s-report.html.")
        self.assertEqual(log.rows, [])

    def test_url_wrapped_after_slash_joins_without_space(self):
        self.assertEqual(join_lines(["see https://example.org/reports/", "2019/annual.pdf for"]),
                         "see https://example.org/reports/2019/annual.pdf for")
        self.assertEqual(join_lines(["at https://example.org/search?q=", "war"]),
                         "at https://example.org/search?q=war")

    def test_url_wrapped_after_dot_joins_before_url_text(self):
        self.assertEqual(join_lines(["at www.example.", "com/data."]), "at www.example.com/data.")
        self.assertEqual(join_lines(["at https://data.", "example.org."]), "at https://data.example.org.")

    def test_url_ending_a_sentence_keeps_the_space(self):
        log = RepairLog()
        self.assertEqual(join_lines(["see www.example.com.", "The next"], log=log),
                         "see www.example.com. The next")
        self.assertEqual(join_lines(["see www.example.com", "for details"], log=log),
                         "see www.example.com for details")
        self.assertEqual(log.rows, [])

    def test_ambiguous_url_dot_is_logged(self):
        log = RepairLog()
        self.assertEqual(join_lines(["see www.example.com.", "then more"], log=log, page=4),
                         "see www.example.com. then more")
        self.assertEqual(log.kinds(), ["url-join-uncertain"])

    def test_plain_slash_word_is_not_a_url_wrap_unless_it_ends_in_slash(self):
        self.assertEqual(join_lines(["either and/or.", "Next"]), "either and/or. Next")


class Headings(unittest.TestCase):
    def test_heading_with_note_number(self):
        paras = ["4", "The Long War2", "Body text."]
        self.assertEqual(strip_chapter_heading(paras, "The Long War", 4), ["Body text."])

    def test_title_word_with_digit_is_not_a_note_number(self):
        paras = ["Plan B2", "Body text."]
        self.assertEqual(strip_chapter_heading(paras, "Plan B2"), ["Body text."])


class ListMarkers(unittest.TestCase):
    def test_list_item_on_next_page_is_not_joined(self):
        for item in ["(e) Assist the parties.", "4. The next note.", "12 Another note, 2020.", "• A bullet."]:
            pages = [(1, ["Members shall not: (d) acquire devices;"]), (2, [item])]
            self.assertEqual(len(plain_pages(pages)), 2, item)

    def test_closing_quote_or_bracket_ends_sentence(self):
        self.assertTrue(ends_sentence("as the minister put it, ‘we will not.’"))
        self.assertTrue(ends_sentence("[Written before the war.]"))
        self.assertFalse(ends_sentence("the workers’"))


class Hyphenation(unittest.TestCase):
    def detect(self, lines):
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        for i, text in enumerate(lines):
            page.insert_text((72, 72 + 14 * i), text, fontsize=11)
        return DocEvidence.from_doc(doc)

    def test_typeset_document_breaks_words(self):
        ev = self.detect(["the popu-", "lation of the", "country and its", "popula-", "tion grew with its",
                          "govern-", "ment and the", "political government", "govern-", "ment of the population."])
        self.assertTrue(ev.hyphenates)

    def test_reflowed_document_does_not(self):
        ev = self.detect(["a life-", "saving drug and", "a life-saving", "cure with the non-", "military",
                          "and non-military aid", "we saw a", "self-", "made man, self-made."])
        self.assertFalse(ev.hyphenates)


def make_pdf(path, pages):
    """pages: list of [(y, text)] placed at the left margin of a Letter page."""
    doc = pymupdf.open()
    for items in pages:
        page = doc.new_page(width=612, height=792)
        for y, text in items:
            page.insert_text((72, y), text, fontsize=11)
    doc.save(path)
    doc.close()


class BlockParagraphs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "t.pdf")

    def tearDown(self):
        self.tmp.cleanup()

    def paras(self, items, log=None):
        make_pdf(self.path, [items])
        with pymupdf.open(self.path) as doc:
            return extract.block_paragraphs(doc[0], 0, 10000, log=log)

    def test_number_in_table_is_kept_and_page_number_dropped(self):
        log = RepairLog()
        paras = self.paras([(100, "Population by year."), (300, "1990"), (500, "More text."), (760, "12")], log)
        self.assertEqual(paras, ["Population by year.", "1990", "More text."])
        self.assertEqual(log.rows, [("", 1, "furniture-dropped", "12")])

    def test_number_at_top_of_page_is_dropped(self):
        self.assertEqual(self.paras([(40, "xii 14"), (60, "7"), (200, "Body.")]), ["xii 14", "7", "Body."])
        self.assertEqual(self.paras([(40, "14"), (200, "Body.")]), ["Body."])

    def test_date_stamp_mid_page_is_kept(self):
        self.assertEqual(self.paras([(100, "Body."), (300, "01/02/2020 10:11:12"), (500, "End.")]),
                         ["Body.", "01/02/2020 10:11:12", "End."])


class Extractor(unittest.TestCase):
    def test_chapter_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_pdf(os.path.join(tmp, "src.pdf"), [
                [(100, "War"), (200, "The war began in the spring and the treaty was"), (760, "1")],
                [(100, "signed in 1919 by the Anglo-Saxon powers."), (300, "1990"), (760, "2")],
            ])
            old = extract.SOURCES
            extract.SOURCES = tmp
            try:
                log = RepairLog()
                cfg = {"pdf": "src.pdf", "header_ymax": 0, "footer_ymin": 10000}
                ch = {"unit_id": "ch-01", "title": "War", "start": 1, "end": 2}
                paras = [strip_comments(p) for p in extract.make_extractor(cfg, log)(ch)]
            finally:
                extract.SOURCES = old
        self.assertEqual(paras, [
            "The war began in the spring and the treaty was signed in 1919 by the Anglo-Saxon powers.",
            "1990",
        ])
        self.assertEqual(log.kinds(), ["furniture-dropped", "furniture-dropped", "heading-stripped", "page-join"])


class Ligatures(unittest.TestCase):
    def test_presentation_forms_are_expanded(self):
        spans = [{"font": "F", "size": 10, "chars": [
            {"c": c, "bbox": (i * 5, 0, i * 5 + 5, 10)} for i, c in enumerate("ﬁrst ﬄuid")]}]
        self.assertEqual(extract.line_text(spans), "first ffluid")


class SpaceRepair(unittest.TestCase):
    def chars(self, groups):
        out, x = [], 0
        for word in groups:
            for c in word:
                out.append({"c": c, "bbox": (x, 0, x + 5, 10)})
                x += 5
            x += 3  # a gap with no space glyph
        return [{"font": "Serif", "size": 10, "chars": out}]

    def test_gap_without_space_glyph_gets_a_space_for_listed_font(self):
        spans = self.chars(["the", "war"])
        self.assertEqual(extract.line_text(spans), "thewar")
        self.assertEqual(extract.line_text(spans, {"Serif": 0.2}), "the war")

    def test_gap_below_threshold_is_not_a_space(self):
        self.assertEqual(extract.line_text(self.chars(["the", "war"]), {"Serif": 0.5}), "thewar")


class AltTitle(unittest.TestCase):
    def test_alternate_heading_spelling_is_stripped(self):
        paras = ["2", "The Quiet Harhour", "Body text."]
        out = strip_chapter_heading(paras, "The Quiet Harbour", 2, alt=["The Quiet Harhour"])
        self.assertEqual(out, ["Body text."])


class Epub(unittest.TestCase):
    XHTML = (
        '<html><head><title>x</title></head><body>'
        '<h2 class="chno"><a id="page_11"/>1</h2>'
        '<h2 class="chtitle">The Title</h2>'
        '<p>First paragraph runs on to <a id="page_12"/>the next page.</p>'
        '<p><a id="page_13"/>Second paragraph.</p>'
        '</body></html>'
    )

    def test_headings_dropped_and_page_markers_kept(self):
        paras = extract.epub_paragraphs(self.XHTML, {"unit_id": "ch-01", "title": "The Title"},
                                        heading_classes=["chno", "chtitle"])
        self.assertEqual(paras, [
            "<!-- page 11 -->",
            "First paragraph runs on to <!-- page 12 --> the next page.",
            "<!-- page 13 -->\nSecond paragraph.",
        ])

    def test_custom_anchor_and_heading_classes(self):
        xhtml = ('<body><h1 class="chapter-head"><span id="pg5"></span>Title</h1>'
                 '<p>Body.</p></body>')
        paras = extract.epub_paragraphs(xhtml, {"unit_id": "ch-01", "title": "Title"},
                                        anchor="pg", heading_classes=["chapter-head"])
        self.assertEqual(paras, ["<!-- page 5 -->", "Body."])

    def test_missing_heading_is_logged(self):
        log = RepairLog()
        extract.epub_paragraphs("<body><p>Body.</p></body>", {"unit_id": "ch-01", "title": "T"}, log)
        self.assertEqual(log.kinds(), ["heading-not-found"])


class LonePunctuation(unittest.TestCase):
    def test_stray_period_block_is_dropped(self):
        self.assertTrue(extract.LONE_PUNCT.match("."))
        self.assertFalse(extract.LONE_PUNCT.match("1990"))


if __name__ == "__main__":
    unittest.main()
