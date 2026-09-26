"""Tests for page markers, part context, and assembly checks. Run from the project root:

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
import assemble  # noqa: E402
import split_parts  # noqa: E402
from check_parts import CONTEXT_RE  # noqa: E402
from common import OWNED_END, OWNED_START, owned_text  # noqa: E402
from count_words import words_in_text  # noqa: E402


class Markers(unittest.TestCase):
    def test_marker_line_stays_with_following_paragraph(self):
        body = "<!-- page 4 -->\nFirst.\n\nSecond.\n\n<!-- page 5 -->\nThird.\n"
        spans = split_parts.paragraph_units(body)
        self.assertEqual([body[a:b].strip() for a, b in spans],
                         ["<!-- page 4 -->\nFirst.", "Second.", "<!-- page 5 -->\nThird."])

    def test_marker_only_paragraph_joins_the_next(self):
        body = "First.\n\n<!-- page 5 -->\n\nSecond.\n"
        spans = split_parts.paragraph_units(body)
        self.assertEqual([body[a:b] for a, b in spans], ["First.\n\n", "<!-- page 5 -->\n\nSecond.\n"])

    def test_heading_after_marker_is_a_preferred_break(self):
        para = "Word " * 700 + "end.\n\n"  # about 3.5KB per paragraph
        body = "".join("<!-- page %d -->\n%s" % (i, para) for i in range(1, 7))
        body += "<!-- page 7 -->\nA New Section\n\n" + para * 3
        parts, _ = split_parts.make_parts(body, 30_000)
        starts = [body[a:a + 40] for a, _ in parts]
        self.assertTrue(any(s.startswith("<!-- page 7 -->\nA New Section") for s in starts), starts)

    def test_sentence_split_ignores_marker_before_lowercase(self):
        body = "One ends here. <!-- page 9 --> and continues. Two starts."
        cuts = [body[a:b] for a, b in split_parts.sentence_units(body, 0, len(body))]
        self.assertEqual(cuts, ["One ends here. <!-- page 9 --> and continues. ", "Two starts."])

    def test_part_page_range_from_markers(self):
        body = "<!-- page 4 -->\nA.\n\nB runs <!-- page 5 --> on.\n\nC.\n\n<!-- page 6 -->\nD.\n"
        c = body.index("C.")
        self.assertEqual(split_parts.part_pages(body, 0, c, "4-6"), "4-5")
        self.assertEqual(split_parts.part_pages(body, c, len(body), "4-6"), "5-6")
        self.assertEqual(split_parts.part_pages("No markers.", 0, 11, "4-6"), "4-6")

    def test_inline_marker_is_not_counted(self):
        self.assertEqual(words_in_text("the popu<!-- page 5 -->lation was <!-- page 6 --> large"), 4)

    def test_block_quote_marker_is_not_counted(self):
        self.assertEqual(words_in_text("> I used to feel\n\n<!-- page 5 -->\n> that way.\n\nProse."), 7)

    def test_part_boundary_never_falls_inside_a_block_quotation(self):
        para = "Word " * 700 + "end.\n\n"  # about 3.5KB per paragraph
        # Eight 1.5KB verse paragraphs, so the 29KB target falls inside the verse.
        verse = "".join("> Verse line %d " % i + "word " * 300 + "end.\n\n" for i in range(8))
        body = para * 5 + "She sings:\n\n" + verse + para * 4
        parts, _ = split_parts.make_parts(body, 30_000)
        self.assertGreater(len(parts), 1)
        for a, _ in parts[1:]:
            self.assertFalse(body[a:].startswith(">"), "part starts inside a block quotation: %r" % body[a:a + 20])


class PartContext(unittest.TestCase):
    body = "Alpha defines a term.\n\nBeta uses it.\n\nGamma concludes.\n"

    def spans(self):
        units = split_parts.paragraph_units(self.body)
        return [units[0], units[1], units[2]]

    def test_context_from_earlier_and_later_parts(self):
        notes = []
        entries = [{"text": "Alpha defines a term."}, {"text": "Gamma concludes."}]
        before, after = split_parts.place_context(entries, self.body, self.spans(), 2, "ch-01", notes)
        self.assertEqual(before, [("ch-01 part 1", "Alpha defines a term.")])
        self.assertEqual(after, [("ch-01 part 3", "Gamma concludes.")])
        self.assertEqual(notes, [])

    def test_bad_context_is_reported_not_added(self):
        notes = []
        entries = [{"text": "Not in the chapter."}, {"text": "Beta uses it."}]
        before, after = split_parts.place_context(entries, self.body, self.spans(), 2, "ch-01", notes)
        self.assertEqual((before, after), ([], []))
        self.assertEqual(len(notes), 2)

    def test_rendered_context_is_found_by_checker_and_owned_text_is_exact(self):
        owned = "Beta uses it.\n\n"
        content = split_parts.render_part([("unit_id", "ch-01")], "# T", [], owned,
                                          [("ch-01 part 1", "Alpha defines a term.")],
                                          [("ch-01 part 3", "Gamma concludes.")])
        self.assertEqual(owned_text(content), owned)
        self.assertEqual(CONTEXT_RE.findall(content), ["Alpha defines a term.", "Gamma concludes."])
        self.assertLess(content.index("Alpha"), content.index(OWNED_START))
        self.assertGreater(content.index("Gamma"), content.index(OWNED_END))

    def test_config_entries_need_part_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "part_context.json"
            path.write_text(json.dumps([{"source_slug": "s", "unit_id": "u", "text": "x"}]), encoding="utf-8")
            old = split_parts.CONTEXT_CONFIG
            split_parts.CONTEXT_CONFIG = path
            try:
                grouped, problems = split_parts.load_context()
                self.assertEqual(grouped, {})
                self.assertEqual(len(problems), 1)
                self.assertIn("part_index", problems[0])
            finally:
                split_parts.CONTEXT_CONFIG = old


class Assemble(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "Work" / "Summaries" / "src").mkdir(parents=True)
        self.saved = {k: getattr(assemble, k) for k in
                      ("ROOT", "SUMS", "MANIFEST", "PARTS_MANIFEST", "OUT", "PARTS", "INTRO", "LIMITATIONS")}
        assemble.ROOT = root
        assemble.SUMS = root / "Work" / "Summaries"
        assemble.MANIFEST = root / "Work" / "manifest.json"
        assemble.PARTS_MANIFEST = root / "Work" / "parts_manifest.json"
        assemble.OUT = root / "Summary.md"
        assemble.PARTS = [("src", "# Part 1: A Book")]
        assemble.INTRO = "# Introduction\n\nThis summarizes one book in two chapters.\n"
        assemble.LIMITATIONS = {}
        self.root = root

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(assemble, k, v)
        self.tmp.cleanup()

    def write(self, chapters, statuses=None):
        manifest = []
        for i, text in enumerate(chapters, 1):
            rel_path = "Work/Summaries/src/%02d-c.md" % i
            (self.root / rel_path).write_text(text, encoding="utf-8")
            manifest.append({"source_slug": "src", "unit_id": "ch-%02d" % i, "path": rel_path,
                             "status": (statuses or {}).get(i, "accepted")})
        assemble.MANIFEST.write_text(json.dumps(manifest), encoding="utf-8")
        assemble.PARTS_MANIFEST.write_text(json.dumps(
            [{"source_slug": "src", "unit_id": m["unit_id"], "part": 1, "title": "Chapter %d" % i}
             for i, m in enumerate(manifest, 1)]), encoding="utf-8")

    def run_main(self):
        out = io.StringIO()
        with redirect_stdout(out):
            try:
                assemble.main()
                code = 0
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue()

    def test_clean_run_reports_intro_and_body_separately(self):
        self.write(["## One\n\nThe author argues a point.\n", "## Two\n\nThe author concludes.\n"])
        code, out = self.run_main()
        self.assertEqual(code, 0, out)
        self.assertIn("introduction: 7 words; chapter summaries: 8 words; 2 chapter(s)", out)
        self.assertTrue(assemble.OUT.exists())

    def test_structural_problems_block_writing(self):
        self.write([
            "The author argues a point.\n",                                  # no ## heading
            "## Two\n\nAs shown on p. 12, it holds. <!-- page 12 -->\n\nWord count: 12\n\nSee Work/Drafts/x.md.\n",
        ])
        code, out = self.run_main()
        self.assertEqual(code, 1)
        for label in ["does not open with a ## chapter heading", "page reference", "leftover HTML comment",
                      "leaked review note", "working-file reference"]:
            self.assertIn(label, out)
        self.assertFalse(assemble.OUT.exists())

    def test_unfilled_template_intro_fails(self):
        assemble.INTRO = "# Introduction\n\n{Identify the sources.}\n"
        self.write(["## One\n\nText.\n"])
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("unfilled template placeholder", out)

    def test_unfinished_unit_fails(self):
        self.write(["## One\n\nText.\n", "## Two\n\nText.\n"], {2: "drafted"})
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("src/ch-02 is drafted", out)

    def test_blocked_unit_needs_limitation_then_adds_partial_notice(self):
        self.write(["## One\n\nText.\n", "## Two\n\nText.\n"], {2: "blocked"})
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("add its limitation to LIMITATIONS", out)

        assemble.LIMITATIONS = {"src/ch-02": "the scanned pages are illegible"}
        code, out = self.run_main()
        self.assertEqual(code, 0, out)
        text = assemble.OUT.read_text(encoding="utf-8")
        self.assertIn("This summary is partial.", text)
        self.assertIn("- Part 1, Chapter 2: the scanned pages are illegible", text)
        self.assertNotIn("## Two", text)
        self.assertIn("PARTIAL", out)

    def test_pilot_units_assemble_only_the_pilot(self):
        self.write(["## One\n\nThe pilot chapter.\n", "## Two\n\nText.\n"], {2: "pending"})
        saved = assemble.PILOT_UNITS
        assemble.PILOT_UNITS = [("src", "ch-01")]
        try:
            code, out = self.run_main()
        finally:
            assemble.PILOT_UNITS = saved
        self.assertEqual(code, 0, out)
        text = assemble.OUT.read_text(encoding="utf-8")
        self.assertIn("## One", text)
        self.assertNotIn("## Two", text)

    def test_sibling_folder_path_is_rejected(self):
        self.write(["## One\n\nText.\n"])
        manifest = json.loads(assemble.MANIFEST.read_text(encoding="utf-8"))
        manifest[0]["path"] = "../%s2/x.md" % self.root.name
        assemble.MANIFEST.write_text(json.dumps(manifest), encoding="utf-8")
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("escapes the project root", out)


if __name__ == "__main__":
    unittest.main()
