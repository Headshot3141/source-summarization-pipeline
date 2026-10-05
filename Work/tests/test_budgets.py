"""Tests for the compression budgets, merge protection, and work queues.

Run from the project root: python -m unittest discover -s Work/tests
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import check_words  # noqa: E402
import make_review_queue  # noqa: E402
import make_verify_queue  # noqa: E402
import merge_chapters  # noqa: E402
import split_parts  # noqa: E402
from common import draft_range, review_ceiling  # noqa: E402
from test_helpers import Project, run  # noqa: E402


def words(n):
    return " ".join(["word"] * n)


class Ranges(unittest.TestCase):
    def test_draft_range_and_ceiling(self):
        self.assertEqual(draft_range(400), (340, 460))
        self.assertEqual(review_ceiling(400, 1000), 500)


class MergeProtection(Project):
    def ready(self):
        for p in self.parts[0]["parts"]:
            p["status"] = "accepted"
        self.save()
        self.write("Work/Summaries/s/parts/01-one-part1-of-2.md", "First part.\n")
        self.write("Work/Summaries/s/parts/01-one-part2-of-2.md", "Second part.\n")

    def test_merge_records_its_hash_and_refuses_an_edited_chapter(self):
        self.ready()
        self.assertEqual(run(merge_chapters.main)[0], 0)
        self.assertTrue(self.load()[0][0].get("merged_sha"))
        chapter = self.root / "Work/Summaries/s/01-one.md"
        chapter.write_text("## One\n\nFirst part, with a seam fix.\n\nSecond part.\n", encoding="utf-8")
        code, out = run(merge_chapters.main)
        self.assertNotEqual(code, 0)
        self.assertIn("REFUSED s/ch-01", out)
        self.assertIn("seam fix", chapter.read_text(encoding="utf-8"))

    def test_unedited_chapter_can_be_remerged(self):
        self.ready()
        run(merge_chapters.main)
        self.write("Work/Summaries/s/parts/01-one-part2-of-2.md", "Second part, reworked.\n")
        code, out = run(merge_chapters.main)
        self.assertEqual(code, 0, out)
        self.assertIn("reworked", (self.root / "Work/Summaries/s/01-one.md").read_text(encoding="utf-8"))

    def test_chapter_not_written_by_the_merge_is_refused_unless_forced(self):
        self.ready()
        self.write("Work/Summaries/s/01-one.md", "## One\n\nHand-made.\n")
        self.assertNotEqual(run(merge_chapters.main)[0], 0)
        self.assertNotEqual(run(merge_chapters.main, ["--force"])[0], 0)  # needs an explicit unit
        code, out = run(merge_chapters.main, ["--force", "s", "ch-01"])
        self.assertEqual(code, 0, out)
        self.assertNotIn("Hand-made", (self.root / "Work/Summaries/s/01-one.md").read_text(encoding="utf-8"))

    def test_source_section_headings_allowed_other_headings_refused(self):
        self.ready()
        self.write("Work/Summaries/s/parts/01-one-part2-of-2.md", "### A Section\n\nSecond part.\n")
        self.assertEqual(run(merge_chapters.main)[0], 0)
        self.write("Work/Summaries/s/parts/01-one-part2-of-2.md", "## Wrong\n\nSecond part.\n")
        (self.root / "Work/Summaries/s/01-one.md").unlink()
        code, out = run(merge_chapters.main)
        self.assertNotEqual(code, 0)
        self.assertIn("heading other than ###", out)


class Queues(Project):
    """A manifest with full unit fields, for the word check and the queues."""

    def setUp(self):
        super().setUp()
        for mod in (check_words, make_review_queue, make_verify_queue):
            self.saved.append((mod, "MANIFEST", mod.MANIFEST))
            mod.MANIFEST = self.root / "Work/parts_manifest.json"
            if hasattr(mod, "ROOT"):
                self.saved.append((mod, "ROOT", mod.ROOT))
                mod.ROOT = self.root
        for mod, name in ((make_review_queue, "review_queue.txt"), (make_verify_queue, "verify_queue.txt")):
            self.saved.append((mod, "QUEUE", mod.QUEUE))
            mod.QUEUE = self.root / "Work" / name
        part = {"part_count": 2, "words": 500, "budget": 200}
        self.parts[0].update({"words": 1000, "budget": 400, "part_count": 2})
        for k, p in enumerate(self.parts[0]["parts"], 1):
            p.update(part, part_index=k, draft="Work/Drafts/s/parts/01-one-part%d-of-2.md" % k,
                     record="Work/Reviews/s/parts/01-one-part%d-of-2.md" % k)
        self.parts[1].update({"words": 500, "budget": 200, "part_count": 1})
        self.parts[1]["parts"][0].update({"part_count": 1, "words": 500, "budget": 200,
                                          "draft": "Work/Drafts/s/02-two.md", "record": "Work/Reviews/s/02-two.md"})
        self.save()

    def test_word_check_flags_drafts_ceilings_and_document_ratio(self):
        self.write("Work/Drafts/s/02-two.md", "## Two\n\n" + words(300))      # over 230
        self.write("Work/Summaries/s/02-two.md", "## Two\n\n" + words(260))   # ceiling 250
        code, out = run(check_words.main)
        self.assertEqual(code, 1)
        self.assertIn("DRAFT OVER CHAPTER Work/Drafts/s/02-two.md", out)
        self.assertIn("ABOVE CEILING CHAPTER Work/Summaries/s/02-two.md", out)
        self.assertIn("RATIO s: 0.520", out)
        self.assertIn("above target", out)
        self.assertNotIn("MISSING", out)

    def test_word_check_fails_over_document_maximum(self):
        self.write("Work/Summaries/s/02-two.md", "## Two\n\n" + words(290))
        code, out = run(check_words.main)
        self.assertEqual(code, 1)
        self.assertIn("OVER MAXIMUM", out)

    def test_word_check_passes_in_range(self):
        self.write("Work/Drafts/s/02-two.md", "## Two\n\n" + words(200))
        self.write("Work/Summaries/s/02-two.md", "## Two\n\n" + words(240))
        code, out = run(check_words.main)
        self.assertEqual(code, 0, out)
        self.assertIn("RATIO document: 0.480", out)

    def test_review_queue_has_ranges_and_skips_accepted_units(self):
        self.parts[1]["parts"][0]["status"] = "accepted"
        self.save()
        run(make_review_queue.main)
        lines = (self.root / "Work/review_queue.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0].split("|")[4:], ["200", "170", "230", "250"])

    def test_verify_queue_gives_neighbouring_parts(self):
        for e in self.parts:
            e["status"] = "accepted"
        self.save()
        run(make_verify_queue.main, ["--round", "2"])
        lines = (self.root / "Work/verify_queue.txt").read_text(encoding="utf-8").splitlines()
        first, second, unsplit = (ln.split("|") for ln in lines)
        self.assertEqual(first[5:7], ["-", "Work/Chapters/s/parts/01-one-part2-of-2.md"])
        self.assertEqual(second[5:7], ["Work/Chapters/s/parts/01-one-part1-of-2.md", "-"])
        self.assertEqual(unsplit[4:7], ["Work/Chapters/s/02-two.md", "-", "-"])
        self.assertEqual(first[8], "Work/Reviews/s/verify-round2/01-one-part1-of-2.md")


class TableWords(unittest.TestCase):
    def test_table_counts_cell_words_only(self):
        from count_words import words_in_text
        table = "| Year | Workers |\n|---|:---:|\n| 1930 | 45 |\n"
        self.assertEqual(words_in_text(table), 4)
        self.assertEqual(words_in_text("Text with a | pipe."), 5)  # a pipe in prose still counts


class BlockQuoteFixFolder(unittest.TestCase):
    def test_parts_folder_is_skipped(self):
        import tempfile
        import extract
        with tempfile.TemporaryDirectory() as folder:
            os.mkdir(os.path.join(folder, "parts"))
            with open(os.path.join(folder, "01-one.md"), "w", encoding="utf-8") as f:
                f.write("Lead-in:\n\n> Quoted words.\n")
            cfg = {"block_quote_fixes": {"add": ["Quoted words."], "remove": ["Missing"]}}
            self.assertEqual(extract.check_block_quote_fixes(cfg, folder), [("remove", "Missing")])


class Overlap(unittest.TestCase):
    def test_overlap_extends_back_to_the_minimum_words(self):
        body = "\n\n".join(["One " + words(100) + ".", "Two " + words(100) + ".", "Three short."]) + "\n"
        span = (0, len(body))
        self.assertEqual(len(split_parts.overlap_blocks(body, span, 1)), 1)
        got = split_parts.overlap_blocks(body, span, 1, 150)
        self.assertEqual(len(got), 3)
        self.assertTrue(got[0].startswith("One"))


if __name__ == "__main__":
    unittest.main()
