"""Tests for the source-fidelity checker (check_fidelity.py) and the
paragraph, attribution, quotation, and number-word checks in
check_style_pass.py. Run from the project root:

    python -m unittest discover -s Work/tests
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import check_author_refs  # noqa: E402
import check_fidelity  # noqa: E402
import check_style_pass  # noqa: E402

SOURCE = """---
title: "The Mill"
word_count: 120
---

# The Mill

<!-- page 1 -->
In 1931 the mill employed 1,250 workers, twelve of them boys, and output was 12 percent lower. Ada Penhale wrote that the town was “a place of quiet, stubborn people who kept the river’s counsel.” Costs rose to 3 million pounds.

Marlow described the harbour:

<!-- page 2 -->
> We watched the harbour closely. And I knew the <!-- page 3 --> boats.

> Every one of them, 40 in all. (Marlow 1986, 82)

Then Tom Smyth came to the town in 1937.

> The river keeps its own counsel. —Ada Penhale 1937, 16
"""


def flags(summary, source=SOURCE, allowed=()):
    return check_fidelity.check(summary, source, allowed)


def kinds(found):
    return [(f[0], f[1]) for f in found]


class FidelityNumbers(unittest.TestCase):
    def test_unsupported_digit_is_flagged(self):
        found = flags("## T\n\nThe mill employed 1,300 workers in 1931.\n")
        self.assertEqual(kinds(found), [("NUMBER", "1,300")])
        self.assertEqual(found[0][2:4], (2, 3))

    def test_thousands_separators_percent_and_ordinals(self):
        self.assertEqual(flags("## T\n\nIt employed 1250 workers; output was 12% lower in the 1931st year.\n"), [])
        self.assertEqual(flags("## T\n\nIt employed 1,250 workers.\n", "It employed 1250 workers.\n"), [])

    def test_digit_and_word_forms_support_each_other(self):
        # "twelve" in the source supports 12; 3 million supports 3,000,000.
        self.assertEqual(flags("## T\n\nTwelve were boys, and 12 more. Costs reached 3,000,000 pounds.\n"), [])
        self.assertEqual(flags("## T\n\nIt had twelve boys.\n", "It had 12 boys.\n"), [])
        self.assertEqual(flags("## T\n\nCosts were 3 million.\n", "Costs were 3,000,000.\n"), [])

    def test_number_words_flagged_only_without_any_form(self):
        self.assertEqual(kinds(flags("## T\n\nOutput fell by half and then by a third.\n")),
                         [("NUMBER", "half"), ("NUMBER", "third")])
        self.assertEqual(kinds(flags("## T\n\nTwenty-five ships came.\n")), [("NUMBER", "Twenty-five")])
        self.assertEqual(flags("## T\n\nOutput fell by half.\n", "Output fell by 1/2.\n"), [])
        self.assertEqual(flags("## T\n\nOutput fell 12 percent.\n", "Output fell 12%.\n"), [])

    # Bug 2: a multi-word run needs its value, not just its words, in the source.
    def test_multi_word_runs_need_their_value(self):
        src = "Three thousand came, and a hundred left. Five looms and twenty spindles stood.\n"
        self.assertEqual(kinds(flags("## T\n\nThree hundred workers came.\n", src)),
                         [("NUMBER", "Three hundred")])
        self.assertEqual(kinds(flags("## T\n\nThere were twenty-five looms.\n", src)),
                         [("NUMBER", "twenty-five")])
        self.assertEqual(flags("## T\n\nThere were twenty-five looms.\n", "There were 25 looms.\n"), [])
        self.assertEqual(flags("## T\n\nThere were 25 looms.\n", "There were twenty five looms.\n"), [])
        # A single word is still supported by the same word.
        self.assertEqual(flags("## T\n\nA hundred left.\n", src), [])

    # Bug 3: "and" joins number words only after a scale, for a smaller value.
    def test_and_does_not_sum_separate_numbers(self):
        src = "It cost between two and three pence.\n"
        self.assertEqual(kinds(flags("## T\n\nIt cost 5 pence.\n", src)), [("NUMBER", "5")])
        self.assertEqual(kinds(flags("## T\n\nIt cost two or three pence.\n", src)), [])
        self.assertEqual(flags("## T\n\nIt cost 205 pence.\n", "It cost two hundred and five pence.\n"), [])
        self.assertEqual(flags("## T\n\nIt cost two hundred and five pence.\n", "It cost 205 pence.\n"), [])
        self.assertEqual(flags("## T\n\nIt cost 1,500.\n", "It cost one thousand and five hundred.\n"), [])
        self.assertEqual(kinds(flags("## T\n\nTwo and three came.\n", "It cost 5 pence.\n")),
                         [("NUMBER", "Two"), ("NUMBER", "three")])
        runs = check_fidelity.number_word_runs("a hundred and two thousand")
        self.assertEqual([w for _, _, w in runs], [["hundred"], ["two", "thousand"]])

    def test_ordinal_words_match_digit_ordinals(self):
        self.assertEqual(flags("## T\n\nIn the nineteenth century, the twenty-first mill.\n",
                               "In the 19th century, the 21st mill.\n"), [])
        self.assertEqual(flags("## T\n\nIn the 19th century.\n", "In the nineteenth century.\n"), [])
        self.assertEqual(flags("## T\n\nThe twenty-third mill.\n", "The 23rd mill.\n"), [])
        self.assertEqual(kinds(flags("## T\n\nThe fifth mill.\n", "The mill.\n")), [("NUMBER", "fifth")])
        # "first", "second" and "third" alone are not numbers (or, for third, a fraction).
        self.assertEqual(flags("## T\n\nThe first and second mills.\n", "The mills.\n"), [])

    def test_vulgar_fractions_are_numbers(self):
        self.assertEqual(kinds(flags("## T\n\nOutput fell by ⅓.\n", "Output fell.\n")), [("NUMBER", "⅓")])
        self.assertEqual(kinds(flags("## T\n\nIt was 1½ miles.\n", "It was 1 mile.\n")), [("NUMBER", "½")])
        for src in ("Output fell by ⅓.\n", "Output fell by 1/3.\n", "Output fell by a third.\n",
                    "Output fell by one-third.\n", "Output fell by One Third.\n"):
            self.assertEqual(flags("## T\n\nOutput fell by ⅓.\n", src), [], src)
        self.assertEqual(flags("## T\n\nHalf left, then ½ and ¾ more, then ⅔.\n",
                               "Half left, then three quarters, then two-thirds.\n"), [])
        # Neither the value nor the words: 1/4 does not support ¾, nor "third" ⅔.
        self.assertEqual(kinds(flags("## T\n\nThen ¾ and ⅔.\n", "Then 1/4 and a third.\n")),
                         [("NUMBER", "¾"), ("NUMBER", "⅔")])

    # A fraction in words is supported by the character the source prints.
    def test_fraction_words_are_supported_by_the_character(self):
        for summary, src in [("Two-thirds left.", "Then ⅔ left."), ("Three-quarters left.", "Then ¾ left."),
                             ("One fifth left.", "Then ⅕ left."), ("Three eighths left.", "Then ⅜ left."),
                             ("Two thirds left.", "Then 2/3 left."), ("2/3 left.", "Then ⅔ left."),
                             ("⅔ left.", "Then two-thirds left.")]:
            self.assertEqual(flags("## T\n\n%s\n" % summary, src + "\n"), [], summary)
        # A different fraction still does not support it.
        self.assertEqual(kinds(flags("## T\n\nTwo-thirds left.\n", "Then ⅓ left.\n")), [("NUMBER", "Two")])
        self.assertEqual(kinds(flags("## T\n\nThree quarters left.\n", "Then ¼ left.\n")), [("NUMBER", "Three")])

    def test_numbers_in_a_reproduced_block_quote_are_ignored_only_if_it_passes(self):
        good = "## T\n\nMarlow recalls:\n\n> We watched the harbour closely. And I knew the boats.\n\n> Every one of them, 40 in all.\n"
        self.assertEqual(flags(good), [])
        bad = good.replace("40", "41")
        self.assertEqual([f[0] for f in flags(bad)], ["BLOCKQUOTE", "NUMBER"])


class FidelityQuotes(unittest.TestCase):
    def test_exact_quote_passes_across_quote_styles(self):
        self.assertEqual(flags('## T\n\nShe calls it "a place of quiet, stubborn people who kept the river\'s counsel."\n'), [])
        self.assertEqual(flags("## T\n\nShe calls it ‘a place of quiet, stubborn people’.\n"), [])

    def test_altered_quote_is_flagged(self):
        found = flags("## T\n\nShe calls it “a place of quiet, stubborn folk.”\n")
        self.assertEqual(kinds(found), [("QUOTE", "a place of quiet, stubborn folk.")])
        found = flags("## T\n\nShe calls it ‘a place of loud people’.\n")
        self.assertEqual(kinds(found), [("QUOTE", "a place of loud people")])

    def test_first_letter_case_and_trailing_punctuation(self):
        self.assertEqual(flags("## T\n\nThe town was, she says, “A place of quiet, stubborn people.”\n"), [])

    def test_ellipsis_is_a_gap_in_order(self):
        self.assertEqual(flags("## T\n\nIt was “a place of quiet … who kept the river’s counsel.”\n"), [])
        self.assertEqual(flags("## T\n\nIt was “a place of quiet ... who kept the river’s counsel.”\n"), [])
        found = flags("## T\n\nIt was “who kept the river’s counsel … a place of quiet.”\n")
        self.assertEqual([f[0] for f in found], ["QUOTE"])

    def test_short_quotes_and_apostrophes_are_not_checked(self):
        # Two-word quotation; apostrophes in mill’s, workers’, ’tis are not quotes.
        text = "## T\n\nThe mill’s workers’ union called it “the end” and ’tis said they left the Penhale mill’s yard.\n"
        self.assertEqual([f for f in flags(text, allowed={"Penhale"}) if f[0] == "QUOTE"], [])
        self.assertEqual(check_fidelity.quote_spans("the mill’s workers’ union met ‘in the old yard’ today"),
                         [(30, 47, "in the old yard")])

    # Bug 6: straight single quotations are checked; apostrophes are not quotes.
    def test_straight_single_quotes_are_checked(self):
        self.assertEqual(flags("## T\n\nShe calls it 'a place of quiet, stubborn people' today.\n"), [])
        found = flags("## T\n\nShe calls it 'a place of loud people' today.\n")
        self.assertEqual(kinds(found), [("QUOTE", "a place of loud people")])
        found = flags("## T\n\nShe calls it ('a place of loud people').\n")
        self.assertEqual(kinds(found), [("QUOTE", "a place of loud people")])

    def test_straight_apostrophes_are_not_paired(self):
        text = ("The workers' houses and the owners' mills, and 'tis said they don't leave "
                "the yard's gate; the '90s rock 'n' roll, 'em all, the mill's 'old ways'.")
        self.assertEqual(check_fidelity.quote_spans(text), [])
        self.assertEqual(check_fidelity.quote_spans(text, straight_single=False), [])
        # Mixed with a real quotation, only the quotation is taken.
        text = "The workers' union said 'the mill is closed' and the owners' agent agreed."
        self.assertEqual([q for _, _, q in check_fidelity.quote_spans(text)], ["the mill is closed"])
        # Straight single quotation nested in a double one is not separate.
        text = "He wrote \"they said 'the mill is closed' to us\" then."
        self.assertEqual([q for _, _, q in check_fidelity.quote_spans(text)],
                         ["they said 'the mill is closed' to us"])

    def test_quoting_part_of_a_block_quotation_is_flagged(self):
        found = flags("## T\n\nMarlow says he “watched the harbour closely.”\n")
        self.assertEqual(kinds(found), [("QUOTE", "watched the harbour closely.")])
        self.assertIn("block quotation", found[0][4])


class FidelityBlockQuotes(unittest.TestCase):
    def test_whole_quotation_minus_citation_passes(self):
        text = "## T\n\nMarlow recalls:\n\n> We watched the harbour closely. And I knew the boats.\n\n> Every one of them, 40 in all.\n"
        self.assertEqual(flags(text), [])

    def test_dash_attribution_is_stripped(self):
        self.assertEqual(flags("## T\n\nThe chapter opens:\n\n> The river keeps its own counsel.\n"), [])

    def test_partial_quotation_is_flagged(self):
        found = flags("## T\n\nMarlow recalls:\n\n> We watched the harbour closely. And I knew the boats.\n")
        self.assertEqual(found[0][0], "BLOCKQUOTE")
        self.assertTrue(found[0][1].startswith("PARTIAL"))

    def test_altered_quotation_is_flagged(self):
        found = flags("## T\n\nMarlow recalls:\n\n> We watched the harbor closely. And I knew the boats.\n\n> Every one of them, 40 in all.\n")
        self.assertTrue(found[0][1].startswith("ALTERED"))
        self.assertIn("closest source quotation: We watched the harbour", found[0][4])

    def test_kept_citation_is_flagged(self):
        found = flags("## T\n\nMarlow recalls:\n\n> We watched the harbour closely. And I knew the boats.\n\n> Every one of them, 40 in all. (Marlow 1986, 82)\n")
        self.assertTrue(found[0][1].startswith("ALTERED"))
        self.assertIn("citation", found[0][4])


class FidelityNames(unittest.TestCase):
    def test_corrected_spelling_and_invented_actor_are_flagged(self):
        found = flags("## T\n\nIn 1937 the town met Tom Smith and later John Brown.\n")
        self.assertEqual(kinds(found), [("NAME", "Smith"), ("NAME", "John Brown")])

    def test_sentence_start_capitals_are_not_flagged(self):
        text = ("## T\n\nTherefore the mill closed. Afterwards it stayed shut: Nobody came. "
                "“Whatever happened,” she said. (Meanwhile it rained.)\n\n- Despite this, it reopened.\n")
        found = [f for f in flags(text) if f[0] == "NAME"]
        self.assertEqual(kinds(found), [("NAME", "Meanwhile")])

    def test_author_forms_and_builtin_allowlist(self):
        text = "## T\n\nIn this Chapter the town, as I read it, is what Hale calls quiet.\n"
        self.assertEqual(kinds(flags(text)), [("NAME", "Hale")])
        self.assertEqual(flags(text, allowed={"Hale"}), [])

    def test_author_forms_come_from_author_refs(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "author_refs.json"
            config.write_text(json.dumps({"refs": {"s": ["Ida Hale", "Hale"], "s/03-talk": ["Quint"]}}),
                              encoding="utf-8")
            saved = check_author_refs.CONFIG
            check_author_refs.CONFIG = config
            try:
                forms = check_fidelity.author_forms("Work/Drafts/s/parts/03-talk-part1-of-2.md")
            finally:
                check_author_refs.CONFIG = saved
        self.assertTrue({"Ida", "Hale", "Quint"} <= forms)

    def test_quoted_text_and_headings_are_skipped(self):
        text = "## Smith and Brown\n\nShe calls it “a place of quiet, stubborn Folk.”\n"
        self.assertEqual([f[0] for f in flags(text)], ["QUOTE"])

    # Bug 4: the period after a title or an initial does not end a sentence.
    def test_names_after_titles_and_initials_are_checked(self):
        source = "The mill was run by Mr. Penhale, Dr. Hale and J. Marlow in St. Ives.\n"
        self.assertEqual(flags("## T\n\nIt was run by Mr. Penhale and J. Marlow in St. Ives.\n", source), [])
        found = flags("## T\n\nIt was run by Mr. Jones, Dr. Brown, Prof. Grey, Gen. Lee, Rev. Ames "
                      "and J. Smith in St. Albans.\n", source + "Prof. Gen. Rev.\n")
        self.assertEqual(kinds(found), [("NAME", n) for n in ("Jones", "Brown", "Grey", "Lee", "Ames",
                                                               "Smith", "Albans")])
        # A real sentence end, and the pronoun "I.", still start a sentence.
        self.assertEqual(flags("## T\n\nThe mill closed. Then it rained, as did I. Afterwards it dried.\n",
                               "The mill closed.\n"), [])

    # A respelled name at a sentence or paragraph start, after ":", after a
    # closing straight quote, or after a trailing possessive is checked.
    def test_names_at_sentence_start_and_after_colon_quotes_and_possessives(self):
        src = ("Josiah Hartley opened the mill. Two men led it: Hodges and Bray. "
               "He said \"the end\" and Smith left. The workers' Union met at Jones' Mill.\n")
        self.assertEqual(kinds(flags("## T\n\nJosias Hartley opened the mill. It grew.\n", src)),
                         [("NAME", "Josias")])
        self.assertEqual(kinds(flags("## T\n\nThe mill closed. Josias Hartley left.\n", src)),
                         [("NAME", "Josias")])
        self.assertEqual(kinds(flags("## T\n\nTwo men led it: Hodge and Bray.\n", src)), [("NAME", "Hodge")])
        self.assertEqual(kinds(flags('## T\n\nHe said "the end" Smyth left.\n', src)), [("NAME", "Smyth")])
        self.assertEqual(kinds(flags("## T\n\nThe workers' Onion met at Jones' Mull.\n", src)),
                         [("NAME", "Onion"), ("NAME", "Mull")])
        self.assertEqual(flags("## T\n\nThe workers' Union met at Jones' Mill.\n", src), [])
        # An opening straight quote still starts a sentence.
        self.assertEqual(check_fidelity.sentence_start('He said "'), True)
        self.assertEqual(check_fidelity.sentence_start('He said "x" '), False)

    def test_sentence_start_words_need_any_case_or_an_opener(self):
        src = "The mill closed and wages fell. Bray left.\n"
        # Openers, a word the source has in lower case, and "-ly," adverbs pass.
        text = ("## T\n\nHowever, the mill closed. Wages fell: Nobody stayed. Unfortunately, Bray left. "
                "Several left.\n\n- Mill closed.\n")
        self.assertEqual(flags(text, src), [])
        self.assertEqual(kinds(flags("## T\n\nMarlow left. Wages fell: Quint stayed.\n", src)),
                         [("NAME", "Marlow"), ("NAME", "Quint")])

    def test_hard_wrapped_quotation_is_checked(self):
        self.assertEqual(flags("## T\n\nShe calls it “a place of quiet,\nstubborn people.”\n"), [])
        found = flags("## T\n\nShe calls it “a place of quiet,\nstubborn folk.”\n")
        self.assertEqual(kinds(found), [("QUOTE", "a place of quiet, stubborn folk.")])

    # Bug 5: a heading line hides only itself, not the text after it.
    def test_text_after_a_heading_line_is_checked(self):
        found = flags("### Section\nThe mill employed 99 men under Jones.\n")
        self.assertEqual(kinds(found), [("NUMBER", "99"), ("NAME", "Jones")])
        self.assertEqual(found[0][2:4], (1, 2))


class FidelityCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.saved = (check_fidelity.ROOT, check_fidelity.PARTS_MANIFEST)
        check_fidelity.ROOT = self.root
        check_fidelity.PARTS_MANIFEST = self.root / "Work" / "parts_manifest.json"

    def tearDown(self):
        check_fidelity.ROOT, check_fidelity.PARTS_MANIFEST = self.saved
        self.tmp.cleanup()

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def run_main(self, argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = check_fidelity.main(argv)
        return code, out.getvalue()

    def test_two_file_mode_output_and_exit_status(self):
        src = self.write("Work/Chapters/s/01-one.md", SOURCE)
        bad = self.write("Work/Drafts/s/01-one.md", "## One\n\nThe mill had 1,300 workers.\n")
        code, out = self.run_main([str(bad), str(src)])
        self.assertEqual(code, 1)
        self.assertIn('NUMBER para 2, line 3: "1,300" | The mill had 1,300 workers.', out)
        self.assertIn("NUMBER 1, QUOTE 0, BLOCKQUOTE 0, NAME 0; 1 flag(s)", out)
        good = self.write("Work/Drafts/s/01-one.md", "## One\n\nThe mill had 1,250 workers.\n")
        self.assertEqual(self.run_main([str(good), str(src)])[0], 0)

    def test_manifest_mode_checks_parts_against_part_files(self):
        part = ("---\nsource_slug: \"s\"\npart_index: 2\n---\n\n# One (Part 2 of 2)\n\n"
                "<!-- overlap context from the end of the previous part: use for reference only -->\n\n"
                "In 1931 the mill employed 1,250 workers.\n\n<!-- end overlap context -->\n\n"
                "<!-- begin owned text -->\nThen Tom Smyth came in 1937.\n<!-- end owned text -->\n")
        self.write("Work/Chapters/s/01-one.md", SOURCE)
        self.write("Work/Chapters/s/parts/01-one-part2-of-2.md", part)
        self.write("Work/Chapters/s/02-two.md", "# Two\n\nNothing happened in 1950.\n")
        # Before the merge: the part summary may use the overlap's number;
        # part 1 has no summary yet.
        self.write("Work/Summaries/s/parts/01-one-part2-of-2.md", "Smyth arrived in 1937, after 1,250 workers.\n")
        self.write("Work/Summaries/s/02-two.md", "## Two\n\nNothing happened in 1950.\n")
        manifest = [
            {"source_slug": "s", "unit_id": "ch-01", "chapter_source": "Work/Chapters/s/01-one.md",
             "summary": "Work/Summaries/s/01-one.md", "part_count": 2, "parts": [
                 {"part_index": 1, "source": "Work/Chapters/s/parts/01-one-part1-of-2.md",
                  "summary": "Work/Summaries/s/parts/01-one-part1-of-2.md"},
                 {"part_index": 2, "source": "Work/Chapters/s/parts/01-one-part2-of-2.md",
                  "summary": "Work/Summaries/s/parts/01-one-part2-of-2.md"}]},
            {"source_slug": "s", "unit_id": "ch-02", "chapter_source": "Work/Chapters/s/02-two.md",
             "summary": "Work/Summaries/s/02-two.md", "part_count": 1, "parts": [
                 {"part_index": 1, "source": "Work/Chapters/s/02-two.md",
                  "summary": "Work/Summaries/s/02-two.md"}]},
        ]
        self.write("Work/parts_manifest.json", json.dumps(manifest))
        code, out = self.run_main([])
        self.assertEqual(code, 0, out)
        self.assertIn("parts/01-one-part2-of-2.md vs ", out)
        self.assertIn("checked 2 summary file(s): NUMBER 0, QUOTE 0, BLOCKQUOTE 0, NAME 0; 0 flag(s)", out)
        # After the merge the chapter summary is checked against the whole
        # chapter, and the stale part summary (now wrong) is skipped.
        self.write("Work/Summaries/s/parts/01-one-part2-of-2.md", "Smyth arrived in 1939.\n")
        self.write("Work/Summaries/s/01-one.md", "## One\n\nSmyth arrived in 1938.\n")
        code, out = self.run_main([])
        self.assertEqual(code, 1)
        self.assertEqual(out.count("== "), 2)
        self.assertNotIn("parts/", out)
        self.assertIn('NUMBER para 2, line 3: "1938"', out)
        self.assertIn("checked 2 summary file(s): NUMBER 1, QUOTE 0, BLOCKQUOTE 0, NAME 0; 1 flag(s)", out)

    def write_manifest(self, units):
        self.write("Work/parts_manifest.json", json.dumps([
            {"source_slug": "s", "unit_id": "ch-%02d" % n, "chapter_source": src, "summary": summ,
             "part_count": 1, "parts": [{"part_index": 1, "source": src, "summary": summ}]}
            for n, (summ, src) in enumerate(units, 1)]))

    # Bug 7: a summary whose source is missing counts as a flag.
    def test_manifest_mode_counts_a_missing_source(self):
        self.write("Work/Summaries/s/01-one.md", "## One\n\nNothing happened.\n")
        self.write_manifest([("Work/Summaries/s/01-one.md", "Work/Chapters/s/01-one.md")])
        code, out = self.run_main([])
        self.assertEqual(code, 1)
        self.assertIn("MISSING source", out)
        self.assertIn("checked 0 summary file(s): NUMBER 0, QUOTE 0, BLOCKQUOTE 0, NAME 0, MISSING 1; 1 flag(s)", out)

    # Bug 1: a cp1252 stdout escapes characters it cannot encode instead of
    # raising, so the report and manifest mode run to the end.
    def test_unencodable_flag_text_is_escaped(self):
        self.write("Work/Chapters/s/01-one.md", "In 1931 the mill opened.\n")
        self.write("Work/Chapters/s/02-two.md", "In 1950 the mill closed.\n")
        self.write("Work/Summaries/s/01-one.md", "## One\n\nIn 1931 Łukasz opened the mill → ⅓ of it.\n")
        self.write("Work/Summaries/s/02-two.md", "## Two\n\nIn 1951 the mill closed.\n")
        self.write_manifest([("Work/Summaries/s/01-one.md", "Work/Chapters/s/01-one.md"),
                             ("Work/Summaries/s/02-two.md", "Work/Chapters/s/02-two.md")])
        raw = io.BytesIO()
        out = io.TextIOWrapper(raw, encoding="cp1252", newline="\n")
        with redirect_stdout(out):
            code = check_fidelity.main([])
        out.flush()
        text = raw.getvalue().decode("cp1252")
        self.assertEqual(code, 1)
        self.assertIn('NAME para 2, line 3: "\\u0141ukasz"', text)
        self.assertIn("\\u2192 \\u2153", text)
        self.assertIn('NUMBER para 2, line 3: "1951"', text)
        self.assertIn("checked 2 summary file(s)", text)


class StylePassMarkers(unittest.TestCase):
    check = staticmethod(check_style_pass.check)

    def test_new_protected_markers(self):
        for word in ("not", "never", "without", "only", "some", "unless", "one of the", "for example"):
            old = "## T\n\nIt is %s the case here, he says.\n" % word
            problems = self.check(old, old.replace(word + " ", ""))
            self.assertTrue(any('"%s" 1 -> 0 in paragraph 2' % word in p for p in problems), (word, problems))

    def test_contractions_count_as_not(self):
        self.assertEqual(self.check("## T\n\nIt did not grow.\n", "## T\n\nIt didn't grow.\n"), [])

    def test_markers_are_compared_per_paragraph(self):
        old = "## T\n\nIt perhaps grew.\n\nIt fell.\n"
        problems = self.check(old, "## T\n\nIt grew.\n\nIt perhaps fell.\n")
        self.assertEqual(problems, ['PROTECTED MARKER hedges "perhaps" 1 -> 0 in paragraph 2'])

    def test_paragraph_count_change_falls_back_to_whole_file(self):
        old = "## T\n\nIt perhaps grew.\n\nIt fell.\n"
        problems = self.check(old, "## T\n\nIt grew and it perhaps fell.\n")
        self.assertEqual(problems, ["PARAGRAPH COUNT 3 -> 2"])

    def test_change_of_tense_is_not_a_loss(self):
        self.assertEqual(self.check("## T\n\nHale argues that it grew.\n", "## T\n\nHale argued that it grew.\n"), [])

    def test_author_preface_is_advisory(self):
        for old in ("## T\n\nPenhale argues that the mill failed.\n",
                    "## T\n\nAs Ada Penhale has argued, the mill failed.\n",
                    "## T\n\nThe author argues that the mill failed.\n",
                    "## T\n\nI argue that the mill failed.\n",
                    "## T\n\nProfessor Penhale argues that the mill failed.\n",
                    "## T\n\nIn Penhale's view, the mill failed.\n"):
            problems = self.check(old, "## T\n\nThe mill failed.\n", ["Ada Penhale", "Penhale"])
            self.assertEqual(len(problems), 1, problems)
            self.assertTrue(problems[0].startswith("ADVISORY"), problems)
            self.assertIn("author preface removed", problems[0])

    def test_other_speaker_marker_drop_is_flagged(self):
        cases = {
            "## T\n\nThe critics argue that the mill failed.\n": "The critics",
            "## T\n\nMarlow claimed that the mill failed.\n": "Marlow",
            '## T\n\n"The mill failed," says Marlow.\n': "Marlow",
            "## T\n\nAccording to Marlow, the mill failed.\n": "Marlow",
            "## T\n\nMarlow and Penhale argue that the mill failed.\n": "Marlow and Penhale",
            "## T\n\nAccording to Marlow and Penhale, the mill failed.\n": "Marlow and Penhale",
            "## T\n\nKelly argues that the mill failed.\n": "Kelly",
            "## T\n\nTom Penhale argues that the mill failed.\n": "Tom Penhale",
        }
        for old, subject in cases.items():
            new = '## T\n\n"The mill failed."\n' if old.startswith('## T\n\n"') else "## T\n\nThe mill failed.\n"
            problems = [p for p in self.check(old, new, ["Penhale"], ["Tom Penhale"]) if "QUOTE" not in p]
            self.assertEqual(len(problems), 1, (old, problems))
            self.assertTrue(problems[0].startswith("ATTRIBUTION DROP"), problems)
            self.assertIn('by "%s"' % subject, problems[0])

    def test_attribution_kept_with_same_subject_passes(self):
        old = "## T\n\nMarlow claimed that the mill failed.\n"
        self.assertEqual(self.check(old, "## T\n\nThe mill failed, Marlow claimed.\n"), [])

    def test_single_curly_quotes_are_checked_and_apostrophes_ignored(self):
        old = "## T\n\nThe mill’s owner called it ‘a quiet, stubborn place’.\n"
        self.assertEqual(self.check(old, "## T\n\nThe owner of the mill called it ‘a quiet, stubborn place’.\n"), [])
        problems = self.check(old, "## T\n\nThe mill’s owner called it ‘a quiet place’.\n")
        self.assertIn('QUOTE CHANGED: "a quiet, stubborn place" -> "a quiet place"', problems)

    def test_number_words_are_checked(self):
        old = "## T\n\nTwelve boys and half the men left.\n"
        problems = self.check(old, "## T\n\nBoys and men left, 12 in all.\n")
        self.assertIn("NUMBER WORD REMOVED: half, twelve", problems)
        self.assertIn("NUMBER ADDED: 12", problems)

    # Bug 9: markers are counted by class, so a swap within a class passes.
    def test_swaps_within_a_class_pass(self):
        swaps = [("but", "however"), ("although", "though"), ("for example", "for instance"),
                 ("no one", "nobody"), ("says", "argues"), ("perhaps", "probably"),
                 ("if", "unless"), ("before", "until")]
        for a, b in swaps:
            old = "## T\n\nMarlow %s it grew, %s the mill fell.\n" % (a, a)
            new = "## T\n\nMarlow %s it grew, %s the mill fell.\n" % (b, b)
            self.assertEqual(self.check(old, new), [], (a, b))

    def test_class_drop_is_flagged_with_lost_markers(self):
        old = "## T\n\nIt grew, but slowly; yet it fell, though not far.\n"
        problems = self.check(old, "## T\n\nIt grew, however slowly; yet it fell, not far.\n")
        self.assertEqual(problems, ['PROTECTED MARKER contrast "but, though" 3 -> 2 in paragraph 2'])
        problems = self.check("## T\n\nIt grew while it fell.\n", "## T\n\nIt grew and it fell.\n")
        self.assertEqual(len(problems), 1)
        self.assertIn('PROTECTED MARKER contrast "while" 1 -> 0 in paragraph 2', problems[0])
        self.assertIn("check sense: 'while' may be temporal", problems[0])

    def test_frame_and_sequence_classes(self):
        cases = [
            ("Suppose the mill closed.", "The mill closed.", 'frames "suppose"'),
            ("Did the mill close?", "The mill closed.", 'frames "?"'),
            ("It asks whether the mill closed.", "It asks if the mill closed.", 'frames "whether"'),
            ("At first the mill grew.", "The mill grew.", 'sequence "at first"'),
            ("The mill grew, then it closed.", "The mill grew and it closed.", 'sequence "then"'),
            ("Nobody came.", "People came.", 'negation "nobody"'),
            ("It grew, provided rain fell.", "It grew as rain fell.", 'conditionals "provided"'),
            ("Mills such as this grew.", "Mills grew.", 'reach "such as"'),
        ]
        for old, new, label in cases:
            problems = self.check("## T\n\n%s\n" % old, "## T\n\n%s\n" % new)
            self.assertTrue(any(p.startswith("PROTECTED MARKER %s" % label) for p in problems), (old, problems))

    # Bug 10: a pronoun subject is a failing ATTRIBUTION CHECK, not ADVISORY.
    def test_pronoun_subject_is_a_failing_check(self):
        cases = [
            ("He argues that", "argue", "He"),
            ("She argues that", "argue", "She"),
            ("It is said that", "say", "It"),
            ("In his view,", "in his view", "his"),
            ("According to them,", "according to", "them"),
        ]
        for preface, marker, subject in cases:
            old = "## T\n\n%s the mill failed.\n" % preface
            problems = self.check(old, "## T\n\nThe mill failed.\n", ["Penhale"])
            self.assertEqual(problems, [
                "ATTRIBUTION CHECK \"%s\" 1 -> 0 in paragraph 2 by pronoun '%s': "
                "confirm who; defect if it was another speaker" % (marker, subject)], old)

    def test_subject_kind(self):
        kind = check_style_pass.subject_kind
        forms, not_author = ["Penhale", "the author", "the authors"], ["Tom Penhale"]
        for subject, expected in [("Penhale", "author"), ("Ada Penhale", "author"),
                                  ("Professor Penhale", "author"), ("The Authors", "author"),
                                  ("I", "author"), ("Penhale and I", "author"), ("he", "pronoun"),
                                  ("Penhale and he", "pronoun"), ("Marlow and Penhale", "other"),
                                  ("Marlow and he", "other"), ("Tom Penhale", "other"),
                                  ("Kelly", "other"), ("?", "other")]:
            self.assertEqual(kind(subject, forms, not_author), expected, subject)

    def test_capitalized_ly_word_is_a_subject_not_an_adverb(self):
        self.assertEqual(check_style_pass.marker_subject(
            "argue", check_style_pass.CLASS_PATTERNS["reporting"][0][1].search("Italy argued it."),
            "Italy argued it."), "Italy")
        text = "Penhale repeatedly argues it."
        match = check_style_pass.CLASS_PATTERNS["reporting"][0][1].search(text)
        self.assertEqual(check_style_pass.marker_subject("argue", match, text), "Penhale")

    # Bug 8: a byte-order mark is not a change.
    def test_bom_is_ignored(self):
        old = "## T\n\nIt perhaps grew.\n"
        self.assertEqual(self.check("﻿" + old, old), [])

    def test_subject_is_found_across_comma_asides(self):
        cases = [
            ("Marlow, for his part, believes Penhale misread the ledgers.", "Penhale misread the ledgers.",
             "ATTRIBUTION DROP", "Marlow"),
            ("Penhale, however, argues that wages fell.", "Wages fell.", "ADVISORY", "Penhale"),
            ("Penhale, the historian, says the mill closed.", "The mill closed.", "ADVISORY", "Penhale"),
            ("Penhale, the historian, however, says the mill closed.", "The mill closed.", "ADVISORY", "Penhale"),
            ("In 1931, Marlow, for his part, believes the mill closed in 1931.", "The mill closed in 1931.",
             "ATTRIBUTION DROP", "Marlow"),
            ("As a rule, the critics, for their part, argue the mill closed.", "As a rule, the mill closed.",
             "ATTRIBUTION DROP", "the critics"),
            # Inverted order after a closing quote (with or without a comma), or with only a subject after the verb.
            ('"The mill closed", says Marlow.', '"The mill closed."', "ATTRIBUTION DROP", "Marlow"),
            ("The mill closed, says Marlow.", "The mill closed.", "ATTRIBUTION DROP", "Marlow"),
        ]
        for old, new, kind, subject in cases:
            problems = [p for p in self.check("## T\n\n%s\n" % old, "## T\n\n%s\n" % new, ["Penhale"])
                        if "reporting" in p or p.startswith(("ADVISORY", "ATTRIBUTION"))]
            self.assertEqual(len(problems), 1, (old, problems))
            self.assertTrue(problems[0].startswith(kind), (old, problems))
            self.assertIn('by "%s"' % subject, problems[0])

    def test_only_the_unit_voice_is_the_author(self):
        refs = {"s": ["Ada Penhale", "Penhale"], "s/03-talk": [["Ida Marlow", "Marlow"], ["Quint"]],
                "s/04-essay": ["Bray"]}
        voice = check_style_pass.voice_forms
        self.assertEqual(voice("s", "01-one", refs), ["Ada Penhale", "Penhale"])
        self.assertEqual(voice("s", "03-talk", refs), ["Ida Marlow", "Marlow"])
        self.assertEqual(voice("s", "04-essay", refs), ["Bray"])
        self.assertEqual(voice("t", "01-one", {"t": [["Hale"], ["Ames"]]}), ["Hale"])
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "author_refs.json"
            config.write_text(json.dumps({"refs": refs, "not_author": {"s": ["Tom Penhale"]}}), encoding="utf-8")
            saved = check_author_refs.CONFIG
            check_author_refs.CONFIG = config
            try:
                forms, not_author = check_style_pass.author_forms_for("Work/Summaries/s/03-talk.md")
            finally:
                check_author_refs.CONFIG = saved
        self.assertEqual((forms, not_author), (["Ida Marlow", "Marlow"], ["Tom Penhale"]))
        self.assertEqual(check_style_pass.name_groups("s", "03-talk", refs),
                         [["Ida Marlow", "Marlow"], ["Quint"], ["Ada Penhale", "Penhale"]])
        self.assertEqual(check_style_pass.name_groups("s", "01-one", refs), [["Ada Penhale", "Penhale"]])
        # In the interview unit, the interviewer's and a second interviewee's
        # markers are another speaker's; only the interviewee's is a preface.
        for speaker, kind in (("Quint", "ATTRIBUTION DROP"), ("Penhale", "ATTRIBUTION DROP"),
                              ("Marlow", "ADVISORY")):
            problems = self.check("## T\n\n%s argues that wages fell.\n" % speaker, "## T\n\nWages fell.\n",
                                  forms, not_author)
            self.assertEqual(len(problems), 1, problems)
            self.assertTrue(problems[0].startswith(kind), (speaker, problems))

    def test_ordinals_are_number_words(self):
        problems = self.check("## T\n\nIn the nineteenth century came the fourth strike.\n",
                              "## T\n\nIn the eighteenth century came the fifth strike.\n")
        self.assertEqual(problems, ["NUMBER WORD REMOVED: fourth, nineteenth",
                                    "NUMBER WORD ADDED: eighteenth, fifth"])
        self.assertIn("NUMBER WORD REMOVED: first, twenty",
                      self.check("## T\n\nThe twenty-first mill.\n", "## T\n\nThe new mill.\n"))
        # A lone first/second is not a number word.
        self.assertEqual(self.check("## T\n\nThe first mill.\n", "## T\n\nThe earliest mill.\n"), [])

    def test_fractions_are_numbers(self):
        self.assertEqual(self.check("## T\n\nIt fell by ⅓.\n", "## T\n\nIt fell by ¼.\n"),
                         ["NUMBER REMOVED: ⅓", "NUMBER ADDED: ¼"])

    def test_change_of_speaker_is_flagged(self):
        old = "## T\n\nMarlow argues that wages fell.\n"
        problems = self.check(old, "## T\n\nQuint argues that wages fell.\n", ["Penhale"])
        self.assertEqual(problems, [
            'ATTRIBUTION DROP "argue" 1 -> 1 in paragraph 2 by "Marlow" (now "Quint"): '
            "speaker changed; defect unless the source gives the view to the new speaker"])
        # The author's view handed to another speaker fails too.
        problems = self.check("## T\n\nPenhale argues that wages fell.\n",
                              "## T\n\nMarlow argues that wages fell.\n", ["Penhale"])
        self.assertTrue(problems[0].startswith('ATTRIBUTION DROP "argue" 1 -> 1 in paragraph 2 by "Penhale"'),
                        problems)
        # A pronoun resolved to a name needs confirming.
        problems = self.check("## T\n\nHe argues that wages fell.\n", "## T\n\nMarlow argues that wages fell.\n")
        self.assertTrue(problems[0].startswith("ATTRIBUTION CHECK"), problems)
        # Same speaker in another form, word order, or with a different verb passes.
        for a, b in [("Penhale argues", "Ada Penhale argues"), ("The critics argue", "Critics argue"),
                     ("Marlow argues", "Marlow notes"), ("Marlow and Quint argue", "Quint and Marlow argue")]:
            self.assertEqual(self.check("## T\n\n%s that wages fell.\n" % a, "## T\n\n%s that wages fell.\n" % b,
                                        ["Ada Penhale", "Penhale"]), [], (a, b))
        # One speaker lost while the count rises is still flagged.
        problems = self.check(old, "## T\n\nQuint argues that wages fell, and Quint says so.\n")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn('by "Marlow"', problems[0])

    def test_widened_reporting_scope_and_sequence_classes(self):
        swaps = [("argues", "notes"), ("says", "points out"), ("claims", "observed"), ("believes", "concedes"),
                 ("warns", "explained"), ("holds", "acknowledges"), ("admits", "recalls"),
                 ("states", "remarked"), ("adds", "asserts"), ("concludes", "said")]
        for a, b in swaps:
            self.assertEqual(self.check("## T\n\nMarlow %s that it grew.\n" % a,
                                        "## T\n\nMarlow %s that it grew.\n" % b), [], (a, b))
        for a, b in [("only", "merely"), ("solely", "just"), ("afterwards", "later"),
                     ("subsequently", "then"), ("previously", "before"), ("formerly", "earlier")]:
            self.assertEqual(self.check("## T\n\nIt %s grew.\n" % a, "## T\n\nIt %s grew.\n" % b), [], (a, b))
        problems = self.check("## T\n\nIt merely grew; formerly it fell.\n", "## T\n\nIt grew; it fell.\n")
        self.assertEqual(problems, ['PROTECTED MARKER scope "merely" 1 -> 0 in paragraph 2',
                                    'PROTECTED MARKER sequence "formerly" 1 -> 0 in paragraph 2'])
        problems = self.check("## T\n\nMarlow pointed out that it grew.\n", "## T\n\nIt grew.\n")
        self.assertEqual(len(problems), 1)
        self.assertIn('ATTRIBUTION DROP "point out" 1 -> 0 in paragraph 2 by "Marlow"', problems[0])
        # The noun "state" (or "note") is not a reporting verb.
        self.assertEqual(self.check("## T\n\nThe state grew, and a note and his notes survive.\n",
                                    "## T\n\nThe government grew, and a memo and his papers survive.\n"), [])

    def test_hard_wrapped_quotation_is_checked(self):
        old = '## T\n\nShe called it "a quiet,\nstubborn place" then.\n'
        self.assertEqual(self.check(old, '## T\n\nShe called it "a quiet, stubborn\nplace" then.\n'), [])
        problems = self.check(old, '## T\n\nShe called it "a quiet\nplace" then.\n')
        self.assertEqual(problems, ['QUOTE CHANGED: "a quiet, stubborn place" -> "a quiet place"'])

    def subject(self, text, marker="claim"):
        pattern = dict(check_style_pass.CLASS_PATTERNS["reporting"])[marker]
        return check_style_pass.marker_subject(marker, pattern.search(text), text)

    def attribution(self, old, new, *speakers):
        return [p for p in self.check("## T\n\n%s\n" % old, "## T\n\n%s\n" % new, *speakers)
                if not p.startswith("PROTECTED MARKER") or "reporting" in p]

    # Style bug 1: a digit comma is no clause break, and "that" is no subject.
    def test_digit_commas_and_that_are_not_subjects(self):
        self.assertEqual(self.subject("Marlow, the journalist, claimed that 4,000 marched."), "Marlow")
        self.assertEqual(self.subject("Output rose 1.5 percent, Marlow claims."), "Marlow")
        self.assertEqual(self.subject("In Leeds, the mill failed, claims Marlow."), "Marlow")
        self.assertEqual(self.subject("Penhale, however, argues the owners, not the union, were to blame.", "argue"),
                         "Penhale")
        self.assertEqual(self.subject("Marlow, for his part, claims Penhale."), "Marlow")
        self.assertEqual(self.attribution("Thompson, however, claims that 4,000 marched.",
                                          "Penhale, however, claims that 4,000 marched.", ["Penhale"]), [
            'ATTRIBUTION DROP "claim" 1 -> 1 in paragraph 2 by "Thompson" (now "Penhale"): '
            "speaker changed; defect unless the source gives the view to the new speaker"])
        problems = self.attribution("Penhale, however, argues the owners, not the union, were to blame.",
                                    "However, the owners, not the union, were to blame.", ["Penhale"])
        self.assertEqual(len(problems), 1, problems)
        self.assertTrue(problems[0].startswith('ADVISORY "argue" 1 -> 0 in paragraph 2 by "Penhale"'), problems)

    # Style bug 2: speakers are aligned in order, and a view that moved fails.
    def test_speakers_are_aligned_in_order(self):
        self.assertEqual(self.check("## T\n\nQuint says the union was weak; Marlow says it was strong.\n",
                                    "## T\n\nQuint says the union was strong; Marlow says it was weak.\n"), [
            'VIEW MOVED "say" 2 -> 2 in paragraph 2: "Quint" now reports "strong" (from "Marlow"); '
            '"Marlow" now reports "weak" (from "Quint"): defect unless the source gives each view to its new speaker'])
        # The voice and the interviewer swapped: the order changed.
        voice, groups = ["Ida Marlow", "Marlow"], [["Ida Marlow", "Marlow"], ["Quint"]]
        problems = self.check("## T\n\nMarlow says the pits were safe; Quint suggests they were not.\n",
                              "## T\n\nQuint says the pits were safe; Marlow suggests they were not.\n",
                              voice, [], groups)
        self.assertIn('SPEAKER ORDER "suggest" 2 -> 2 in paragraph 2: "Marlow", "Quint" -> "Quint", "Marlow": '
                      "the same speakers report in a different order; defect unless each view still goes to "
                      "its own speaker", problems)
        # The author's view handed to the speaker whose preface stayed is no removed preface.
        for new in ("Thompson argues the strike was planned; it was class war.",
                    "Thompson argues the strike was planned, but it was class war."):
            old = new.replace("Thompson argues", "Penhale argues").replace("; it", ". Thompson thinks it").replace(
                ", but it", ", but Thompson thinks it")
            problems = self.attribution(old, new, ["Penhale"])
            self.assertEqual(problems, [
                'ATTRIBUTION DROP "think" 2 -> 1 in paragraph 2 by "Penhale": author preface removed while the '
                'marker of "Thompson" moved onto other words; defect if the author\'s view now goes to that speaker'],
                old)
        # Faithful edits pass: a removed preface with the other speaker left
        # in place, merged sentences, a pronoun for a noun, new wording.
        problems = self.check("## T\n\nPenhale argues the strike was planned. Thompson thinks it was class war.\n",
                              "## T\n\nThe strike was planned. Thompson thinks it was class war.\n", ["Penhale"])
        self.assertEqual([p[:8] for p in problems], ["ADVISORY"])
        for old, new in [("Marlow says the mill failed. Quint says wages fell.",
                          "Marlow says the mill failed, and Quint says wages fell."),
                         ("Marlow says the union was weak; Quint says it was strong.",
                          "Marlow says it was weak; Quint says the union was strong."),
                         ("Marlow argues that wages fell sharply.", "Marlow contends that pay dropped steeply."),
                         ("Marlow claimed that the mill failed.", "The mill failed, Marlow claimed.")]:
            self.assertEqual(self.check("## T\n\n%s\n" % old, "## T\n\n%s\n" % new), [], old)

    # Style bug 3: a not_author person or another name group never pairs with the voice.
    def test_another_person_sharing_a_surname_never_pairs(self):
        problems = self.attribution("Tom Penhale argues that wages fell.", "Penhale argues that wages fell.",
                                    ["Penhale"], ["Tom Penhale"])
        self.assertEqual(len(problems), 1, problems)
        self.assertTrue(problems[0].startswith('ATTRIBUTION DROP "argue" 1 -> 1 in paragraph 2 by "Tom Penhale"'))
        voice, groups = ["Ida Marlow", "Marlow"], [["Ida Marlow", "Marlow"], ["Thomas Marlow"]]
        problems = self.attribution("Thomas Marlow claimed that wages fell.", "Marlow claimed that wages fell.",
                                    voice, [], groups)
        self.assertEqual(len(problems), 1, problems)
        self.assertTrue(problems[0].startswith('ATTRIBUTION DROP "claim" 1 -> 1 in paragraph 2 by "Thomas Marlow"'))
        # Forms of one person still pair.
        self.assertEqual(self.check("## T\n\nIda Marlow claimed that wages fell.\n",
                                    "## T\n\nMarlow claimed that wages fell.\n", voice, [], groups), [])
        same = check_style_pass.Speakers(voice, ["Tom Marlow"], groups).same
        self.assertTrue(same("Professor Marlow", "Marlow"))
        self.assertFalse(same("Tom Marlow", "Marlow"))
        self.assertFalse(same("Thomas Marlow", "Ida Marlow"))
        self.assertTrue(same("Thomas Marlow", "Thomas Marlow"))

    # Style bug 4: a relative pronoun stands for its antecedent.
    def test_relative_pronouns_take_their_antecedent(self):
        self.assertEqual(self.subject("Parfit, who also argues X, came.", "argue"), "Parfit")
        self.assertEqual(self.subject("It rests on ordinary opinion, which suggests X.", "suggest"),
                         "ordinary opinion")
        self.assertEqual(self.subject("The critics who argue X are wrong.", "argue"), "The critics")
        self.assertEqual(self.subject("That suggests X.", "suggest"), "That")
        self.assertEqual(self.check("## T\n\nParfit, who argues X, came.\n", "## T\n\nParfit argues X, and came.\n"), [])
        self.assertEqual(self.check("## T\n\nIt rests on ordinary opinion, which suggests X.\n",
                                    "## T\n\nIt rests on ordinary opinions, and they suggest X.\n"), [])
        problems = self.attribution("Parfit, who argues X, came.", "Quint argues X, and came.")
        self.assertTrue(problems[0].startswith('ATTRIBUTION DROP "argue" 1 -> 1 in paragraph 2 by "Parfit"'), problems)
        # An elided subject is the earlier speaker's.
        self.assertEqual(self.subject("Thompson thinks it was class war, and claims that 4,000 marched."),
                         "Thompson")
        self.assertEqual(self.check("## T\n\nThe critics argue X. They also say Y.\n",
                                    "## T\n\nThe critics argue X and say Y.\n"), [])

    # Style bug 5: a pronoun is read as the nearest earlier known name or speaker.
    def test_pronouns_resolve_to_the_nearest_known_name(self):
        problems = self.check("## T\n\nPenhale counts the looms. Most families, she notes, were poor.\n",
                              "## T\n\nPenhale counts the looms. Most families were poor.\n", ["Penhale"])
        self.assertEqual(problems, [
            "ADVISORY \"note\" 1 -> 0 in paragraph 2 by pronoun 'she' (read as \"Penhale\"): author preface "
            "removed; correct if it only introduced the author's own view"])
        problems = self.check("## T\n\nAda Penhale counts the looms. In her view, families were poor.\n",
                              "## T\n\nAda Penhale counts the looms. Families were poor.\n", ["Ada Penhale", "Penhale"])
        self.assertEqual([p[:8] for p in problems], ["ADVISORY"], problems)
        # Another speaker's pronoun: a not_author name, or a reporting subject.
        problems = self.check("## T\n\nTom Penhale came. He notes that families were poor.\n",
                              "## T\n\nTom Penhale came. Families were poor.\n", ["Penhale"], ["Tom Penhale"])
        self.assertEqual(problems, [
            "ATTRIBUTION DROP \"note\" 1 -> 0 in paragraph 2 by pronoun 'He' (read as \"Tom Penhale\"): "
            "another speaker's marker removed; defect unless the view is still marked"])
        problems = self.check("## T\n\nMarlow says wages fell. In his view, families were poor.\n",
                              "## T\n\nMarlow says wages fell. Families were poor.\n", ["Penhale"])
        self.assertTrue(problems[0].startswith("ATTRIBUTION DROP"), problems)
        # A name that is neither known nor a speaker, or none, leaves it unresolved.
        problems = self.check("## T\n\nKelly came. She notes that families were poor.\n",
                              "## T\n\nKelly came. Families were poor.\n", ["Penhale"])
        self.assertTrue(problems[0].startswith("ATTRIBUTION CHECK"), problems)
        # A pronoun for its name, or the reverse, is the same speaker.
        for a, b in [("He argues", "Marlow argues"), ("Marlow argues", "He argues")]:
            self.assertEqual(self.check("## T\n\nMarlow came. %s that wages fell.\n" % a,
                                        "## T\n\nMarlow came. %s that wages fell.\n" % b), [], a)
        # "They" is read as a plural speaker only.
        problems = self.check("## T\n\nThe critics argue X. Penhale agrees. They say Y.\n",
                              "## T\n\nThe critics argue X. Penhale agrees. Y.\n", ["Penhale"])
        self.assertIn("pronoun 'They' (read as \"The critics\")", problems[0])

    # Style bug 6: the same lost subject is reported once, with a count.
    def test_repeated_lost_subject_is_counted(self):
        problems = self.check("## T\n\nPenhale argues A. Penhale argues B.\n", "## T\n\nA. B.\n", ["Penhale"])
        self.assertEqual(problems, [
            'ADVISORY "argue" 2 -> 0 in paragraph 2 by "Penhale" (2 times): author preface removed; '
            "correct if it only introduced the author's own view"])


class StylePassScenarios(unittest.TestCase):
    """Whole units: a faithful house-style rewrite passes (ADVISORY at most);
    each corrupted variant of it fails."""
    REFS = {"mills": ["Ada Penhale", "Penhale"],
            "mills/03-talk": [["Ida Marlow", "Marlow"], ["Quint"], ["Thomas Marlow"]],
            "mills/04-essay": [["Derek Bray", "Bray"]]}

    HISTORY_OLD = """## The Strike of 1926

Penhale argues that the strike was planned months in advance. Thompson, however, thinks it was a spontaneous outbreak of class war, and claims that 4,000 marched on the first day. Penhale, the historian, notes that the owners had stockpiled coal since March.

The union, which suggests in its minutes that wages were the cause, kept no record of the vote, Penhale observes. Most families, she notes, were living on two-thirds of their former wage. Tom Penhale, a mill clerk, recalled that "nobody knew what had been decided."

In Penhale's view, the settlement was a defeat. Marlow says the union was weak; Quint says it was strong. According to Penhale, neither account explains why the strike ended in May.
"""
    HISTORY_NEW = """## The Strike of 1926

The strike was planned months in advance. Thompson, however, holds that it was a spontaneous outbreak of class war, and claims that 4,000 marched on the first day. The owners had stockpiled coal since March.

The union, which suggests in its minutes that wages were the cause, kept no record of the vote. Most families were living on two-thirds of their former wage. Tom Penhale, a mill clerk, recalled that "nobody knew what had been decided."

The settlement was a defeat. Marlow says the union was weak; Quint says it was strong. Neither account explains why the strike ended in May.
"""
    HISTORY_BAD = {
        "speakers swapped": ("Marlow says the union was weak; Quint says it was strong.",
                             "Quint says the union was weak; Marlow says it was strong."),
        "views swapped": ("Marlow says the union was weak; Quint says it was strong.",
                          "Marlow says the union was strong; Quint says it was weak."),
        "other's view into the voice": ("Thompson, however, holds that it was a spontaneous outbreak of class war, "
                                        "and claims that", "However, it was a spontaneous outbreak of class war, and"),
        "voice's view to another": ("The strike was planned months in advance. Thompson, however, holds that it was",
                                    "Thompson argues the strike was planned months in advance; however, it was"),
        "not_author read as the voice": ("Tom Penhale, a mill clerk, recalled", "Penhale recalled"),
        "other speaker renamed as the voice": ("Thompson, however, holds", "Penhale, however, holds"),
    }

    INTERVIEW_OLD = """## Interview with Ida Marlow

Quint asks about the pits. Marlow says the shafts were safe until 1931, but Quint suggests that the owners had cut the timbering. Ida Marlow insists that "the men knew every prop."

Thomas Marlow, her brother, claimed that the lamps were faulty. Marlow adds that he was never underground, and in her view the lamps were sound.

Marlow recalls that the village, which believed the owners, did not strike. According to Quint, the village was divided.
"""
    INTERVIEW_NEW = """## Interview with Ida Marlow

Quint asks about the pits. The shafts were safe until 1931, but Quint suggests that the owners had cut the timbering. Ida Marlow insists that "the men knew every prop."

Thomas Marlow, her brother, claimed that the lamps were faulty. He was never underground, and the lamps were sound.

The village, which believed the owners, did not strike. According to Quint, the village was divided.
"""
    INTERVIEW_BAD = {
        "voice and interviewer swapped": ("The shafts were safe until 1931, but Quint suggests",
                                          "Quint says the shafts were safe until 1931, but Marlow suggests"),
        "interviewer's view into the voice": ("According to Quint, the village", "The village"),
        "brother read as the voice": ("Thomas Marlow, her brother, claimed", "Marlow claimed"),
        "voice's view to the interviewer": ("The shafts were safe until 1931, but Quint suggests",
                                            "Quint says the shafts were safe until 1931, but suggests"),
    }

    ESSAY_OLD = """## On Promising

Bray argues that a promise binds only when it is freely given. Parfit, who argues that obligations fade with personal identity, would deny this. Bray rests his case on ordinary opinion, which suggests that a coerced promise binds no one.

In Bray's view, the hard case is the deathbed promise. Bray notes that Parfit and Scanlon disagree here: Parfit holds that the promise lapses, while Scanlon maintains that it binds the heirs. Bray concludes that neither is right.
"""
    ESSAY_NEW = """## On Promising

A promise binds only when it is freely given. Parfit argues that obligations fade with personal identity, and would deny this. The case rests on ordinary opinions, and they suggest that a coerced promise binds no one.

The hard case is the deathbed promise. Parfit and Scanlon disagree here: Parfit holds that the promise lapses, while Scanlon maintains that it binds the heirs. Neither is right, Bray concludes.
"""
    ESSAY_BAD = {
        "two speakers' views swapped": ("Parfit holds that the promise lapses, while Scanlon maintains",
                                        "Scanlon holds that the promise lapses, while Parfit maintains"),
        "other's view into the voice": ("Parfit argues that obligations fade with personal identity, and would",
                                        "Obligations fade with personal identity, and Parfit would"),
        "voice's view to another": (
            "A promise binds only when it is freely given. Parfit argues that obligations fade with personal identity,",
            "Parfit argues that a promise binds only when it is freely given; obligations fade with personal identity,"),
    }

    def run_unit(self, stem, old, new, bad):
        forms = check_style_pass.voice_forms("mills", stem, self.REFS)
        groups = check_style_pass.name_groups("mills", stem, self.REFS)
        problems = check_style_pass.check(old, new, forms, ["Tom Penhale"], groups)
        self.assertTrue(problems, stem)
        self.assertEqual([p for p in problems if not p.startswith("ADVISORY")], [], stem)
        for label, (a, b) in bad.items():
            self.assertIn(a, new, label)
            problems = check_style_pass.check(old, new.replace(a, b), forms, ["Tom Penhale"], groups)
            self.assertTrue([p for p in problems if not p.startswith("ADVISORY")], (stem, label, problems))

    def test_history_chapter(self):
        self.run_unit("01-strike", self.HISTORY_OLD, self.HISTORY_NEW, self.HISTORY_BAD)

    def test_interview_unit(self):
        self.run_unit("03-talk", self.INTERVIEW_OLD, self.INTERVIEW_NEW, self.INTERVIEW_BAD)

    def test_essay_unit(self):
        self.run_unit("04-essay", self.ESSAY_OLD, self.ESSAY_NEW, self.ESSAY_BAD)


class StylePassCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.saved = check_style_pass.CURRENT
        check_style_pass.CURRENT = self.root / "Summaries"

    def tearDown(self):
        check_style_pass.CURRENT = self.saved
        self.tmp.cleanup()

    def write(self, rel, data):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def run_main(self, stdout, targets=()):
        saved_argv = sys.argv
        sys.argv = ["check_style_pass.py", "--archive", str(self.root / "Archive")] + list(targets)
        try:
            with redirect_stdout(stdout):
                try:
                    check_style_pass.main()
                except SystemExit as e:
                    return e.code
        finally:
            sys.argv = saved_argv

    def test_bom_in_one_file_is_not_a_heading_change(self):
        text = "## One\n\nIt perhaps grew.\n".encode("utf-8")
        self.write("Archive/s/01-one.md", text)
        self.write("Summaries/s/01-one.md", b"\xef\xbb\xbf" + text.replace(b"grew", b"rose"))
        out = io.StringIO()
        self.assertEqual(self.run_main(out), 0, out.getvalue())
        self.assertNotIn("HEADINGS CHANGED", out.getvalue())

    def test_unencodable_report_text_is_escaped(self):
        # Bug 1 (style pass): a cp1252 stdout no longer raises on Ł.
        self.write("Archive/s/01-one.md", "## One\n\nIt grew, Łukasz says.\n".encode("utf-8"))
        self.write("Summaries/s/01-one.md", "## One\n\nIt grew.\n".encode("utf-8"))
        raw = io.BytesIO()
        out = io.TextIOWrapper(raw, encoding="cp1252", newline="\n")
        self.assertEqual(self.run_main(out), 1)
        out.flush()
        self.assertIn(b'by "\\u0141ukasz"', raw.getvalue())

    def test_target_outside_summaries_is_reported_cleanly(self):
        self.write("Archive/s/01-one.md", b"## One\n\nIt grew.\n")
        self.write("Summaries/s/01-one.md", b"## One\n\nIt grew.\n")
        stray = self.write("Drafts/s/01-one.md", b"## One\n\nIt grew.\n")
        out = io.StringIO()
        code = self.run_main(out, [str(stray), str(self.root / "Summaries/s/01-one.md"),
                                   str(self.root / "Summaries/s/02-two.md")])
        self.assertEqual(code, 1, out.getvalue())
        self.assertIn("[error] %s is not under" % stray.as_posix(), out.getvalue())
        self.assertIn("[error] s/02-two.md not found", out.getvalue())
        self.assertIn("[unchanged] s/01-one.md", out.getvalue())
        self.assertNotIn("Traceback", out.getvalue())


if __name__ == "__main__":
    unittest.main()
