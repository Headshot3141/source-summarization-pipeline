"""Rebuild damaged lines of a docling Markdown file from the PDF's text layer, keeping every letter and digit.

Docling often flattens a PDF's typography: curly quotation marks become
straight ones, dashes become hyphens or vanish at a line end, italics are
lost (leaving a space before the next punctuation mark), a paragraph's
short first word runs into the next, and line-end hyphens are kept with a
space or dropped from real compounds. The PDF's text layer usually has all
of it right. This script rebuilds each Markdown line of the given ranges
from the PDF:

- The line is found in the PDF's character stream (PyMuPDF rawdict: each
  character with its font and size; running heads, footers, and folios
  left out as in pdf_to_paged_txt.py) by its skeleton, its letters and
  digits only, searching forward from the last line found.
- Its letters and digits are kept exactly as docling has them. Everything
  between them (spaces, punctuation, quotation marks, dashes) is taken
  from the PDF, and so is the punctuation before its first letter or
  digit and after its last. Its Markdown prefix ("## ", "- ", "> ") is
  docling's.
- Italic runs are marked *...*: characters whose font name matches
  --italic-font, or by default whose font flags say italic.
- Next to a superscript note number the docling spacing is kept, so a
  note reference stays as the export prints it ("Penhale. 1 The").
- A PDF line end is a space, except after a closed dash ("quay—" / "and"
  gives "quay—and") and after a line-end hyphen, which is kept or dropped
  by the book's own mid-line usage of the word, then the dictionary, then
  a known prefix, then the rule that a break between two known words
  keeps its hyphen (extract.hyphen_decision).

A line the PDF does not hold in one run is looked for in pieces (a
paragraph interrupted by footnotes and a page turn), out of order (notes
docling swapped), and without its note numbers (an export that dropped
them); the report lists each. A line not found is left as docling has it.
Table rows, code fences, comments, and lines without letters or digits
are skipped.

Only changed lines are written, as {line number: text}, to the --out JSON
(Work/Proof/<slug>.rebuilt.json). A config feeds them to build_line_edits,
which checks that each keeps its line's letters and digits:

    "line_edits": lambda: build_line_edits(MD, rebuilt=rebuilt_lines(SLUG), ...),

--report prints how each line was matched, the lines not found, the
uncertain hyphen decisions, and how many quotation marks, dashes, and
italics differ between the export and the PDF, the evidence for the
"Extract from" choice in Preflight. Usage:

    python Work/rebuild_from_pdf.py --md Sources/<file>.md --pdf Sources/<file>.pdf --lines 95-293,435-603
        [--italic-font REGEX] [--superscript-max PT] [--header-ymax N --footer-ymin N]
        --out Work/Proof/<slug>.rebuilt.json [--report]
"""
import argparse
import bisect
import json
import os
import re
import sys
import unicodedata
from collections import Counter

import pymupdf

import source_helpers
from extract import MD_EMPHASIS, DocEvidence, hyphen_decision
from pdf_to_paged_txt import DROP_CAP_FACTOR, HYPHENS, Glyph, Layout, PagedText, mark_italics, pdf_path
from source_helpers import md_entities

BREAK = "\n"
# A line with fewer letters and digits than this is looked for only within
# the stretch the docling lines since the last match should take (their
# skeleton length, times 1.5, plus SLACK), so it cannot match far ahead.
LONG = 40
SLACK = 3000
# How far back (letters and digits) a line docling put out of order is looked for.
BACK = 5000
# A line interrupted in the PDF is matched in at most MAX_PIECES pieces,
# each found by its first SEED characters within SKIP characters of the
# previous piece's end.
MAX_PIECES = 4
SEED = 16
SKIP = 6000
DASHES = "—–"
QUOTES = "\"'“”‘’"
CURLY = "“”‘’"
BULLETS = "•▪◦●■‣·"
MD_PREFIX = re.compile(r"\s*(?:#{1,6}\s+|[-*+]\s+|>\s?)*")


def keys(c):
    """The skeleton characters of c: NFKC-normalized, lowercased letters and digits ("ﬁ" -> "fi", "¹" -> "1")."""
    if not c.isalnum():
        return ""
    return "".join(ch for ch in unicodedata.normalize("NFKC", c).lower() if ch.isalnum())


def parse_ranges(spec):
    """Line numbers from "95-293,435-603"."""
    out = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        a, _, b = part.partition("-")
        a, b = int(a), int(b or a)
        if a < 1 or b < a:
            raise SystemExit("--lines: bad range %r" % part)
        out.update(range(a, b + 1))
    return sorted(out)


def read_md(md):
    """The Markdown file's path (as given, or in Sources/) and its lines, read as source_helpers.md_lines reads them."""
    path = md if os.path.exists(md) else os.path.join(source_helpers.SOURCES, md)
    if not os.path.exists(path):
        raise SystemExit("%s: not found" % md)
    with open(path, encoding="utf-8-sig") as f:
        return path, [ln.rstrip() for ln in f.read().splitlines()]


def skip_reasons(lines):
    """For each line, why it is not rebuilt (None if it is)."""
    out, fence = [], False
    for ln in lines:
        s = ln.strip()
        if s.startswith("```"):
            fence = not fence
            out.append("fence")
        elif fence:
            out.append("fence")
        elif not s:
            out.append("blank")
        elif s.startswith("|"):
            out.append("table")
        elif s.startswith("<!--") and s.endswith("-->"):
            out.append("comment")
        elif not any(c.isalnum() for c in s):
            out.append("no letters")
        else:
            out.append(None)
    return out


def gap_kinds(old, new):
    """What differs between docling's text and the PDF's in one gap between letters."""
    kinds = set()
    if old == new:
        return kinds
    if [c for c in old if c in QUOTES] != [c for c in new if c in QUOTES]:
        kinds.add("quotation marks")
    if [c for c in old if c in DASHES + "-"] != [c for c in new if c in DASHES + "-"]:
        kinds.add("dashes")
    if any(c.isspace() for c in old) != any(c.isspace() for c in new):
        kinds.add("spaces")
    rest = [re.sub(r"[\s\\*_" + QUOTES + DASHES + "-]", "", t) for t in (old, new)]
    if rest[0] != rest[1]:
        kinds.add("other punctuation")
    return kinds


class Stream:
    """The PDF's body text as one character stream, with its skeleton for searching."""

    def __init__(self, doc, layout):
        self.G = []
        for _, _, body, _ in PagedText(doc, layout).pages:
            for ln in body:
                self.G.extend(ln.glyphs)
                self.G.append(Glyph(BREAK, False, False, 0, 0, 0, 0, ln.page))
        skel, index, skel2, index2 = [], [], [], []
        for i, g in enumerate(self.G):
            for ch in keys(g.c):
                skel.append(ch)
                index.append(i)
                if not g.sup:
                    skel2.append(ch)
                    index2.append(i)
        # S: every letter and digit; S2: without superscripts (note numbers).
        self.S, self.SI = "".join(skel), index
        self.S2, self.SI2 = "".join(skel2), index2

    def locate(self, K, cursor, expect):
        """Where skeleton K is in the stream, searching from glyph cursor: (glyph per K char, how, piece starts) or None."""
        short = len(K) < LONG
        s0 = bisect.bisect_left(self.SI, cursor)
        p = self.S.find(K, s0, s0 + expect + len(K)) if short else self.S.find(K, s0)
        if p >= 0:
            return [self.SI[p + k] for k in range(len(K))], "found", set()
        t0 = bisect.bisect_left(self.SI2, cursor)
        p = self.S2.find(K, t0, t0 + expect + len(K)) if short else self.S2.find(K, t0)
        if p >= 0:
            return [self.SI2[p + k] for k in range(len(K))], "without note numbers", set()
        p = self.S.find(K, max(0, s0 - BACK), s0 + len(K) - 1)
        if p >= 0:
            return [self.SI[p + k] for k in range(len(K))], "out of order", set()
        got = self._pieces(K, s0, s0 + expect if short else None)
        if got:
            return got[0], "in pieces", got[1]
        return None

    def _pieces(self, K, s0, hi):
        """K matched in up to MAX_PIECES runs, each within SKIP of the last: (glyphs, K indexes where a run starts)."""
        pieces, k, at, tries = [], 0, s0, 0
        while k < len(K):
            if len(pieces) >= MAX_PIECES:
                return None
            seed = K[k:k + SEED]
            end = (hi if not pieces else at + SKIP)
            p = self.S.find(seed, at) if end is None else self.S.find(seed, at, end + len(seed))
            if p < 0:
                # The previous run may have run on into text that is not this line's.
                if pieces and tries < 3 and pieces[-1][2] > SEED:
                    pieces[-1][2] -= 1
                    k, at, tries = k - 1, at - 1, tries + 1
                    continue
                return None
            tries = 0
            m = len(seed)
            while k + m < len(K) and p + m < len(self.S) and self.S[p + m] == K[k + m]:
                m += 1
            pieces.append([k, p, m])
            k, at = k + m, p + m
        if len(pieces) < 2:
            return None
        pos = [self.SI[p + j] for _, p, m in pieces for j in range(m)]
        return pos, {k for k, _, _ in pieces[1:]}

    def leading_run(self, i):
        """The punctuation right before glyph i, back to a space, line end, or letter."""
        k = i
        while k > 0 and not self.G[k - 1].c.isspace() and not self.G[k - 1].c.isalnum():
            k -= 1
        return [g for g in self.G[k:i] if g.c not in BULLETS]

    def trailing_run(self, i):
        """The punctuation right after glyph i, up to a space, line end, or letter."""
        k = i + 1
        while k < len(self.G) and not self.G[k].c.isspace() and not self.G[k].c.isalnum():
            k += 1
        return self.G[i + 1:k]


def entries(glyphs):
    """PDF glyphs as (text, italic) pieces: one space for any space, "-" for a hyphen character, "*" and "_" escaped."""
    out = []
    for g in glyphs:
        c = g.c
        if c == "­":
            continue
        if c in HYPHENS:
            c = "-"
        elif c.isspace():
            c = " "
        elif c in "*_":
            c = "\\" + c
        out.append((c, g.italic and not g.sup))
    return out


def plain(text):
    return [(c, False) for c in text]


class Rebuilder:
    """Rebuilds docling lines from a PDF and keeps the counts for the report."""

    def __init__(self, doc, layout, ev):
        self.stream = Stream(doc, layout)
        self.layout, self.ev = layout, ev
        self.hyphens = []     # (line, stem, first, kept, basis)
        self.gaps = Counter()
        self.lines_with = Counter()

    def _hyphen(self, no, left, right):
        """Keep (True) or drop the hyphen at a PDF line end between left and right."""
        stem = re.search(r"[A-Za-z]*$", left).group(0)
        m = re.match(r"[a-z]+", right)
        if not stem or not m:
            return True   # a capital, digit, or other letter after the break: the hyphen belongs to the word
        sep, basis = hyphen_decision(stem, m.group(0), self.ev)
        self.hyphens.append((no, stem, m.group(0), sep == "-", basis))
        return sep == "-"

    def gap(self, no, glyphs, dl_gap, ga, gb, left, right):
        """The text between two letters: from the PDF's glyphs, or docling's spacing next to a superscript."""
        if ga is gb or ga.size >= DROP_CAP_FACTOR * gb.size:
            return plain(dl_gap)   # one glyph for two letters ("½"), or after a drop cap: the export's spacing stands
        glyphs = [g for g in glyphs if not g.c.isalnum()]
        if ga.sup or gb.sup:
            # The PDF's punctuation with docling's spacing: "turn.¹" exported
            # as "turn 1" gives "turn. 1".
            ink = [g for g in glyphs if not g.c.isspace()]
            if re.sub(r"\s", "", dl_gap) == "".join(g.c for g in ink):
                return plain(dl_gap)
            if not dl_gap.strip():
                space = plain(" ") if dl_gap else []
                return entries(ink) + space if gb.sup else space + entries(ink)
            return plain(" " if dl_gap[0].isspace() else "") + entries(ink) + plain(" " if dl_gap[-1].isspace() else "")
        breaks = [k for k, g in enumerate(glyphs) if g.c == BREAK]
        if not breaks:
            out = []
            for e in entries(glyphs):
                if not (e[0] == " " and out and out[-1][0] == " "):
                    out.append(e)
            return out
        before = glyphs[:breaks[0]]
        while before and before[-1].c.isspace():
            before.pop()
        after = glyphs[breaks[-1] + 1:]
        while after and after[0].c.isspace():
            after.pop(0)
        bt = "".join(g.c for g in before)
        if len(bt) == 1 and bt in HYPHENS and left[-1:].isalpha():
            keep = self._hyphen(no, left, right)
            return ([("-", before[0].italic)] if keep else []) + entries(after)
        closed = bt and bt[-1] in DASHES + HYPHENS and (len(bt) == 1 or not bt[-2].isspace())
        sep = [] if closed or bt.endswith("/") else [(" ", False)]
        return entries(before) + sep + entries(after)

    def rebuild(self, no, text, pos, cuts):
        """Line no's text rebuilt from the stream positions pos of its skeleton (cuts: where a new piece starts)."""
        G, st = self.stream.G, self.stream
        prefix = MD_PREFIX.match(text).group(0)
        body = md_entities(text[len(prefix):])
        units, kpos = [], 0
        for i, c in enumerate(body):
            k = keys(c)
            if k:
                units.append((i, pos[kpos], pos[kpos + len(k) - 1], kpos))
                kpos += len(k)
        kinds = set()

        def add(old, new):
            got = gap_kinds(old, "".join(t for t, _ in new))
            for kind in got:
                self.gaps[kind] += 1
            kinds.update(got)
            out.extend(new)

        out = []
        add(body[:units[0][0]], entries(st.leading_run(units[0][1])))
        for u, (i, first, last, kstart) in enumerate(units):
            if u:
                pi, _, a, _ = units[u - 1]
                if kstart in cuts:
                    glyphs = st.trailing_run(a) + [Glyph(BREAK, False, False, 0, 0, 0, 0)] + st.leading_run(first)
                else:
                    glyphs = G[a + 1:first]
                add(body[pi + 1:i], self.gap(no, glyphs, body[pi + 1:i], G[a], G[first],
                                             "".join(t for t, _ in out), body[i:]))
            out.append((body[i], G[first].italic and not G[first].sup))
        i, _, last, _ = units[-1]
        add(body[i + 1:], entries(st.trailing_run(last)))
        rebuilt = mark_italics(out) if self.layout.italics else "".join(t for t, _ in out)
        if len(MD_EMPHASIS.findall(body)) != len(MD_EMPHASIS.findall(rebuilt)):
            kinds.add("italics")
        for kind in kinds:
            self.lines_with[kind] += 1
        return prefix + rebuilt


def rebuild_lines(md, pdf, line_numbers, layout=None, hyphenates=None):
    """Rebuild the given lines of md from pdf; return (changed {line: text}, report dict)."""
    layout = layout or Layout()
    md_path, lines = read_md(md)
    bad = [n for n in line_numbers if not 1 <= n <= len(lines)]
    if bad:
        raise SystemExit("%s: lines %s are not in the file (1-%d)" % (md_path, ", ".join(map(str, bad[:5])), len(lines)))
    reasons = skip_reasons(lines)
    # Running count of skeleton characters, for how far a short line may be looked for.
    cum = [0]
    for ln, why in zip(lines, reasons):
        cum.append(cum[-1] + (0 if why else sum(len(keys(c)) for c in md_entities(ln))))
    with pymupdf.open(pdf_path(pdf)) as doc:
        ev = DocEvidence.from_doc(doc, hyphenates)
        rb = Rebuilder(doc, layout, ev)
    changed, how, skipped, unmatched = {}, {}, Counter(), []
    cursor, last_no = 0, 0
    for no in line_numbers:
        text = lines[no - 1]
        if reasons[no - 1]:
            skipped[reasons[no - 1]] += 1
            continue
        prefix = MD_PREFIX.match(text).group(0)
        body = md_entities(text[len(prefix):])
        if any(c.isalnum() and not keys(c) for c in body):
            unmatched.append((no, text, "a letter with no plain form"))
            continue
        K = "".join(keys(c) for c in body)
        expect = int(1.5 * (cum[no - 1] - cum[last_no])) + SLACK
        got = rb.stream.locate(K, cursor, expect)
        if got is None:
            unmatched.append((no, text, "not found"))
            continue
        pos, kind, cuts = got
        pages = sorted({rb.stream.G[p].page for p in (pos[0], pos[-1])})
        how[no] = (kind, pages, len(cuts) + 1)
        if kind != "out of order":
            cursor, last_no = max(cursor, pos[-1] + 1), no
        new = rb.rebuild(no, text, pos, cuts)
        if new != text:
            changed[no] = new
    report = {"md": md_path, "pdf": pdf_path(pdf), "lines": line_numbers, "skipped": skipped, "how": how,
              "unmatched": unmatched, "changed": changed, "gaps": rb.gaps, "lines_with": rb.lines_with,
              "hyphens": rb.hyphens, "hyphenates": ev.hyphenates}
    old = [md_entities(lines[n - 1]) for n in how]
    new = [md_entities(changed.get(n, lines[n - 1])) for n in how]
    report["counts"] = {name: tuple(sum(t.count(c) for t in texts for c in chars) for texts in (old, new))
                        for name, chars in (("straight quotation marks", "\"'"), ("curly quotation marks", CURLY),
                                            ("em dashes", "—"), ("en dashes", "–"), ("hyphens", "-"))}
    report["counts"]["italic runs"] = tuple(sum(len(MD_EMPHASIS.findall(t)) for t in texts) for texts in (old, new))
    return changed, report


def _ranges_text(numbers):
    out, start = [], None
    for i, n in enumerate(numbers):
        if start is None:
            start = n
        if i + 1 == len(numbers) or numbers[i + 1] != n + 1:
            out.append(str(start) if start == n else "%d-%d" % (start, n))
            start = None
    return ",".join(out)


def format_report(report, out_path=None):
    how = report["how"]
    kinds = Counter(k for k, _, _ in how.values())
    rows = ["%s, lines %s, against %s" % (report["md"], _ranges_text(report["lines"]), report["pdf"]),
            "  lines: %d in range, %d skipped (%s), %d matched (%s), %d not matched, %d changed%s"
            % (len(report["lines"]), sum(report["skipped"].values()),
               ", ".join("%s %d" % kv for kv in sorted(report["skipped"].items())) or "none",
               len(how), ", ".join("%s %d" % kv for kv in sorted(kinds.items())) or "none",
               len(report["unmatched"]), len(report["changed"]), " -> " + out_path if out_path else ""),
            "",
            "Differences in the matched lines (docling -> PDF):"]
    for name, (a, b) in report["counts"].items():
        rows.append("  %-26s %5d -> %d" % (name, a, b))
    for kind in ("quotation marks", "dashes", "spaces", "other punctuation", "italics"):
        if kind in report["lines_with"]:
            rows.append("  lines with changed %s: %d%s" % (kind, report["lines_with"][kind],
                                                           " (%d gaps)" % report["gaps"][kind] if kind in report["gaps"] else ""))
    hy = report["hyphens"]
    rows.append("  line-end hyphens before a lowercase letter: %d dropped, %d kept (document %s at line ends)"
                % (sum(not k for _, _, _, k, _ in hy), sum(k for _, _, _, k, _ in hy),
                   "breaks words" if report["hyphenates"] else "does not break words"))
    if report["unmatched"]:
        rows += ["", "Not matched (left as docling has them):"]
        rows += ["  MD %d: %s: %s" % (no, why, text[:90]) for no, text, why in report["unmatched"]]
    odd = [(no, h) for no, h in sorted(how.items()) if h[0] != "found"]
    if odd:
        rows += ["", "Matched another way (check against the page):"]
        rows += ["  MD %d: %s, PDF p. %s%s" % (no, kind, "-".join(map(str, pages)),
                                              ", %d pieces" % n if kind == "in pieces" else "")
                 for no, (kind, pages, n) in odd]
    uncertain = [h for h in hy if h[4].startswith("uncertain")]
    if uncertain:
        rows += ["", "Uncertain line-end hyphens (check against the page):"]
        rows += ["  MD %d: %s- / %s -> %s (%s)" % (no, stem, first, stem + ("-" if kept else "") + first, basis)
                 for no, stem, first, kept, basis in uncertain]
    return "\n".join(rows)


def write_rebuilt(path, changed):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({str(n): changed[n] for n in sorted(changed)}, f, ensure_ascii=False, indent=1)
        f.write("\n")


def main(argv):
    from common import utf8_output
    utf8_output()
    ap = argparse.ArgumentParser(description="Rebuild docling Markdown lines from the PDF's text layer, keeping every letter and digit.")
    ap.add_argument("--md", required=True, help="the docling Markdown: a path, or a file name in Sources/")
    ap.add_argument("--pdf", required=True, help="the PDF it was exported from: a path, or a file name in Sources/")
    ap.add_argument("--lines", required=True, help="Markdown line ranges to rebuild, A-B[,C-D]")
    ap.add_argument("--italic-font", help="regex on the font name that marks italics (default: the font flags)")
    ap.add_argument("--no-italics", action="store_true", help="mark no italics (a typography policy without them)")
    ap.add_argument("--superscript-max", type=float, help="type size (points) at or under which a character is a superscript")
    ap.add_argument("--header-ymax", type=float, help="lines wholly above this y (points) are running heads")
    ap.add_argument("--footer-ymin", type=float, help="lines wholly below this y (points) are footers")
    ap.add_argument("--artifact-gap", type=float, default=Layout.artifact_gap,
                    help="drop space glyphs with a smaller gap to their neighbours (points)")
    ap.add_argument("--hyphenates", choices=("auto", "yes", "no"), default="auto",
                    help="whether the book breaks words at line ends (auto: detected from the PDF)")
    ap.add_argument("--out", help="the JSON to write, Work/Proof/<slug>.rebuilt.json")
    ap.add_argument("--report", action="store_true", help="print what was matched, what was not, and the differences")
    args = ap.parse_args(argv)
    if not args.out and not args.report:
        ap.error("give --out, --report, or both")
    layout = Layout(args.header_ymax, args.footer_ymin, not args.no_italics, args.italic_font, args.superscript_max,
                    args.artifact_gap)
    hyphenates = {"auto": None, "yes": True, "no": False}[args.hyphenates]
    changed, report = rebuild_lines(args.md, args.pdf, parse_ranges(args.lines), layout, hyphenates)
    if args.out:
        write_rebuilt(args.out, changed)
    if args.report:
        print(format_report(report, args.out))
    else:
        print("%d lines changed -> %s (%d not matched; --report lists them)" % (len(changed), args.out,
                                                                              len(report["unmatched"])))


if __name__ == "__main__":
    main(sys.argv[1:])
