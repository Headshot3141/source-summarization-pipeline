"""Tests for page markers, part context, assembly checks, the whole-document
chunks, and the verification queue. Run from the project root:

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
import make_doc_chunks  # noqa: E402
import make_verify_queue  # noqa: E402
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
        self.assertEqual(before, [("ch-01 part 1", "Alpha defines a term.", False)])
        self.assertEqual(after, [("ch-01 part 3", "Gamma concludes.", False)])
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
                                          [("ch-01 part 1", "Alpha defines a term.", False)],
                                          [("ch-01 part 3", "Gamma concludes.", False)])
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
                      ("ROOT", "SUMS", "MANIFEST", "PARTS_MANIFEST", "INTRO_FILE", "OUT", "PARTS",
                       "LIMITATIONS", "QUOTE_STYLE")}
        assemble.ROOT = root
        assemble.SUMS = root / "Work" / "Summaries"
        assemble.MANIFEST = root / "Work" / "manifest.json"
        assemble.PARTS_MANIFEST = root / "Work" / "parts_manifest.json"
        assemble.OUT = root / "Summary.md"
        assemble.PARTS = [("src", "# Part 1: A Book")]
        assemble.INTRO_FILE = root / "Work" / "Introduction.md"
        assemble.INTRO_FILE.write_text("# Introduction\n\nThis summarizes one book in two chapters.\n",
                                       encoding="utf-8")
        assemble.LIMITATIONS = {}
        assemble.QUOTE_STYLE = None
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

    def run_main(self, *argv):
        out = io.StringIO()
        saved = sys.argv
        sys.argv = ["assemble.py"] + list(argv)
        try:
            with redirect_stdout(out):
                try:
                    assemble.main()
                    code = 0
                except SystemExit as exc:
                    code = exc.code
        finally:
            sys.argv = saved
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
        # The Introduction stub the template ships.
        shipped = Path(assemble.__file__).resolve().parent / "Introduction.md"
        assemble.INTRO_FILE.write_text(shipped.read_text(encoding="utf-8"), encoding="utf-8")
        self.write(["## One\n\nText.\n"])
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("unfilled template placeholder", out)
        self.assertFalse(assemble.OUT.exists())

    def test_introduction_file_must_exist_and_open_with_its_heading(self):
        self.write(["## One\n\nText.\n"])
        for content, message in ((None, "Work/Introduction.md is missing"),
                                 ("\n  \n", "Work/Introduction.md is empty"),
                                 ("## Introduction\n\nText.\n", 'must start with "# Introduction"')):
            if content is None:
                assemble.INTRO_FILE.unlink()
            else:
                assemble.INTRO_FILE.write_text(content, encoding="utf-8")
            code, out = self.run_main()
            self.assertEqual(code, 1, out)
            self.assertIn(message, out)
            self.assertFalse(assemble.OUT.exists())

    def test_introduction_is_read_from_its_file(self):
        assemble.INTRO_FILE.write_bytes("\ufeff# Introduction\n\nTwo chapters of one book.\n".encode("utf-8"))
        self.write(["## One\n\nText.\n"])
        code, out = self.run_main()
        self.assertEqual(code, 0, out)
        self.assertTrue(assemble.OUT.read_text(encoding="utf-8").startswith(
            "# Introduction\n\nTwo chapters of one book.\n\n# Part 1: A Book\n\n## One\n"))

    def test_lost_blank_lines_block_assembly(self):
        self.write(["## One\n\nFirst.\nSecond.\n\n### Sub\nText.\n"])
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("Work/Summaries/src/01-c.md line 4: two text lines without a blank line", out)
        self.assertIn("Work/Summaries/src/01-c.md line 7: heading without a blank line", out)
        self.assertEqual(out.count("01-c.md line"), 2, out)
        self.assertFalse(assemble.OUT.exists())
        # In the Introduction too.
        assemble.INTRO_FILE.write_text("# Introduction\nOne book.\n", encoding="utf-8")
        self.write(["## One\n\nText.\n"])
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("Work/Introduction.md line 2: heading without a blank line", out)

    def test_adjacent_list_items_and_quotation_lines_pass(self):
        self.write(["## One\n\nThe list:\n\n- one\n- two\n\n> A quotation\n> runs on.\n\nText.\n"])
        code, out = self.run_main()
        self.assertEqual(code, 0, out)

    def test_summaries_are_read_without_a_byte_order_mark(self):
        self.write(["## One\n\nText.\n"])
        path = self.root / "Work/Summaries/src/01-c.md"
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
        code, out = self.run_main()
        self.assertEqual(code, 0, out)
        self.assertNotIn("\ufeff", assemble.OUT.read_text(encoding="utf-8"))

    def test_out_writes_elsewhere(self):
        self.write(["## One\n\nText.\n"])
        code, out = self.run_main("--out", "Work/scratch/check.md")
        self.assertEqual(code, 0, out)
        self.assertIn("wrote Work/scratch/check.md", out)
        self.assertFalse(assemble.OUT.exists())
        first = (self.root / "Work/scratch/check.md").read_bytes()
        self.assertEqual(self.run_main()[0], 0)
        self.assertEqual(assemble.OUT.read_bytes(), first)
        self.assertNotEqual(self.run_main("--out")[0], 0)

    def test_heading_that_differs_from_the_manifest_title_is_a_note(self):
        self.write(["## Chapter 1\n\nText.\n", "## Renamed\n\nText.\n"])
        parts = [{"source_slug": "src", "unit_id": "ch-%02d" % i, "title": "Chapter %d" % i,
                  "summary": "Work/Summaries/src/%02d-c.md" % i} for i in (1, 2)]
        assemble.PARTS_MANIFEST.write_text(json.dumps(parts), encoding="utf-8")
        code, out = self.run_main()
        self.assertEqual(code, 0, out)
        self.assertIn("notes (not blocking):", out)
        self.assertIn("02-c.md: heading 'Renamed' differs from the parts manifest title 'Chapter 2'", out)
        self.assertNotIn("01-c.md: heading", out)

    def test_quote_style_lists_the_other_style_without_blocking(self):
        self.write(["## One\n\nShe called it \u201ca quiet place\u201d, and it wasn\u2019t.\n\n"
                    "He said \"no\" twice.\n"])
        code, out = self.run_main()
        self.assertEqual(code, 0, out)
        self.assertNotIn("notes", out)
        assemble.QUOTE_STYLE = "curly"
        code, out = self.run_main()
        self.assertEqual(code, 0, out)
        self.assertIn("Summary.md: 1 line(s) hold straight quotation marks", out)
        self.assertIn("line 11: 'He said \"no\" twice.'", out)
        assemble.QUOTE_STYLE = "straight"
        code, out = self.run_main()
        self.assertEqual(code, 0, out)
        self.assertIn("Summary.md: 1 line(s) hold curly quotation marks", out)
        assemble.QUOTE_STYLE = "Curly"
        code, out = self.run_main()
        self.assertEqual(code, 1, out)
        self.assertIn("QUOTE_STYLE must be None", out)

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


class DocChunks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.saved = {k: getattr(make_doc_chunks, k) for k in ("ROOT", "MANIFEST", "OUT")}
        make_doc_chunks.ROOT = self.root
        make_doc_chunks.MANIFEST = self.root / "Work" / "manifest.json"
        make_doc_chunks.OUT = self.root / "Work" / "whole_doc_chunks.txt"

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(make_doc_chunks, k, v)
        self.tmp.cleanup()

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_main(self, *argv):
        saved, out = sys.argv, io.StringIO()
        sys.argv = ["make_doc_chunks.py"] + list(argv)
        try:
            with redirect_stdout(out):
                make_doc_chunks.main()
        finally:
            sys.argv = saved
        return out.getvalue()

    def setup_chapters(self, n, size=100):
        manifest = []
        for i in range(1, n + 1):
            path = "Work/Summaries/s/%02d-c.md" % i
            self.write(path, "## C\n\n" + "x" * size + "\n")
            manifest.append({"source_slug": "s", "unit_id": "ch-%02d" % i, "path": path, "status": "accepted"})
        self.write("Work/manifest.json", json.dumps(manifest))

    def test_introduction_opens_chunk_one_and_counts_bytes_not_chapters(self):
        self.setup_chapters(4)
        self.write("Work/Introduction.md", "# Introduction\n\nText.\n")
        out = self.run_main()
        self.assertIn("4 accepted chapter(s) in 2 chunk(s), the Introduction first", out)
        lines = make_doc_chunks.OUT.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines, [
            "CHUNK 1: Work/Introduction.md ; Work/Summaries/s/01-c.md ; Work/Summaries/s/02-c.md ; "
            "Work/Summaries/s/03-c.md",
            "CHUNK 2: Work/Summaries/s/04-c.md"])
        # Its bytes count: a long Introduction leaves room for one chapter.
        self.write("Work/Introduction.md", "# Introduction\n\n" + "y" * 250 + "\n")
        self.run_main("--max-bytes", "400")
        lines = make_doc_chunks.OUT.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "CHUNK 1: Work/Introduction.md ; Work/Summaries/s/01-c.md")

    def test_defaults_are_small_chunks(self):
        self.assertEqual((make_doc_chunks.MAX_CHAPTERS, make_doc_chunks.MAX_BYTES), (3, 60_000))

    def test_out_keeps_an_earlier_round(self):
        self.setup_chapters(2)
        self.run_main()
        first = make_doc_chunks.OUT.read_text(encoding="utf-8")
        out = self.run_main("--max-chapters", "1", "--out", "Work/whole_doc_chunks_round2.txt")
        self.assertIn("note: Work/Introduction.md not found", out)
        self.assertEqual(make_doc_chunks.OUT.read_text(encoding="utf-8"), first)
        self.assertEqual((self.root / "Work/whole_doc_chunks_round2.txt").read_text(encoding="utf-8").splitlines(),
                         ["CHUNK 1: Work/Summaries/s/01-c.md", "CHUNK 2: Work/Summaries/s/02-c.md"])


class VerifyQueue(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.saved = {k: getattr(make_verify_queue, k) for k in ("ROOT", "MANIFEST", "QUEUE", "WHOLE_MAX_BYTES")}
        make_verify_queue.ROOT = self.root
        make_verify_queue.MANIFEST = self.root / "Work" / "parts_manifest.json"
        make_verify_queue.QUEUE = self.root / "Work" / "verify_queue.txt"
        part = "Work/Chapters/s/parts/01-one-part%d-of-2.md"
        self.manifest = [
            {"source_slug": "s", "unit_id": "ch-01", "status": "accepted",
             "chapter_source": "Work/Chapters/s/01-one.md", "summary": "Work/Summaries/s/01-one.md",
             "parts": [{"part_index": k, "source": part % k} for k in (1, 2)]},
            {"source_slug": "s", "unit_id": "ch-02", "status": "accepted",
             "chapter_source": "Work/Chapters/s/02-two.md", "summary": "Work/Summaries/s/02-two.md",
             "parts": [{"part_index": 1, "source": "Work/Chapters/s/02-two.md"}]},
            {"source_slug": "s", "unit_id": "ch-03", "status": "drafted",
             "chapter_source": "Work/Chapters/s/03-x.md", "summary": "Work/Summaries/s/03-x.md",
             "parts": [{"part_index": 1, "source": "Work/Chapters/s/03-x.md"}]},
        ]
        (self.root / "Work" / "Chapters" / "s").mkdir(parents=True)
        (self.root / "Work/Chapters/s/01-one.md").write_text("x" * 500, encoding="utf-8")
        (self.root / "Work/Chapters/s/02-two.md").write_text("x" * 100, encoding="utf-8")
        make_verify_queue.MANIFEST.write_text(json.dumps(self.manifest), encoding="utf-8")

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(make_verify_queue, k, v)
        self.tmp.cleanup()

    def run_main(self, *argv):
        saved, out = sys.argv, io.StringIO()
        sys.argv = ["make_verify_queue.py"] + list(argv)
        try:
            with redirect_stdout(out):
                make_verify_queue.main()
        finally:
            sys.argv = saved
        return out.getvalue()

    def lines(self, name):
        return (self.root / "Work" / name).read_text(encoding="utf-8").splitlines()

    def test_each_round_gets_its_own_queue(self):
        out = self.run_main()
        self.assertIn("3 verification task(s) in Work/verify_queue.txt", out)
        self.assertEqual(self.lines("verify_queue.txt")[0].split("|")[8],
                         "Work/Reviews/s/verify-round1/01-one-part1-of-2.md")
        self.run_main("--round", "2")
        lines = self.lines("verify_queue_round2.txt")
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0].split("|")[8], "Work/Reviews/s/verify-round2/01-one-part1-of-2.md")
        self.assertEqual(len(self.lines("verify_queue.txt")), 3)
        self.run_main("--round", "3", "--out", "Work/q.txt", "s", "ch-02")
        self.assertEqual(self.lines("q.txt"), [
            "s|ch-02|1|1|Work/Chapters/s/02-two.md|-|-|Work/Summaries/s/02-two.md|"
            "Work/Reviews/s/verify-round3/02-two.md"])

    def test_whole_lists_one_task_per_chapter(self):
        self.run_main("--whole", "--round", "4")
        self.assertEqual(self.lines("verify_queue_round4.txt"), [
            "s|ch-01|1|1|Work/Chapters/s/01-one.md|-|-|Work/Summaries/s/01-one.md|"
            "Work/Reviews/s/verify-round4/01-one.md",
            "s|ch-02|1|1|Work/Chapters/s/02-two.md|-|-|Work/Summaries/s/02-two.md|"
            "Work/Reviews/s/verify-round4/02-two.md"])

    def test_whole_keeps_parts_for_a_chapter_too_large(self):
        make_verify_queue.WHOLE_MAX_BYTES = 300
        out = self.run_main("--whole")
        self.assertIn("s/ch-01: Work/Chapters/s/01-one.md is 500 bytes, over WHOLE_MAX_BYTES (300)", out)
        lines = [ln.split("|") for ln in self.lines("verify_queue.txt")]
        self.assertEqual([ln[1:4] for ln in lines], [["ch-01", "1", "2"], ["ch-01", "2", "2"], ["ch-02", "1", "1"]])
        self.assertEqual(lines[0][5:7], ["-", "Work/Chapters/s/parts/01-one-part2-of-2.md"])


if __name__ == "__main__":
    unittest.main()
