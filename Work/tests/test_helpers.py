"""Tests for the coordinator helpers: status updates, merging, queues,
snapshots, the style-pass checker, the author-reference checker, and the
sentence-end test shared by extraction and splitting. Run from the project
root:

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
import check_style_pass  # noqa: E402
import make_doc_chunks  # noqa: E402
import make_transition_queue  # noqa: E402
import merge_chapters  # noqa: E402
import set_status  # noqa: E402
import snapshot_summaries  # noqa: E402
from common import ends_sentence, paragraph_break_problems  # noqa: E402


def run(fn, argv=None):
    """Call fn() with sys.argv set; return (exit code, stdout)."""
    saved = sys.argv
    sys.argv = ["x"] + list(argv or [])
    out = io.StringIO()
    try:
        with redirect_stdout(out):
            try:
                fn()
                code = 0
            except SystemExit as exc:
                # sys.exit("message") exits with status 1 and prints the message.
                if isinstance(exc.code, str):
                    out.write(exc.code)
                    code = 1
                else:
                    code = exc.code or 0
    finally:
        sys.argv = saved
    return code, out.getvalue()


class Project(unittest.TestCase):
    """A temporary project with one split chapter (2 parts) and one unsplit."""

    MODULES = {
        set_status: {"PARTS": "Work/parts_manifest.json", "MANIFEST": "Work/manifest.json"},
        merge_chapters: {"PARTS_MANIFEST": "Work/parts_manifest.json", "ROOT": ""},
        make_transition_queue: {"MANIFEST": "Work/parts_manifest.json", "QUEUE": "Work/transition_queue.txt",
                                "ROOT": ""},
        make_doc_chunks: {"MANIFEST": "Work/manifest.json", "OUT": "Work/whole_doc_chunks.txt", "ROOT": ""},
        snapshot_summaries: {"SUMS": "Work/Summaries", "ROOT": ""},
    }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # Resolved, because common.rel() resolves the paths it is given.
        self.root = root = Path(self.tmp.name).resolve()
        self.saved = []
        for mod, attrs in self.MODULES.items():
            for name, rel in attrs.items():
                self.saved.append((mod, name, getattr(mod, name)))
                setattr(mod, name, root / rel if rel else root)
        (root / "Work" / "Summaries" / "s" / "parts").mkdir(parents=True)
        self.parts = [
            {"source_slug": "s", "unit_id": "ch-01", "title": "One", "status": "pending", "budget": 20,
             "summary": "Work/Summaries/s/01-one.md", "parts": [
                 {"part_index": 1, "status": "pending", "source": "Work/Chapters/s/parts/01-one-part1-of-2.md",
                  "summary": "Work/Summaries/s/parts/01-one-part1-of-2.md"},
                 {"part_index": 2, "status": "pending", "source": "Work/Chapters/s/parts/01-one-part2-of-2.md",
                  "summary": "Work/Summaries/s/parts/01-one-part2-of-2.md"}]},
            {"source_slug": "s", "unit_id": "ch-02", "title": "Two", "status": "pending", "budget": 10,
             "summary": "Work/Summaries/s/02-two.md", "parts": [
                 {"part_index": 1, "status": "pending", "source": "Work/Chapters/s/02-two.md",
                  "summary": "Work/Summaries/s/02-two.md"}]},
        ]
        self.manifest = [
            {"source_slug": "s", "unit_id": "ch-01", "path": "Work/Summaries/s/01-one.md", "status": "pending"},
            {"source_slug": "s", "unit_id": "ch-02", "path": "Work/Summaries/s/02-two.md", "status": "pending"},
        ]
        self.save()

    def tearDown(self):
        for mod, name, value in self.saved:
            setattr(mod, name, value)
        self.tmp.cleanup()

    def save(self):
        (self.root / "Work" / "parts_manifest.json").write_text(json.dumps(self.parts), encoding="utf-8")
        (self.root / "Work" / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def load(self):
        return (json.loads((self.root / "Work" / "parts_manifest.json").read_text(encoding="utf-8")),
                json.loads((self.root / "Work" / "manifest.json").read_text(encoding="utf-8")))

    def write(self, rel, text):
        (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.root / rel).write_text(text, encoding="utf-8")


class SetStatus(Project):
    def test_split_chapter_cannot_be_accepted_with_open_parts(self):
        code, out = run(set_status.main, ["chapter", "accepted", "s", "ch-01"])
        self.assertNotEqual(code, 0)
        self.assertIn("not accepted", out)

    def test_parts_then_chapter_sync_both_manifests(self):
        run(set_status.main, ["part", "accepted", "s", "ch-01", "1", "2"])
        code, _ = run(set_status.main, ["chapter", "accepted", "s", "ch-01"])
        self.assertEqual(code, 0)
        parts, manifest = self.load()
        self.assertEqual(parts[0]["status"], "accepted")
        self.assertEqual(manifest[0]["status"], "accepted")

    def test_unsplit_part_status_updates_chapter(self):
        run(set_status.main, ["part", "accepted", "s", "ch-02", "1"])
        parts, manifest = self.load()
        self.assertEqual(parts[1]["status"], "accepted")
        self.assertEqual(manifest[1]["status"], "accepted")

    def test_reopening_a_part_clears_chapter_acceptance(self):
        run(set_status.main, ["part", "accepted", "s", "ch-01", "1", "2"])
        run(set_status.main, ["chapter", "accepted", "s", "ch-01"])
        run(set_status.main, ["part", "drafted", "s", "ch-01", "2"])
        parts, manifest = self.load()
        self.assertEqual(parts[0]["status"], "drafted")
        self.assertEqual(manifest[0]["status"], "drafted")

    def test_unknown_status_and_part_are_refused(self):
        self.assertNotEqual(run(set_status.main, ["part", "done", "s", "ch-01", "1"])[0], 0)
        self.assertNotEqual(run(set_status.main, ["part", "accepted", "s", "ch-01", "3"])[0], 0)


class Merge(Project):
    def accept_parts(self):
        for p in self.parts[0]["parts"]:
            p["status"] = "accepted"
        self.save()

    def test_merge_adds_one_heading_and_keeps_order(self):
        self.accept_parts()
        self.write("Work/Summaries/s/parts/01-one-part1-of-2.md", "First part.\n")
        self.write("Work/Summaries/s/parts/01-one-part2-of-2.md", "Second part.\n")
        code, out = run(merge_chapters.main)
        self.assertEqual(code, 0, out)
        text = (self.root / "Work/Summaries/s/01-one.md").read_text(encoding="utf-8")
        self.assertEqual(text, "## One\n\nFirst part.\n\nSecond part.\n")

    def test_leaked_markers_block_the_merge(self):
        self.accept_parts()
        self.write("Work/Summaries/s/parts/01-one-part1-of-2.md",
                   "---\nsource_slug: s\n---\n<!-- begin owned text -->\nText.\n")
        self.write("Work/Summaries/s/parts/01-one-part2-of-2.md", "Second part.\n")
        code, out = run(merge_chapters.main)
        self.assertNotEqual(code, 0)
        self.assertIn("YAML frontmatter", out)
        self.assertFalse((self.root / "Work/Summaries/s/01-one.md").exists())

    def test_unsplit_and_unready_chapters_are_skipped(self):
        self.write("Work/Summaries/s/02-two.md", "## Two\n\nText.\n")
        code, out = run(merge_chapters.main)
        self.assertEqual(code, 0, out)
        self.assertIn("merged 0 chapter(s); skipped 2", out)
        self.assertEqual((self.root / "Work/Summaries/s/02-two.md").read_text(encoding="utf-8"), "## Two\n\nText.\n")


class Queues(Project):
    def test_transition_queue_lists_merged_split_chapters_only(self):
        for p in self.parts[0]["parts"]:
            p["status"] = "accepted"
        self.save()
        self.write("Work/Summaries/s/01-one.md", "## One\n\nText.\n")
        run(make_transition_queue.main)
        line = (self.root / "Work/transition_queue.txt").read_text(encoding="utf-8").strip()
        self.assertEqual(line, "s|ch-01|2|Work/Summaries/s/01-one.md|One|"
                               "Work/Chapters/s/parts/01-one-part1-of-2.md;Work/Chapters/s/parts/01-one-part2-of-2.md")

    def test_doc_chunks_respect_chapter_limit(self):
        for m in self.manifest:
            m["status"] = "accepted"
            self.write(m["path"], "## T\n\nText.\n")
        self.save()
        run(make_doc_chunks.main, ["--max-chapters", "1"])
        lines = (self.root / "Work/whole_doc_chunks.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines, ["CHUNK 1: Work/Summaries/s/01-one.md", "CHUNK 2: Work/Summaries/s/02-two.md"])


class Snapshot(Project):
    def test_snapshot_copies_chapters_and_never_overwrites(self):
        self.write("Work/Summaries/s/01-one.md", "## One\n\nOld.\n")
        self.write("Work/Summaries/s/parts/01-one-part1-of-2.md", "Part.\n")
        run(snapshot_summaries.main, ["style"])
        snap = self.root / "Work/Summaries_prestyle/s/01-one.md"
        self.assertEqual(snap.read_text(encoding="utf-8"), "## One\n\nOld.\n")
        self.assertFalse((self.root / "Work/Summaries_prestyle/s/parts").exists())
        self.write("Work/Summaries/s/01-one.md", "## One\n\nNew.\n")
        _, out = run(snapshot_summaries.main, ["style"])
        self.assertIn("kept 1 existing", out)
        self.assertEqual(snap.read_text(encoding="utf-8"), "## One\n\nOld.\n")


class StylePassCheck(unittest.TestCase):
    OLD = '## Title\n\nThe author says growth was "slow, uneven." It perhaps fell 12% in 1931, but recovered.\n'

    def test_clean_rewording_passes(self):
        new = '## Title\n\nThe author says growth was "slow, uneven". It perhaps fell 12% in 1931, but recovered.\n'
        self.assertEqual(check_style_pass.check(self.OLD, new), [])

    def test_dropped_hedge_and_contrast_are_flagged(self):
        new = '## Title\n\nThe author says growth was "slow, uneven." It fell 12% in 1931 and recovered.\n'
        problems = check_style_pass.check(self.OLD, new)
        self.assertTrue(any('"perhaps" 1 -> 0' in p for p in problems), problems)
        self.assertTrue(any('"but" 1 -> 0' in p for p in problems), problems)

    def test_marker_matches_whole_words_only(self):
        old = "## T\n\nThough small, it grew.\n"
        new = "## T\n\nIt grew, though small, as he thought.\n"
        self.assertEqual(check_style_pass.check(old, new), [])
        self.assertTrue(check_style_pass.check(old, "## T\n\nHe thought it grew.\n"))

    def test_number_after_comma_and_reorder(self):
        old = "## T\n\nIn 1931, output was 12 and costs 40.\n"
        self.assertEqual(check_style_pass.check(old, "## T\n\nIn 1931, output was 12 and costs 40.\n"), [])
        reordered = check_style_pass.check(old, "## T\n\nCosts were 40 and output 12 in 1931.\n")
        self.assertEqual(len(reordered), 1)
        self.assertIn("NUMBER ORDER", reordered[0])
        changed = check_style_pass.check(old, "## T\n\nIn 1931, output was 13 and costs 40.\n")
        self.assertIn("NUMBER REMOVED: 12", changed)

    def test_block_quote_edit_is_flagged(self):
        old = "## T\n\nShe writes:\n\n> We watch the harbor closely. And I know the boats.\n"
        new = "## T\n\nShe writes:\n\n> We watch the harbor closely and I know the boats.\n"
        self.assertTrue(any("BLOCK QUOTE CHANGED" in p for p in check_style_pass.check(old, new)))
        self.assertEqual(check_style_pass.check(old, old.replace("She writes", "She wrote")), [])

    def test_quote_edit_heading_and_paragraph_changes_are_flagged(self):
        new = '## Title 2\n\nThe author says growth was "slow."\n\nIt perhaps fell 12% in 1931, but recovered.\n'
        problems = " | ".join(check_style_pass.check(self.OLD, new))
        for label in ("QUOTE CHANGED", "HEADINGS CHANGED", "PARAGRAPH COUNT"):
            self.assertIn(label, problems)


class SentenceEnds(unittest.TestCase):
    """Docling prints a note reference after a space: "world. 7"."""

    def test_note_number_after_a_space_ends_a_sentence(self):
        self.assertTrue(ends_sentence("with the natural world. 7"))
        self.assertTrue(ends_sentence("directed by the harbour board.13"))
        self.assertTrue(ends_sentence("the quay was “closed.” 12"))

    def test_reference_abbreviation_before_a_number_stays_open(self):
        for text in ("see p. 12", "as printed in Vol. 3", "the rules in art. 7", "cf. 4"):
            self.assertFalse(ends_sentence(text), text)

    def test_number_without_punctuation_stays_open(self):
        self.assertFalse(ends_sentence("with the natural world 7"))
        self.assertFalse(ends_sentence("in the year 1917"))
        self.assertFalse(ends_sentence("in the year. 1917"))  # four digits is no note number

    def test_extraction_does_not_join_a_noted_paragraph_end_across_a_page(self):
        import extract
        self.assertFalse(extract.continues_across("with the natural world. 7", "The next paragraph begins here."))
        self.assertTrue(extract.continues_across("as the harbour master wrote on p. 12",
                                                 "Then the argument continues."))


class ParagraphBreaks(unittest.TestCase):
    """common.paragraph_break_problems: lines Markdown would run together."""

    def test_lost_blank_lines_are_found(self):
        text = "## One\n\nFirst.\nSecond.\n\n### Sub\nText.\n"
        problems = paragraph_break_problems(text)
        self.assertEqual([n for n, _ in problems], [4, 7])
        self.assertIn("one paragraph", problems[0][1])
        self.assertIn("heading", problems[1][1])

    def test_quotation_running_into_text_is_found(self):
        problems = paragraph_break_problems("> Quoted words.\nThe author's comment.\n")
        self.assertEqual(len(problems), 1)
        self.assertIn("quotation", problems[0][1])

    def test_lists_quotations_and_tables_may_be_adjacent(self):
        text = ("- a\n- b\n\n1. one\n2. two\n\n> line one\n> line two\n\n"
                "| Year | Output |\n|---|---|\n| 1930 | 12 |\n\nPlain text.\n")
        self.assertEqual(paragraph_break_problems(text), [])


class AuthorRefs(unittest.TestCase):
    REFS = {"s": ["Ada Penhale", "Penhale"], "s/03-interview": ["Marlow"]}

    def flags(self, text, stem="01-ch-01", exclude=()):
        groups = check_author_refs.ref_groups("s", stem, self.REFS)
        patterns = [check_author_refs.ref_pattern(g) for g in groups]
        return check_author_refs.flagged_paragraphs(text, patterns, exclude)

    def test_one_reference_per_paragraph_passes(self):
        text = "## Title\n\nPenhale argues that X. The mill closed in 1937.\n\nThe author adds Y.\n"
        self.assertEqual(self.flags(text), [])

    def test_repeated_name_and_generic_form_are_flagged(self):
        text = "## Title\n\nAda Penhale argues X. Penhale notes Y. The author adds Z.\n"
        self.assertEqual(self.flags(text), [(3, ["Ada Penhale", "Penhale", "The author"])])

    def test_quotations_block_quotes_and_headings_are_ignored(self):
        text = '## Penhale and Penhale\n\nPenhale quotes a critic: "Penhale is wrong."\n\n> Penhale, Penhale.\n'
        self.assertEqual(self.flags(text), [])

    def test_slug_and_stem_from_paths(self):
        slug_and_stem = check_author_refs.slug_and_stem
        self.assertEqual(slug_and_stem("Work/Summaries/penhale-mills/03-ch-02.md"),
                         ("penhale-mills", "03-ch-02"))
        self.assertEqual(slug_and_stem("Work/Drafts/penhale-mills/parts/03-ch-02-part1-of-2.md"),
                         ("penhale-mills", "03-ch-02"))
        self.assertEqual(slug_and_stem("Work/Summaries_prestyle/penhale-mills/03-ch-02.md")[0],
                         "penhale-mills")

    def test_each_person_is_counted_separately(self):
        text = "Penhale asks X. Marlow answers Y.\n\nPenhale asks Z. Marlow says W. Marlow adds V.\n"
        self.assertEqual(self.flags(text, "03-interview"), [(3, ["Marlow", "Marlow"])])

    def test_unit_groups_and_generic_forms(self):
        groups = check_author_refs.ref_groups("s", "03-interview", self.REFS)
        self.assertEqual(groups, [["Ada Penhale", "Penhale", "the authors", "the author"], ["Marlow"]])
        self.assertEqual(check_author_refs.ref_groups("t", "02-essay", {"t/02-essay": ["Hale"]}),
                         [["Hale", "the authors", "the author"]])
        self.assertEqual(check_author_refs.ref_groups("u", "01", {}), [["the authors", "the author"]])
        two = {"u": ["Hale"], "u/04-interview": [["Ida Marlow", "Marlow"], ["Quint"]]}
        self.assertEqual(check_author_refs.ref_groups("u", "04-interview", two),
                         [["Hale", "the authors", "the author"], ["Ida Marlow", "Marlow"], ["Quint"]])

    def test_not_author_phrases_are_removed_first(self):
        text = "Penhale contrasts Tom Penhale's view with Y.\n"
        self.assertEqual(self.flags(text), [(1, ["Penhale", "Penhale"])])
        self.assertEqual(self.flags(text, exclude=["Tom Penhale"]), [])


if __name__ == "__main__":
    unittest.main()
