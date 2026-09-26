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


class PagedText(unittest.TestCase):
    """The paged .txt path: furniture, drop caps, dehyphenation, paragraphs."""

    def test_running_heads_and_page_number_dropped_from_top(self):
        cfg = {"header_patterns": [r"^[A-Z][A-Z’'.,:&\- ]+$"]}
        lines = ["4", "", "HARBOR", "", "TOWN HISTORY", "", "connections to the text."]
        self.assertEqual([l for l in extract.strip_txt_furniture(lines, cfg) if l], ["connections to the text."])

    def test_header_scan_stops_at_first_body_line(self):
        cfg = {"header_patterns": [r"^[A-Z][A-Z ]+$"]}
        lines = ["HARBOR", "Body text starts here.", "ALL CAPS BODY LINE"]
        self.assertEqual([l for l in extract.strip_txt_furniture(lines, cfg) if l],
                         ["Body text starts here.", "ALL CAPS BODY LINE"])

    def test_drop_cap_joins_word_or_stays_a_word(self):
        self.assertEqual([l for l in extract.join_drop_caps(["I", "", "n 1831 Edith"]) if l], ["In 1831 Edith"])
        self.assertEqual([l for l in extract.join_drop_caps(["U", "", ".S. Navy ships"]) if l], ["U.S. Navy ships"])
        self.assertEqual([l for l in extract.join_drop_caps(["I", "", "initially wrote"]) if l], ["I initially wrote"])
        self.assertEqual([l for l in extract.join_drop_caps(["“", "I", "", "n order to"]) if l], ["“In order to"])

    def test_compound_hyphen_restored_by_document_majority(self):
        ev = DocEvidence()
        ev.counts = {"working-class": 40, "workingclass": 5, "antiracist": 9, "anti-racist": 1}
        long_line = "x " * 60 + "workingclass women and antiracist work"
        out = extract.restore_compound_hyphens(long_line, ev, 76)
        self.assertIn("working-class women", out)
        self.assertIn("antiracist work", out)

    def test_compound_hyphen_fix_list_applies(self):
        ev = DocEvidence()
        ev.counts = {}
        out = extract.restore_compound_hyphens("the groupderived view", ev, 76, fixes={"groupderived": "group-derived"})
        self.assertEqual(out, "the group-derived view")

    def test_kerning_gap_restored(self):
        cfg = {"kerning_spaces": True}
        self.assertEqual(extract.apply_line_fixes(["the place.This is U.S.West and asked,“How"], cfg),
                         ["the place. This is U.S. West and asked, “How"])

    def test_line_fix_can_make_a_heading_block(self):
        cfg = {"line_fixes": {"O b j e c t s": "\nObjects\n"}}
        self.assertEqual(extract.apply_line_fixes(["O b j e c t s", "Body."], cfg), ["", "Objects", "", "Body."])

    def test_paragraphs_break_at_short_sentence_end_and_colon(self):
        lines = ["A full line of ordinary text that runs to the margin and on and on", "and ends here.",
                 "Next paragraph starts and it also runs all the way to the right margin", "describes this:",
                 "I used to feel that the boats would not come back, and this line runs long", "(Marlow 1986, 82)"]
        paras = extract.txt_paragraphs(lines, {}, DocEvidence(), 70)
        self.assertEqual(len(paras), 3)
        self.assertTrue(paras[1].endswith("describes this:"))

    def test_note_numbers_start_paragraphs(self):
        import re
        lines = ["1. First note text that runs on for a while and on to the right margin here", "ends here without much room left in the line",
                 "2. Second note."]
        paras = extract.txt_paragraphs(lines, {}, DocEvidence(), 70, para_start=re.compile(r"^\d{1,3}\.\s"))
        self.assertEqual(len(paras), 2)


class BlockQuotes(unittest.TestCase):
    """Block quotations are marked "> " so agents can tell them from the author's prose."""

    def test_colon_lead_in_to_block_citation(self):
        paras = ["Ines Marlow describes this change:", "I used to feel that. (Marlow 1986, 82)", "The author resumes."]
        out = extract.mark_block_quotes(paras)
        self.assertEqual(out, [paras[0], "> I used to feel that. (Marlow 1986, 82)", "The author resumes."])

    def test_verse_runs_to_standalone_citation_and_keeps_page_marker_first(self):
        paras = ["She sings:", "The tide came in.", "<!-- page 5 -->\nThe boats came home, late.", "(Penhale 1982, 133)", "Prose."]
        out = extract.mark_block_quotes(paras)
        self.assertEqual(out[1:4], ["> The tide came in.", "<!-- page 5 -->\n> The boats came home, late.", "> (Penhale 1982, 133)"])
        self.assertEqual(out[4], "Prose.")

    def test_no_citation_marks_first_paragraph_only_and_logs_it(self):
        log = RepairLog()
        out = extract.mark_block_quotes(["He said:", "Quoted words here.", "Her own prose."], log)
        self.assertEqual(out[1:], ["> Quoted words here.", "Her own prose."])
        self.assertIn("blockquote-nocite", log.kinds())

    def test_short_verse_line_after_lead_in_is_not_taken_for_a_heading(self):
        out = extract.mark_block_quotes(["Consider this verse:", "Low the moon and long the road", "(Penhale 1984, 144)"])
        self.assertTrue(out[1].startswith("> "))

    def test_citation_without_lead_in_and_epigraph(self):
        out = extract.mark_block_quotes(["For centuries the valley served. (Arden 1981, 42)",
                                         "The river keeps its counsel so far as I can see. —Ada Penhale 1937, 16",
                                         "Her words end “here” (Smith 1990, 4)."])
        self.assertEqual([p[:2] for p in out], ["> ", "> ", "He"])

    def test_note_numbers_never_start_a_quotation(self):
        import re
        out = extract.mark_block_quotes(["1. A note ending:", "2. Next note."], item_start=re.compile(r"^\d{1,3}\.\s"))
        self.assertEqual(out, ["1. A note ending:", "2. Next note."])

    def test_fixes_join_start_add_remove(self):
        fixes = {"join": ["control of knowledge:"], "start": ["In the harbor novels"],
                 "add": ["When will you come?"], "remove": ["Dealing with"]}
        paras = ["They exercise control of knowledge:", "<!-- page 81 -->\nThey are the planners.",
                 "It is essential. In the harbor novels this change occurs. (Lund 1983, xxiv)",
                 "She sings:", "Where did you go?", "When will you come?",
                 "Dealing with it, “we are late” (Arden 1996, 106)"]
        out = extract.mark_block_quotes(paras, fixes=fixes)
        self.assertEqual(out, [
            "They exercise control of knowledge: <!-- page 81 --> They are the planners.",
            "It is essential.",
            "> In the harbor novels this change occurs. (Lund 1983, xxiv)",
            "She sings:", "> Where did you go?", "> When will you come?",
            "Dealing with it, “we are late” (Arden 1996, 106)"])

    def test_colon_line_breaks_paragraph_before_capital_but_not_lowercase(self):
        cfg = {"block_quotes": True}
        lines = ["A line of ordinary text that runs to the margin and describes this:",
                 "They are the planners of work.",
                 "Prose runs to the margin again and creates three characters:",
                 "a young domestic worker and a mother in her thirties."]
        paras = extract.txt_paragraphs(lines, cfg, DocEvidence(), 70)
        self.assertEqual(len(paras), 3)
        self.assertTrue(paras[2].startswith("Prose runs") and paras[2].endswith("thirties."))

    def test_block_citation_line_ends_paragraph_at_any_width(self):
        cfg = {"block_quotes": True}
        lines = ["quoted words that run all the way to the right margin and end. (Marlow 1986, 82)",
                 "The harbor workers have been talking about it ever since then."]
        self.assertEqual(len(extract.txt_paragraphs(lines, cfg, DocEvidence(), 70)), 2)
