"""Regression tests for Work/extract.py and the extraction helpers (source_helpers.py,
check_chapters.py, md_toc.py, count_words.words_of). Run from the project root:

    python -m unittest discover -s Work/tests
"""
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import check_chapters  # noqa: E402
import extract  # noqa: E402
import md_toc  # noqa: E402
import source_helpers  # noqa: E402
from common import ends_sentence, is_heading, parse_frontmatter, strip_comments  # noqa: E402
from count_words import words_of  # noqa: E402
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

    def test_skip_class_is_dropped_but_is_not_the_heading(self):
        log = RepairLog()
        xhtml = '<body><p>Body.</p><p class="nav">Next chapter</p></body>'
        paras = extract.epub_paragraphs(xhtml, {"unit_id": "ch-01", "title": "T"}, log,
                                        heading_classes=["h"], skip_classes=["nav"])
        self.assertEqual(paras, ["Body."])
        self.assertEqual(log.kinds(), ["heading-not-found"])

    def test_multi_file_chapter_keeps_later_headings(self):
        import zipfile
        files = {
            "OPS/a.htm": '<body><h2 class="t">Title</h2><p>One.</p></body>',
            "OPS/b.htm": '<body><h2 class="t">Section Two</h2><p>Two.</p><p class="nav">Index</p></body>',
        }
        with tempfile.TemporaryDirectory() as d:
            with zipfile.ZipFile(os.path.join(d, "x.epub"), "w") as z:
                for name, text in files.items():
                    z.writestr(name, text)
            old = extract.SOURCES
            extract.SOURCES = d
            try:
                cfg = {"epub": "x.epub", "epub_page_anchor": "", "epub_heading_classes": ["t"],
                       "epub_skip_classes": ["nav"]}
                log = RepairLog()
                ch = {"unit_id": "ch-01", "title": "Title", "files": ["OPS/a.htm", "OPS/b.htm"]}
                paras = extract.make_epub_extractor(cfg, log)(ch)
            finally:
                extract.SOURCES = old
        self.assertEqual(paras, ["One.", "Section Two", "Two."])
        self.assertEqual(log.kinds(), [])

    def test_file_and_files_are_exclusive(self):
        base = {"slug": "x", "epub": "x.epub", "part": 1}
        ch = {"unit_id": "ch-01", "slug": "c", "title": "T"}
        both = dict(base, chapters=[dict(ch, file="a.htm", files=["a.htm"])])
        none = dict(base, chapters=[dict(ch)])
        multi = dict(base, chapters=[dict(ch, files=["a.htm", "b.htm"])])
        self.assertTrue(any("both file and files" in e for e in extract.validate_config(both)))
        self.assertTrue(any("no EPUB file" in e for e in extract.validate_config(none)))
        self.assertEqual(extract.validate_config(multi), [])


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
        paras = ["Ida Marlow describes this change:", "I used to feel that. (Marlow 1986, 82)", "The author resumes."]
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
                                         "The river keeps its own counsel. —Ada Penhale 1937, 16",
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


class DoclingMarkdown(unittest.TestCase):
    """The docling Markdown path: chapter bounds, page breaks, unescaping, footnotes."""

    def extract(self, md, chapters, **cfg):
        """Run the Markdown extractor on md; return ({unit_id: paragraphs}, log)."""
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "src.md"), "w", encoding="utf-8", newline="\n") as f:
                f.write(md)
            old = extract.SOURCES
            extract.SOURCES = tmp
            try:
                log = RepairLog()
                cfg = dict(cfg, md="src.md", slug="src", chapters=chapters)
                ex = extract.make_md_extractor(cfg, log)
                return {ch["unit_id"]: ex(ch) for ch in chapters}, log
            finally:
                extract.SOURCES = old

    def one(self, body, title="War", **cfg):
        out, log = self.extract("## %s\n\n%s" % (title, body), [{"unit_id": "ch-01", "slug": "a", "title": title}], **cfg)
        return out["ch-01"], log

    def test_chapters_split_at_headings_and_headings_stripped(self):
        md = ("# The Book\n\n## Contents\n\nFront matter.\n\n## Chapter 1\n\n## The Long War\n\nWar began.\n\n"
              "## 2 The Peace\n\nPeace came.\n\n## Index\n\nwar, 1\n")
        chapters = [{"unit_id": "ch-01", "slug": "a", "title": "The Long War", "num": 1},
                    {"unit_id": "ch-02", "slug": "b", "title": "The Peace", "num": 2, "stop_line": "## Index"}]
        out, log = self.extract(md, chapters)
        self.assertEqual(out, {"ch-01": ["War began."], "ch-02": ["Peace came."]})
        self.assertEqual([r[3] for r in log.rows if r[2] == "heading-stripped"], ["Chapter 1", "The Long War", "2 The Peace"])
        self.assertEqual(log.kinds().count("no-page-markers"), 1)

    def test_page_breaks_become_page_markers(self):
        body = ("The treaty was\n\n<!-- page break -->\n\nsigned in 1919.\n\nNext paragraph.\n\n"
                "<!-- page break -->\n\nA new page starts here.\n")
        paras, log = self.one(body, first_page=5)
        self.assertEqual(paras, ["<!-- page 5 -->\nThe treaty was <!-- page 6 --> signed in 1919.",
                                 "Next paragraph.", "<!-- page 7 -->\nA new page starts here."])
        self.assertIn("page-break-joined", log.kinds())
        self.assertNotIn("no-page-markers", log.kinds())

    def test_pdf_pages_from_page_breaks(self):
        md = "## War\n\nFirst page.\n\n<!-- page break -->\n\nSecond page.\n"
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "src.md"), "w", encoding="utf-8") as f:
                f.write(md)
            old = extract.SOURCES, extract.OUT
            extract.SOURCES, extract.OUT = tmp, tmp
            try:
                cfg = {"md": "src.md", "slug": "src", "first_page": 3,
                       "chapters": [{"unit_id": "ch-01", "slug": "war", "title": "War", "num": None}]}
                self.assertEqual(extract.validate_config(cfg), [])
                extract.build_markdown("Book", 1, cfg["chapters"], extract.make_md_extractor(cfg), "src", "src.md")
                with open(os.path.join(tmp, "src", "01-war.md"), encoding="utf-8") as f:
                    text = f.read()
            finally:
                extract.SOURCES, extract.OUT = old
        self.assertIn('pdf_pages: "3-4"\n', text)
        self.assertIn("word_count: 4\n", text)
        self.assertTrue(text.endswith("# War\n\n<!-- page 3 -->\nFirst page.\n\n<!-- page 4 -->\nSecond page.\n"))

    def test_entities_and_backslash_escapes_are_undone(self):
        paras, _ = self.one("Smith &amp; Jones wrote \\_init\\_ and &lt;b&gt; for AT&T \\*not emphasis\\*.\n")
        self.assertEqual(paras, ["Smith & Jones wrote _init_ and <b> for AT&T *not emphasis*."])

    def test_image_and_formula_placeholders_dropped_and_logged(self):
        paras, log = self.one("Text before.\n\n<!-- image -->\n\n<!-- formula-not-decoded -->\n\nText after.\n")
        self.assertEqual(paras, ["Text before.", "Text after."])
        self.assertIn("image-placeholder", log.kinds())
        self.assertIn("formula-placeholder", log.kinds())

    def test_table_kept_as_one_block(self):
        table = "| Year | Count \\| total |\n|------|-------|\n| 1990 | 12 &lt; 13 |"
        paras, _ = self.one("Table 1 Counts\n\n" + table + "\n\nAfter.\n")
        self.assertEqual(paras, ["Table 1 Counts", "| Year | Count \\| total |\n|------|-------|\n| 1990 | 12 < 13 |", "After."])

    def test_list_items_kept(self):
        paras, _ = self.one("The rules are:\n\n- arrive on time\n- leave early\n")
        self.assertEqual(paras, ["The rules are:", "- arrive on time\n- leave early"])

    def test_footnotes_moved_and_interrupted_paragraph_rejoined(self):
        body = ("The treaty was\n\n1 A note on the treaty.\n\n2 Another note.\n\n<!-- page break -->\n\n"
                "signed in 1919.\n\nThe next paragraph.\n")
        paras, log = self.one(body, footnote_pattern=r"^\d{1,3}\s")
        self.assertEqual(paras, [
            "<!-- page 1 -->\nThe treaty was <!-- page 2 --> signed in 1919.",
            "The next paragraph.",
            extract.FOOTNOTES_LABEL,
            "<!-- footnote on page 1 -->\n1 A note on the treaty.",
            "<!-- footnote on page 1 -->\n2 Another note.",
        ])
        self.assertEqual(log.kinds().count("footnote-moved"), 2)
        self.assertIn("page-break-joined", log.kinds())

    def test_footnote_without_page_breaks_rejoins_paragraph(self):
        paras, log = self.one("The treaty was\n\n12 A note.\n\nsigned in 1919.\n", footnote_pattern=r"^\d{1,3}\s")
        self.assertEqual(paras, ["The treaty was signed in 1919.", extract.FOOTNOTES_LABEL, "12 A note."])
        self.assertEqual([k for k in log.kinds() if k.startswith("page-break")], ["page-break-joined"])

    def test_footnote_mid_page_is_kept_and_logged(self):
        body = "Body.\n\n1 Not a note but a numbered line.\n\nMore body.\n\n<!-- page break -->\n\nNext.\n"
        paras, log = self.one(body, footnote_pattern=r"^\d{1,3}\s")
        self.assertIn("1 Not a note but a numbered line.", paras)
        self.assertIn("footnote-candidate", log.kinds())

    def test_running_head_dropped_and_logged(self):
        body = "The treaty was\n\nHARBOR TOWN HISTORY\n\nsigned in 1919.\n\n## HARBOR TOWN HISTORY\n\nMore.\n"
        paras, log = self.one(body, header_patterns=[r"^HARBOR TOWN HISTORY$"])
        self.assertEqual(paras, ["The treaty was signed in 1919.", "More."])
        self.assertEqual(log.kinds().count("furniture-dropped"), 2)

    def test_source_block_quotes_kept(self):
        paras, log = self.one("She wrote:\n\n> The tide came in.\n> The boats came home.\n>\n> Second quoted paragraph.\n\nProse.\n")
        self.assertEqual(paras, ["She wrote:", "> The tide came in. The boats came home.",
                                 "> Second quoted paragraph.", "Prose."])
        self.assertIn("blockquote-source", log.kinds())

    def test_block_quote_detection_does_not_double_mark_or_touch_tables(self):
        body = "She wrote:\n\n> I used to feel that. (Marlow 1986, 82)\n\nAs shown:\n\n| a | b |\n|---|---|\n\nProse.\n"
        paras, _ = self.one(body, block_quotes=True)
        self.assertEqual(paras, ["She wrote:", "> I used to feel that. (Marlow 1986, 82)",
                                 "As shown:", "| a | b |\n|---|---|", "Prose."])

    def test_section_headings_become_plain_lines(self):
        paras, log = self.one("Intro.\n\n### A Section\n\nBody of section.\n")
        self.assertEqual(paras, ["Intro.", "A Section", "Body of section."])
        self.assertTrue(is_heading(paras[1]))
        self.assertIn("section-heading", log.kinds())

    def test_hyphen_space_logged_or_rejoined(self):
        paras, log = self.one("The popu- lation grew, pre- and post-war.\n")
        self.assertEqual(paras, ["The popu- lation grew, pre- and post-war."])
        self.assertEqual(log.kinds().count("hyphen-space-kept"), 1)
        paras, log = self.one("The popu- lation grew.\n", hyphen_spaces=True)
        self.assertEqual(paras, ["The population grew."])
        self.assertIn("hyphen-removed", log.kinds())

    def test_ligatures_normalized_and_bad_characters_logged(self):
        paras, log = self.one("The ﬁrst � mark GLYPH<c=3,font=/AB>.\n")
        self.assertEqual(paras, ["The first � mark GLYPH<c=3,font=/AB>."])
        self.assertIn("replacement-char", log.kinds())
        self.assertIn("glyph-placeholder", log.kinds())

    def test_raw_text_saved_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "src.md"), "w", encoding="utf-8", newline="\n") as f:
                f.write("## War\n\nA &amp; B.\n")
            old = extract.SOURCES, extract.RAW
            extract.SOURCES, extract.RAW = tmp, tmp
            try:
                with open(extract.save_md_raw({"md": "src.md", "slug": "src"}), encoding="utf-8") as f:
                    self.assertEqual(f.read(), "## War\n\nA &amp; B.\n")
            finally:
                extract.SOURCES, extract.RAW = old

    def test_list_like_footnotes_moved_and_paragraph_rejoined(self):
        body = ("The treaty was\n\n1. Harbor Board minutes, 1921.\n\n* Not in the first edition.\n\n"
                "<!-- page break -->\n\nsigned in 1919.\n")
        paras, log = self.one(body, footnote_pattern=r"^(?:\d{1,3}\.|\*)\s")
        self.assertEqual(paras, [
            "<!-- page 1 -->\nThe treaty was <!-- page 2 --> signed in 1919.",
            extract.FOOTNOTES_LABEL,
            "<!-- footnote on page 1 -->\n1. Harbor Board minutes, 1921.",
            "<!-- footnote on page 1 -->\n* Not in the first edition.",
        ])
        self.assertEqual(log.kinds().count("footnote-moved-from-list"), 2)
        self.assertNotIn("footnote-moved", log.kinds())
        self.assertIn("page-break-joined", log.kinds())

    def test_list_block_of_several_footnotes_split_and_moved(self):
        body = "The treaty was\n\n1. Harbor Board minutes.\n2. Second note.\n\n<!-- page break -->\n\nsigned in 1919.\n"
        paras, log = self.one(body, footnote_pattern=r"^\d{1,3}\.?\s")
        self.assertEqual(paras, [
            "<!-- page 1 -->\nThe treaty was <!-- page 2 --> signed in 1919.",
            extract.FOOTNOTES_LABEL,
            "<!-- footnote on page 1 -->\n1. Harbor Board minutes.",
            "<!-- footnote on page 1 -->\n2. Second note.",
        ])
        self.assertEqual(log.kinds().count("footnote-moved-from-list"), 2)
        self.assertIn("page-break-joined", log.kinds())

    def test_page_end_list_like_a_footnote_but_not_the_pattern_is_a_candidate(self):
        body ="The treaty was signed.\n\n1. Harbor Board minutes.\n2. Second note.\n\n<!-- page break -->\n\nNext page.\n"
        paras, log = self.one(body, footnote_pattern=r"^\d{1,3}\s")
        self.assertIn("1. Harbor Board minutes.\n2. Second note.", paras)
        self.assertEqual(log.kinds().count("footnote-candidate"), 1)

    def test_body_list_at_page_end_is_not_taken_for_footnotes(self):
        fpat = r"^\d{1,3}\.?\s"
        body = ("The board set three rules:\n\n1. Every ship registers by May.\n\n<!-- page break -->\n\n"
                "2. Every ship pays its dues.\n3. Every ship flies the flag.\n")
        paras, log = self.one(body, footnote_pattern=fpat)
        self.assertNotIn(extract.FOOTNOTES_LABEL, paras)
        self.assertIn("1. Every ship registers by May.", paras)
        self.assertNotIn("footnote-moved-from-list", log.kinds())
        self.assertEqual(log.kinds().count("footnote-candidate"), 2)
        # No colon lead-in: the next page's list continuing the numbering is enough.
        body = ("The board set rules.\n\n1. Every ship registers by May.\n\n<!-- page break -->\n\n"
                "2. Every ship pays its dues.\n\nThe rules held.\n")
        paras, log = self.one(body, footnote_pattern=fpat)
        self.assertNotIn(extract.FOOTNOTES_LABEL, paras)
        # A colon lead-in alone keeps a bulleted item too.
        paras, _ = self.one("The rule was:\n\n- Ships register.\n\n<!-- page break -->\n\nNext.\n",
                            footnote_pattern=r"^(?:\d{1,3}\.|-)\s")
        self.assertNotIn(extract.FOOTNOTES_LABEL, paras)

    def test_interruptions_within_a_page_are_joined_or_logged(self):
        # list, moved footnote, lowercase paragraph: no page breaks, then footnotes_at_page_end False
        body = "Rules:\n\n- arrive on time and\n\n12 A note.\n\nleave early.\n"
        paras, log = self.one(body, footnote_pattern=r"^\d{1,3}\s")
        self.assertEqual(paras, ["Rules:", "- arrive on time and leave early.", extract.FOOTNOTES_LABEL, "12 A note."])
        self.assertIn("list-page-joined", log.kinds())
        paras, log = self.one(body + "\n<!-- page break -->\n\nNext.\n", footnote_pattern=r"^\d{1,3}\s",
                              footnotes_at_page_end=False)
        self.assertEqual(paras[1], "- arrive on time and leave early.")
        # list, image, lowercase paragraph on the same page
        paras, log = self.one("Rules:\n\n- arrive on time and\n\n<!-- image -->\n\nleave early.\n\n"
                              "<!-- page break -->\n\nNext.\n")
        self.assertEqual(paras[1], "- arrive on time and leave early.")
        self.assertIn("list-page-joined", log.kinds())
        # open-ended paragraph, table, continuation on the same page: logged, not joined
        paras, log = self.one("The treaty was\n\n| a | b |\n|---|---|\n\nsigned in 1919.\n\n<!-- page break -->\n\nNext.\n")
        self.assertEqual(paras[:3], ["<!-- page 1 -->\nThe treaty was", "| a | b |\n|---|---|", "signed in 1919."])
        self.assertEqual(log.kinds().count("block-unjoined"), 1)
        self.assertNotIn("page-break-unjoined", log.kinds())
        # open-ended paragraph or heading-like line, image, then a capital or a list on the same page
        _, log = self.one("The treaty was\n\n<!-- image -->\n\nSigned in 1919.\n\n<!-- page break -->\n\nNext.\n")
        self.assertEqual(log.kinds().count("block-unjoined"), 1)
        self.assertNotIn("page-break-unjoined", log.kinds())
        _, log =self.one("The rules were\n\n<!-- image -->\n\n- arrive on time\n\n<!-- page break -->\n\nNext.\n")
        self.assertEqual(log.kinds().count("block-unjoined"), 1)
        _, log = self.one("Table 1 Counts\n\n| a | b |\n|---|---|\n\nAfter.\n")
        self.assertNotIn("block-unjoined", log.kinds())
        self.assertNotIn("page-break-unjoined", log.kinds())

    def test_list_item_run_on_with_nothing_between_is_joined(self):
        # No page breaks: a list item split across a page looks like this.
        paras, log = self.one("Rules:\n\n- arrive on time and\n\nleave early.\n")
        self.assertEqual(paras, ["Rules:", "- arrive on time and leave early."])
        self.assertEqual(log.kinds().count("list-page-joined"), 1)
        # With page breaks, on the same page.
        paras, log = self.one("Rules:\n\n- arrive on time and\n\nleave early.\n\n<!-- page break -->\n\nNext.\n")
        self.assertEqual(paras[1], "- arrive on time and leave early.")
        self.assertIn("list-page-joined", log.kinds())
        # A capital is not joined; with no page breaks it is logged as a paragraph pair would be.
        paras, log = self.one("Rules:\n\n- arrive on time and\n\nLeave early.\n")
        self.assertEqual(paras, ["Rules:", "- arrive on time and", "Leave early."])
        rows = [r[3] for r in log.rows if r[2] == "page-break-unjoined"]
        self.assertEqual(len(rows), 1)
        self.assertIn("no page evidence", rows[0])
        _, log = self.one("Rules:\n\n- arrive on time and\n\nLeave early.\n\n<!-- page break -->\n\nNext.\n")
        self.assertNotIn("page-break-unjoined", log.kinds())
        self.assertNotIn("block-unjoined", log.kinds())
        # No page breaks: an open-ended paragraph before a quotation is logged too,
        # but not a lead-in before a list or a heading-like line before a table.
        _, log = self.one("In a long letter to her sister that winter she wrote that\n\n> the tide came in.\n")
        self.assertEqual(log.kinds().count("page-break-unjoined"), 1)
        for body in ["The rules are\n\n- arrive on time\n", "Table 1 Counts\n\n| a | b |\n|---|---|\n",
                     "She wrote that\n\n> the tide came in.\n",
                     "Rules:\n\n- arrive on time.\n\nleave early.\n"]:
            paras, log = self.one(body)
            self.assertNotIn("page-break-unjoined", log.kinds(), body)
            self.assertNotIn("list-page-joined", log.kinds(), body)

    def test_open_ended_list_continued_on_next_page_is_body_not_footnote(self):
        fpat = r"^\d{1,3}\.?\s"
        body = "Three steps followed.\n\n1. the board would meet and\n\n<!-- page break -->\n\nvote on the dues.\n"
        paras, log = self.one(body, footnote_pattern=fpat)
        self.assertEqual(paras, ["<!-- page 1 -->\nThree steps followed.",
                                 "1. the board would meet and <!-- page 2 --> vote on the dues."])
        self.assertIn("list-page-joined", log.kinds())
        self.assertNotIn("footnote-moved-from-list", log.kinds())
        self.assertNotIn("footnote-open-ended", log.kinds())
        self.assertEqual(log.kinds().count("footnote-candidate"), 1)

    def test_open_ended_footnote_running_to_next_page_still_moves(self):
        fpat = r"^\d{1,3}\.?\s"
        # The next page's body starts with a capital: the note moves, flagged as open-ended.
        body = ("The treaty was signed.\n\n1. Harbor Board minutes, see the\n\n<!-- page break -->\n\n"
                "The next page begins.\n")
        paras, log = self.one(body, footnote_pattern=fpat)
        self.assertEqual(paras, ["<!-- page 1 -->\nThe treaty was signed.", "<!-- page 2 -->\nThe next page begins.",
                                 extract.FOOTNOTES_LABEL, "<!-- footnote on page 1 -->\n1. Harbor Board minutes, see the"])
        self.assertIn("footnote-open-ended", log.kinds())
        self.assertNotIn("list-page-joined", log.kinds())
        # The note interrupted a body paragraph that runs on in lowercase: the
        # paragraph rejoins, and the note still moves.
        body = "The treaty was\n\n1. Harbor Board minutes, see the\n\n<!-- page break -->\n\nsigned in 1919.\n"
        paras, log = self.one(body, footnote_pattern=fpat)
        self.assertEqual(paras, ["<!-- page 1 -->\nThe treaty was <!-- page 2 --> signed in 1919.",
                                 extract.FOOTNOTES_LABEL, "<!-- footnote on page 1 -->\n1. Harbor Board minutes, see the"])
        self.assertIn("footnote-open-ended", log.kinds())
        self.assertIn("page-break-joined", log.kinds())
        self.assertNotIn("list-page-joined", log.kinds())

    def test_list_like_footnote_mid_page_stays_a_list(self):
        body = "Body.\n\n1. A numbered line.\n\nMore body.\n\n<!-- page break -->\n\nNext.\n"
        paras, log = self.one(body, footnote_pattern=r"^\d{1,3}\.\s")
        self.assertEqual(paras, ["<!-- page 1 -->\nBody.", "1. A numbered line.", "More body.", "<!-- page 2 -->\nNext."])
        self.assertIn("footnote-candidate", log.kinds())

    def test_footnote_hint_on_one_item_lists_only(self):
        _, log = self.one("Body text.\n\n1. Harbor Board minutes, 1921.\n")
        self.assertEqual(log.kinds().count("footnote-candidate"), 1)
        _, log = self.one("The rules are:\n\n1. Arrive on time.\n2. Leave early.\n")
        self.assertNotIn("footnote-candidate", log.kinds())

    def test_footnote_moved_without_page_breaks_is_flagged(self):
        _, log = self.one("The treaty was\n\n12 A note.\n\nsigned in 1919.\n", footnote_pattern=r"^\d{1,3}\s")
        self.assertIn("footnote-moved-no-page-evidence", log.kinds())
        self.assertNotIn("footnote-moved", log.kinds())

    def test_chapter_with_no_body_words_is_an_error(self):
        md = ("## Contents\n\n## The Long War\n\n## The Peace\n\n"
              "## The Long War\n\nWar began.\n\n## The Peace\n\nPeace came.\n")
        chapters = [{"unit_id": "ch-01", "slug": "a", "title": "The Long War"},
                    {"unit_id": "ch-02", "slug": "b", "title": "The Peace"}]
        with self.assertRaises(SystemExit) as cm:
            self.extract(md, chapters)
        self.assertIn("ch-01", str(cm.exception))
        self.assertIn("occurrence", str(cm.exception))
        chapters[0]["occurrence"] = 2
        chapters[1]["occurrence"] = 1  # counted from just after ch-01's start
        out, _ = self.extract(md, chapters)
        self.assertEqual(out, {"ch-01": ["War began."], "ch-02": ["Peace came."]})

    def test_contents_page_numbers_do_not_count_as_body_words(self):
        md = ("## Contents\n\n## The Long War\n\n1\n\n## The Peace\n\n9\n\n"
              "## The Long War\n\nWar began.\n\n## The Peace\n\nPeace came.\n")
        chapters = [{"unit_id": "ch-01", "slug": "a", "title": "The Long War"},
                    {"unit_id": "ch-02", "slug": "b", "title": "The Peace"}]
        with self.assertRaises(SystemExit) as cm:
            self.extract(md, chapters)
        self.assertIn("ch-01: no body words (only bare numbers)", str(cm.exception))
        self.assertNotIn("ch-02:", str(cm.exception))

    def test_empty_chapter_stops_before_any_file_and_writes_the_log(self):
        md = ("## Contents\n\n## The Long War\n\n## The Peace\n\n"
              "## The Long War\n\nWar began.\n\n## The Peace\n\nPeace came.\n")
        cfg = {"md": "src.md", "slug": "src", "title": "Book", "part": 1,
               "chapters": [{"unit_id": "ch-01", "slug": "war", "title": "The Long War"},
                            {"unit_id": "ch-02", "slug": "peace", "title": "The Peace"}]}
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "src.md"), "w", encoding="utf-8", newline="\n") as f:
                f.write(md)
            old = extract.SOURCES, extract.OUT, extract.RAW
            extract.SOURCES, extract.OUT, extract.RAW = tmp, os.path.join(tmp, "out"), os.path.join(tmp, "raw")
            try:
                with self.assertRaises(SystemExit) as cm:
                    extract.build_md_source(cfg)
                self.assertFalse(os.path.exists(os.path.join(tmp, "out", "src")))
                with open(os.path.join(tmp, "raw", "src", "repairs.tsv"), encoding="utf-8") as f:
                    rows = f.read()
            finally:
                extract.SOURCES, extract.OUT, extract.RAW = old
        self.assertIn("ch-01", str(cm.exception))
        self.assertNotIn("ch-02:", str(cm.exception))
        # ch-02 runs from the contents entry over ch-01's real start heading.
        self.assertIn("ch-02\tNone\tchapter-start-inside\tthe start of ch-01 also matches line 7", rows)
        self.assertIn("outside-chapters", rows)

    def test_other_chapter_start_inside_a_chapter_is_logged(self):
        md = ("## The Long War\n\nWar began.\n\n## Aftermath\n\nA section.\n\n"
              "## The Peace\n\nPeace came.\n\n## Aftermath\n\nAfter.\n")
        chapters = [{"unit_id": "ch-01", "slug": "a", "title": "The Long War"},
                    {"unit_id": "ch-02", "slug": "b", "title": "The Peace"},
                    {"unit_id": "ch-03", "slug": "c", "title": "Aftermath"}]
        out, log = self.extract(md, chapters)
        self.assertEqual(out["ch-03"], ["After."])
        rows = [r for r in log.rows if r[2] == "chapter-start-inside"]
        self.assertEqual([(r[0], "ch-03" in r[3], "line 5" in r[3]) for r in rows], [("ch-01", True, True)])

    def test_bare_number_taken_in_across_placeholder_and_page_break(self):
        md = ("## War\n\nWar text.\n\n## 2\n\n<!-- image -->\n\n<!-- page break -->\n\n"
              "## The Peace\n\nPeace came.\n")
        chapters = [{"unit_id": "ch-01", "slug": "a", "title": "War", "num": 1},
                    {"unit_id": "ch-02", "slug": "b", "title": "The Peace", "num": 2}]
        out, log = self.extract(md, chapters)
        self.assertEqual(out, {"ch-01": ["<!-- page 1 -->\nWar text."], "ch-02": ["<!-- page 2 -->\nPeace came."]})
        self.assertIn("2", [r[3] for r in log.rows if r[2] == "heading-stripped"])

    def test_bare_number_paragraph_taken_in(self):
        md = "## War\n\nWar text.\n\n2\n\n<!-- formula-not-decoded -->\n\n## The Peace\n\nPeace came.\n"
        chapters = [{"unit_id": "ch-01", "slug": "a", "title": "War", "num": 1},
                    {"unit_id": "ch-02", "slug": "b", "title": "The Peace", "num": 2}]
        out, _ = self.extract(md, chapters)
        self.assertEqual(out, {"ch-01": ["War text."], "ch-02": ["Peace came."]})

    def test_text_outside_chapters_is_logged(self):
        md = ("# The Book\n\n## Contents\n\nFront matter.\n\n## The Long War\n\nWar began.\n\n## Notes\n\n"
              "Some notes.\n\n## Part Two\n\n## The Peace\n\nPeace came.\n\n## Index\n\nwar, 1\n")
        chapters = [{"unit_id": "ch-01", "slug": "a", "title": "The Long War", "stop_line": "## Notes"},
                    {"unit_id": "ch-02", "slug": "b", "title": "The Peace", "stop_line": "## Index"}]
        out, log = self.extract(md, chapters)
        self.assertEqual(out, {"ch-01": ["War began."], "ch-02": ["Peace came."]})
        rows = [r[3] for r in log.rows if r[2] == "outside-chapters"]
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[0].startswith("lines 1-5, 5 words left out: The Book Contents Front matter."))
        self.assertTrue(rows[1].startswith("lines 11-15, 5 words left out: Notes Some notes. Part Two"))
        self.assertTrue(rows[2].startswith("lines 21-23, 3 words left out: Index war, 1"))

    def test_only_docling_backslash_escapes_are_undone_and_logged(self):
        paras, log = self.one("Match \\d+\\.\\d+ on \\\\server\\share for \\_id\\_ and \\[1\\].\n")
        self.assertEqual(paras, ["Match \\d+\\.\\d+ on \\\\server\\share for _id_ and [1]."])
        rows = [r[3] for r in log.rows if r[2] == "unescaped"]
        self.assertEqual(rows[0][:8], "\\[ -> [ ")
        self.assertEqual(len(rows), 2)
        rows = [r[3] for r in log.rows if r[2] == "unescaped-underscores"]
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].startswith("2 \\_ -> _ (line 3), e.g. in: "), rows[0])

    def test_escaped_underscores_logged_once_per_chapter(self):
        md = ("## War\n\nThe \\_a\\_ and \\_b\\_ fields.\n\n| \\_c | d |\n\n<!-- page break -->\n\nMore \\_e here.\n\n"
              "## Peace\n\nNo escapes.\n")
        chapters = [{"unit_id": "ch-01", "slug": "a", "title": "War"}, {"unit_id": "ch-02", "slug": "b", "title": "Peace"}]
        out, log = self.extract(md, chapters)
        self.assertIn("_a_ and _b_", out["ch-01"][0])
        rows = [r for r in log.rows if r[2] == "unescaped-underscores"]
        self.assertEqual([(r[0], r[1]) for r in rows], [("ch-01", 1)])
        self.assertTrue(rows[0][3].startswith("6 \\_ -> _ (1 to 2)"), rows[0][3])
        self.assertNotIn("unescaped", log.kinds())

    def test_outside_chapters_counts_words_not_table_pipes(self):
        md = "| a | b |\n|---|---|\n| 1 | 2 |\n\n## War\n\nWar began.\n"
        _, log = self.extract(md, [{"unit_id": "ch-01", "slug": "a", "title": "War"}])
        rows = [r[3] for r in log.rows if r[2] == "outside-chapters"]
        self.assertEqual(len(rows), 1)
        self.assertIn(", 4 words left out", rows[0])

    def test_heading_after_colon_lead_in_not_quoted(self):
        paras, _ = self.one("The ration rules were these:\n\n### Rationing\n\nBread was scarce.\n", block_quotes=True)
        self.assertEqual(paras, ["The ration rules were these:", "Rationing", "Bread was scarce."])

    def test_leading_markup_kept_as_prose(self):
        from count_words import words_in_text
        body = "\\#1 was the best seller.\n\n&gt; is the prompt.\n\n<!-- page break -->\n\n#hashtag trends.\n"
        paras, log = self.one(body)
        self.assertEqual(paras, ["<!-- page 1 -->\n\\#1 was the best seller.", "\\> is the prompt.",
                                 "<!-- page 2 -->\n\\#hashtag trends."])
        self.assertEqual(log.kinds().count("leading-markup-kept"), 3)
        self.assertEqual(words_in_text("\n\n".join(paras)), 11)

    def test_list_continued_on_next_page_is_joined(self):
        body = "The rules are:\n\n- arrive on time and\n\n<!-- page break -->\n\nleave early.\n\nNext.\n"
        paras, log = self.one(body)
        self.assertEqual(paras, ["<!-- page 1 -->\nThe rules are:", "- arrive on time and <!-- page 2 --> leave early.", "Next."])
        self.assertIn("list-page-joined", log.kinds())

    def test_open_ended_blocks_before_page_break_are_logged(self):
        cases = ["She wrote:\n\n> The tide came in and\n\n<!-- page break -->\n\n> the boats came home.\n",
                 "Counts:\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n<!-- page break -->\n\n| 3 | 4 |\n",
                 "The rules are\n\n<!-- page break -->\n\n- arrive on time\n",
                 "Rules:\n\n- arrive on time and\n\n<!-- page break -->\n\nLeave early.\n"]
        for body in cases:
            _, log = self.one(body)
            self.assertEqual(log.kinds().count("page-break-unjoined"), 1, body)
        _, log = self.one("Rules:\n\n- arrive on time.\n\n<!-- page break -->\n\nNext.\n")
        self.assertNotIn("page-break-unjoined", log.kinds())

    def test_kept_hyphen_keeps_its_space(self):
        paras, log = self.one("The long- versus short-term view.\n", hyphen_spaces=True)
        self.assertEqual(paras, ["The long- versus short-term view."])
        self.assertIn("hyphen-kept", log.kinds())


class TempProject:
    """Mixin: point extract.py and source_helpers.py at temporary Sources, Chapters, Raw, and Proof folders."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        for name in ("Sources", "Chapters", "Raw", "Proof"):
            os.makedirs(os.path.join(self.tmp, name))
        saved = (extract.SOURCES, extract.OUT, extract.RAW, extract.ROOT, source_helpers.SOURCES, source_helpers.PROOF)

        def restore():
            (extract.SOURCES, extract.OUT, extract.RAW, extract.ROOT,
             source_helpers.SOURCES, source_helpers.PROOF) = saved

        self.addCleanup(restore)
        extract.SOURCES = source_helpers.SOURCES = os.path.join(self.tmp, "Sources")
        extract.OUT = os.path.join(self.tmp, "Chapters")
        extract.RAW = os.path.join(self.tmp, "Raw")
        extract.ROOT = self.tmp
        source_helpers.PROOF = os.path.join(self.tmp, "Proof")

    def write(self, rel, text):
        path = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return path


def quiet(fn, *args, **kwargs):
    """Call fn with stdout captured; return (result, output)."""
    out = io.StringIO()
    with redirect_stdout(out):
        result = fn(*args, **kwargs)
    return result, out.getvalue()


# Line numbers of LINE_EDITS_MD, for the line-edit tests.
LINE_EDITS_MD = "\n".join([
    "## The Quay",                                   # 1
    "",
    'The boats came "home" at dawn - late.',         # 3
    "",
    "Tbe tide was low.",                             # 5
    "",
    "The harbour board wrote",                       # 7
    "",
    "that the quay was unsafe.",                     # 9
    "",
    "3 A note on the board.",                        # 11
    "",
    "Translator's note: the board met monthly.",     # 13
    "",
    "It ruled:",                                     # 15
    "Close the quay.",                               # 16
    "Open the slip.",                                # 17
    "",
    "Smith &amp; Sons rebuilt it.",                  # 19
]) + "\n"


class LineEdits(TempProject, unittest.TestCase):
    """source_helpers.build_line_edits: line-numbered edits, each checked against its line."""

    def setUp(self):
        super().setUp()
        self.write("Sources/q.md", LINE_EDITS_MD)

    def edits(self, **ops):
        return source_helpers.build_line_edits("q.md", **ops)

    def stops(self, message, **ops):
        with self.assertRaises(SystemExit) as cm:
            self.edits(**ops)
        self.assertIn(message, str(cm.exception))

    def test_md_lines_and_skeleton(self):
        lines = source_helpers.md_lines("q.md")
        self.assertEqual(lines[2], 'The boats came "home" at dawn - late.')
        self.assertEqual(source_helpers.skeleton("Dawn—late, “home”: 1937!"), "dawnlatehome1937")

    def test_rebuilt_line_keeps_its_letters_and_digits(self):
        rebuilt = "The boats came “home” at dawn—late."
        self.assertEqual(self.edits(rebuilt={3: rebuilt}), {3: rebuilt})
        self.assertEqual(self.edits(rebuilt={19: "Smith & Sons rebuilt it."}), {19: "Smith & Sons rebuilt it."})
        self.stops("q.md: line 3: rebuilt text changes letters or digits", rebuilt={3: "The boats came home at noon."})

    def test_replace_and_edits(self):
        self.assertEqual(self.edits(replace={5: ("Tbe", "The tide was low.")}), {5: "The tide was low."})
        self.assertEqual(self.edits(replace={5: "The tide was low."}), {5: "The tide was low."})
        self.stops("line 5: does not start with 'The'", replace={5: ("The", "x")})
        self.stops("line 4: is blank", replace={4: "x"})
        self.assertEqual(self.edits(edits={5: [("Tbe", "The"), ("low", "out")]}), {5: "The tide was out."})
        self.assertEqual(self.edits(edits={3: [("e", "E", 4)]}), {3: 'ThE boats camE "homE" at dawn - latE.'})
        self.stops("line 5: 'e' occurs 2 times, expected 1", edits={5: [("e", "E")]})

    def test_swaps_joins_moves_drops(self):
        self.assertEqual(self.edits(swaps=[(3, 5)]), {3: "Tbe tide was low.", 5: LINE_EDITS_MD.split("\n")[2]})
        self.assertEqual(self.edits(joins=[(7, 9)]), {7: "The harbour board wrote that the quay was unsafe.", 9: ""})
        self.stops("line 8: is blank", joins=[(7, 8)])
        self.assertEqual(self.edits(moves=[(11, 15)]), {15: "It ruled:\n\n3 A note on the board.", 11: ""})
        self.assertEqual(self.edits(drops={13: "Translator's note"}), {13: ""})
        self.stops("line 13: dropped line does not contain 'Editor'", drops={13: "Editor"})
        self.stops("line 99 is not a line of the file (1-19)", drops={99: "x"})

    def test_quotes_set_off_items_written_without_blank_lines(self):
        self.assertEqual(self.edits(quotes=[16, 17]), {16: "\n> Close the quay.", 17: "\n> Open the slip."})
        self.assertEqual(self.edits(quotes=[5]), {5: "> Tbe tide was low."})
        self.stops("line 4: quoted line is blank", quotes=[4])

    def test_operations_apply_in_order(self):
        out = self.edits(edits={5: [("Tbe", "The")]}, joins=[(3, 5)], quotes=[3])
        self.assertEqual(out[3], '> The boats came "home" at dawn - late. The tide was low.')

    def test_markdown_source_applies_line_edits_by_number(self):
        cfg = {"md": "q.md", "slug": "q", "title": "Q", "part": 1,
               "line_edits": lambda: self.edits(edits={5: [("Tbe", "The")]}, joins=[(7, 9)],
                                                 drops={13: "Translator's note"}, quotes=[16, 17]),
               "chapters": [{"unit_id": "ch-01", "slug": "the-quay", "title": "The Quay"}]}
        cfg = extract.resolve_config(cfg)
        self.assertEqual(extract.validate_config(cfg), [])
        log = RepairLog()
        paras = quiet(extract.make_md_extractor, cfg, log)[0](cfg["chapters"][0])
        self.assertEqual(paras, ['The boats came "home" at dawn - late.', "The tide was low.",
                                 "The harbour board wrote that the quay was unsafe.", "3 A note on the board.",
                                 "It ruled:", "> Close the quay.", "> Open the slip.", "Smith & Sons rebuilt it."])
        self.assertEqual(log.kinds().count("line-edited"), 6)
        self.assertIn(("", "line 13", "line-edited", "Translator's note: the board met monthly. -> (dropped)"), log.rows)

    def test_split_and_past_the_end(self):
        log = RepairLog()
        cfg = {"md": "q.md", "slug": "q", "line_edits": {5: "The tide.\n\nIt was low.", 3: ""},
               "chapters": [{"unit_id": "ch-01", "slug": "a", "title": "The Quay"}]}
        paras = quiet(extract.make_md_extractor, cfg, log)[0](cfg["chapters"][0])
        self.assertEqual(paras[:2], ["The tide.", "It was low."])
        with self.assertRaises(SystemExit) as cm:
            extract.MdSource(dict(cfg, line_edits={20: "x", 25: "y"}))
        self.assertIn("q.md: line_edits for lines past the end of the file (19 lines): 20, 25", str(cm.exception))

    def test_unused_line_fixes_are_logged_and_printed(self):
        log = RepairLog()
        cfg = {"md": "q.md", "slug": "q", "line_fixes": {"Tbe tide was low.": "The tide was low.", "Nowhere.": "x"},
               "chapters": [{"unit_id": "ch-01", "slug": "a", "title": "The Quay"}]}
        _, out = quiet(extract.MdSource, cfg, log)
        self.assertEqual([r for r in log.rows if r[2] == "line-fix-unused"],
                         [("", None, "line-fix-unused", "line_fixes key matches no line: 'Nowhere.'")])
        self.assertIn("WARNING q: line_fixes key matches no line: 'Nowhere.'", out)

    def test_unused_line_fixes_in_paged_text(self):
        self.write("Sources/t.txt", "Chapter One\n\nThe boats came home.\n\fNot extracted.\n")
        cfg = {"txt": "t.txt", "slug": "t", "line_fixes": {"The boats came home.": "The boats came in.",
                                                           "Not extracted.": "x"}}
        log = RepairLog()
        ex = quiet(extract.make_txt_extractor, cfg, log)[0]
        self.assertEqual(ex({"unit_id": "ch-01", "start": 1, "end": 1, "first_line": "The boats"}),
                         ["<!-- page 1 -->\nThe boats came in."])
        self.assertEqual(quiet(extract.report_unused_line_fixes, cfg, ex.source.fixes_used, log)[0], ["Not extracted."])
        self.assertIn("line-fix-unused", log.kinds())


class ProofFixes(TempProject, unittest.TestCase):
    """source_helpers.proof_fixes and write_preproof: a proofreading pass as line edits."""

    def setUp(self):
        super().setUp()
        self.write("Sources/q.md", LINE_EDITS_MD)

    def proof(self, listed, fixes):
        self.write("Proof/q.preproof.json", json.dumps([{"line": n, "text": t} for n, t in listed]))
        self.write("Proof/q.fixes.json", json.dumps(fixes))

    def test_fixes_are_keyed_by_line_number(self):
        self.proof([(5, "Tbe tide was low."), (7, "The harbour board wrote")], {"5": "The tide was low."})
        fixes = source_helpers.proof_fixes("q", "q.md")
        self.assertEqual(fixes, {5: "The tide was low."})
        self.assertEqual(source_helpers.build_line_edits("q.md", replace=fixes, quotes=[5]), {5: "> The tide was low."})

    def test_changed_source_or_unlisted_line_stops(self):
        self.proof([(5, "Tbe tide was high.")], {"5": "The tide was high."})
        with self.assertRaises(SystemExit) as cm:
            source_helpers.proof_fixes("q", "q.md")
        self.assertIn("line 5 of q.md no longer reads as it did when it was proofread (source changed)",
                      str(cm.exception))
        self.proof([(5, "Tbe tide was low.")], {"7": "x"})
        with self.assertRaises(SystemExit) as cm:
            source_helpers.proof_fixes("q", "q.md")
        self.assertIn("fixes for lines not in the pre-proof listing: 7", str(cm.exception))

    def test_missing_files_give_no_fixes(self):
        self.assertEqual(source_helpers.proof_fixes("q", "q.md"), {})

    def test_one_fixes_file_per_unit_is_merged(self):
        self.proof([(5, "Tbe tide was low."), (7, "The harbour board wrote")], {"5": "The tide was low."})
        self.write("Proof/q.ch-02.fixes.json", json.dumps({"7": "The harbour board wrote:"}))
        self.write("Proof/q-other.ch-01.fixes.json", json.dumps({"9": "not this source"}))
        self.assertEqual(source_helpers.proof_fixes("q", "q.md"), {5: "The tide was low.", 7: "The harbour board wrote:"})
        self.write("Proof/q.ch-03.fixes.json", json.dumps({"5": "The tide was out."}))
        with self.assertRaises(SystemExit) as cm:
            source_helpers.proof_fixes("q", "q.md")
        self.assertIn("line 5 is fixed differently in", str(cm.exception))
        self.assertIn("q.ch-03.fixes.json", str(cm.exception))

    def test_write_preproof_adds_lines_and_keeps_entries(self):
        self.assertEqual(source_helpers.write_preproof("q", "q.md", 1, 5), 3)
        self.assertEqual(source_helpers.write_preproof("q", "q.md", 3, 9), 2)
        with open(os.path.join(self.tmp, "Proof", "q.preproof.json"), encoding="utf-8") as f:
            listed = json.load(f)
        self.assertEqual([e["line"] for e in listed], [1, 3, 5, 7, 9])
        self.assertEqual(listed[2], {"line": 5, "text": "Tbe tide was low."})


class SourceConfigFiles(TempProject, unittest.TestCase):
    """Work/SourceConfigs: one config file per source, loaded and resolved by extract.py."""

    def folder(self, files):
        folder = os.path.join(self.tmp, "Configs")
        os.makedirs(folder, exist_ok=True)
        for name, text in files.items():
            self.write(os.path.join("Configs", name), text)
        return folder

    @staticmethod
    def config(slug, md="x.md"):
        return ("from source_helpers import build_line_edits\n\n"
                "CONFIG = {'slug': %r, 'md': %r, 'title': 'T', 'part': 1,\n"
                "          'line_edits': lambda: build_line_edits(%r),\n"
                "          'chapters': [{'unit_id': 'ch-01', 'slug': 'war', 'title': 'War'}]}\n" % (slug, md, md))

    def test_template_entries_are_documentation_only(self):
        self.assertEqual(extract.SOURCES_CONFIG, [])

    def test_one_file_per_source_appended_in_file_name_order(self):
        folder = self.folder({"b_src.py": self.config("b-src"), "a_src.py": self.config("a-src"),
                              "_notes.py": "x = 1\n", "README.md": "# Source configs\n"})
        self.assertEqual([c["slug"] for c in extract.all_sources(folder)], ["a-src", "b-src"])
        self.assertEqual(extract.all_sources(os.path.join(self.tmp, "absent")), [])

    def test_duplicate_slug_is_rejected(self):
        folder = self.folder({"a_src.py": self.config("same"), "b_src.py": self.config("same")})
        with self.assertRaises(SystemExit) as cm:
            extract.all_sources(folder)
        self.assertIn("b_src.py: slug 'same' is already used by", str(cm.exception))
        self.assertIn("a_src.py", str(cm.exception))

    def test_bad_file_is_rejected_naming_the_line(self):
        cases = {"CONFIG = {'slug': 'a',\n": "failed to import (line 1): SyntaxError",
                 "x = 1\nCONFIG = {'slug': undefined_name}\n": "failed to import (line 2): NameError",
                 "SETTINGS = {'slug': 'a'}\n": "defines no CONFIG dict",
                 "CONFIG = {'md': 'x.md'}\n": "CONFIG has no slug"}
        for text, message in cases.items():
            folder = self.folder({"bad_src.py": text})
            with self.assertRaises(SystemExit) as cm:
                extract.all_sources(folder)
            self.assertIn("bad_src.py: ", str(cm.exception))
            self.assertIn(message, str(cm.exception))

    def test_slug_filtering(self):
        configs = [{"slug": "a-src"}, {"slug": "b-src"}, {"slug": "c-src"}]
        self.assertEqual(extract.select_sources(configs, []), configs)
        self.assertEqual(extract.select_sources(configs, ["c-src", "a-src"]), [configs[0], configs[2]])
        with self.assertRaises(SystemExit) as cm:
            extract.select_sources(configs, ["a-src", "d-src"])
        self.assertIn("no source has slug 'd-src'; configured: a-src, b-src, c-src", str(cm.exception))
        with self.assertRaises(SystemExit) as cm:
            extract.select_sources([], ["a-src"])
        self.assertIn("configured: none", str(cm.exception))

    def test_callables_are_resolved_only_when_extracted(self):
        # The config loads with no Sources/x.md; its line_edits read the file only when resolved.
        cfg = extract.all_sources(self.folder({"a_src.py": self.config("a-src")}))[0]
        self.assertTrue(callable(cfg["line_edits"]))
        self.assertEqual(extract.validate_config(cfg), [])
        with self.assertRaises(SystemExit) as cm:
            extract.resolve_config(cfg)
        self.assertIn("a-src: line_edits: ", str(cm.exception))
        self.assertIn("x.md: not found", str(cm.exception))
        resolved = extract.resolve_config(dict(cfg, line_edits=lambda: {3: "x"}, line_fixes=lambda: {"a": "b"}))
        self.assertEqual((resolved["line_edits"], resolved["line_fixes"]), ({3: "x"}, {"a": "b"}))
        self.assertTrue(callable(cfg["line_edits"]))   # the loaded config is not changed

        def broken():
            return {}["missing"]

        with self.assertRaises(SystemExit) as cm:
            extract.resolve_config(dict(cfg, line_fixes=broken))
        self.assertIn("a-src: line_fixes failed (", str(cm.exception))
        self.assertIn("KeyError: 'missing'", str(cm.exception))

    def test_main_extracts_named_sources_and_rejects_unknown_ones(self):
        self.write("Sources/x.md", "## War\n\nWar began.\n")
        old = extract.SOURCE_CONFIGS
        extract.SOURCE_CONFIGS = self.folder({"a_src.py": self.config("a-src")})
        try:
            code, out = quiet(extract.main, ["a-src"])
            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(os.path.join(extract.OUT, "a-src", "01-war.md")))
            self.assertEqual(quiet(extract.main, ["--check"])[0], 0)
            for argv, message in ((["nope"], "no source has slug 'nope'"), (["--bogus"], "unknown option --bogus")):
                with self.assertRaises(SystemExit) as cm:
                    quiet(extract.main, argv)
                self.assertIn(message, str(cm.exception))
        finally:
            extract.SOURCE_CONFIGS = old

    def test_project_configs_load_validate_and_are_named_by_slug(self):
        # Vacuous until the project has configs; then every one must pass.
        for cfg in extract.all_sources(extract.SOURCE_CONFIGS)[len(extract.SOURCES_CONFIG):]:
            self.assertEqual(extract.validate_config(cfg), [], cfg["slug"])
            name = cfg["slug"].replace("-", "_") + ".py"
            self.assertTrue(os.path.exists(os.path.join(extract.SOURCE_CONFIGS, name)), name)

    def test_example_config_loads_validates_and_resolves(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "SourceConfigs",
                            "_example_md.py")
        spec = importlib.util.spec_from_file_location("example_md", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cfg = module.CONFIG
        self.assertEqual(extract.validate_config(cfg), [])
        self.assertEqual(cfg["register"], "modern")   # a 1937 text
        lines = ["Line %d of the book." % n for n in range(1, 461)]
        lines[454] = "Tbe tide turned."
        lines[300] = "Translator's note: a harbour term."
        self.write("Sources/penhale-grey-harbour.md", "\n".join(lines) + "\n")
        edits = extract.resolve_config(cfg)["line_edits"]
        self.assertEqual(sorted(edits), [212, 214, 288, 290, 301, 455])
        self.assertEqual(edits[455], "The tide turned.")


class FileNumbers(unittest.TestCase):
    def test_default_is_list_order(self):
        self.assertEqual(extract.file_numbers([{}, {}, {}]), [1, 2, 3])

    def test_file_no_keeps_a_later_chapter_first(self):
        # An existing chapter (no file_no) listed after chapters added before it keeps 01.
        chapters = [{"file_no": 2}, {"file_no": 3}, {}, {"file_no": 4}]
        self.assertEqual(extract.file_numbers(chapters), [2, 3, 1, 4])
        self.assertEqual(extract.file_numbers([{"file_no": 1}, {}, {}]), [1, 2, 3])

    def test_validation(self):
        ch = {"unit_id": "ch-01", "slug": "a", "title": "T"}
        cfg = {"md": "src.md", "slug": "src", "part": 1,
               "chapters": [dict(ch, file_no=2), dict(ch, unit_id="ch-02", slug="b")]}
        self.assertEqual(extract.validate_config(cfg), [])
        cfg["chapters"][1]["file_no"] = 2
        self.assertIn("duplicate file_no", " | ".join(extract.validate_config(cfg)))
        cfg["chapters"][1]["file_no"] = 0
        self.assertIn("file_no 0 must be a whole number from 1 up", " | ".join(extract.validate_config(cfg)))


class ValidateConfig(unittest.TestCase):
    CH = {"unit_id": "ch-01", "slug": "a", "title": "T"}

    def errors(self, **cfg):
        return " | ".join(extract.validate_config(dict({"slug": "s", "chapters": [dict(self.CH)]}, **cfg)))

    def test_exactly_one_source_file(self):
        self.assertIn("set exactly one source file, pdf, epub, txt, or md (found none)", self.errors())
        self.assertIn("(found pdf, md)", self.errors(md="a.md", pdf="a.pdf"))

    def test_line_edits_and_line_fixes(self):
        self.assertEqual(self.errors(md="a.md", line_edits={3: "x"}, line_fixes={"a": "b"}), "")
        self.assertEqual(self.errors(md="a.md", line_edits=lambda: {}, line_fixes=lambda: {}), "")
        self.assertIn("line_edits are for docling Markdown sources only",
                      self.errors(txt="a.txt", line_edits={3: "x"}, chapters=[dict(self.CH, start=1, end=1)]))
        self.assertIn("bad entries: 0, '3'", self.errors(md="a.md", line_edits={0: "x", "3": "y"}))
        self.assertIn("line_fixes must map", self.errors(md="a.md", line_fixes={1: "b"}))

    def test_paged_text_keys(self):
        txt = {"txt": "a.txt", "chapters": [dict(self.CH, start=1, end=2)]}
        self.assertEqual(self.errors(paragraphs="blank_lines", build_txt=lambda path: None, **txt), "")
        self.assertIn("paragraphs must be", self.errors(paragraphs="lines", **txt))
        self.assertIn("paragraphs must be", self.errors(md="a.md", paragraphs="blank_lines"))
        self.assertIn("build_txt must be a callable", self.errors(build_txt="make.py", **txt))
        self.assertIn("needs start and end PDF pages", self.errors(pdf="a.pdf"))

    def test_register_is_modern_or_source_on_the_source_and_each_chapter(self):
        self.assertEqual(self.errors(md="a.md", register="modern", chapters=[dict(self.CH, register="source")]), "")
        self.assertEqual(self.errors(md="a.md"), "")   # unset: a warning when extracted, not an error
        for bad in ("", "old", "Modern", None):
            self.assertIn("s: register %r must be \"modern\"" % bad, self.errors(md="a.md", register=bad))
            self.assertIn("s: chapter 'ch-01': register %r must be \"modern\"" % bad,
                          self.errors(md="a.md", chapters=[dict(self.CH, register=bad)]))


class PdfChapterCuts(unittest.TestCase):
    """PDF chapters can start and end mid-page (first_line, stop_line)."""

    def extract(self, ch, cfg=None):
        with tempfile.TemporaryDirectory() as tmp:
            make_pdf(os.path.join(tmp, "src.pdf"), [
                [(100, "End of the last chapter."), (300, "New Chapter"), (400, "The new chapter starts here.")],
                [(100, "It goes on to the end."), (300, "Next Chapter"), (400, "Other text.")],
            ])
            old = extract.SOURCES
            extract.SOURCES = tmp
            try:
                log = RepairLog()
                cfg = dict({"pdf": "src.pdf", "header_ymax": 0, "footer_ymin": 10000}, **(cfg or {}))
                ex = extract.with_char_map(quiet(extract.make_extractor, cfg, log)[0], cfg, log)
                return [strip_comments(p) for p in ex(dict({"unit_id": "ch-02", "title": "New Chapter"}, **ch))], log
            finally:
                extract.SOURCES = old

    def test_first_and_last_pages_are_cut(self):
        paras, log = self.extract({"start": 1, "end": 2, "first_line": "The new chapter", "stop_line": "Next Chapter"})
        self.assertEqual(paras, ["The new chapter starts here.", "It goes on to the end."])
        self.assertEqual([r[3] for r in log.rows if r[2] == "heading-stripped"], ["End of the last chapter.", "New Chapter"])
        self.assertNotIn("heading-not-found", log.kinds())

    def test_one_page_chapter_and_missing_prefix(self):
        paras, _ = self.extract({"start": 2, "end": 2, "stop_line": "Next Chapter"})
        self.assertEqual(paras, ["It goes on to the end."])
        with self.assertRaises(SystemExit) as cm:
            self.extract({"start": 1, "end": 1, "first_line": "Nowhere"})
        self.assertIn("first_line 'Nowhere' not found", str(cm.exception))

    def test_char_map_on_pdf_paragraphs(self):
        paras, log = self.extract({"start": 2, "end": 2, "stop_line": "Next Chapter"}, {"char_map": {"goes": "went"}})
        self.assertEqual(paras, ["It went on to the end."])
        self.assertIn(("ch-02", None, "char-mapped", "ch-02: 'goes' -> 'went' x1"), log.rows)


class CharMapAndPrivateUse(unittest.TestCase):
    def test_char_map_applied_and_logged(self):
        log = RepairLog()
        f = extract.with_char_map(lambda ch: ['England "” Thomas Hobbes "” has', "plain"],
                                  {"char_map": {'"”': "—"}}, log)
        self.assertEqual(f({"unit_id": "u"}), ["England — Thomas Hobbes — has", "plain"])
        self.assertEqual(log.kinds(), ["char-mapped"])

    def test_no_char_map_returns_extractor(self):
        g = lambda ch: ["x"]  # noqa: E731
        self.assertIs(extract.with_char_map(g, {}), g)

    def test_private_use_characters_are_logged_once_each(self):
        log = RepairLog()
        f = extract.with_private_use_log(lambda ch: ["<!-- page 4 -->\nBorn in .", "x"], log)
        self.assertEqual(f({"unit_id": "u"})[1], "x")
        self.assertEqual([r[3] for r in log.rows],
                         ["U+F731 x2, first in: Born in .",
                          "U+F737 x1, first in: Born in .",
                          "U+F738 x1, first in: Born in ."])
        self.assertEqual(set(log.kinds()), {"private-use"})


class PagedTextOptions(TempProject, unittest.TestCase):
    """Paged TXT: blank-line paragraphs, Work/ paths, build_txt, and table rows."""

    def test_blank_lines_make_the_paragraphs(self):
        lines = ["A Short Heading", "Body line one that is short.", "", "Second para,", "continues here.", "",
                 "1. A note", "2. Another"]
        cfg = {"paragraphs": "blank_lines"}
        self.assertEqual(extract.txt_paragraphs(lines, cfg, DocEvidence(), 70),
                         ["A Short Heading Body line one that is short.", "Second para, continues here.",
                          "1. A note 2. Another"])
        import re
        self.assertEqual(extract.txt_paragraphs(lines, cfg, DocEvidence(), 70, para_start=re.compile(r"^\d\.\s"))[-2:],
                         ["1. A note", "2. Another"])
        self.assertEqual(extract.txt_paragraphs(lines[:2], {}, DocEvidence(), 70),
                         ["A Short Heading", "Body line one that is short."])

    def test_work_path_and_build_txt(self):
        self.assertEqual(extract.txt_path({"txt": "a.txt"}), os.path.join(self.tmp, "Sources", "a.txt"))
        path = extract.txt_path({"txt": "Work/Raw/s/paged.txt"})
        self.assertEqual(path, os.path.join(self.tmp, "Work/Raw/s/paged.txt"))
        calls = []

        def build(p):
            calls.append(p)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write("Page one.\n\fPage two.\n")

        cfg = {"slug": "s", "txt": "Work/Raw/s/paged.txt", "build_txt": build}
        quiet(extract.ensure_txt, cfg)
        quiet(extract.ensure_txt, cfg)
        self.assertEqual(calls, [path])            # not rebuilt while the file exists
        quiet(extract.ensure_txt, cfg, True)
        self.assertEqual(len(calls), 2)            # --rebuild-txt
        self.assertEqual(extract.txt_page_texts(path), ["Page one.\n", "Page two.\n"])
        with self.assertRaises(SystemExit) as cm:
            extract.ensure_txt({"slug": "s", "txt": "Work/missing.txt"})
        self.assertIn("set build_txt", str(cm.exception))

    def test_table_rows_join_into_one_block(self):
        paras = ["Lead-in:", "| A | B |", "| --- | --- |", "| 1 | 2 |", "After."]
        self.assertEqual(extract.join_table_rows(paras),
                         ["Lead-in:", "| A | B |\n| --- | --- |\n| 1 | 2 |", "After."])
        self.assertEqual(extract.join_table_rows(["a | b", "| A |"]), ["a | b", "| A |"])


class ReextractionCheck(TempProject, unittest.TestCase):
    """extract.py --check: re-extract into temporary folders and compare with Work/Chapters."""

    CFG = {"md": "src.md", "slug": "src", "title": "Book", "part": 1,
           "chapters": [{"unit_id": "ch-01", "slug": "war", "title": "War"}]}

    def test_identical_then_changed_then_missing(self):
        self.write("Sources/src.md", "## War\n\nWar began.\n")
        self.assertTrue(quiet(extract.extract_source, self.CFG)[0])
        chapters = extract.OUT
        self.assertEqual(quiet(extract.check_sources, [self.CFG])[0], 0)
        self.assertEqual(extract.OUT, chapters)      # restored after the check
        path = os.path.join(chapters, "src", "01-war.md")
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write("A hand edit.\n")
        problems, out = quiet(extract.check_sources, [self.CFG])
        self.assertEqual(problems, 1)
        self.assertIn("DIFFERS Work/Chapters/src/01-war.md", out)
        self.assertIn("-A hand edit.", out)
        os.rename(path, os.path.join(chapters, "src", "01-peace.md"))
        problems, out = quiet(extract.check_sources, [self.CFG])
        self.assertEqual(problems, 2)
        self.assertIn("NEW Work/Chapters/src/01-war.md", out)
        self.assertIn("MISSING Work/Chapters/src/01-peace.md", out)

    def test_a_stopped_run_still_writes_the_repair_log(self):
        self.write("Sources/t.txt", "Chapter One\n\nThe boats came home.\n")
        cfg = {"txt": "t.txt", "slug": "t", "title": "T", "part": 1,
               "chapters": [{"unit_id": "ch-01", "slug": "a", "title": "A", "start": 1, "end": 1,
                             "first_line": "Nowhere"}]}
        with self.assertRaises(SystemExit):
            quiet(extract.extract_source, cfg)
        self.assertTrue(os.path.exists(os.path.join(extract.RAW, "t", "repairs.tsv")))

    def test_config_errors_stop_before_anything_is_written(self):
        cfg = dict(self.CFG, line_edits={0: "x"})
        with self.assertRaises(SystemExit) as cm:
            quiet(extract.extract_source, cfg)
        self.assertIn("config errors in src:", str(cm.exception))
        self.assertFalse(os.path.exists(os.path.join(extract.OUT, "src")))
        self.assertFalse(quiet(extract.extract_source, dict(self.CFG, chapters=[]))[0])


class Register(TempProject, unittest.TestCase):
    """The source's register (a chapter's own overrides it) goes into each chapter file's frontmatter."""

    MD = "## War\n\nWar began.\n\n## Peace\n\nPeace came.\n"
    CHAPTERS = [{"unit_id": "ch-01", "slug": "war", "title": "War"},
                {"unit_id": "ch-02", "slug": "peace", "title": "Peace"}]

    def config(self, slug, register=None, chapter_registers=(None, None)):
        chapters = [dict(ch, register=r) if r else dict(ch) for ch, r in zip(self.CHAPTERS, chapter_registers)]
        cfg = {"md": "src.md", "slug": slug, "title": "Book", "part": 1, "chapters": chapters}
        if register:
            cfg["register"] = register
        return cfg

    def front(self, slug, name):
        return parse_frontmatter(Path(extract.OUT, slug, name).read_text(encoding="utf-8"))[0]

    def setUp(self):
        super().setUp()
        self.write("Sources/src.md", self.MD)

    def test_frontmatter_order_and_chapter_override(self):
        _, out = quiet(extract.extract_source, self.config("src", "modern", (None, "source")))
        war = self.front("src", "01-war.md")
        self.assertEqual(list(war), ["source", "source_slug", "unit_id", "part", "chapter", "title", "register",
                                     "pdf_pages", "printed_pages", "word_count"])
        self.assertEqual(war["register"], "modern")
        self.assertEqual(self.front("src", "02-peace.md")["register"], "source")
        self.assertIn('title: "War"\nregister: "modern"\npdf_pages: ""\n',
                      Path(extract.OUT, "src", "01-war.md").read_text(encoding="utf-8"))
        self.assertNotIn("register not set", out)

    def test_unset_register_is_source_with_one_warning_per_source(self):
        folder = os.path.join(self.tmp, "Configs")
        os.makedirs(folder)
        configs = {"a_src.py": self.config("a-src"), "b_src.py": self.config("b-src", "modern"),
                   "c_src.py": self.config("c-src", None, ("modern", "source")),
                   "d_src.py": self.config("d-src", None, ("modern", None))}
        for name, cfg in configs.items():
            self.write(os.path.join("Configs", name), "CONFIG = %r\n" % cfg)
        old = extract.SOURCE_CONFIGS
        extract.SOURCE_CONFIGS = folder
        try:
            code, out = quiet(extract.main, [])
        finally:
            extract.SOURCE_CONFIGS = old
        self.assertEqual(code, 0, out)
        warnings = [ln for ln in out.splitlines() if "register not set" in ln]
        self.assertEqual(warnings, ["WARNING a-src: register not set; using source (plan.md Preflight)",
                                    "WARNING d-src: register not set; using source (plan.md Preflight)"])
        self.assertEqual([self.front("a-src", n)["register"] for n in ("01-war.md", "02-peace.md")],
                         ["source", "source"])
        self.assertEqual([self.front("d-src", n)["register"] for n in ("01-war.md", "02-peace.md")],
                         ["modern", "source"])

    def test_invalid_register_stops_before_anything_is_written(self):
        with self.assertRaises(SystemExit) as cm:
            quiet(extract.extract_source, self.config("src", None, (None, "victorian")))
        self.assertIn("src: chapter 'ch-02': register 'victorian' must be", str(cm.exception))
        self.assertFalse(os.path.exists(os.path.join(extract.OUT, "src")))


class CountWordsOfFiles(TempProject, unittest.TestCase):
    def test_frontmatter_is_not_counted(self):
        self.write("Sources/src.md", "## War\n\n<!-- page break -->\n\nWar began in the spring.\n")
        cfg = {"md": "src.md", "slug": "src", "title": "Book", "part": 1,
               "chapters": [{"unit_id": "ch-01", "slug": "war", "title": "War"}]}
        quiet(extract.extract_source, cfg)
        path = os.path.join(extract.OUT, "src", "01-war.md")
        self.assertIn("word_count: 5\n", Path(path).read_text(encoding="utf-8"))
        self.assertEqual(words_of(path), 5)

    def test_files_without_frontmatter_are_counted_whole(self):
        self.assertEqual(words_of(self.write("a.md", "## Heading\n\nFour words of summary.\n")), 4)
        self.assertEqual(words_of(self.write("b.md", "---\nno closing line\n")), 4)


class ChapterScan(TempProject, unittest.TestCase):
    """check_chapters.py: forbidden characters, warnings, and boundary paragraphs."""

    RAW = ('---\nsource: "Book"\nword_count: 999\n---\n\n# War\n\n'
           '<!-- page 3 -->\nThe war began in the spring.\n\n'
           'Smith &amp; Jones of AT&T; met � there.\n\n'
           "A run  of words , a popu- lation, pre- and post-war, Polish'spring and Penhale's boat.\n\n"
           '> A quoted line that runs on for more than ten words and then stops\n\n'
           'This paragraph also runs on for more than ten words and stops without\n\n'
           'A Section Heading\n\n'
           'Last body paragraph ends here.\n\n'
           'Notes to this chapter (printed as footnotes in the source):\n\n'
           '<!-- footnote on page 3 -->\n1 A note without an end\n')

    def test_errors_warnings_and_boundaries(self):
        result = check_chapters.scan(self.RAW)
        self.assertEqual(result["errors"], [(11, "U+FFFD replacement character x1: ...mith &amp; Jones of AT&T; met "
                                                 "� there."),
                                            (11, "HTML entity x1: Smith &amp; Jones of AT&T; met � there.")])
        messages = [m.split(":")[0] for _, m in result["warnings"]]
        self.assertEqual(messages, ["word_count 999 in the frontmatter, 80 on a recount", "double space",
                                    "space before punctuation", "hyphen-space (x- y)",
                                    "letter, quotation mark, letter run together",
                                    "paragraph does not end a sentence", "paragraph does not end a sentence"])
        self.assertIn("Polish'spring", result["warnings"][4][1])
        # The short unpunctuated line reads as a section heading and is not flagged.
        self.assertEqual([n for n, m in result["warnings"] if m.startswith("paragraph")], [15, 17])
        self.assertEqual(result["first"], "The war began in the spring.")
        self.assertEqual(result["last"], "Last body paragraph ends here.")

    def test_names_and_series_items_are_not_flagged(self):
        raw = ('---\nword_count: 29\n---\n\n# T\n\nCh’en and Dong’an met o\'clock-wise at Penhale\'s quay, '
               'and the students’ union met too.\n\n'
               'That the council shall meet monthly in the hall of the harbour board at Northgate;\n')
        self.assertEqual(check_chapters.scan(raw)["warnings"], [])

    def test_every_forbidden_kind(self):
        for text in ("xy", "co­operate", "&#8212;", "ﬁrst", "GLYPH<c=3>", "@@furniture 12"):
            raw = '---\nword_count: 1\n---\n\n# T\n\n%s\n' % text
            self.assertEqual(len(check_chapters.scan(raw)["errors"]), 1, text)

    def test_extract_labels_come_from_common(self):
        from common import NOTES_LABELS
        self.assertEqual((extract.FOOTNOTES_LABEL, extract.NOTES_LABEL), NOTES_LABELS)
        raw = ('---\nword_count: 1\n---\n\n# T\n\nBody ends.\n\n%s\n\n1 A note without an end\n' % NOTES_LABELS[1])
        self.assertEqual(check_chapters.scan(raw)["warnings"][1:], [])
        self.assertEqual(check_chapters.scan(raw)["last"], "Body ends.")

    def test_main_exit_status(self):
        old = check_chapters.CHAPTERS
        check_chapters.CHAPTERS = Path(self.tmp) / "Chapters"
        try:
            self.write("Chapters/src/01-war.md", '---\nword_count: 2\n---\n\n# War\n\nWar began.\n')
            self.write("Chapters/src/parts/01-war-part1-of-2.md", "Bad �.\n")
            code, out = quiet(check_chapters.main, ["src"])
            self.assertEqual(code, 0, out)
            self.assertIn("1 chapter file(s): 0 with forbidden characters, 0 warning(s)", out)
            self.write("Chapters/src/02-peace.md", '---\nword_count: 2\n---\n\n# Peace\n\nPeace �.\n')
            code, out = quiet(check_chapters.main, [])
            self.assertEqual(code, 1)
            self.assertIn("ERROR line 7: U+FFFD", out)
            with self.assertRaises(SystemExit) as cm:
                check_chapters.main(["nope"])
            self.assertIn("no chapter folder Work/Chapters/nope", str(cm.exception))
        finally:
            check_chapters.CHAPTERS = old


class MarkdownToc(unittest.TestCase):
    MD = ("# The Grey Harbour\n\nBy Ada Penhale.\n\n<!-- page break -->\n\nTHE GREY HARBOUR\n\n## 1 The Quay\n\n"
          "The boats came \"home\" at dawn — late.\n\n<!-- image -->\n\nTHE GREY HARBOUR\n\n"
          "A popu- lation of *fishers* &amp; others.\n\n<!-- page break -->\n\nTHE GREY HARBOUR\n\n"
          "## 2 The Tide\n\nIt’s low - again.\n")

    def test_heading_table_and_counts(self):
        out = md_toc.toc(self.MD, "grey.md")
        self.assertEqual(out[0], "# grey.md: 31 words, 3 headings, 25 lines")
        self.assertEqual(out[1], "# placeholders: page break 2; image 1; formula 0; other comment lines: none")
        self.assertIn("HTML entities 1", out[2])
        self.assertEqual(out[3], "# quotes: straight \" 2, ' 0; curly “ 0, ” 0, ‘ 0, ’ 1")
        self.assertEqual(out[4], "# dashes: em — 1, en – 0; spaced hyphen \" - \" 1; hyphen-space \"x- y\" 1")
        self.assertEqual(out[5], "# emphasis spans (*x* or **x**): 1")
        self.assertEqual(out[6], "# repeated short paragraphs (running heads?): 'THE GREY HARBOUR' x3")
        self.assertEqual(out[8:], ["     0       0  (start)", "     1       6  # The Grey Harbour",
                                   "     9      21  ## 1 The Quay", "    23       4  ## 2 The Tide"])
