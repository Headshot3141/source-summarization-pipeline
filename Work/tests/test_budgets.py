"""Tests for the compression budgets, the splitter, merge protection, the
word check and its exceptions, and the work queues.

Run from the project root: python -m unittest discover -s Work/tests
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import check_parts  # noqa: E402
import check_words  # noqa: E402
import common  # noqa: E402
import fill_final_words  # noqa: E402
import make_review_queue  # noqa: E402
import make_verify_queue  # noqa: E402
import merge_chapters  # noqa: E402
import raise_exceptions  # noqa: E402
import split_parts  # noqa: E402
from common import HARD_CAP, draft_range, review_ceiling  # noqa: E402
from count_words import words_in_text  # noqa: E402
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
        # Parts unchanged: the edited chapter is kept, and that is not a failure.
        code, out = run(merge_chapters.main)
        self.assertEqual(code, 0, out)
        self.assertIn("kept s/ch-01", out)
        self.assertIn("seam fix", chapter.read_text(encoding="utf-8"))
        # Parts changed: refusing protects the edits.
        self.write("Work/Summaries/s/parts/01-one-part2-of-2.md", "Second part, reworked.\n")
        code, out = run(merge_chapters.main)
        self.assertNotEqual(code, 0)
        self.assertIn("REFUSED s/ch-01", out)
        self.assertIn("seam fix", chapter.read_text(encoding="utf-8"))

    def test_crlf_or_bom_copy_of_a_fresh_merge_is_kept(self):
        self.ready()
        chapter = self.root / "Work/Summaries/s/01-one.md"
        chapter.write_bytes(b"\xef\xbb\xbf## One\r\n\r\nFirst part.\r\n\r\nSecond part.\r\n")
        code, out = run(merge_chapters.main)
        self.assertEqual(code, 0, out)
        self.assertIn("kept s/ch-01", out)
        self.assertTrue(self.load()[0][0].get("merged_sha"))

    def test_bad_part_is_reported_and_other_chapters_continue(self):
        self.ready()
        (self.root / "Work/Summaries/s/parts/01-one-part2-of-2.md").unlink()
        code, out = run(merge_chapters.main)
        self.assertNotEqual(code, 0)
        self.assertIn("NOT MERGED s/ch-01: missing part summary", out)

    def test_merge_keeps_a_status_set_meanwhile(self):
        self.ready()
        original, calls = merge_chapters.load, []

        def load():
            # After the script's first read, another tool accepts ch-02.
            if calls:
                self.parts[1]["status"] = "accepted"
                self.save()
            calls.append(1)
            return original()

        merge_chapters.load = load
        try:
            run(merge_chapters.main)
        finally:
            merge_chapters.load = original
        self.assertEqual(self.load()[0][1]["status"], "accepted")

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


class QueueProject(Project):
    """A manifest with full unit fields, for the word check and the queues."""

    def setUp(self):
        super().setUp()
        for mod in (check_words, make_review_queue, make_verify_queue):
            self.saved.append((mod, "MANIFEST", mod.MANIFEST))
            mod.MANIFEST = self.root / "Work/parts_manifest.json"
            if hasattr(mod, "ROOT"):
                self.saved.append((mod, "ROOT", mod.ROOT))
                mod.ROOT = self.root
        # The project's own exceptions file must never settle these fixtures' flags.
        self.saved.append((check_words, "EXCEPTIONS", check_words.EXCEPTIONS))
        check_words.EXCEPTIONS = self.root / "Work/budget_exceptions.json"
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


class Queues(QueueProject):
    def test_word_check_flags_drafts_ceilings_and_document_ratio(self):
        self.write("Work/Drafts/s/parts/01-one-part1-of-2.md", words(300))   # over 230, not yet reviewed
        self.write("Work/Summaries/s/02-two.md", "## Two\n\n" + words(260))   # ceiling 250
        code, out = run(check_words.main)
        self.assertEqual(code, 1)
        self.assertIn("DRAFT OVER PART Work/Drafts/s/parts/01-one-part1-of-2.md", out)
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

    def test_settled_drafts_and_merged_parts_stop_flagging(self):
        # An out-of-range draft stops counting once its reviewed summary exists.
        self.write("Work/Drafts/s/02-two.md", "## Two\n\n" + words(300))
        self.write("Work/Summaries/s/02-two.md", "## Two\n\n" + words(200))
        # Part summaries are stale once the chapter is merged.
        self.write("Work/Summaries/s/parts/01-one-part1-of-2.md", words(900))
        self.write("Work/Summaries/s/01-one.md", "## One\n\n" + words(450))
        code, out = run(check_words.main)
        self.assertEqual(code, 0, out)
        self.assertIn("RATIO document: 0.433", out)

    def check_with_exceptions(self, exceptions, argv=None):
        self.write("Work/budget_exceptions.json", json.dumps(exceptions))
        return run(check_words.main, argv)

    def test_recorded_exception_is_settled(self):
        self.write("Work/Summaries/s/02-two.md", "## Two\n\n" + words(260))   # ceiling 250
        code, out = self.check_with_exceptions(
            {"s/ch-02": {"flag": "ABOVE CEILING", "max_words": 260, "reason": "restored reversals"}})
        self.assertIn("EXCEPTION ABOVE CEILING", out)
        self.assertNotIn("OVER MAXIMUM", out)
        self.assertEqual(code, 0, out)

    def test_exception_settles_only_its_kind_and_approved_length(self):
        self.write("Work/Summaries/s/02-two.md", "## Two\n\n" + words(270))
        code, out = self.check_with_exceptions(
            {"s/ch-02": {"flag": "ABOVE CEILING", "max_words": 260, "reason": "approved at 260"}})
        self.assertEqual(code, 1)   # grew past the approved length
        self.assertIn("ABOVE CEILING CHAPTER", out)
        code, out = self.check_with_exceptions({"s/ch-02": {"flag": "UNDER", "reason": "apparatus"}})
        self.assertEqual(code, 1)   # an UNDER exception does not settle a ceiling overage
        self.assertIn("unused exception s/ch-02", out)

    def test_malformed_exception_is_rejected(self):
        for bad in ("just a reason",
                    {"flag": "ABOVE CEILING", "max_words": "260", "reason": "x"},
                    {"flag": "ABOVE CEILING", "reason": "no max"},
                    {"flag": "UNDER", "min_words": None, "reason": "x"}):
            code, out = self.check_with_exceptions({"s/ch-02": bad})
            self.assertNotEqual(code, 0, bad)
            self.assertIn("needs", out)

    def test_under_exception_has_a_floor(self):
        self.write("Work/Summaries/s/02-two.md", "## Two\n\n" + words(100))   # floor 170
        settled = {"s/ch-02": {"flag": "UNDER", "min_words": 90, "reason": "apparatus-heavy"}}
        self.assertEqual(self.check_with_exceptions(settled)[0], 0)
        self.write("Work/Summaries/s/02-two.md", "## Two\n\n" + words(20))
        self.assertEqual(self.check_with_exceptions(settled)[0], 1)

    def test_evaluate_returns_structured_flags_and_json(self):
        self.write("Work/Summaries/s/02-two.md", "## Two\n\n" + words(260))   # ceiling 250
        result = check_words.evaluate()
        self.assertEqual(len(result["flags"]), 1)
        flag = result["flags"][0]
        self.assertEqual({k: flag[k] for k in ("kind", "level", "key", "path", "words", "limit")},
                         {"kind": "ABOVE CEILING", "level": "CHAPTER", "key": "s/ch-02",
                          "path": "Work/Summaries/s/02-two.md", "words": 260, "limit": 250})
        self.assertEqual(result["totals"]["sources"]["s"]["words"], 260)
        code, out = run(check_words.main, ["--json"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["flags"][0]["key"], "s/ch-02")

    def test_stored_ceiling_and_budget_basis_are_used(self):
        self.parts[1]["parts"][0].update({"ceiling": 230, "budget_words": 400})
        self.save()
        self.write("Work/Summaries/s/02-two.md", "## Two\n\n" + words(240))   # recomputed ceiling 250
        code, out = run(check_words.main)
        self.assertEqual(code, 1)
        self.assertIn("ABOVE CEILING CHAPTER Work/Summaries/s/02-two.md: 240 words (budget 200, ceiling 230)", out)
        self.assertIn("RATIO s: 0.600 (240 summary words / 400 source words)", out)

    def test_zero_ceiling_part_is_never_recomputed(self):
        # An apparatus-only part whose notes are all left out of the budget basis.
        part = {"budget": 0, "words": 500, "budget_words": 0, "ceiling": 0}
        self.assertEqual(check_words.check_summary("x.md", 0, part, "PART"), [])
        self.assertEqual(check_words.check_summary("x.md", 5, part, "PART")[0][0], "ABOVE CEILING")
        self.parts[1]["parts"][0].update({"ceiling": 0})
        self.save()
        run(make_review_queue.main)
        lines = (self.root / "Work/review_queue.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[-1].split("|")[-1], "0")

    def test_projection_adds_the_ceilings_of_units_not_yet_reviewed(self):
        self.write("Work/Summaries/s/02-two.md", "## Two\n\n" + words(240))
        code, out = run(check_words.main)
        self.assertEqual(code, 0, out)
        # 240 reviewed + 2 x 250 (ch-01's part ceilings) over 1,500 source words.
        self.assertIn("PROJECTED document: 0.493 (740 words: 240 reviewed, 500 in the ceilings of 2 unit(s)", out)
        for p in self.parts[0]["parts"]:
            p["ceiling"] = 400
        self.save()
        code, out = run(check_words.main)
        self.assertEqual(code, 1)
        self.assertIn("OVER MAXIMUM PROJECTED document: 0.693", out)

    def test_document_exception_settles_an_approved_maximum(self):
        self.write("Work/Summaries/s/02-two.md", "## Two\n\n" + words(290))   # 0.58 of 500
        approved = {"flag": "OVER MAXIMUM", "max_words": 300, "reason": "The user approved 0.60."}
        code, out = self.check_with_exceptions(
            {"s/ch-02": {"flag": "ABOVE CEILING", "max_words": 290, "reason": "restored"}, "DOCUMENT": approved})
        self.assertEqual(code, 0, out)
        self.assertIn("EXCEPTION OVER MAXIMUM RATIO document: 0.580", out)
        self.assertIn("The user approved 0.60.", out)
        self.write("Work/Summaries/s/02-two.md", "## Two\n\n" + words(310))
        code, out = self.check_with_exceptions(
            {"s/ch-02": {"flag": "ABOVE CEILING", "max_words": 310, "reason": "restored"}, "DOCUMENT": approved})
        self.assertEqual(code, 1)
        self.assertIn("OVER MAXIMUM RATIO document: 0.620", out)
        code, out = self.check_with_exceptions({"DOCUMENT": {"flag": "UNDER", "reason": "x"}})
        self.assertNotEqual(code, 0)
        self.assertIn("DOCUMENT: needs", out)

    def test_merged_chapters_supersede_their_part_exceptions(self):
        self.write("Work/Summaries/s/01-one.md", "## One\n\n" + words(400))
        code, out = self.check_with_exceptions({
            "s/ch-01/part 1": {"flag": "UNDER", "reason": "apparatus"},
            "s/ch-01/part 2": {"flag": "DRAFT OVER", "max_words": 300, "reason": "folded notes"},
            "s/ch-02": {"flag": "UNDER", "reason": "stale"}})
        self.assertIn("2 part exception(s) superseded by merged chapters; delete: s/ch-01/part 1, s/ch-01/part 2", out)
        self.assertNotIn("unused exception s/ch-01", out)
        self.assertIn("unused exception s/ch-02", out)

    def test_settled_reasons_are_shortened_unless_asked(self):
        self.write("Work/Summaries/s/02-two.md", "## Two\n\n" + words(260))
        reason = "Restored the reversals. " + "Then another pass added more history. " * 8
        exceptions = {"_about": "comments are skipped",
                      "s/ch-02": {"flag": "ABOVE CEILING", "max_words": 260, "reason": reason,
                                  "history": ["verify2 (2026-10-12): +10 words"]}}
        code, out = self.check_with_exceptions(exceptions)
        self.assertEqual(code, 0, out)
        line = next(ln for ln in out.splitlines() if ln.startswith("EXCEPTION"))
        self.assertLess(len(line.split(" -- ", 1)[1]), 110)
        self.assertTrue(line.endswith("\u2026"))
        code, out = self.check_with_exceptions(exceptions, ["--reasons"])
        self.assertIn(" ".join(reason.split()), out)
        exceptions["s/ch-02"]["history"] = "not a list"
        code, out = self.check_with_exceptions(exceptions)
        self.assertNotEqual(code, 0)
        self.assertIn("history", out)

    def test_merge_report_uses_the_stored_ceiling(self):
        self.parts[0]["ceiling"] = 3
        for p in self.parts[0]["parts"]:
            p["status"] = "accepted"
        self.save()
        self.write("Work/Summaries/s/parts/01-one-part1-of-2.md", "First part.\n")
        self.write("Work/Summaries/s/parts/01-one-part2-of-2.md", "Second part.\n")
        code, out = run(merge_chapters.main)
        self.assertEqual(code, 0, out)
        self.assertIn("<-- ABOVE CEILING 3", out)

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
        lines = (self.root / "Work/verify_queue_round2.txt").read_text(encoding="utf-8").splitlines()
        first, second, unsplit = (ln.split("|") for ln in lines)
        self.assertEqual(first[5:7], ["-", "Work/Chapters/s/parts/01-one-part2-of-2.md"])
        self.assertEqual(second[5:7], ["Work/Chapters/s/parts/01-one-part1-of-2.md", "-"])
        self.assertEqual(unsplit[4:7], ["Work/Chapters/s/02-two.md", "-", "-"])
        self.assertEqual(first[8], "Work/Reviews/s/verify-round2/01-one-part1-of-2.md")


class RaiseExceptions(QueueProject):
    """raise_exceptions.py after a pass whose snapshot is Work/Summaries_preverify5/."""

    def setUp(self):
        super().setUp()
        for name, value in (("ROOT", self.root), ("SUMS", self.root / "Work/Summaries")):
            self.saved.append((raise_exceptions, name, getattr(raise_exceptions, name)))
            setattr(raise_exceptions, name, value)
        self.write("Work/Summaries_preverify5/s/02-two.md", "## Two\n\n" + words(260))
        self.write("Work/Summaries/s/02-two.md", "## Two\n\n" + words(275))       # ceiling 250
        self.write("Work/Summaries_preverify5/s/01-one.md", "## One\n\n" + words(480))
        self.write("Work/Summaries/s/01-one.md", "## One\n\n" + words(520))       # merged, ceiling 500
        self.write("Work/budget_exceptions.json", json.dumps({
            "s/ch-02": {"flag": "ABOVE CEILING", "max_words": 260, "reason": "Restored \u0141ukasz's reply."},
            "s/ch-01/part 1": {"flag": "UNDER", "reason": "apparatus"}}))

    def exceptions(self):
        return json.loads((self.root / "Work/budget_exceptions.json").read_text(encoding="utf-8"))

    def test_raises_existing_and_creates_missing_entries(self):
        code, out = run(raise_exceptions.main, ["verify5", "--note", "Seam fixes only."])
        self.assertEqual(code, 0, out)
        self.assertIn("s/ch-02 260 275", out)
        self.assertIn("s/ch-01 - 520", out)
        data = self.exceptions()
        two = data["s/ch-02"]
        self.assertEqual((two["max_words"], two["reason"]), (275, "Restored \u0141ukasz's reply."))
        self.assertEqual(len(two["history"]), 1)
        self.assertRegex(two["history"][0], r"^verify5 \(\d{4}-\d\d-\d\d\): \+15 words against "
                                            r"Work/Summaries_preverify5/ \(260 -> 275\); records in "
                                            r"Work/Reviews/s/verify5/\. Seam fixes only\.$")
        self.assertEqual((data["s/ch-01"]["flag"], data["s/ch-01"]["max_words"]), ("ABOVE CEILING", 520))
        self.assertIn("+40 words", data["s/ch-01"]["history"][0])
        self.assertIn("s/ch-01/part 1", data)   # kept without --prune-stale
        raw = (self.root / "Work/budget_exceptions.json").read_text(encoding="utf-8")
        self.assertIn("\u0141ukasz", raw)                  # ensure_ascii=False
        self.assertTrue(raw.startswith('{\n  "s/ch-02"'))   # indent=2
        self.assertEqual(run(check_words.main)[0], 0)
        # A second raise appends to the history.
        self.write("Work/Summaries/s/02-two.md", "## Two\n\n" + words(280))
        run(raise_exceptions.main, ["verify5"])
        self.assertEqual(len(self.exceptions()["s/ch-02"]["history"]), 2)

    def test_unchanged_files_and_other_kinds_are_left(self):
        self.write("Work/Summaries_preverify5/s/02-two.md", "## Two\n\n" + words(275))
        self.write("Work/budget_exceptions.json", json.dumps({"s/ch-01": {"flag": "UNDER", "reason": "x"}}))
        code, out = run(raise_exceptions.main, ["verify5"])
        self.assertEqual(code, 0, out)
        self.assertIn("left s/ch-02: Work/Summaries/s/02-two.md is unchanged since Work/Summaries_preverify5/", out)
        self.assertIn("left s/ch-01: holds a UNDER exception", out)
        self.assertEqual(self.exceptions(), {"s/ch-01": {"flag": "UNDER", "reason": "x"}})

    def test_dry_run_and_prune_stale(self):
        before = self.exceptions()
        code, out = run(raise_exceptions.main, ["verify5", "--dry-run", "--prune-stale"])
        self.assertEqual(code, 0, out)
        self.assertIn("pruned s/ch-01/part 1", out)
        self.assertIn("dry run: nothing written", out)
        self.assertEqual(self.exceptions(), before)
        run(raise_exceptions.main, ["verify5", "--prune-stale"])
        self.assertNotIn("s/ch-01/part 1", self.exceptions())

    def test_missing_snapshot_stops(self):
        code, out = run(raise_exceptions.main, ["style"])
        self.assertEqual(code, 1)
        self.assertIn("snapshot folder", out)


FILL_PLAN = """# Plan

## Word Budgets

### Part 1: The Grey Harbour

| Source slug | Unit ID | Title | Source words | Target | Ceiling | Final words | Reason for deviation |
|---|---|---|---|---|---|---|---|
| s | ch-01 | One | 1,000 | 400 | 500 | | |
| s | ch-02 | Two | 500 | 200 | 250 | | denser; above ceiling: Work/budget_exceptions.json |

Source total: 1,500 words; draft target total: 600 words (0.40); final: {n} words (ratio {r}).

Grand total: 1,500 source words; final: {n} words (ratio {r}; target 0.50, at most 0.55).

## Pipeline
"""


class FillFinalWords(QueueProject):
    def setUp(self):
        super().setUp()
        for name, value in (("ROOT", self.root), ("PLAN", self.root / "plan.md"),
                            ("MANIFEST", self.root / "Work/parts_manifest.json")):
            self.saved.append((fill_final_words, name, getattr(fill_final_words, name)))
            setattr(fill_final_words, name, value)
        self.parts[0]["ceiling"] = 500
        self.parts[1]["ceiling"] = 250
        self.save()
        self.write("plan.md", FILL_PLAN)

    def rows(self):
        lines = (self.root / "plan.md").read_text(encoding="utf-8").splitlines()
        rows = {ln.split("|")[2].strip(): [c.strip() for c in ln.split("|")] for ln in lines if ln.startswith("| s ")}
        return rows, lines

    def test_final_words_notes_and_totals(self):
        self.write("Work/Summaries/s/01-one.md", "## One\n\n" + words(520))   # above 500
        self.write("Work/Summaries/s/02-two.md", "## Two\n\n" + words(240))   # back under 250
        code, out = run(fill_final_words.main)
        self.assertEqual(code, 0, out)
        rows, lines = self.rows()
        self.assertEqual(rows["ch-01"][7:9], ["520", "above ceiling: Work/budget_exceptions.json"])
        self.assertEqual(rows["ch-02"][7:9], ["240", "denser"])
        self.assertIn("Source total: 1,500 words; draft target total: 600 words (0.40); "
                      "final: 760 words (ratio 0.507).", lines)
        self.assertIn("Grand total: 1,500 source words; final: 760 words (ratio 0.507; target 0.50, at most 0.55).",
                      lines)
        run(fill_final_words.main)   # rerunning adds the note only once
        self.assertEqual(self.rows()[0]["ch-01"][8], "above ceiling: Work/budget_exceptions.json")

    def test_missing_summary_leaves_the_totals_and_dry_run_writes_nothing(self):
        self.write("Work/Summaries/s/02-two.md", "## Two\n\n" + words(240))
        code, out = run(fill_final_words.main, ["--dry-run"])
        self.assertEqual(code, 0, out)
        self.assertEqual((self.root / "plan.md").read_text(encoding="utf-8"), FILL_PLAN)
        self.assertIn("s/ch-01: no summary yet", out)
        run(fill_final_words.main)
        rows, lines = self.rows()
        self.assertEqual(rows["ch-02"][7], "240")
        self.assertTrue(any(ln.endswith("final: {n} words (ratio {r}).") for ln in lines))


def split_plan(long_words, long_target, short_row="| b | ch-02 | Two | 100 | 40 | | | |"):
    return f"""# Plan

## Word Budgets

### Part 1: The Grey Harbour

| Source slug | Unit ID | Title | Source words | Target | Ceiling | Final words | Reason for deviation |
|---|---|---|---|---|---|---|---|
| a | ch-01 | One | {long_words} | {long_target} | | | |

Source total: {long_words} words; draft target total: {long_target} words (0.40); final: {{n}} words (ratio {{r}}).

### Part 2: Salt and Iron

| Source slug | Unit ID | Title | Source words | Target | Ceiling | Final words | Reason for deviation |
|---|---|---|---|---|---|---|---|
{short_row}

## Pipeline
"""


NOTES_LABEL = "Notes to this chapter (printed at the back of the book):"


def para(name, n=599, end=" end."):
    """A paragraph of about 3KB that starts with name."""
    return name + " " + words(n) + end


class SplitBudgets(unittest.TestCase):
    """split_parts.py on a temporary project: a/ch-01 (over the hard cap, split,
    Part 1) and b/ch-02 (unsplit, Part 2)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # Resolved, because rel() resolves the paths it is given.
        self.root = root = Path(self.tmp.name).resolve()
        self.saved = [(common, "ROOT", common.ROOT), (check_parts, "ROOT", check_parts.ROOT),
                      (check_parts, "MANIFEST", check_parts.MANIFEST)]
        common.ROOT = check_parts.ROOT = root
        check_parts.MANIFEST = root / "Work/parts_manifest.json"
        for name, rel in (("CHAPTERS", "Work/Chapters"), ("PLAN", "plan.md"),
                          ("REPORT", "Work/parts_report.txt"), ("PARTS_MANIFEST", "Work/parts_manifest.json"),
                          ("CHAPTER_MANIFEST", "Work/manifest.json"), ("CONTEXT_CONFIG", "Work/part_context.json"),
                          ("BOUNDARIES_CONFIG", "Work/part_boundaries.json"),
                          ("EXCLUSIONS_CONFIG", "Work/budget_exclusions.json")):
            self.saved.append((split_parts, name, getattr(split_parts, name)))
            setattr(split_parts, name, root / rel)
        self.long_paras = [para("Para%02d" % i) for i in range(12)]
        self.long_body = "\n\n".join(self.long_paras) + "\n"
        self.chapter("a", "01-one.md", "ch-01", 1, "One", self.long_body)
        self.chapter("b", "02-two.md", "ch-02", 2, "Two", words(99) + " end.\n")
        self.plan()

    def tearDown(self):
        for mod, name, value in self.saved:
            setattr(mod, name, value)
        self.tmp.cleanup()

    def chapter(self, slug, name, unit, part, title, body):
        fields = [("source_slug", slug), ("unit_id", unit), ("part", part), ("title", title),
                  ("word_count", words_in_text(body))]
        front = "---\n" + "".join("%s: %s\n" % (k, json.dumps(v)) for k, v in fields) + "---\n\n"
        path = self.root / "Work" / "Chapters" / slug / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(front + "# " + title + "\n\n" + body, encoding="utf-8", newline="\n")
        return body

    def long_chapter(self, paras):
        return self.chapter("a", "01-one.md", "ch-01", 1, "One", "\n\n".join(paras) + "\n")

    def plan(self, long_words=None, short_row="| b | ch-02 | Two | 100 | 40 | | | |", body=None):
        n = long_words or words_in_text(body or self.long_body)
        (self.root / "plan.md").write_text(split_plan(n, f"{round(n * 0.4):,}", short_row), encoding="utf-8")

    def config(self, name, data):
        (self.root / "Work" / name).write_text(json.dumps(data), encoding="utf-8")

    def split(self, argv=None):
        return run(split_parts.main, argv)

    def manifests(self):
        return (json.loads((self.root / "Work/parts_manifest.json").read_text(encoding="utf-8")),
                json.loads((self.root / "Work/manifest.json").read_text(encoding="utf-8")))

    def report(self):
        return (self.root / "Work/parts_report.txt").read_text(encoding="utf-8")

    def owned(self, part):
        return (self.root / part["source"]).read_text(encoding="utf-8").split(common.OWNED_START, 1)[1]

    def test_rows_parse(self):
        budgets, errors = split_parts.parse_plan_budgets()
        self.assertEqual(errors, [])
        self.assertEqual(budgets[("b", "ch-02")], {"target": 40, "title": "Two", "plan_part": 2, "reason": "",
                                                   "source_words": 100})
        self.assertEqual(budgets[("a", "ch-01")]["plan_part"], 1)

    def test_split_budgets_ceilings_and_check_parts(self):
        code, out = self.split()
        self.assertEqual(code, 0, out)
        (long, short), manifest = self.manifests()
        self.assertEqual([(e["source_slug"], e["unit_id"]) for e in manifest], [("a", "ch-01"), ("b", "ch-02")])
        self.assertEqual((short["budget"], short["budget_words"], short["ceiling"]), (40, 100, 50))
        self.assertEqual(short["parts"][0]["ceiling"], review_ceiling(40, 100))
        self.assertGreater(long["part_count"], 1)
        self.assertEqual(sum(p["budget"] for p in long["parts"]), long["budget"])
        self.assertEqual(sum(p["budget_words"] for p in long["parts"]), long["words"])
        for p in long["parts"]:
            self.assertEqual(p["ceiling"], review_ceiling(p["budget"], p["words"]))
            self.assertLessEqual(p["bytes"], HARD_CAP)
        self.assertEqual(long["ceiling"], sum(p["ceiling"] for p in long["parts"]))
        report = self.report()
        self.assertRegex(report, r"  part 1: \d+ bytes \(\d+ under the cap\), \d+ words, budget \d+, ceiling \d+, "
                                 r"overlap 0 block\(s\), context 0 before and 0 after; starts 'Para00 word")
        self.assertNotIn("!!", report)
        self.assertEqual(run(check_parts.main)[0], 0)

    def test_duplicate_missing_and_unmatched_rows_write_nothing(self):
        n = words_in_text(self.long_body)
        dup = "| b | ch-02 | Two | 100 | 40 | | | |\n| b | ch-02 | Two | 100 | 40 | | | |"
        (self.root / "plan.md").write_text(split_plan(n, round(n * 0.4), dup), encoding="utf-8")
        code, out = self.split()
        self.assertEqual(code, 1)
        self.assertIn("duplicate budget row for b/ch-02", out)
        self.plan(short_row="| c | ch-03 | Three | 10 | 4 | | | |")
        code, out = self.split()
        self.assertEqual(code, 1)
        self.assertIn("no budget row for b/ch-02", out)
        self.assertIn("budget row c/ch-03 matches no chapter file", out)
        self.assertFalse((self.root / "Work/parts_manifest.json").exists())

    def test_frontmatter_part_must_match_the_row(self):
        self.chapter("b", "02-two.md", "ch-02", 1, "Two", words(99) + " end.\n")
        code, out = self.split()
        self.assertEqual(code, 1)
        self.assertIn("frontmatter part 1 differs from its plan.md row's Part 2", out)
        self.assertFalse((self.root / "Work/manifest.json").exists())

    def test_stale_rows_are_noted_and_information_is_not_a_problem(self):
        self.plan(short_row="| b | ch-02 | Second | 120 | 70 | | | |")
        code, out = self.split()
        self.assertEqual(code, 0, out)
        report = self.report()
        self.assertIn("!! Title 'Second' in plan.md differs from the chapter's title 'Two'", report)
        self.assertIn("!! Source words 120 in plan.md differ from the budget basis 100", report)
        self.assertIn("!! Target 70 differs from 0.4 x 100 source words (40)", report)
        self.assertIn("3 issue(s) flagged", out)

    def notes_body(self):
        return (words(89) + " end.\n\nFurther reading\n\nA list of books.\n\n" + NOTES_LABEL +
                "\n\n<!-- page 3 -->\n1 Ibid., p. 4.\n\n2. A substantive note with six more words.\n\n"
                "A second paragraph of note 2.\n\nb) A lettered note.\n")

    def test_exclusions_leave_the_budget_basis(self):
        body = self.chapter("b", "02-two.md", "ch-02", 2, "Two", self.notes_body())
        total = words_in_text(body)
        note2 = words_in_text("2. A substantive note with six more words.\n\nA second paragraph of note 2.")
        self.config("budget_exclusions.json", {"_about": "test", "b/ch-02": {
            "notes": [2], "paragraphs": ["Further reading"], "reason": "a note and a reading list"}})
        basis = total - note2 - 2
        self.plan(short_row=f"| b | ch-02 | Two | {basis} | {round(basis * 0.4)} | | | |")
        code, out = self.split()
        self.assertEqual(code, 0, out)
        short = self.manifests()[0][1]
        self.assertEqual((short["words"], short["budget_words"]), (total, basis))
        self.assertEqual(short["ceiling"], review_ceiling(short["budget"], basis))
        report = self.report()
        self.assertIn(f"-- budget basis {basis}: {total - basis} words in 3 paragraph(s) left out", report)
        self.assertNotIn("!!", report)

    def test_excluding_every_note_takes_the_label_too(self):
        body = self.chapter("b", "02-two.md", "ch-02", 2, "Two", self.notes_body())
        self.config("budget_exclusions.json", {"b/ch-02": {"notes": ["1", "2"], "reason": "citations"}})
        self.split()
        before_label = words_in_text(body.split(NOTES_LABEL)[0])
        self.assertEqual(self.manifests()[0][1]["budget_words"],
                         before_label + words_in_text(NOTES_LABEL) + words_in_text("b) A lettered note."))
        self.config("budget_exclusions.json", {"b/ch-02": {"notes": ["1", "2", "b"], "reason": "citations"}})
        self.split()
        self.assertEqual(self.manifests()[0][1]["budget_words"], before_label)

    def test_bad_exclusions_write_nothing(self):
        self.chapter("b", "02-two.md", "ch-02", 2, "Two", self.notes_body())
        self.config("budget_exclusions.json", {"b/ch-02": {"notes": ["7"], "paragraphs": ["Nowhere"], "reason": "x"},
                                               "a/ch-01": {"notes": ["1"], "reason": "x"},
                                               "z/ch-09": {"notes": ["1"], "reason": "x"}})
        code, out = self.split()
        self.assertEqual(code, 1)
        self.assertIn("b/ch-02: note 7 not found in the notes block", out)
        self.assertIn("b/ch-02: paragraph 'Nowhere' starts 0 paragraphs, not 1", out)
        self.assertIn("a/ch-01: no notes block", out)
        self.assertIn("entry 'z/ch-09' matches no chapter file", out)
        self.config("budget_exclusions.json", {"b/ch-02": {"notes": ["1"]}})
        code, out = self.split()
        self.assertEqual(code, 1)
        self.assertIn("and a \"reason\"", out)
        self.assertFalse((self.root / "Work/manifest.json").exists())

    def test_a_notes_only_part_with_every_note_excluded_has_no_budget(self):
        notes = [para(str(n)) for n in range(1, 5)]
        body = self.long_chapter(self.long_paras[:8] + [NOTES_LABEL] + notes)
        self.config("budget_exclusions.json", {"a/ch-01": {"notes": ["1", "2", "3", "4"], "reason": "citations"}})
        self.plan(body=body, long_words=words_in_text("\n\n".join(self.long_paras[:8])))
        code, out = self.split()
        self.assertEqual(code, 0, out)
        long = self.manifests()[0][0]
        # The notes block (about 12KB) does not fit after 24KB of text: the label starts a part.
        self.assertEqual(long["part_count"], 2)
        self.assertTrue(self.owned(long["parts"][1]).startswith(NOTES_LABEL))
        last = long["parts"][1]
        self.assertEqual((last["budget_words"], last["budget"], last["ceiling"]), (0, 0, 0))
        self.assertEqual(long["parts"][0]["budget"], long["budget"])
        self.assertEqual(check_words.check_summary("x.md", 0, last, "PART"), [])   # no UNDER flag
        self.assertIn("!! part 2 holds only notes (apparatus-only part)", self.report())
        self.assertNotIn("starts inside the notes block", self.report())

    def test_a_part_starting_inside_the_notes_block_is_flagged(self):
        self.long_chapter(self.long_paras[:3] + [NOTES_LABEL] + [para(str(n)) for n in range(1, 9)])
        self.plan(body=(self.root / "Work/Chapters/a/01-one.md").read_text(encoding="utf-8").split("# One\n\n")[1])
        code, out = self.split()
        self.assertEqual(code, 0, out)
        report = self.report()
        self.assertRegex(report, r"!! part 2 starts inside the notes block \(after note \d\): set a boundary at "
                                 r"the label or earlier in part_boundaries.json")
        self.assertIn("!! part 2 holds only notes", report)

    def test_boundary_config_forces_a_part_start(self):
        self.config("part_boundaries.json", {"_about": "hand-set", "a/ch-01": ["Para03 "]})
        code, out = self.split()
        self.assertEqual(code, 0, out)
        long = self.manifests()[0][0]
        self.assertTrue(self.owned(long["parts"][1]).startswith("Para03 "))
        self.assertIn("  -- 1 boundary(ies) set in part_boundaries.json", self.report())
        self.assertNotIn("issue(s) flagged", out)
        self.assertEqual(run(check_parts.main)[0], 0)

    def test_no_sliver_part_before_a_forced_break(self):
        # Ten paragraphs (about 30KB) fit under the limit, but pass TARGET: measured to
        # the chapter's end, the text left would allow a break before Para09, leaving
        # it alone in front of the forced break at Para10.
        self.config("part_boundaries.json", {"a/ch-01": ["Para10"]})
        code, out = self.split()
        self.assertEqual(code, 0, out)
        long = self.manifests()[0][0]
        self.assertEqual(long["part_count"], 2)
        self.assertTrue(self.owned(long["parts"][1]).startswith("Para10 "))

    def test_bad_boundaries_write_nothing(self):
        paras = list(self.long_paras)
        paras[3] = para("Para03", end="")                  # ends mid-sentence
        paras[5] = para("para05")                          # starts in lowercase
        paras[7] = "> " + para("Verse one")
        paras[8] = "> " + para("Verse two")
        self.long_chapter(paras)
        self.config("part_boundaries.json", {"a/ch-01": ["Para00", "Para04", "para05", "Verse two", "Para1"]})
        code, out = self.split()
        self.assertEqual(code, 1)
        for text in ("boundary 'Para00' is the chapter's first paragraph",
                     "boundary 'Para04': the paragraph before it ends mid-sentence",
                     "boundary 'para05': the paragraph starts in lowercase",
                     "boundary 'Verse two' falls inside a block quotation",
                     "boundary 'Para1' starts 2 paragraphs, not 1"):
            self.assertIn(text, out)
        self.assertFalse((self.root / "Work/parts_manifest.json").exists())

    def test_boundaries_of_an_unsplit_chapter_are_ignored_and_reported(self):
        self.config("part_boundaries.json", {"b/ch-02": ["word"]})
        code, out = self.split()
        self.assertEqual(code, 0, out)
        self.assertIn("!! 1 boundary(ies) in part_boundaries.json ignored", self.report())

    def test_dry_run_writes_nothing_and_takes_proposals(self):
        proposal = self.root / "proposal.json"
        proposal.write_text(json.dumps({"a/ch-01": ["Para05"]}), encoding="utf-8")
        context = self.root / "context.json"
        context.write_text(json.dumps([{"source_slug": "a", "unit_id": "ch-01", "receiver": "Para07 ",
                                        "text": self.long_paras[1], "why": "test"}]), encoding="utf-8")
        code, out = self.split(["--dry-run", "--boundaries", str(proposal), "--context", str(context)])
        self.assertEqual(code, 0, out)
        self.assertIn("  -- 1 boundary(ies) set in part_boundaries.json", out)
        self.assertRegex(out, r"part 2: \d+ bytes \(\d+ under the cap\).*context 1 before and 0 after; starts 'Para05")
        self.assertIn("dry run: nothing written", out)
        self.assertFalse((self.root / "Work/parts_manifest.json").exists())
        self.assertFalse((self.root / "Work/Chapters/a/parts").exists())
        code, out = self.split(["--context", str(context)])
        self.assertEqual(code, 2)   # needs --dry-run

    def test_receiver_context_follows_the_text_across_a_resplit(self):
        entry = {"source_slug": "a", "unit_id": "ch-01", "receiver": "Para10 ", "text": self.long_paras[1]}
        self.config("part_context.json", [entry, dict(entry, receiver="word word")])
        code, out = self.split()
        self.assertEqual(code, 0, out)
        long = self.manifests()[0][0]
        owner = next(p for p in long["parts"] if "Para10 " in self.owned(p))
        self.assertEqual(owner["context_from"], ["ch-01 part 1"])
        self.assertIn("receiver 'word word' occurs", self.report())
        self.config("part_boundaries.json", {"a/ch-01": ["Para09"]})
        self.split()
        long = self.manifests()[0][0]
        owner = next(p for p in long["parts"] if "Para10 " in self.owned(p))
        self.assertEqual(owner["context_from"], ["ch-01 part 1"])
        self.assertEqual(run(check_parts.main)[0], 0)


class NoteContext(unittest.TestCase):
    def test_fold_entry_gets_the_note_marker_and_still_parses_as_context(self):
        from check_parts import CONTEXT_RE
        body = "Text with a reference 3 here.\n\nMore text.\n\nNotes:\n\n3 A substantive note.\n"
        spans = [(0, body.index("Notes:")), (body.index("Notes:"), len(body))]
        notes = []
        before, after = split_parts.place_context(
            [{"text": "3 A substantive note.", "fold": True}], body, spans, 1, "ch-01", notes)
        self.assertEqual(after, [("ch-01 part 2", "3 A substantive note.", True)])
        block = split_parts.context_block(*after[0])
        self.assertIn("fold its substance in", block)
        self.assertEqual(CONTEXT_RE.findall(block + "\n"), ["3 A substantive note."])
        self.assertIn("do not summarize it", split_parts.context_block("x", "y"))


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
