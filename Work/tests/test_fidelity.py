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
        # The part summary may use the overlap's number; the chapter summary is
        # checked against the whole chapter; part 1 has no summary yet.
        self.write("Work/Summaries/s/parts/01-one-part2-of-2.md", "Smyth arrived in 1937, after 1,250 workers.\n")
        self.write("Work/Summaries/s/01-one.md", "## One\n\nSmyth arrived in 1938.\n")
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
        self.assertEqual(code, 1)
        self.assertEqual(out.count("== "), 3)
        self.assertIn('NUMBER para 2, line 3: "1938"', out)
        self.assertIn("checked 3 summary file(s): NUMBER 1, QUOTE 0, BLOCKQUOTE 0, NAME 0; 1 flag(s)", out)


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
        self.assertEqual(problems, ['PROTECTED MARKER "perhaps" 1 -> 0 in paragraph 2'])

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
                    "## T\n\nShe argues that the mill failed.\n",
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
            "## T\n\nIt is said that the mill failed.\n": "It",
        }
        for old, subject in cases.items():
            new = '## T\n\n"The mill failed."\n' if old.startswith('## T\n\n"') else "## T\n\nThe mill failed.\n"
            problems = [p for p in self.check(old, new, ["Penhale"]) if "QUOTE" not in p]
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


if __name__ == "__main__":
    unittest.main()
