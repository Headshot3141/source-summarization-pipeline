"""Tests for the pass tools: prompt filling, the pass gate, item collection,
and the coordinator's replacement list. Run from the project root:

    python -m unittest discover -s Work/tests
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import apply_replacements  # noqa: E402
import check_author_refs  # noqa: E402
import collect_items  # noqa: E402
import gate_pass  # noqa: E402
import make_prompts  # noqa: E402
from count_words import words_in_text  # noqa: E402

REAL_ROOT = Path(__file__).resolve().parents[2]


def call(main, argv):
    """(exit code, stdout and stderr) of main(argv)."""
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(out):
        try:
            code = main(argv) or 0
        except SystemExit as exc:
            if isinstance(exc.code, str):
                out.write(exc.code)
                code = 1
            else:
                code = exc.code or 0
    return code, out.getvalue()


CH1 = "Work/Chapters/s/01-one.md"
CH2 = "Work/Chapters/s/02-two.md"
P1 = "Work/Chapters/s/parts/01-one-part1-of-2.md"
P2 = "Work/Chapters/s/parts/01-one-part2-of-2.md"
S1 = "Work/Summaries/s/01-one.md"
S2 = "Work/Summaries/s/02-two.md"

SOURCE_TWO = """---
title: "Two"
---
# Two

<!-- page 3 -->
The harbour froze in the winter of 1890, and the mills of Penhale's town closed for most of a month. Many of the workers left the town to look for work on the coast.

<!-- page 4 -->
The closure, Penhale argues, was only temporary. It ended when the ice broke in March.
"""

SUMMARY_TWO = """## Two

The harbour froze in the winter of 1890, and the mills closed for a month. Workers left the town to look for work.

The closure was temporary. It ended when the ice broke in March.
"""

SUMMARY_ONE = """## One

The mill at Grey Harbour opened in 1871. It employed forty weavers.

The weavers struck in the spring.
"""


class PassProject(unittest.TestCase):
    """A temporary project: chapter s/ch-01 split into two parts, s/ch-02 unsplit."""

    MODULES = {
        make_prompts: {"ROOT": "", "PROMPTS": "Work/Prompts", "PROMPTS_MD": "prompts.md", "PASSES": "passes",
                       "PARTS_MANIFEST": "Work/parts_manifest.json", "REVIEW_QUEUE": "Work/review_queue.txt",
                       "TRANSITION_QUEUE": "Work/transition_queue.txt", "CHUNKS": "Work/whole_doc_chunks.txt",
                       "AUTHOR_REFS": "Work/author_refs.json", "EXCEPTIONS": "Work/budget_exceptions.json"},
        collect_items: {"ROOT": "", "PROMPTS": "Work/Prompts", "REVIEWS": "Work/Reviews",
                        "PARTS_MANIFEST": "Work/parts_manifest.json", "MANIFEST": "Work/manifest.json",
                        "CHUNKS": "Work/whole_doc_chunks.txt"},
        gate_pass: {"ROOT": "", "PROMPTS": "Work/Prompts", "PARTS_MANIFEST": "Work/parts_manifest.json"},
        apply_replacements: {"ROOT": ""},
        check_author_refs: {"CONFIG": "Work/author_refs.json", "MANIFEST": "Work/manifest.json"},
    }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = root = Path(self.tmp.name).resolve()
        self.saved = []
        for mod, attrs in self.MODULES.items():
            for name, rel in attrs.items():
                self.saved.append((mod, name, getattr(mod, name)))
                setattr(mod, name, root / rel if rel else root)
        self.build()

    def tearDown(self):
        for mod, name, value in self.saved:
            setattr(mod, name, value)
        self.tmp.cleanup()

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
        return p

    def read(self, rel):
        return (self.root / rel).read_text(encoding="utf-8")

    def build(self):
        part = lambda k, status="accepted": {
            "part_index": k, "part_count": 2, "status": status, "words": 500, "budget": 200, "ceiling": 250,
            "source": "Work/Chapters/s/parts/01-one-part%d-of-2.md" % k,
            "draft": "Work/Drafts/s/parts/01-one-part%d-of-2.md" % k,
            "summary": "Work/Summaries/s/parts/01-one-part%d-of-2.md" % k,
            "record": "Work/Reviews/s/parts/01-one-part%d-of-2.md" % k}
        self.parts = [
            {"source_slug": "s", "unit_id": "ch-01", "title": "One", "chapter_source": CH1, "summary": S1,
             "words": 1000, "budget": 400, "ceiling": 500, "part_count": 2, "status": "drafted",
             "parts": [part(1), part(2)]},
            {"source_slug": "s", "unit_id": "ch-02", "title": "Two", "chapter_source": CH2, "summary": S2,
             "words": 60, "budget_words": 50, "budget": 24, "ceiling": 30, "part_count": 1, "status": "accepted",
             "parts": [{"part_index": 1, "part_count": 1, "status": "accepted", "words": 60, "budget": 24,
                        "ceiling": 30, "source": CH2, "draft": "Work/Drafts/s/02-two.md", "summary": S2,
                        "record": "Work/Reviews/s/02-two.md"}]},
        ]
        self.write("Work/parts_manifest.json", json.dumps(self.parts))
        self.write("Work/manifest.json", json.dumps(
            [{"source_slug": "s", "unit_id": u, "path": s, "status": "accepted"}
             for u, s in (("ch-01", S1), ("ch-02", S2))]))
        self.write("Work/author_refs.json", json.dumps({
            "refs": {"s": ["Ada Penhale", "Penhale"]},
            "conventions": {"s": "Call the author Penhale. The source never genders Penhale: use no pronoun."}}))
        self.write(CH1, "---\ntitle: \"One\"\n---\n# One\n\nThe mill at Grey Harbour opened in 1871. "
                        "It employed forty weavers.\n\nThe weavers struck in the spring.\n")
        self.write(P1, "<!-- begin owned text -->\nThe mill at Grey Harbour opened in 1871.\n<!-- end owned text -->\n")
        self.write(P2, "<!-- begin owned text -->\nThe weavers struck.\n<!-- end owned text -->\n")
        self.write(CH2, SOURCE_TWO)
        self.write(S1, SUMMARY_ONE)
        self.write(S2, SUMMARY_TWO)
        self.write("Work/Summaries/s/parts/01-one-part1-of-2.md", "The mill opened in 1871.\n")
        self.write("Work/Summaries/s/parts/01-one-part2-of-2.md", "The weavers struck.\n")
        self.write("Work/Drafts/s/02-two.md", "The harbour froze.\n")
        self.write("Work/Introduction.md", "This document summarizes one book.\n")
        self.write("Work/review_queue.txt", "".join(
            "|".join([p["source"], p["draft"], p["summary"], p["record"], "200", "170", "230", "250"]) + "\n"
            for p in self.parts[0]["parts"]) + "|".join(
            [CH2, "Work/Drafts/s/02-two.md", S2, "Work/Reviews/s/02-two.md", "24", "20", "28", "30"]) + "\n")
        self.write("Work/transition_queue.txt", "s|ch-01|2|%s|One|%s;%s\n" % (S1, P1, P2))
        self.write("Work/whole_doc_chunks.txt", "CHUNK 1: Work/Introduction.md ; %s\nCHUNK 2: %s\n" % (S1, S2))
        self.write("Work/verify_queue.txt", "".join([
            "s|ch-01|1|2|%s|-|%s|%s|Work/Reviews/s/verify-round2/01-one-part1-of-2.md\n" % (P1, P2, S1),
            "s|ch-01|2|2|%s|%s|-|%s|Work/Reviews/s/verify-round2/01-one-part2-of-2.md\n" % (P2, P1, S1),
            "s|ch-02|1|1|%s|-|-|%s|Work/Reviews/s/verify-round2/02-two.md\n" % (CH2, S2)]))
        self.write("Work/Reviews/s/verify-round1/02-two.md", "# Verifier: Two (s ch-02)\n")
        for s, text in ((S1, SUMMARY_ONE), (S2, SUMMARY_TWO)):
            self.write(s.replace("Work/Summaries/", "Work/Summaries_presnap/"), text)
        for name in ("s--01-one.md", "s--02-two.md"):
            self.write("Work/Prompts/fixture/items/" + name, "# Items\n\n### NR-1 (new report)\n- NR-1: a report.\n")

    def copy_templates(self):
        shutil.copy(REAL_ROOT / "prompts.md", self.root / "prompts.md")
        shutil.copytree(REAL_ROOT / "passes", self.root / "passes")


# ---------------------------------------------------------------------- make_prompts

def template_sections(path):
    """Level-2 headings whose first content block is a ```text template (fragment sections excluded)."""
    headings, fences = make_prompts.outline(path.read_text(encoding="utf-8"))
    found = []
    for line, level, text in headings:
        if level != 2:
            continue
        nxt = next((l for l, _, _ in headings if l > line), float("inf"))
        if any(line < start < nxt and lang == "text" for start, _, lang, _ in fences):
            found.append(text)
    return found


class MakePrompts(PassProject):
    def make(self, *argv):
        return call(make_prompts.main, list(argv))

    def prompt(self, out, n=None):
        files = sorted((self.root / "Work/Prompts" / out).glob("*-%s.txt" % (n or "*")))
        return [f.read_text(encoding="utf-8") for f in files]

    def assert_filled(self, label, code, output, out):
        self.assertEqual(code, 0, "%s:\n%s" % (label, output))
        texts = self.prompt(out)
        self.assertTrue(texts, label)
        for text in texts:
            left = make_prompts.PLACEHOLDER.findall(text)
            self.assertFalse(left, "%s: unfilled %s" % (label, left))

    def test_every_template_in_prompts_md_fills_for_unsplit_and_split_units(self):
        self.copy_templates()
        self.write("Work/boundaries.txt", "s/ch-01 1|2\n")
        sections = template_sections(self.root / "prompts.md")
        self.assertTrue(sections)
        roles = {v: k for k, v in make_prompts.ROLES.items()}
        for heading in sections:
            role = make_prompts.prompts_role(heading)
            with self.subTest(heading=heading):
                self.assertIsNotNone(role, "prompts.md template %r is not in make_prompts.ROLES" % heading)
                name = roles[role]
                if role == "Boundary inspector":
                    runs = [["--set", "BOUNDARY_LIST=@Work/boundaries.txt", "--set", "RECORD=Work/Boundaries/group1.md",
                             "--set", "PROPOSALS=Work/Boundaries/group1.json"]]
                elif role == "Whole-document reviewer":
                    runs = [["chunk1"], ["chunk2"]]
                elif role in ("Merger", "Transition reviewer"):
                    runs = [["s/ch-01"]]  # split chapters only
                else:
                    runs = [["s/ch-01/1"], ["s/ch-02"]]
                for i, extra in enumerate(runs):
                    out = "t-%s-%d" % (name, i)
                    code, output = self.make(out, name, *extra)
                    self.assert_filled("%s %s" % (heading, extra), code, output, out)

    def test_every_brief_prompt_in_passes_fills_for_unsplit_and_split_units(self):
        """Every computed field fills in every brief prompt. Placeholders the
        script does not compute are the coordinator's (--set, or filled by hand
        when the brief is copied): they are listed, then supplied, and the rest
        of the prompt must fill."""
        self.copy_templates()
        failures, coordinator = [], {}
        for brief in sorted((self.root / "passes").glob("*.md")):
            for heading in template_sections(brief):
                _, template = make_prompts.section_template(brief, heading)
                others = sorted(set(make_prompts.PLACEHOLDER.findall(template)) - set(make_prompts.FIELDS))
                if others:
                    coordinator["%s, %s" % (brief.name, heading)] = others
                sets = [a for name in others for a in ("--set", "%s=%s value" % (name, name.lower()))]
                for i, key in enumerate(("s/ch-01/1", "s/ch-02")):
                    out = re.sub(r"[^A-Za-z0-9._-]", "-", "%s-%s-%d" % (brief.stem, heading[:20], i))
                    code, output = self.make(out, "task", key, "--brief", "passes/" + brief.name,
                                             "--section", heading, "--queue", "Work/verify_queue.txt",
                                             "--items", "Work/Prompts/fixture/items", "--snapshot", "snap", *sets)
                    left = [t for text in self.prompt(out) for t in make_prompts.PLACEHOLDER.findall(text)]
                    if code or left:
                        failures.append("%s, %s, %s: %s" % (brief.name, heading, key, output.strip()[-400:] or left))
        self.assertFalse(failures, "brief prompts that do not fill:\n" + "\n".join(failures))
        for where, names in coordinator.items():
            print("\nnote: %s uses fields make_prompts.py does not compute (--set or by hand): %s"
                  % (where, ", ".join(names)), file=sys.stderr)

    def test_split_unit_gets_part_fragments_and_unsplit_its_heading_rule(self):
        self.copy_templates()
        frags = make_prompts.fragments()
        self.make("a", "summarizer", "s/ch-01/1", "s/ch-02")
        split, unsplit = self.prompt("a", 1)[0], self.prompt("a", 2)[0]
        first = lambda name, variant: frags[name][variant].split("\n")[0].replace("{CHAPTER_TITLE}", "Two")
        self.assertIn(make_prompts.fill(frags["PART_RULES"]["part"], {"UNIT_LABEL": "s ch-01, part 1 of 2"})[0]
                      .split("\n")[0], split)
        self.assertIn(first("HEADING_RULE", "part"), split)
        self.assertIn(first("HEADING_RULE", "unsplit"), unsplit)
        self.assertNotIn("{PART_RULES}", unsplit)
        # The summarizer writes the draft and is checked against its own part file.
        self.assertIn("Work/Drafts/s/parts/01-one-part1-of-2.md %s" % P1, split)

    def test_leftover_placeholder_is_an_error_and_nothing_is_written(self):
        self.write("brief.md", "# Brief\n\n## Agent prompt\n\n```text\nSUMMARY: {SUMMARY}\nODD: {NOT_A_FIELD}\n```\n")
        code, output = self.make("b", "pass", "s/ch-02", "--brief", "brief.md")
        self.assertNotEqual(code, 0)
        self.assertIn("{NOT_A_FIELD}", output)
        self.assertFalse((self.root / "Work/Prompts/b").exists())

    def test_used_folder_is_refused_without_force_and_numbers_are_kept(self):
        self.write("brief.md", "# Brief\n\n## Agent prompt\n\n```text\nSUMMARY: {SUMMARY}\nNOTE: {X}\n```\n")
        self.assertEqual(self.make("c", "pass", "--all", "--brief", "brief.md", "--set", "X=one")[0], 0)
        code, output = self.make("c", "pass", "--all", "--brief", "brief.md", "--set", "X=two")
        self.assertNotEqual(code, 0)
        self.assertIn("already holds prompts", output)
        self.assertIn("NOTE: one", self.read("Work/Prompts/c/pass-2.txt"))
        code, output = self.make("c", "pass", "s/ch-02", "--brief", "brief.md", "--set", "X=two", "--force")
        self.assertEqual(code, 0, output)
        self.assertIn("NOTE: two", self.read("Work/Prompts/c/pass-2.txt"))
        rows = make_prompts.read_index(self.root / "Work/Prompts/c")
        self.assertEqual([(r["n"], r["key"]) for r in rows], [("1", "s/ch-01"), ("2", "s/ch-02")])

    def test_ready_runs_parts_of_one_summary_in_order(self):
        self.write("brief.md", "# Brief\n\n## Agent prompt\n\n```text\n{SUMMARY} {RECORD} {MODE}\n```\n")
        self.assertEqual(self.make("d", "fix", "--all", "--brief", "brief.md", "--queue", "Work/verify_queue.txt")[0], 0)
        code, output = self.make("d", "--ready")
        self.assertIn("ready: 1 3", output)
        self.assertIn("waiting: 2 (after 1)", output)
        self.write("Work/Reviews/s/verify-round2/01-one-part1-of-2.md", "done\n")
        self.write("Work/Prompts/d/dispatched.txt", "3\n")
        code, output = self.make("d", "--ready")
        self.assertIn("ready: 2", output)
        self.assertIn("dispatched, not done: 3", output)
        self.assertIn("done: 1 of 3", output)

    def test_mode_round1_earlier_and_notes(self):
        self.write("brief.md", "# Brief\n\n## Agent prompt\n\n```text\nMODE: {MODE}\nROUND1: {ROUND1}\n"
                               "EARLIER: {EARLIER}\nCAP: {CAP}\nRATIO: {RATIO}\nAUTHOR: {AUTHOR_CONVENTION}\n```\n")
        self.write("Work/Prompts/e/notes.json", json.dumps({"s/ch-02": "Note for two."}))
        code, output = self.make("e", "fix", "s/ch-01/2", "s/ch-02", "--brief", "brief.md",
                                 "--queue", "Work/verify_queue.txt")
        self.assertEqual(code, 0, output)
        part, whole = self.read("Work/Prompts/e/fix-1.txt"), self.read("Work/Prompts/e/fix-2.txt")
        self.assertIn("MODE: A", part)
        self.assertNotIn("ROUND1", part)  # no round-1 record: the line goes
        self.assertNotIn("EARLIER", part)  # no snapshot: the line goes
        self.assertIn("MODE: B\nROUND1: Work/Reviews/s/verify-round1/02-two.md", whole)
        self.assertIn("RATIO: %.2f" % (words_in_text(SUMMARY_TWO) / 50), whole)
        self.assertIn("Coordinator notes:\n\nNote for two.", whole)
        self.assertNotIn("Coordinator notes", part)
        code, output = self.make("e2", "fix", "s/ch-02", "--brief", "brief.md", "--queue", "Work/verify_queue.txt",
                                 "--snapshot", "snap", "--cap-ratio", "1.1")
        self.assertIn("EARLIER: Work/Summaries_presnap/s/02-two.md\nCAP: %d" % round(1.1 * words_in_text(SUMMARY_TWO)),
                      self.read("Work/Prompts/e2/fix-1.txt"))

    def test_register_comes_from_the_chapter_file(self):
        # A part takes its chapter's register (part files carry none); a file without one is "source".
        self.write(CH1, self.read(CH1).replace('title: "One"\n', 'title: "One"\nregister: "modern"\n'))
        self.write("brief.md", "# Brief\n\n## Agent prompt\n\n```text\nREGISTER: {REGISTER}\n```\n")
        code, output = self.make("r", "fix", "s/ch-01/1", "s/ch-02", "--brief", "brief.md",
                                 "--queue", "Work/verify_queue.txt")
        self.assertEqual(code, 0, output)
        self.assertEqual(self.read("Work/Prompts/r/fix-1.txt"), "REGISTER: modern\n")
        self.assertEqual(self.read("Work/Prompts/r/fix-2.txt"), "REGISTER: source\n")
        code, output = self.make("r2", "pass", "--all", "--brief", "brief.md")   # chapter units
        self.assertEqual(code, 0, output)
        self.assertEqual([t.strip() for t in self.prompt("r2")], ["REGISTER: modern", "REGISTER: source"])

    def test_whole_document_chapters_mark_modern_chapters(self):
        self.write(CH1, self.read(CH1).replace('title: "One"\n', 'title: "One"\nregister: "modern"\n'))
        self.write("brief.md", "# Brief\n\n## Agent prompt\n\n```text\nCHAPTERS: {CHAPTERS}\n```\n")
        code, output = self.make("wd", "pass", "--all", "--brief", "brief.md", "--chunks", "Work/whole_doc_chunks.txt")
        self.assertEqual(code, 0, output)
        self.assertEqual(self.read("Work/Prompts/wd/pass-1.txt"),
                         "CHAPTERS: Work/Introduction.md; %s (REGISTER modern)\n" % S1)
        self.assertEqual(self.read("Work/Prompts/wd/pass-2.txt"), "CHAPTERS: %s\n" % S2)
        self.write("Work/whole_doc_chunks.txt", "CHUNK 1: Work/Summaries/s/09-gone.md\n")
        code, output = self.make("wd2", "pass", "--all", "--brief", "brief.md", "--chunks", "Work/whole_doc_chunks.txt")
        self.assertNotEqual(code, 0)
        self.assertIn("Work/Summaries/s/09-gone.md is in a chunk but not in Work/parts_manifest.json", output)

    def test_invalid_register_is_an_error_and_nothing_is_written(self):
        self.write(CH2, SOURCE_TWO.replace('title: "Two"\n', 'title: "Two"\nregister: "victorian"\n'))
        self.write("brief.md", "# Brief\n\n## Agent prompt\n\n```text\nREGISTER: {REGISTER}\n```\n")
        code, output = self.make("ri", "pass", "--all", "--brief", "brief.md")
        self.assertNotEqual(code, 0)
        self.assertIn("%s: frontmatter register 'victorian' must be \"modern\" or \"source\"" % CH2, output)
        self.assertFalse((self.root / "Work/Prompts/ri").exists())

    def test_missing_author_convention_is_an_error(self):
        self.write("Work/author_refs.json", json.dumps({"conventions": {}}))
        self.write("brief.md", "# Brief\n\n## Agent prompt\n\n```text\nAUTHOR: {AUTHOR_CONVENTION}\n```\n")
        code, output = self.make("f", "pass", "s/ch-02", "--brief", "brief.md")
        self.assertNotEqual(code, 0)
        self.assertIn("no author convention for s/02-two", output)


# ---------------------------------------------------------------------- gate_pass

RECORD_TWO = """# Targeted fix: Two (s ch-02)
Model: test. Date: 2026-01-01.

### NR-1 (tier 2): lost scope word
Disposition: restored
Source: "the mills of Penhale's town closed for most of a month" (<!-- page 3 -->)
Before: "The harbour froze in the winter of 1890, and the mills closed for a month."
After: "The harbour froze in the winter of 1890, and the mills closed for most of a month."
Words: +2
Reason: The source says most of a month.

## New reports
None.
"""


class GatePass(PassProject):
    def setUp(self):
        super().setUp()
        for s, text in ((S1, SUMMARY_ONE), (S2, SUMMARY_TWO)):
            self.write(s.replace("Work/Summaries/", "Work/Summaries_prefix/"), text)
        self.write("Work/Prompts/fix/index.txt", "n|key|summary|source|record|words|cap|items\n"
                   "1|s/ch-02|%s|%s|Work/Reviews/s/fix/02-two.md|25|30|NR-1\n" % (S2, CH2))
        self.edit("closed for a month", "closed for most of a month")
        self.record(RECORD_TWO)

    def edit(self, old, new):
        text = self.read(S2)
        self.assertEqual(text.count(old), 1)
        self.write(S2, text.replace(old, new))

    def record(self, text):
        self.write("Work/Reviews/s/fix/02-two.md", text)

    def gate(self, *argv):
        return call(gate_pass.main, ["fix"] + list(argv))

    def test_recorded_edit_matches(self):
        code, output = self.gate()
        self.assertEqual(code, 0, output)
        w = words_in_text(SUMMARY_TWO)
        self.assertIn("%d -> %d words (+2, cap 30)" % (w, w + 2), output)
        self.assertIn("1 changed run(s), 0 unmatched", output)
        self.assertIn("OK", self.read("Work/Prompts/fix/gate_log.md"))

    def test_unrecorded_edit_is_unmatched(self):
        self.edit("Workers left", "Some workers left")
        code, output = self.gate()
        self.assertEqual(code, 1, output)
        self.assertIn('UNMATCHED replace: old "', output)
        self.assertIn("Some workers left", output)
        self.assertIn("UNMATCHED x1", self.read("Work/Prompts/fix/gate_log.md"))
        # A pass whose records hold no edit entries (the style pass) can make them notes.
        code, output = self.gate("--no-match")
        self.assertEqual(code, 0, output)
        self.assertIn("note: UNMATCHED", output)

    def test_joined_paragraph_is_a_problem(self):
        self.edit("look for work.\n\nThe closure", "look for work.\nThe closure")
        code, output = self.gate()
        self.assertEqual(code, 1, output)
        self.assertIn("PARAGRAPHS 3 -> 2", output)
        self.assertIn("BREAK line 4: two text lines without a blank line", output)
        code, output = self.gate("--keep-structure")
        self.assertIn("note: PARAGRAPHS 3 -> 2", output)
        self.assertEqual(code, 1, output)  # the joined lines still fail

    def test_fabricated_source_excerpt(self):
        self.record(RECORD_TWO.replace("the mills of Penhale's town closed for most of a month",
                                       "the mills of the town closed for nearly the whole month"))
        code, output = self.gate()
        self.assertEqual(code, 1, output)
        self.assertIn('SOURCE NOT FOUND (02-two.md:6): "the mills of the town closed', output)

    def test_new_fidelity_flag(self):
        self.edit("winter of 1890", "winter of 1891")
        self.record(RECORD_TWO.replace("After: \"The harbour froze in the winter of 1890",
                                       "After: \"The harbour froze in the winter of 1891"))
        code, output = self.gate()
        self.assertEqual(code, 1, output)
        self.assertIn('NEW FIDELITY FLAG NUMBER para 2, line 3: "1891"', output)
        self.assertNotIn("UNMATCHED", output)

    def test_word_change_over_limit_and_misreported(self):
        code, output = self.gate("--max-delta", "1")
        self.assertEqual(code, 1, output)
        self.assertIn("OVER MAX DELTA NR-1: +2 (limit +1)", output)
        self.record(RECORD_TWO.replace("Words: +2", "Words: +1"))
        code, output = self.gate()
        self.assertIn("WORDS NR-1: the record says +1, counted +2", output)

    def test_after_text_must_be_in_the_summary_and_items_need_entries(self):
        self.record(RECORD_TWO.replace("### NR-1", "### NR-2").replace("closed for most of a month.\"\nWords",
                                                                         "closed for much of a month.\"\nWords"))
        code, output = self.gate("--sections", "New reports;Author naming")
        self.assertEqual(code, 1, output)
        self.assertIn("AFTER NOT IN SUMMARY NR-2", output)
        self.assertIn("NO RECORD ENTRY for item NR-1", output)
        self.assertIn('MISSING SECTION "Author naming"', output)
        self.assertNotIn('MISSING SECTION "New reports"', output)

    def test_show_marks_pronouns_in_the_next_sentence(self):
        self.edit("The closure was temporary.", "The closure was only temporary.")
        self.record(RECORD_TWO + "\n### NR-9 (tier 2): x\nBefore: \"The closure was temporary.\"\n"
                                 "After: \"The closure was only temporary.\"\nWords: +1\n")
        code, output = self.gate("--show")
        self.assertEqual(code, 0, output)
        self.assertIn("+ The closure was only temporary.", output)
        self.assertIn("after:  [[It]] ended when", output)

    def test_chapter_waits_until_all_records_exist(self):
        self.write("Work/Prompts/fix/index.txt", self.read("Work/Prompts/fix/index.txt") +
                   "2|s/ch-01/1|%s|%s|Work/Reviews/s/fix/01-one-part1-of-2.md|20|-|-\n" % (S1, P1) +
                   "3|s/ch-01/2|%s|%s|Work/Reviews/s/fix/01-one-part2-of-2.md|20|-|-\n" % (S1, P2))
        self.write("Work/Reviews/s/fix/01-one-part1-of-2.md", "# Part 1\n")
        code, output = self.gate()
        self.assertEqual(code, 0, output)
        self.assertIn("1 chapter(s) not gated, records not all written: s/ch-01/1,s/ch-01/2", output)
        code, output = self.gate("s/ch-01")
        self.assertEqual(code, 1, output)
        self.assertIn("records missing (1 of 2), not gated", output)


# ---------------------------------------------------------------------- collect_items

class CollectItems(PassProject):
    def collect(self, *argv):
        return call(collect_items.main, list(argv))

    def test_natural_order_puts_chunk10_after_chunk9(self):
        self.assertEqual(sorted(["chunk10.md", "chunk2.md", "chunk9.md"], key=collect_items.natural_key),
                         ["chunk2.md", "chunk9.md", "chunk10.md"])
        for k in (10, 2, 9):
            self.write("Work/Reviews/whole-document/chunk%d.md" % k,
                       "# Whole-document review: chunk %d\n\n### W-1 (garbled): from chunk %d\nChapter: %s\n"
                       "Summary: \"opened in\"\nProblem: x.\nFix: y.\n" % (k, k, S1))
        code, output = self.collect("wd", "--findings", "Work/Reviews/whole-document/chunk*.md")
        self.assertEqual(code, 0, output)
        text = self.read("Work/Prompts/wd/items/s--01-one.md")
        order = [int(k) for k in re.findall(r"from: Work/Reviews/whole-document/chunk(\d+)\.md", text)]
        self.assertEqual(order, [2, 9, 10])
        self.assertEqual(collect_items.item_ids(text), ["W-1", "R2-W-1", "R3-W-1"])
        self.assertIn("s|ch-01|%s|3|W-1,R2-W-1,R3-W-1" % S1, self.read("Work/Prompts/wd/items/index.txt"))

    def test_settled_and_empty_new_reports_are_dropped(self):
        self.write("Work/Reviews/s/fix/01-one.md", "# Fix\n\n## New reports\n- NR-1: settled one.\n"
                   "- NR-2: open one,\n  continued here.\n\n## Coordinator gate\nSettled: NR-1\n")
        self.write("Work/Reviews/s/fix/02-two.md", "# Fix\n\n## New reports\nNone.\n")
        code, output = self.collect("fix2", "--new-reports", "fix")
        self.assertEqual(code, 0, output)
        items = self.root / "Work/Prompts/fix2/items"
        self.assertEqual(sorted(p.name for p in items.iterdir()), ["index.txt", "s--01-one.md"])
        text = (items / "s--01-one.md").read_text(encoding="utf-8")
        self.assertIn("### NR-2 (new report)\n<!-- from: Work/Reviews/s/fix/01-one.md -->\n- NR-2: open one,\n"
                      "  continued here.", text)
        self.assertNotIn("NR-1", text)
        # A used items folder is kept unless --force.
        self.assertNotEqual(self.collect("fix2", "--new-reports", "fix")[0], 0)

    def test_unnumbered_report_and_unmatched_finding_write_nothing(self):
        self.write("Work/Reviews/s/fix/01-one.md", "# Fix\n\n## New reports\n- a report with no number.\n")
        code, output = self.collect("g", "--new-reports", "fix")
        self.assertEqual(code, 1)
        self.assertIn("UNNUMBERED new report", output)
        self.write("Work/Reviews/whole-document/chunk1.md", "### W-1 (garbled): x\nChapter: 07-missing.md\n")
        code, output = self.collect("h", "--findings", "Work/Reviews/whole-document/chunk1.md")
        self.assertEqual(code, 1)
        self.assertIn("UNMATCHED Work/Reviews/whole-document/chunk1.md W-1", output)
        self.assertFalse((self.root / "Work/Prompts/h").exists())

    def test_validation_findings_collect_fill_and_gate(self):
        """validation-findings.md: #### N.k blocks go to their chapter, I.k to the
        coordinator, D.k and U.k to the coordinator unless they name a summary;
        the gate matches N.k and D.k record entries to the index's items."""
        self.write("validation-findings.md", (
            "# Validation findings\n\n## Part 1: chapter findings\n\n### 1. One\n\n"
            "#### 1.1 (material, preservation): lost hedge\n- **Chapter:** 1. One, `%s`\n"
            "- **Summary:** \"opened in 1871\"\n- **Fix:** restore it.\n\n"
            "#### 1.2 (minor, clarity): unclear pronoun\n- **Chapter:** 1. One, `%s`\n\n"
            "### 2. Two\n\n#### 2.1 (minor, preservation): lost scope word\n- **Chapter:** 2. Two, `%s`\n\n"
            "## Introduction\n\n#### I.1 (minor, clarity): intro wording\n- **Where:** the second paragraph\n\n"
            "## Disputed\n\n#### D.1 (minor, attribution): no chapter named\n- **Problem:** x\n\n"
            "#### D.2 (minor, attribution): names one\n- **Chapter:** 2. Two, `%s`\n\n"
            "## Unverified\n\n#### U.1 (minor, number): unchecked\n- **Problem:** y\n") % (S1, S1, S2, S2))
        code, output = self.collect("valfix", "--findings", "validation-findings.md")
        self.assertEqual(code, 0, output)
        items = "Work/Prompts/valfix/items/"
        self.assertEqual(collect_items.item_ids(self.read(items + "s--01-one.md")), ["1.1", "1.2"])
        self.assertEqual(collect_items.item_ids(self.read(items + "s--02-two.md")), ["2.1", "D.2"])
        self.assertEqual(collect_items.item_ids(self.read(items + "_coordinator.md")), ["I.1", "D.1", "U.1"])
        self.assertIn("#### 2.1 (minor, preservation): lost scope word\n<!-- from: validation-findings.md -->",
                      self.read(items + "s--02-two.md"))

        self.write("brief.md", "# Brief\n\n## Agent prompt\n\n```text\n{SUMMARY} {ITEMS} {RECORD}\n```\n")
        code, output = call(make_prompts.main, ["valfix", "pass", "--all", "--brief", "brief.md",
                                                "--items", items.rstrip("/")])
        self.assertEqual(code, 0, output)
        rows = {r["key"]: r for r in make_prompts.read_index(self.root / "Work/Prompts/valfix")}
        self.assertEqual(rows["s/ch-02"]["items"], "2.1,D.2")
        self.assertEqual(rows["s/ch-02"]["record"], "Work/Reviews/s/valfix/02-two.md")

        self.write("Work/Summaries_prevalfix/s/02-two.md", SUMMARY_TWO)
        self.write(S2, SUMMARY_TWO.replace("closed for a month", "closed for most of a month"))
        record = RECORD_TWO.replace("### NR-1 (tier 2)", "### 2.1 (minor, preservation)") + (
            "\n### D.2 (minor, attribution): names one\nDisposition: not applied\nReason: the source agrees.\n")
        self.write("Work/Reviews/s/valfix/02-two.md", record)
        code, output = call(gate_pass.main, ["valfix", "s/ch-02", "--max-delta", "3"])
        self.assertEqual(code, 0, output)
        self.assertIn("1 edit entry (sum +2)", output)
        self.write("Work/Reviews/s/valfix/02-two.md", record.split("\n### D.2")[0] + "\n")
        code, output = call(gate_pass.main, ["valfix", "s/ch-02"])
        self.assertEqual(code, 1, output)
        self.assertIn("NO RECORD ENTRY for item D.2", output)
        self.assertNotIn("NO RECORD ENTRY for item 2.1", output)

    def test_sections_bare_names_and_skipped_categories(self):
        self.write("Work/Reviews/s/verify-round2/01-one-part2-of-2.md",
                   "# Remediation\n\n## Edits applied\n### E-1 (minor, x): applied\nBefore: a\nAfter: b\n\n"
                   "## Minor findings not applied\n### m-1: left for length\nSummary: \"x\"\n\n"
                   "## Coverage notes\n### c-1: an omission\n\n## Unresolved\nNone.\n")
        code, output = self.collect("v", "--sections", "Minor findings not applied;Coverage notes",
                                    "--from", "verify-round2")
        self.assertEqual(code, 0, output)
        self.assertEqual(collect_items.item_ids(self.read("Work/Prompts/v/items/s--01-one.md")), ["m-1", "c-1"])
        self.write("Work/Reviews/whole-document/chunk1.md",
                   "### W-1 (garbled): x\nChapter: 01-one.md\n\n### W-2 (unexplained term): y\nChapter: %s\n\n"
                   "### W-3 (typography): z\nChapter: Work/Introduction.md\n" % S1)
        code, output = self.collect("w", "--findings", "Work/Reviews/whole-document/chunk1.md",
                                    "--skip-category", "unexplained")
        self.assertEqual(code, 0, output)
        self.assertEqual(collect_items.item_ids(self.read("Work/Prompts/w/items/s--01-one.md")), ["W-1"])
        self.assertIn("### W-3", self.read("Work/Prompts/w/items/_coordinator.md"))


# ---------------------------------------------------------------------- apply_replacements

class ApplyReplacements(PassProject):
    def edits(self, items):
        self.write("edits.json", json.dumps(items))
        return "edits.json"

    def test_ambiguous_old_text_is_refused(self):
        self.write("Work/Introduction.md", "the mill and the mill.\r\n")
        path = self.edits([{"id": "X-1", "path": "Work/Introduction.md", "old": "the mill", "new": "a mill"}])
        code, output = call(apply_replacements.main, [path, "--apply"])
        self.assertEqual(code, 1)
        self.assertIn("FOUND 2 TIMES", output)
        self.assertIn("nothing applied", output)
        self.assertEqual((self.root / "Work/Introduction.md").read_bytes(), b"the mill and the mill.\r\n")

    def test_dry_run_then_apply_in_order_with_lf(self):
        self.write("Work/Introduction.md", "One two.\r\nThree four.\r\n")
        path = self.edits([{"id": "A", "path": "Work/Introduction.md", "old": "One two.", "new": "One, two, three."},
                           {"id": "B", "path": "Work/Introduction.md", "old": "two, three.\nThree", "new": "two.\nThree"}])
        code, output = call(apply_replacements.main, [path, "--max-delta", "1"])
        self.assertEqual(code, 0, output)
        self.assertRegex(output, r"A\s+\+1\s+Work/Introduction.md\n")
        self.assertEqual((self.root / "Work/Introduction.md").read_bytes(), b"One two.\r\nThree four.\r\n")
        code, output = call(apply_replacements.main, [path, "--apply"])
        self.assertEqual(code, 0, output)
        self.assertEqual((self.root / "Work/Introduction.md").read_bytes(), b"One, two.\nThree four.\n")


if __name__ == "__main__":
    unittest.main()
