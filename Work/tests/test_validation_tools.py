"""Tests for the validation-run tools: Work/fingerprint.py,
Work/make_validation_tasks.py, and Work/build_validation_report.py. Run from
the project root:

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
import build_validation_report as report  # noqa: E402
import fingerprint  # noqa: E402
import make_validation_tasks as tasks  # noqa: E402


def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")
    return p


def quiet(fn, *args, **kwargs):
    out = io.StringIO()
    with redirect_stdout(out):
        result = fn(*args, **kwargs)
    return result, out.getvalue()


SOURCE_1 = """---
source: "Sources/penhale.md"
title: "Arrival"
register: "modern"
---

# Arrival

<!-- page 3 -->
Penhale came to the harbour in 1930. But the mills were already closing, and
“some families had left before the winter”, as the clerk wrote.

<!-- page 4 -->
The town council, perhaps fearing unrest, met twice that month.
"""

SUMMARY_1 = """## Penhale: Arrival

Penhale came to the harbour in 1930, when the mills were closing and some families had already left.

The council met twice that month.
"""


def make_project(root):
    """A small project: two sources, four accepted chapters, one blocked."""
    chapters = [
        ("penhale-mills", "ch-01", "01-arrival", "Arrival", SUMMARY_1, SOURCE_1, 60),
        ("penhale-mills", "ch-02", "02-mills", "The Mills", "## Penhale: The Mills\n\nThe mills closed in 1931.\n",
         "# The Mills\n\nThe mills closed in 1931 after a long strike.\n", 10),
        ("quint-harbour", "ch-01", "01-tides", "Tides", "## Quint: Tides\n\nThe tides rose.\n",
         "# Tides\n\nThe tides rose each spring.\n", 5),
        ("quint-harbour", "ch-02", "02-boats", "Boats", "## Quint: Boats\n\nBoats came in.\n",
         "# Boats\n\nBoats came in at dusk.\n", 5),
    ]
    manifest, parts = [], []
    for slug, unit, stem, title, summary, source, words in chapters:
        write(root, "Work/Summaries/%s/%s.md" % (slug, stem), summary)
        write(root, "Work/Chapters/%s/%s.md" % (slug, stem), source)
        manifest.append({"source_slug": slug, "unit_id": unit,
                         "path": "Work/Summaries/%s/%s.md" % (slug, stem), "status": "accepted"})
        parts.append({"source_slug": slug, "unit_id": unit, "title": title,
                      "chapter_source": "Work/Chapters/%s/%s.md" % (slug, stem),
                      "summary": "Work/Summaries/%s/%s.md" % (slug, stem),
                      "words": words, "budget": round(words * 0.4), "ceiling": round(words * 0.5),
                      "status": "accepted", "parts": []})
    manifest.append({"source_slug": "quint-harbour", "unit_id": "ch-03",
                     "path": "Work/Summaries/quint-harbour/03-nets.md", "status": "blocked"})
    write(root, "Work/manifest.json", json.dumps(manifest))
    write(root, "Work/parts_manifest.json", json.dumps(parts))
    write(root, "Work/author_refs.json", json.dumps({
        "refs": {"penhale-mills": ["Ada Penhale", "Penhale"]},
        "conventions": {"penhale-mills": "Call the author Penhale; she.",
                        "penhale-mills/02-mills": "Call the author Penhale; no pronoun in this unit.",
                        "quint-harbour": "Call the author Quint; he."}}))
    write(root, "settled.md", "# Settled decisions\n\n## General\n\nFirst person stays.\n\n"
                              "## penhale-mills\n\nThe date 1930 is printed so.\n\n"
                              "### ch-02\n\nStrike figures as printed.\n\n"
                              "## quint-harbour\n\nTide tables omitted by scope.\n")
    write(root, "Work/Reviews/penhale-mills/verify-round1/01-arrival.md", "# record\n")
    write(root, "Work/Reviews/penhale-mills/01-arrival-part1-of-2.md", "# part record\n")
    write(root, "Work/Reviews/penhale-mills/verify-round1/02-mills.md", "# other chapter\n")
    write(root, "Work/Prompts/verify-round1/gate_log.md", "log\n")
    write(root, "Work/Introduction.md", "# Introduction\n\nThis summary covers two books.\n")
    write(root, "plan.md", "# Plan\n\n## Scope Decisions\n\n- Tide tables omitted.\n\n## Word Budgets\n\nx\n")


class Fingerprint(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        write(self.root, "a.md", "one\n")
        write(self.root, "Work/b.md", "two\n")
        write(self.root, "Work/Prompts/run/x.json", "{}\n")
        write(self.root, ".git/HEAD", "ref\n")
        write(self.root, "Work/__pycache__/c.pyc", "x")
        self.out = self.root / "Work" / "fingerprint.json"
        self.ex = ["Work/Prompts/run", "Work/fingerprint.json"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_unchanged_project_compares_clean(self):
        quiet(fingerprint.save, self.root, self.out, self.ex)
        code, out = quiet(fingerprint.compare, self.root, self.out, [])
        self.assertEqual(code, 0)
        self.assertIn("no file changed", out)
        data = json.loads(self.out.read_text(encoding="utf-8"))
        self.assertEqual(sorted(data["files"]), ["Work/b.md", "a.md"])

    def test_added_removed_and_changed_files_are_listed(self):
        quiet(fingerprint.save, self.root, self.out, self.ex)
        write(self.root, "a.md", "changed\n")
        (self.root / "Work" / "b.md").unlink()
        write(self.root, "new.md", "x\n")
        code, out = quiet(fingerprint.compare, self.root, self.out, [])
        self.assertEqual(code, 1)
        self.assertIn("ADDED: 1\n  new.md", out)
        self.assertIn("REMOVED: 1\n  Work/b.md", out)
        self.assertIn("CHANGED: 1\n  a.md", out)

    def test_excluded_skipped_and_own_output_ignored(self):
        quiet(fingerprint.save, self.root, self.out, self.ex)
        write(self.root, "Work/Prompts/run/found/A-ch-1.json", "{}\n")
        write(self.root, ".git/index", "x")
        write(self.root, "Work/__pycache__/d.pyc", "y")
        code, _ = quiet(fingerprint.compare, self.root, self.out, [])
        self.assertEqual(code, 0)

    def test_main_excludes_its_output_file(self):
        saved = fingerprint.ROOT
        fingerprint.ROOT = self.root
        try:
            for mode in ("save", "compare"):
                with redirect_stdout(io.StringIO()) as out:
                    with self.assertRaises(SystemExit) as cm:
                        fingerprint.main([mode, "--exclude", "Work/Prompts/run"])
                self.assertEqual(cm.exception.code, 0, out.getvalue())
        finally:
            fingerprint.ROOT = saved

    def test_compare_without_save_exits(self):
        with self.assertRaises(SystemExit):
            fingerprint.compare(self.root, self.out, [])


class Grouping(unittest.TestCase):

    def test_overlap(self):
        self.assertTrue(tasks.quotes_overlap("The council met twice", "the council met twice"))
        self.assertTrue(tasks.quotes_overlap("met twice that", "The council met twice that month."))
        self.assertTrue(tasks.quotes_overlap("Penhale came to the harbour in 1930",
                                             "came to the harbour in 1930, when the mills"))
        self.assertFalse(tasks.quotes_overlap("the council", "The council met twice that month."))
        self.assertFalse(tasks.quotes_overlap("Penhale came to the harbour", "The council met twice"))
        self.assertFalse(tasks.quotes_overlap("", "anything"))
        self.assertTrue(tasks.quotes_overlap("Penhale\u2019s mills <!-- page 3 --> closed",
                                             "Penhale's mills closed"))

    def test_groups_are_transitive_and_singletons_have_none(self):
        items = [
            {"id": "A1", "summary_quote": "Penhale came to the harbour in 1930, when the mills were closing"},
            {"id": "B1", "summary_quote": "The council met twice that month."},
            {"id": "W1-1", "summary_quote": "when the mills were closing and some families"},
            {"id": "A2", "summary_quote": "the mills were closing"},
        ]
        self.assertEqual(tasks.group_findings(items), 1)
        self.assertEqual([i["group"] for i in items], ["G1", None, "G1", "G1"])

    def test_fnv1a_and_audit_pick(self):
        self.assertEqual(tasks.fnv1a(""), 0x811C9DC5)
        self.assertEqual(tasks.fnv1a("a"), 0xE40C292C)
        self.assertTrue(tasks.audit_pick(1, {"id": "A1", "class": "clarity"}, {"reason_code": "settled"}))
        self.assertFalse(tasks.audit_pick(1, {"id": "A1", "class": "coverage"}, {"reason_code": "compression"}))
        picked = [i for i in range(1, 200) if tasks.fnv1a("3:B%d" % i) % 10 == 0]
        self.assertTrue(picked)
        self.assertTrue(tasks.audit_pick(3, {"id": "B%d" % picked[0], "class": "preservation"},
                                         {"reason_code": "compression"}))
        other = next(i for i in range(1, 200) if i not in picked)
        self.assertFalse(tasks.audit_pick(3, {"id": "B%d" % other, "class": "preservation"},
                                          {"reason_code": "compression"}))

    def test_location_target(self):
        self.assertEqual(tasks.location_target("chapter 2 summary", {1, 2, 3}), 2)
        self.assertIsNone(tasks.location_target("chapter 5 summary", {1, 2, 3}))
        self.assertEqual(tasks.location_target("Introduction", {1}), "intro")
        self.assertEqual(tasks.location_target("Part 2 heading"), "intro")
        self.assertIsNone(tasks.location_target("somewhere"))


class Project(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_project(self.root)
        self.base = self.root / "Work" / "Prompts" / "validation"

    def tearDown(self):
        self.tmp.cleanup()

    def find(self):
        return quiet(tasks.build_find, self.root, "validation", "validation-run.md", 3)

    def read(self, rel):
        return (self.base / rel).read_text(encoding="utf-8")

    def found(self, label, findings, verdict="MINOR"):
        write(self.base, "found/%s.json" % label,
              json.dumps({"verdict": verdict, "checked": "read it", "findings": findings}))


def finding(location, quote, source="n/a", cls="clarity", severity="minor", fix="x (+1 word)"):
    return {"id": "F", "location": location, "severity": severity, "class": cls, "summary_quote": quote,
            "source_quote": source, "page": "p. 3", "problem": "A problem.", "fix": fix}


class FindStage(Project):

    def test_chapter_assignment(self):
        _, out = self.find()
        self.assertIn("4 chapter(s), 2 chunk(s) of up to 3; 11 find prompt(s)", out)
        ch1 = self.read("assign/ch-1.md")
        self.assertIn("# Assignment: chapter 1 of 4", ch1)
        self.assertIn("HEADING: Penhale: Arrival (penhale-mills ch-01)", ch1)
        self.assertIn("SOURCE: Work/Chapters/penhale-mills/01-arrival.md", ch1)
        self.assertIn('LOCATION: "chapter 1 summary"', ch1)
        self.assertIn("AUTHOR: Call the author Penhale; she.\nREGISTER: modern\nRATIO: ", ch1)
        self.assertIn("now 24 words for 60 source words, about 0.40.", ch1)
        self.assertIn("budget 24 words), ceiling 30 words", ch1)
        self.assertIn("First person stays.", ch1)
        self.assertIn("The date 1930 is printed so.", ch1)
        self.assertIn("Strike figures as printed.", ch1)
        self.assertNotIn("Tide tables", ch1)
        self.assertNotIn("Work/Reviews", ch1)
        self.assertIn("AUTHOR: Call the author Penhale; no pronoun in this unit.\nREGISTER: source\n",
                      self.read("assign/ch-2.md"))   # no register in the chapter file: source

    def test_invalid_register_stops_the_run(self):
        write(self.root, "Work/Chapters/quint-harbour/02-boats.md",
              '---\nregister: "old"\n---\n\n# Boats\n\nBoats came in at dusk.\n')
        with self.assertRaises(SystemExit) as cm:
            self.find()
        self.assertIn("Work/Chapters/quint-harbour/02-boats.md: frontmatter register 'old' must be",
                      str(cm.exception))

    def test_prior_records_are_a_separate_file(self):
        self.find()
        prior = self.read("assign/ch-1-prior.md")
        self.assertIn("- Work/Reviews/penhale-mills/01-arrival-part1-of-2.md", prior)
        self.assertIn("- Work/Reviews/penhale-mills/verify-round1/01-arrival.md", prior)
        self.assertNotIn("02-mills", prior)
        self.assertIn("- Work/Prompts/verify-round1/gate_log.md", prior)
        self.assertIn("RECORDS (this chapter's records under Work/Reviews/quint-harbour/, every pass):\n- none",
                      self.read("assign/ch-3-prior.md"))

    def test_chunks_intro_and_tasks(self):
        self.find()
        c1, c2 = self.read("assign/chunk-1.md"), self.read("assign/chunk-2.md")
        self.assertIn("- [Introduction] Work/Introduction.md\n"
                      "- [chapter 1 summary] Work/Summaries/penhale-mills/01-arrival.md (REGISTER modern)\n", c1)
        self.assertIn("- [chapter 3 summary] Work/Summaries/quint-harbour/01-tides.md (REGISTER source)\n", c1)
        self.assertIn("- chapter 3: Work/Chapters/quint-harbour/01-tides.md", c1)
        self.assertIn("Tide tables omitted by scope.", c1)
        self.assertNotIn("[Introduction]", c2)
        self.assertIn("[chapter 4 summary]", c2)
        intro = self.read("assign/intro.md")
        self.assertIn("Chapters: 4 accepted, 1 blocked (quint-harbour ch-03)", intro)
        self.assertIn("- penhale-mills: 2 chapter(s); summaries 29 words for 70 source words (0.41).", intro)
        self.assertIn("- Document: 4 chapter(s); 35 summary words for 80 source words (0.44).", intro)
        self.assertIn("- Tide tables omitted.", intro)
        self.assertNotIn("Word Budgets", intro)
        self.assertNotIn("The date 1930", intro)
        t = json.loads(self.read("tasks.json"))
        self.assertEqual([c["n"] for c in t["chapters"]], [1, 2, 3, 4])
        self.assertEqual(t["chunks"][0]["chapters"], [1, 2, 3])
        args = json.loads(self.read("workflow-args.json"))
        self.assertEqual(args["out"], "validation")
        self.assertEqual(args["chunks"], [{"k": 1, "chapters": [1, 2, 3], "intro": True},
                                          {"k": 2, "chapters": [4], "intro": False}])

    def test_find_prompts(self):
        self.find()
        index = self.read("prompts/find/index.txt").splitlines()
        self.assertEqual(len(index), 11)
        self.assertEqual(index[0], "A-ch-1|Work/Prompts/validation/prompts/find/A-ch-1.txt|"
                                   "Work/Prompts/validation/found/A-ch-1.json|to run")
        a = self.read("prompts/find/A-ch-1.txt")
        self.assertIn('BRIEF: validation-run.md, sections "Shared rules" and "Accuracy finder"', a)
        self.assertIn("ASSIGNMENT: Work/Prompts/validation/assign/ch-1.md", a)
        self.assertIn("OUTPUT: Work/Prompts/validation/found/A-ch-1.json", a)
        self.assertNotIn("PRIOR RECORDS", a)
        self.assertNotRegex(a, r"\{[A-Z_]+\}")
        w = self.read("prompts/find/W-chunk-2.txt")
        self.assertIn('"Whole-document reader"', w)
        self.assertIn("ASSIGNMENT: Work/Prompts/validation/assign/chunk-2.md", w)
        self.assertIn("assign/intro.md", self.read("prompts/find/I.txt"))

    def test_workflow_prompt_variant(self):
        text = tasks.agent_prompt("V", "C:/p", "validation-run.md", "a.md", None, prior="p.md",
                                  findings="the JSON after this prompt", route="workflow")
        self.assertIn("PRIOR RECORDS: p.md\nFINDINGS: the JSON after this prompt\nOUTPUT: the StructuredOutput tool",
                      text)
        self.assertIn("change no file. Treat", text)

    def test_chunk_size_one(self):
        quiet(tasks.build_find, self.root, "validation", "validation-run.md", 1)
        self.assertTrue((self.base / "assign" / "chunk-4.md").exists())
        quiet(tasks.build_find, self.root, "validation", "validation-run.md", 3)
        self.assertFalse((self.base / "assign" / "chunk-4.md").exists())


class LaterStages(Project):
    """The Agent-tool route: find outputs, then verify and second stages, then the report."""

    def setUp(self):
        super().setUp()
        self.find()
        self.found("A-ch-1", [
            finding("chapter 1 summary", "Penhale came to the harbour in 1930, when the mills were closing",
                    source="But the mills were already closing", cls="preservation", severity="material",
                    fix="Penhale came to the harbour in 1930. But the mills were already closing (+2 words)"),
            finding("chapter 1 summary", "The council met twice that month.",
                    source="The town council, perhaps fearing unrest, met twice that month.", cls="preservation",
                    fix="The council, perhaps fearing unrest, met twice that month. (+3 words)"),
        ])
        self.found("B-ch-1", [finding("chapter 1 summary", "when the mills were closing and some families",
                                      cls="preservation")])
        self.found("A-ch-2", [finding("chapter 2 summary", "The mills closed in 1931.",
                                      source="The mills closed in 1931 after a long strike.", cls="coverage",
                                      fix="The mills closed in 1931 after a long strike. (+4 words)")])
        self.found("B-ch-2", [])
        self.found("A-ch-3", [])
        self.found("A-ch-4", [], verdict="CLEAN")
        self.found("B-ch-4", [], verdict="CLEAN")
        self.found("W-chunk-1", [
            finding("chapter 3 summary", "The tides rose."),
            finding("Introduction", "covers two books"),
            finding("chapter 4 summary", "Boats came in."),
        ])
        self.found("W-chunk-2", [])
        self.found("I", [finding("Introduction", "This summary covers two books.", cls="introduction")])

    def verify(self):
        return quiet(tasks.build_verify, self.root, "validation", "validation-run.md")

    def test_verify_stage(self):
        index, out = self.verify()
        self.assertIn("missing: B-ch-3.json", out)
        self.assertIn("1 unassigned", out)
        ch1 = json.loads(self.read("verify/ch-1.input.json"))
        self.assertEqual([f["id"] for f in ch1["findings"]], ["A1", "A2", "B1"])
        self.assertEqual([f["group"] for f in ch1["findings"]], ["G1", None, "G1"])
        ch3 = json.loads(self.read("verify/ch-3.input.json"))
        self.assertEqual([f["id"] for f in ch3["findings"]], ["W1-1"])
        intro = json.loads(self.read("verify/intro.input.json"))
        self.assertEqual([f["id"] for f in intro["findings"]], ["I1", "W1-2"])
        unassigned = json.loads(self.read("verify/unassigned.json"))
        self.assertEqual([(f["id"], f["chunk"]) for f in unassigned], [("W1-3", 1)])
        self.assertFalse((self.base / "verify" / "ch-4.input.json").exists())
        v = self.read("prompts/verify/V-ch-1.txt")
        self.assertIn("PRIOR RECORDS: Work/Prompts/validation/assign/ch-1-prior.md", v)
        self.assertIn("FINDINGS: Work/Prompts/validation/verify/ch-1.input.json", v)
        self.assertIn("OUTPUT: Work/Prompts/validation/verify/ch-1.json", v)
        self.assertIn("PRIOR RECORDS: none", self.read("prompts/verify/V-intro.txt"))
        self.assertEqual(len(index), 4)
        self.assertIn("verify: 4 prompt(s), 4 to run", out)
        self.verdicts()
        _, out = self.verify()
        self.assertIn("verify: 4 prompt(s), 1 to run", out)
        self.assertIn("V-ch-3|Work/Prompts/validation/prompts/verify/V-ch-3.txt|"
                      "Work/Prompts/validation/verify/ch-3.json|to run", self.read("prompts/verify/index.txt"))

    def verdicts(self):
        write(self.base, "verify/ch-1.json", json.dumps({"results": [
            {"id": "A1", "verdict": "confirmed", "severity": "material", "class": "preservation",
             "reason": "The contrast is lost.", "previously_considered": True,
             "prior_note": "Round 1 checked the date only.",
             "summary_quote": "Penhale came to the harbour in 1930, when the mills were closing",
             "source_quote": "But the mills were already\nclosing", "page": "p. 3",
             "fix": "Penhale came to the harbour in 1930. But the mills were already closing (+2 words)"},
            {"id": "A2", "verdict": "rejected", "reason_code": "settled", "reason": "The ruling covers it.",
             "previously_considered": False},
            {"id": "B1", "verdict": "duplicate", "duplicate_of": "A1", "reason": "Same defect.",
             "previously_considered": False},
        ]}))
        write(self.base, "verify/ch-2.json", json.dumps({"results": [
            {"id": "A1", "verdict": "confirmed", "severity": "minor", "class": "coverage", "reason": "Holds.",
             "previously_considered": False, "summary_quote": "The mills closed in 1931 and then",
             "source_quote": "after a long strike", "page": "none",
             "fix": "The mills closed in 1931 after a long strike. (+4 words)"}]}))
        write(self.base, "verify/intro.json", json.dumps({"results": [
            {"id": "I1", "verdict": "confirmed", "severity": "minor", "class": "introduction",
             "reason": "Vague.", "previously_considered": False,
             "summary_quote": "This summary covers two books.", "fix": "Name them. (+3 words)"},
            {"id": "W1-2", "verdict": "duplicate", "duplicate_of": "I1", "reason": "Same.",
             "previously_considered": False}]}))

    def test_second_stage_picks_material_and_audits(self):
        self.verify()
        self.verdicts()
        index, out = quiet(tasks.build_second, self.root, "validation", "validation-run.md")
        self.assertIn("1 second-opinion prompt(s): 1 material confirmation(s), 1 rejection audit(s)", out)
        items = json.loads(self.read("second/ch-1.input.json"))["items"]
        self.assertEqual([(i["id"], i["kind"]) for i in items], [("A1", "material"), ("A2", "audit")])
        self.assertTrue(items[1]["first_verifier"].startswith("rejected (settled): The ruling covers it."))
        self.assertIn("FINDINGS: Work/Prompts/validation/second/ch-1.input.json",
                      self.read("prompts/second/S-ch-1.txt"))

    def test_report_from_agent_files(self):
        self.verify()
        self.verdicts()
        quiet(tasks.build_second, self.root, "validation", "validation-run.md")
        write(self.base, "second/ch-1.json", json.dumps({"results": [
            {"id": "A1", "verdict": "material", "reason": "Agreed."},
            {"id": "A2", "verdict": "minor", "reason": "The ruling is about the date, not the hedge.",
             "summary_quote": "The council met twice that month.",
             "source_quote": "The town council, perhaps fearing unrest, met twice that month.", "page": "p. 4",
             "fix": "The council, perhaps fearing unrest, met twice that month. (+3 words)"}]}))
        data, label = report.load_result(self.root, "validation")
        self.assertIn("Agent-tool files", label)
        text, stats = report.build(self.root, "validation", data, label, "- check_words: 0 open flags.",
                                   "2026-10-15")
        self.assertIn("- **Chapters checked:** 4 of 4.", text)
        self.assertIn("- **Chapters:** 1 material and 1 minor findings confirmed.", text)
        self.assertIn("- **Introduction:** 0 material and 1 minor.", text)
        self.assertIn("| 1 | Penhale: Arrival | 1 | 0 | 1 | 1 |", text)
        self.assertIn("## penhale-mills\n\n### 1. Penhale: Arrival\n\nSummary: "
                      "`Work/Summaries/penhale-mills/01-arrival.md`; source: "
                      "`Work/Chapters/penhale-mills/01-arrival.md`; 24 words for 60 source words.", text)
        self.assertIn("#### 1.1 (material, preservation)\n\n- **Chapter:** 1. Penhale: Arrival, "
                      "`Work/Summaries/penhale-mills/01-arrival.md`\n- **Text:** \"Penhale came to the harbour "
                      "in 1930, when the mills were closing\"\n- **Evidence (p. 3):** \"But the mills were "
                      "already closing\"", text)
        self.assertIn("- **Verification:** found by the accuracy finder; confirmed by the refuting verifier: "
                      "The contrast is lost. Second opinion (material): Agreed.", text)
        self.assertIn("- **Earlier rounds:** Round 1 checked the date only.", text)
        # Chapter 2's verifier quoted text that is not in the summary.
        self.assertIn("#### 2.1 (minor, coverage)", text)
        self.assertIn("- **Quote check:** the Text was not found verbatim in "
                      "Work/Summaries/penhale-mills/02-mills.md", text)
        self.assertIn("#### I.1 (minor, introduction)\n\n- **Chapter:** Introduction, `Work/Introduction.md`",
                      text)
        self.assertIn("## Disputed findings", text)
        self.assertIn("#### D.1 (minor, preservation)", text)
        self.assertIn("Rejection audit (minor): The ruling is about the date, not the hedge.", text)
        self.assertIn("- **Unassigned reader findings:** 1", text)
        self.assertIn('- 1. Penhale: Arrival, B1 (coverage finder, preservation; duplicate): "when the mills', text)
        self.assertIn("duplicate of A1. Same defect.", text)
        self.assertIn("- check_words: 0 open flags.", text)
        self.assertIn("would change the summaries by about +6 words", text)
        self.assertIn("1 of the 2 confirmed chapter findings concern passages an earlier round", text)
        self.assertIn("0 upheld, 1 reinstated (under Disputed findings)", text)
        self.assertEqual([q[:2] for q in stats["quote_issues"]], [("2.1", "text")])
        self.assertIn("coverage finder chapter 3", ", ".join(stats["did_not_report"]))
        self.assertIn("- **No actionable findings:** chapters 4 (Quint: Boats).", text)
        self.assertIn("### 3. Quint: Tides", text)
        self.assertIn("No confirmed findings yet: see the disputed or unverified findings below.", text)

    def test_report_from_workflow_result(self):
        result = {
            "run": {"chunks": [2]},
            "readers": [{"k": 2, "verdict": "CLEAN", "checked": "x", "count": 0, "missing": False}],
            "chapters": [{"n": 4, "finders": {"A": {"verdict": "MINOR"}, "B": {"verdict": "CLEAN"}}, "merged": [
                {"finding": finding("chapter 4 summary", "Boats came in."),
                 "verdict": {"id": "A1", "verdict": "rejected", "reason_code": "clear",
                             "reason": "Clear on first reading. It parses.", "previously_considered": False}},
                {"finding": dict(finding("chapter 4 summary", "Boats came in."), id="A2"), "verdict": None},
            ]}],
            "intro": None,
            "unassigned": [],
        }
        result["chapters"][0]["merged"][0]["finding"]["id"] = "A1"
        write(self.base, "result.json", json.dumps(result))
        data, label = report.load_result(self.root, "validation")
        self.assertEqual(label, "Work/Prompts/validation/result.json")
        text, stats = report.build(self.root, "validation", data, label, None, "2026-10-15")
        self.assertIn("- **Chapters checked:** 1 of 4.", text)
        self.assertIn("No confirmed findings yet", text)
        self.assertIn("- **Rejection reasons:** clear 1.", text)
        self.assertIn('(accuracy finder, clarity; rejected: clear): "Boats came in.". Clear on first reading.', text)
        self.assertIn("#### U.1 (minor, clarity)", text)
        self.assertIn("no verifier result came back", text)
        self.assertIn("Not recorded. Run the checks", text)
        self.assertEqual(stats["unverified"], 1)


class MergeResults(Project):

    def test_pilot_and_rest_are_merged_and_a_rerun_replaces(self):
        self.find()
        empty = {"verdict": "CLEAN"}

        def chapter(n, reason):
            return {"n": n, "finders": {"A": empty, "B": empty}, "merged": [
                {"finding": dict(finding("chapter %d summary" % n, "x"), id="A1"),
                 "verdict": {"id": "A1", "verdict": "rejected", "reason_code": "clear", "reason": reason,
                             "previously_considered": False}}]}

        pilot = {"readers": [{"k": 1, "missing": False}], "chapters": [chapter(1, "Old."), chapter(2, "Two.")],
                 "intro": {"finders": {"I": empty}, "merged": []},
                 "unassigned": [dict(finding("chapter 9 summary", "y"), id="W1-1", chunk=1)]}
        rest = {"readers": [{"k": 2, "missing": False}], "chapters": [chapter(4, "Four.")], "intro": None,
                "unassigned": []}
        rerun = {"readers": [], "chapters": [chapter(1, "New.")], "intro": None, "unassigned": []}
        write(self.base, "result-1.json", json.dumps(pilot))
        write(self.base, "result-2.json", json.dumps(rest))
        write(self.base, "result-10.json", json.dumps(rerun))
        data, label = report.load_result(self.root, "validation")
        self.assertEqual(label, "Work/Prompts/validation/result-1.json, Work/Prompts/validation/result-2.json, "
                                "Work/Prompts/validation/result-10.json")
        self.assertEqual([c["n"] for c in data["chapters"]], [1, 2, 4])
        self.assertEqual(data["chapters"][0]["merged"][0]["verdict"]["reason"], "New.")
        self.assertEqual([r["k"] for r in data["readers"]], [1, 2])
        self.assertIsNotNone(data["intro"])
        self.assertEqual([f["id"] for f in data["unassigned"]], ["W1-1"])
        text, _ = report.build(self.root, "validation", data, label, None, "2026-10-15")
        self.assertIn("- **Chapters checked:** 3 of 4.", text)
        only, _ = report.load_result(self.root, "validation", ["Work/Prompts/validation/result-2.json"])
        self.assertEqual([c["n"] for c in only["chapters"]], [4])


class QuoteCheck(unittest.TestCase):

    def test_found_in(self):
        text = "<!-- page 3 -->\n“Some families,” he said — <!-- page 4 --> *had* left\nbefore the winter."
        self.assertTrue(report.found_in('"Some families," he said - had left before the winter', text))
        self.assertTrue(report.found_in("Some families ... before the winter.", text))
        self.assertFalse(report.found_in("before the winter ... Some families", text))
        self.assertFalse(report.found_in("some families stayed", text))
        self.assertIsNone(report.found_in("n/a", text))
        self.assertIsNone(report.found_in("", text))

    def test_word_change(self):
        self.assertEqual(report.word_change("New text (+9 words)"), 9)
        self.assertEqual(report.word_change("New text (\u22122 words)"), -2)
        self.assertEqual(report.word_change("New text (+1 word)"), 1)
        self.assertEqual(report.word_change("a (+2 words) then b (+1,204 words)"), 1204)
        self.assertIsNone(report.word_change("No count"))


if __name__ == "__main__":
    unittest.main()
