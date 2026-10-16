"""Write a paged text file from a PDF's text layer, for a paged TXT source (build_txt).

extract.py's PDF route takes whole pages. A source whose units start and
end mid-page, or whose docling export is too damaged to repair line by
line, is extracted in TXT mode instead, from a paged text the project
writes from the PDF: one form feed per PDF page (piece k = PDF page k),
with the page layout turned into the marks TXT mode reads. A config uses
it as its build_txt callable, with "paragraphs": "blank_lines":

    from pdf_to_paged_txt import FURNITURE_PATTERNS, paged_txt_builder

    CONFIG = {
        "slug": "penhale-grey-harbour",
        "txt": "Work/Raw/penhale-grey-harbour/paged.txt",
        "build_txt": paged_txt_builder("penhale-grey-harbour.pdf", header_ymax=52, footer_ymin=600),
        "paragraphs": "blank_lines",
        "header_patterns": FURNITURE_PATTERNS,
        "footer_patterns": FURNITURE_PATTERNS,
        ...
    }

What each page holds (every rule reads the PDF's own layout):

- Each line as the text layer gives it, with artifact spaces dropped: a
  space glyph whose gap to its neighbours is under artifact_gap points
  (the split points some text layers put inside words, "offi cial"), and
  a space before a line-final hyphen. A run of spaces is one space;
  ligatures are spelt out.
- A blank line before each block: a line set further right than the line
  before (a first-line indent, the start of an indented quotation), one
  set further left than the run-on lines of its block (the end of an
  indented quotation), a change of type size, or a vertical gap wider
  than gap_factor times the line spacing. Lines beside a drop cap
  continue its paragraph. On hanging_pages (notes set with a hanging
  indent) a block starts at a line set further left than the line before
  instead.
- Running heads (lines wholly above header_ymax), footers (wholly below
  footer_ymin), sideways text, and bare folios (a page number alone as
  the page's first or last line, near the edge) prefixed "@@furniture ",
  heads first and the rest at the page foot, so header_patterns and
  footer_patterns (FURNITURE_PATTERNS) drop each one, logged in
  repairs.tsv as furniture-dropped. A page with more of them at one end
  than header_scan (default 8) needs a larger header_scan.
- Italic runs marked *...* (italics=False leaves them plain): characters
  whose font name matches italic_font (a regex), or by default whose font
  flags say italic. Spaces and superscripts stay outside a run, and a run
  that goes on over a line end is marked as one run (opened on the first
  line, closed on the second), so TXT mode joins it whole.
- A line ending in a closed dash ("quay—" / "and the boats") takes the
  next line's first word, which TXT mode would otherwise join with a
  space.

Superscript note numbers stay as printed (digits after the punctuation),
and line-end hyphens are left for TXT mode to decide (plan.md, Step 2).
The build summary lists the pages whose first line runs a paragraph on
(not indented) after a page that ends a sentence: TXT mode starts a new
paragraph there unless move_run_on moves that last line to the next page.

Run as a script to write the file, or to print the layout of some pages
(each line's position, size, share of italics, text, and fonts) when
choosing header_ymax, footer_ymin, italic_font, and the gap settings:

    python Work/pdf_to_paged_txt.py --pdf <file> --out Work/Raw/<slug>/paged.txt [options]
    python Work/pdf_to_paged_txt.py --pdf <file> --layout 12-14
"""
import argparse
import os
import re
import statistics
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass

import pymupdf

from extract import LIGATURES, PAGE_NUM_ZONE, is_open_ended

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = os.path.join(ROOT, "Sources")

FURNITURE = "@@furniture "
# header_patterns and footer_patterns for a paged text written here.
FURNITURE_PATTERNS = [r"^@@furniture "]
# A space glyph with less than this gap (points) between its neighbours'
# ink is a split point of the text layer, not a word space. Real word gaps
# are rarely under 1 pt; calibrate against the source when in doubt.
ARTIFACT_GAP = 0.3
# A vertical step between baselines wider than this times the line spacing
# of that type size starts a block.
GAP_FACTOR = 1.2
# Lines whose type sizes differ by this much (points) are in different blocks.
SIZE_STEP = 0.5
# A note reference is set smaller than its line's type and raised above its
# baseline, by at least these fractions of the type size.
SUPERSCRIPT_SHRINK = 0.8
SUPERSCRIPT_RISE = 0.2
# A drop cap is one or two characters at least this many times the size of
# the line beside it.
DROP_CAP_FACTOR = 1.8
HYPHENS = "-­‐‑"
FOLIO = re.compile(r"^[\[(\-–— ]*(?:\d{1,4}|[ivxlcdm]{1,7})[\])\-–— ]*$", re.I)
CLOSED_DASH_END = re.compile(r"\S[—–]$")


@dataclass
class Layout:
    """How the characters of a PDF are read (shared with rebuild_from_pdf.py)."""
    header_ymax: float = None    # lines wholly above are running heads
    footer_ymin: float = None    # lines wholly below are footers
    italics: bool = True         # mark italic runs *...*
    italic_font: str = None      # regex on the font name; None: the font flags decide
    superscript_max: float = None  # characters this size or smaller are superscripts; None: shape decides
    artifact_gap: float = ARTIFACT_GAP
    keep_order: bool = False     # keep the text layer's line order instead of top to bottom


class Glyph:
    """One character of a line, with what the PDF says about it."""
    __slots__ = ("c", "italic", "sup", "size", "x0", "x1", "y", "page", "font")

    def __init__(self, c, italic, sup, size, x0, x1, y, page=0, font=""):
        self.c, self.italic, self.sup, self.size = c, italic, sup, size
        self.x0, self.x1, self.y, self.page, self.font = x0, x1, y, page, font


class Line:
    """One text line: its glyphs (artifact spaces dropped), ink edges, baseline, and type size."""
    __slots__ = ("glyphs", "x0", "x1", "y0", "y1", "base", "size", "rotated", "page")

    def __init__(self, glyphs, x0, x1, y0, y1, base, size, rotated, page):
        self.glyphs, self.x0, self.x1, self.y0, self.y1 = glyphs, x0, x1, y0, y1
        self.base, self.size, self.rotated, self.page = base, size, rotated, page

    def text(self, italics=True):
        return line_text(self.glyphs, italics)


def pdf_path(name):
    """A PDF named by path, or by file name in Sources/."""
    return name if os.path.exists(name) else os.path.join(SOURCES, name)


def _is_italic(span, layout):
    if layout.italic_font:
        return re.search(layout.italic_font, span["font"]) is not None
    return bool(span["flags"] & pymupdf.TEXT_FONT_ITALIC)


def line_glyphs(line, layout, page_no=0, stats=None):
    """A rawdict line's glyphs, its type size, and its baseline; None if it has no ink.

    Ligatures are spelt out, a separate combining accent is composed with
    its letter, superscripts are marked (see Layout.superscript_max), and
    artifact spaces are dropped (see the module docstring).
    """
    raw = []
    for s in line["spans"]:
        italic = _is_italic(s, layout)
        flagged = bool(s["flags"] & pymupdf.TEXT_FONT_SUPERSCRIPT)
        for ch in s["chars"]:
            c = ch["c"]
            if unicodedata.combining(c) and raw:
                composed = unicodedata.normalize("NFC", raw[-1].c + c)
                if len(composed) == 1:
                    raw[-1].c = composed
                    continue
            x0, _, x1, _ = ch["bbox"]
            parts = LIGATURES.get(c, c)
            w = (x1 - x0) / len(parts)
            for k, p in enumerate(parts):
                raw.append(Glyph(p, italic, flagged, s["size"], x0 + k * w, x0 + (k + 1) * w, ch["origin"][1], page_no,
                                 s["font"]))
    ink = [g for g in raw if not g.c.isspace()]
    if not ink:
        return None
    size = statistics.median_low([g.size for g in ink])
    base = statistics.median_low([g.y for g in ink if abs(g.size - size) < 0.5])
    for g in ink:
        if layout.superscript_max is not None:
            g.sup = g.size <= layout.superscript_max
        else:
            g.sup = g.sup or (g.size <= SUPERSCRIPT_SHRINK * size and g.y < base - SUPERSCRIPT_RISE * size)
    out = []
    for i, g in enumerate(raw):
        if not g.c.isspace():
            out.append(g)
            continue
        if not out or out[-1].c == " ":
            continue
        j = next((k for k in range(i + 1, len(raw)) if not raw[k].c.isspace()), None)
        if j is None:
            continue
        nxt = raw[j]
        line_final_hyphen = (nxt.c in HYPHENS and out[-1].c.isalpha()
                             and all(raw[k].c.isspace() for k in range(j + 1, len(raw))))
        if nxt.x0 - out[-1].x1 < layout.artifact_gap or line_final_hyphen:
            if stats is not None:
                stats["artifact spaces dropped"] += 1
            continue
        g.c = " "
        out.append(g)
    return out, size, base


def page_lines(page, layout, stats=None):
    """The page's text lines (Line), top to bottom unless layout.keep_order."""
    lines = []
    for b in page.get_text("rawdict")["blocks"]:
        if b.get("type", 0) != 0:
            continue
        for ln in b["lines"]:
            got = line_glyphs(ln, layout, page.number + 1, stats)
            if got is None:
                continue
            glyphs, size, base = got
            ink = [g for g in glyphs if g.c != " "]
            rotated = (round(ln["dir"][0], 3), round(ln["dir"][1], 3)) != (1.0, 0.0)
            lines.append(Line(glyphs, min(g.x0 for g in ink), max(g.x1 for g in ink), ln["bbox"][1], ln["bbox"][3],
                              base, size, rotated, page.number + 1))
    if not layout.keep_order:
        lines.sort(key=lambda ln: (round(ln.base), ln.x0))
        _drop_caps_first(lines)
    return lines


def _drop_caps_first(lines):
    """Put each drop cap before the lines set beside it: by baseline it sorts after the first of them."""
    for cap in list(lines):
        ink = [g for g in cap.glyphs if g.c != " "]
        if len(ink) > 2 or not any(g.c.isalpha() for g in ink):
            continue
        beside = [j for j, ln in enumerate(lines) if ln is not cap and ln.x0 >= cap.x1 - 1
                  and cap.y0 <= ln.base <= cap.y1 and DROP_CAP_FACTOR * ln.size <= cap.size]
        if beside and min(beside) < lines.index(cap):
            lines.remove(cap)
            lines.insert(min(beside), cap)


def classify(page, lines, layout):
    """Split a page's lines into (running heads, body, foot furniture)."""
    top, body, bottom = [], [], []
    for ln in lines:
        if ln.rotated:
            bottom.append(ln)
        elif layout.header_ymax is not None and ln.y1 <= layout.header_ymax:
            top.append(ln)
        elif layout.footer_ymin is not None and ln.y0 >= layout.footer_ymin:
            bottom.append(ln)
        else:
            body.append(ln)
    zone = PAGE_NUM_ZONE * page.rect.height
    if body and FOLIO.match(body[0].text(False)) and body[0].y1 <= page.rect.y0 + zone:
        top.append(body.pop(0))
    if body and FOLIO.match(body[-1].text(False)) and body[-1].y0 >= page.rect.y1 - zone:
        bottom.insert(0, body.pop())
    return top, body, bottom


def line_text(glyphs, italics=True):
    """The text of glyphs, with italic runs marked *...* when italics is set."""
    if not italics:
        return "".join(g.c for g in glyphs).strip()
    return mark_italics([(g.c, g.italic and not g.sup) for g in glyphs]).strip()


def mark_italics(pieces):
    """Join (text, italic) pieces, wrapping each italic run in *...*.

    Spaces never start or end a run, and a run without a letter or digit
    (an italic comma) is left plain.
    """
    out, i, n = [], 0, len(pieces)
    while i < n:
        text, italic = pieces[i]
        if not italic or text.isspace():
            out.append(text)
            i += 1
            continue
        j = last = i
        while j < n and (pieces[j][1] or pieces[j][0].isspace()):
            if not pieces[j][0].isspace():
                last = j
            j += 1
        run = "".join(t for t, _ in pieces[i:last + 1])
        out.append("*%s*" % run if any(c.isalnum() for c in run) else run)
        i = last + 1
    return "".join(out)


def _ranges(spec):
    """PDF page numbers from "3-5,9"."""
    pages = set()
    for part in str(spec).split(","):
        part = part.strip()
        if part:
            a, _, b = part.partition("-")
            pages.update(range(int(a), int(b or a) + 1))
    return pages


class PagedText:
    """A PDF's pages rendered as paged text (see the module docstring)."""

    def __init__(self, doc, layout=None, gap_factor=GAP_FACTOR, indent=None, hanging_pages=(), size_step=SIZE_STEP):
        self.doc = doc
        self.layout = layout or Layout()
        self.gap_factor, self.indent, self.size_step = gap_factor, indent, size_step
        self.hanging = set(hanging_pages)
        self.stats = Counter()
        self.pages = []   # (page, heads, body, foot) per page
        for page in doc:
            lines = page_lines(page, self.layout, self.stats)
            self.pages.append((page,) + classify(page, lines, self.layout))
        self.pitch = self._pitches()
        sizes = Counter(round(ln.size * 2) / 2 for _, _, body, _ in self.pages for ln in body)
        self.body_size = sizes.most_common(1)[0][0] if sizes else 0
        # The usual left margin of body lines on odd and on even pages (most lines start there).
        self.margin = {}
        for parity in (0, 1):
            xs = Counter(round(ln.x0) for no, (_, _, body, _) in enumerate(self.pages, 1) if no % 2 == parity
                         for ln in body if abs(ln.size - self.body_size) < self.size_step)
            if xs:
                self.margin[parity] = xs.most_common(1)[0][0]

    def _pitches(self):
        """Median baseline step between consecutive body lines, per type size (half points)."""
        steps = {}
        for _, _, body, _ in self.pages:
            for a, b in zip(body, body[1:]):
                if abs(a.size - b.size) < self.size_step and 0 < b.base - a.base < 3 * a.size:
                    steps.setdefault(round(a.size * 2) / 2, []).append(b.base - a.base)
        return {k: statistics.median(v) for k, v in steps.items() if len(v) >= 2}

    def _indent(self, ln):
        return self.indent if self.indent is not None else max(3.0, 0.5 * ln.size)

    def _drop_cap(self, body, k):
        """True if body[k] is a drop cap: one or two characters far larger than the line beside it."""
        ln = body[k]
        ink = [g for g in ln.glyphs if g.c != " "]
        if len(ink) > 2 or not any(g.c.isalpha() for g in ink) or k + 1 >= len(body):
            return False
        nxt = body[k + 1]
        return ln.size >= DROP_CAP_FACTOR * nxt.size and ln.y0 - nxt.size <= nxt.base <= ln.y1 + nxt.size

    def body_rows(self, no):
        """Rows of PDF page no's body: text lines with "" between blocks."""
        _, _, body, _ = self.pages[no - 1]
        italics = self.layout.italics
        hanging = no in self.hanging
        rows, block, block_x = [], [], None
        prev = prev_x = cap = None
        for k, ln in enumerate(body):
            if cap is not None and ln.base > cap.y1 + 0.5 * ln.size:
                cap = None
            x = cap.x0 if cap is not None else ln.x0
            if prev is None:
                new = False
            elif prev is cap:
                new = False
            else:
                step = ln.base - prev.base
                ind = self._indent(ln)
                pitch = self.pitch.get(round(prev.size * 2) / 2, 1.2 * prev.size)
                new = (abs(ln.size - prev.size) >= self.size_step
                       or step > self.gap_factor * pitch or step < -0.5 * ln.size
                       or (not hanging and x - prev_x >= ind)
                       or (hanging and prev_x - x >= ind)
                       or (not hanging and len(block) >= 2 and x <= block_x - ind))
            if new:
                rows.append("")
                block = []
            block.append(ln)
            if len(block) == 2:
                block_x = x
            rows.append(ln.text(italics))
            if self._drop_cap(body, k):
                cap = ln
            prev, prev_x = ln, x
        # An italic run broken by a line end: "*The True*" / "*Story*" -> one run.
        for i in range(len(rows) - 1):
            a, b = rows[i], rows[i + 1]
            if a.endswith("*") and b.startswith("*") and not a.endswith("\\*"):
                rows[i], rows[i + 1] = a[:-1], b[1:]
        # A closed dash ending a line takes the next line's first word.
        for i in range(len(rows) - 1):
            a, b = rows[i], rows[i + 1]
            if a and b and CLOSED_DASH_END.search(a):
                first, _, rest = b.partition(" ")
                rows[i], rows[i + 1] = a + first, rest
                self.stats["dash joins"] += 1
                if not rest:
                    rows[i + 1] = None
        return [r for r in rows if r is not None]

    def runs_on(self, no):
        """True if page no's first body line continues a paragraph: body type, not indented."""
        _, _, body, _ = self.pages[no - 1]
        if not body or abs(body[0].size - self.body_size) >= self.size_step:
            return False
        # The page's left margin: the leftmost position at least two body lines
        # start at, or on a page with fewer lines, the usual one for its side.
        lefts = Counter(round(ln.x0) for ln in body if abs(ln.size - body[0].size) < self.size_step)
        left = min((x for x, n in lefts.items() if n >= 2), default=self.margin.get(no % 2))
        return left is not None and body[0].x0 < left + self._indent(body[0])

    def render(self, move_run_on=False):
        """Each page's text (rows joined, ending in a newline), and a summary."""
        italics = self.layout.italics
        bodies = [self.body_rows(no) for no in range(1, len(self.pages) + 1)]
        run_on, moved = [], []
        for no in range(2, len(self.pages) + 1):
            prev = bodies[no - 2]
            last = next((i for i in range(len(prev) - 1, -1, -1) if prev[i]), None)
            if last is None or not bodies[no - 1] or not self.runs_on(no):
                continue
            if is_open_ended(prev[last].rstrip("*")):
                continue
            run_on.append(no)
            # Only a line of body type moves: a footnote ending the page stays there.
            prev_body = self.pages[no - 2][2]
            if move_run_on and abs(prev_body[-1].size - self.body_size) < self.size_step:
                line = prev.pop(last)
                while prev and not prev[-1]:
                    prev.pop()
                bodies[no - 1].insert(0, line)
                moved.append((no - 1, line))
        texts, furniture_max = [], 0
        for (page, heads, _, foot), rows in zip(self.pages, bodies):
            out = [FURNITURE + ln.text(italics) for ln in heads] + rows + [FURNITURE + ln.text(italics) for ln in foot]
            furniture_max = max(furniture_max, len(heads), len(foot))
            self.stats["furniture lines"] += len(heads) + len(foot)
            self.stats["blocks"] += sum(1 for i, r in enumerate(rows) if r and (i == 0 or not rows[i - 1]))
            self.stats["italic runs"] += sum(len(re.findall(r"(?<!\\)\*", r)) for r in rows) // 2
            texts.append("\n".join(out) + "\n" if out else "")
        summary = {"pages": len(texts), "furniture at one page end (most)": furniture_max,
                   "run-on pages": run_on, "moved": moved}
        summary.update(self.stats)
        return texts, summary

    def layout_rows(self, no):
        """Page no's lines with their geometry and fonts, for choosing the settings."""
        page, heads, body, foot = self.pages[no - 1]
        rows = ["page %d (%.0f x %.0f pt)" % (no, page.rect.width, page.rect.height)]
        for kind, lines in (("head", heads), ("", body), ("foot", foot)):
            for ln in lines:
                ink = [g for g in ln.glyphs if g.c != " "]
                ital = sum(g.italic for g in ink) / len(ink)
                fonts = ",".join(sorted({g.font for g in ink}))
                rows.append("  y %6.1f-%6.1f  base %6.1f  x %6.1f-%6.1f  size %5.2f  ital %3.0f%%  %-4s  %s  [%s]"
                            % (ln.y0, ln.y1, ln.base, ln.x0, ln.x1, ln.size, 100 * ital, kind, ln.text(True), fonts))
        return rows


def write_paged_txt(pdf, out, layout=None, move_run_on=False, **options):
    """Write the paged text of pdf (a path, or a file name in Sources/) to out; return the build summary.

    options go to PagedText: gap_factor, indent, hanging_pages, size_step.
    """
    with pymupdf.open(pdf_path(pdf)) as doc:
        texts, summary = PagedText(doc, layout, **options).render(move_run_on)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(t + "\f" for t in texts))
    os.replace(tmp, out)
    return summary


def format_summary(summary):
    parts = ["%d pages" % summary["pages"]]
    parts += ["%s %d" % (k, v) for k, v in summary.items() if isinstance(v, int) and k != "pages"]
    lines = [", ".join(parts)]
    if summary["run-on pages"]:
        lines.append("pages whose first line runs a paragraph on after a page ending a sentence"
                     " (TXT mode starts a new paragraph unless move_run_on): %s"
                     % ", ".join(map(str, summary["run-on pages"])))
    for no, line in summary["moved"]:
        lines.append("moved from p. %d to p. %d: %s" % (no, no + 1, line))
    return "\n".join(lines)


def paged_txt_builder(pdf, move_run_on=False, gap_factor=GAP_FACTOR, indent=None, hanging_pages=(),
                      size_step=SIZE_STEP, **layout):
    """A build_txt callable for a config: writes the paged text of pdf to the path it is given.

    layout takes the Layout fields (header_ymax, footer_ymin, italics,
    italic_font, superscript_max, artifact_gap, keep_order). Nothing is
    read until the callable runs, so a config can call this at import.
    """
    lay = Layout(**layout)

    def build(path):
        summary = write_paged_txt(pdf, path, lay, move_run_on, gap_factor=gap_factor, indent=indent,
                                  hanging_pages=hanging_pages, size_step=size_step)
        print("  " + format_summary(summary).replace("\n", "\n  "))

    return build


def main(argv):
    from common import utf8_output
    utf8_output()
    ap = argparse.ArgumentParser(description="Write a paged text (one form feed per PDF page) from a PDF's text layer.")
    ap.add_argument("--pdf", required=True, help="the PDF: a path, or a file name in Sources/")
    ap.add_argument("--out", help="the paged text to write (Work/Raw/<slug>/paged.txt)")
    ap.add_argument("--layout", metavar="PAGES", help="print each line's geometry for these PDF pages (3-5,9) instead")
    ap.add_argument("--header-ymax", type=float, help="lines wholly above this y (points) are running heads")
    ap.add_argument("--footer-ymin", type=float, help="lines wholly below this y (points) are footers")
    ap.add_argument("--no-italics", action="store_true", help="leave italic runs unmarked")
    ap.add_argument("--italic-font", help="regex on the font name that marks italics (default: the font flags)")
    ap.add_argument("--superscript-max", type=float, help="type size (points) at or under which a character is a superscript")
    ap.add_argument("--artifact-gap", type=float, default=ARTIFACT_GAP, help="drop space glyphs with a smaller gap (points)")
    ap.add_argument("--gap-factor", type=float, default=GAP_FACTOR, help="a baseline step this many line spacings starts a block")
    ap.add_argument("--indent", type=float, help="indent (points) that starts a block (default: half the type size)")
    ap.add_argument("--hanging-pages", default="", help="PDF pages set with hanging indents (3-5,9)")
    ap.add_argument("--move-run-on", action="store_true", help="move a page's last line to the next page where the paragraph runs on")
    ap.add_argument("--keep-order", action="store_true", help="keep the text layer's line order")
    args = ap.parse_args(argv)
    layout = Layout(args.header_ymax, args.footer_ymin, not args.no_italics, args.italic_font, args.superscript_max,
                    args.artifact_gap, args.keep_order)
    options = {"gap_factor": args.gap_factor, "indent": args.indent, "hanging_pages": _ranges(args.hanging_pages)}
    if args.layout:
        with pymupdf.open(pdf_path(args.pdf)) as doc:
            paged = PagedText(doc, layout, **options)
            for no in sorted(_ranges(args.layout)):
                print("\n".join(paged.layout_rows(no)))
        return
    if not args.out:
        ap.error("give --out, or --layout to inspect pages")
    summary = write_paged_txt(args.pdf, args.out, layout, args.move_run_on, **options)
    print("paged text -> %s\n%s" % (args.out, format_summary(summary)))


if __name__ == "__main__":
    main(sys.argv[1:])
