"""Check that Summary.pdf shows exactly the text of Summary.md.

Run from the project root (Work/build_pdf.py also runs it after every build):

    python Work/check_pdf_text.py [--md Summary.md] [--pdf Summary.pdf]

Text check. The Markdown's words, read with the renderer's own structure
rules (build_pdf.parse_lines: heading, quotation, and list markup removed;
the number of a numbered list item kept, because the browser prints it),
must equal the PDF's words, in order. The PDF text is extracted with
PyMuPDF, without the page numbers the build adds. Line breaks in the PDF:
- A word broken with a hyphen is joined without the hyphen only when the
  joined word occurs in the Markdown and the hyphenated form does not (a
  hyphen the layout inserted); otherwise the hyphen is real and stays.
- The browser can also break a line where the Markdown has no space, as in
  "[x]" / "(y)". The two pieces are joined when the joined form occurs in
  the Markdown and the pieces do not both occur there as words.
Whitespace is collapsed, soft hyphens and zero-width spaces are dropped,
ligature characters are expanded, and words are also split after hyphens
and slashes and around en and em dashes, where the browser may break a line
without a space. Every difference is reported with the words around it, its
Summary.md line, and its PDF page. A difference in spacing only (the same
characters with spaces in different places) is a text-extraction artifact,
not a rendering change, and is listed as a warning.

Structural checks: blank pages, U+FFFD characters, every `#` and `##`
heading present, and no leftover `Work/`, `.md`, `<!--`, or page-reference
strings. Pages with very little text (other than the last) are listed as
warnings for visual inspection.

Exits 1 on any difference or failed check.
"""
import argparse
import re
import sys

import pymupdf

from build_pdf import MD, PDF, parse_lines

SYNC = 6        # equal words needed to realign after a difference
WINDOW = 400    # how far ahead (in words) to look for realignment
CONTEXT = 8     # words of context shown on each side of a difference
SHOWN = 40      # most differing words shown per difference
THIN_WORDS = 25

_DROP = {0x00AD: None, 0x200B: None, 0x200C: None, 0x200D: None, 0x2060: None, 0xFEFF: None}
_LIGATURES = {0xFB00: "ff", 0xFB01: "fi", 0xFB02: "fl", 0xFB03: "ffi", 0xFB04: "ffl",
              0xFB05: "st", 0xFB06: "st"}
_CLEAN = {**_DROP, **_LIGATURES}
_DASH = re.compile(r"([\u2013\u2014\u2015])")
_BREAK_AFTER = re.compile(r"([-\u2010/])")
_LINE_HYPHENS = ("-", "\u2010")

LEFTOVERS = [
    (re.compile(r"Work/"), "working-file path"),
    (re.compile(r"\.md\b"), ".md reference"),
    (re.compile(r"<!--"), "HTML comment"),
    (re.compile(r"\bpp?\. ?\d+|\bpages? \d+|\(p\. ?\d+"), "page reference"),
]


def clean(text):
    return text.translate(_CLEAN)


def tokens(text):
    """Comparison words of a cleaned string."""
    text = _BREAK_AFTER.sub(r"\1 ", _DASH.sub(r" \1 ", text))
    return text.split()


def markdown_words(md_text):
    """(words, line numbers, headings) for Summary.md text.

    headings is a list of (line number, level marker, words) for `#` and `##`.
    """
    words, where, headings = [], [], []
    for line in parse_lines(md_text):
        if line.kind in ("blank", "separator"):
            continue
        text = clean(line.text)
        if line.kind == "item" and line.number is not None:
            text = "%d. %s" % (line.number, text)
        toks = tokens(text)
        words.extend(toks)
        where.extend([line.lineno] * len(toks))
        if line.kind == "heading" and line.marker in ("#", "##"):
            headings.append((line.lineno, line.marker, tokens(clean(line.text))))
    return words, where, headings


def pdf_lines(doc):
    """[(page number, line text)] for every text line, without the added page numbers.

    Also returns the pages' word counts for the blank/thin checks.
    """
    flags = pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP
    lines, counts = [], []
    for pno, page in enumerate(doc, 1):
        bottom = page.rect.height - 72  # the build's page numbers sit in the bottom margin
        page_lines = []
        for block in page.get_text("dict", flags=flags)["blocks"]:
            for line in block.get("lines", []):
                text = "".join(span["text"] for span in line["spans"])
                page_lines.append((line["bbox"][1], text))
        numbered = [k for k, (y, t) in enumerate(page_lines) if t.strip() == str(pno) and y > bottom]
        if numbered:
            del page_lines[numbered[-1]]
        counts.append(sum(len(t.split()) for _, t in page_lines))
        lines.extend((pno, t) for _, t in page_lines)
    return lines, counts


def join_line_breaks(lines, md_vocab):
    """Join words the layout broke across lines. lines: [(page, text)], cleaned.

    md_vocab is the set of the Markdown's whitespace-separated words.
    """
    lines = [list(item) for item in lines]
    for k in range(len(lines) - 1):
        text = lines[k][1].rstrip()
        nxt = lines[k + 1][1].lstrip()
        if not text.split() or not nxt.split():
            continue
        left, right = text.split()[-1], nxt.split()[0]
        if (text.endswith(_LINE_HYPHENS) and left[:-1] + right in md_vocab
                and left + right not in md_vocab):
            lines[k][1] = text[:-1] + right  # a hyphen the layout inserted
        elif left + right in md_vocab and not (left in md_vocab and right in md_vocab):
            lines[k][1] = text + right  # a break where the Markdown has no space
        else:
            continue
        lines[k + 1][1] = nxt[len(right):]
    return [tuple(item) for item in lines]


def pdf_words(lines, md_text):
    """(words, page numbers) from pdf_lines() output."""
    vocab = set(clean(md_text).split())
    joined = []  # a soft hyphen at a line end always joins the word
    for page, text in lines:
        if joined and joined[-1][1].rstrip().endswith("\u00ad"):
            prev_page, prev = joined[-1]
            joined[-1] = (prev_page, prev.rstrip()[:-1] + text.lstrip())
        else:
            joined.append((page, text))
    words, where = [], []
    for page, text in join_line_breaks([(p, clean(t)) for p, t in joined], vocab):
        toks = tokens(text)
        words.extend(toks)
        where.extend([page] * len(toks))
    return words, where


def _resync(a, b, i, j):
    """Smallest (da, db) with a[i+da:] and b[j+db:] equal for SYNC words (or to the end)."""
    index = {}
    for db in range(min(WINDOW, len(b) - j) + 1):
        index.setdefault(tuple(b[j + db:j + db + SYNC]), db)
    best = None
    for da in range(min(WINDOW, len(a) - i) + 1):
        db = index.get(tuple(a[i + da:i + da + SYNC]))
        if db is not None and (best is None or da + db < sum(best)):
            best = (da, db)
    return best


def compare(expected, found):
    """Differences between two word lists, as (i0, i1, j0, j1) spans.

    expected[i0:i1] stands where found[j0:j1] is. Aligns greedily and
    realigns after each difference on the nearest run of SYNC equal words.
    """
    diffs, i, j = [], 0, 0
    while i < len(expected) or j < len(found):
        if i < len(expected) and j < len(found) and expected[i] == found[j]:
            i += 1
            j += 1
            continue
        step = _resync(expected, found, i, j)
        if step is None:
            diffs.append((i, len(expected), j, len(found)))
            break
        diffs.append((i, i + step[0], j, j + step[1]))
        i, j = i + step[0], j + step[1]
    return diffs


def _show(words, a, b):
    part = words[a:b]
    if len(part) > SHOWN:
        part = part[:SHOWN // 2] + ["..."] + part[-SHOWN // 2:]
    return " ".join(part)


def describe(diff, md_words, md_lines, pdf_wds, pdf_pages):
    i0, i1, j0, j1 = diff
    line = md_lines[min(i0, len(md_lines) - 1)] if md_lines else 0
    page = pdf_pages[min(j0, len(pdf_pages) - 1)] if pdf_pages else 0
    before = _show(md_words, max(0, i0 - CONTEXT), i0)
    after = _show(md_words, i1, i1 + CONTEXT)
    return ("Summary.md line %d, PDF page %d:\n"
            "    context:  %s [...] %s\n"
            "    Markdown: [%s]\n"
            "    PDF:      [%s]" % (line, page, before, after,
                                    _show(md_words, i0, i1), _show(pdf_wds, j0, j1)))


def check(md_path=MD, pdf_path=PDF):
    """Run every check, print the results, and return True if all pass."""
    with open(md_path, "r", encoding="utf-8") as fh:
        md_text = fh.read()
    doc = pymupdf.open(pdf_path)
    try:
        raw = "".join(page.get_text() for page in doc)
        lines, counts = pdf_lines(doc)
    finally:
        doc.close()

    problems, warnings = [], []
    for pno, n in enumerate(counts, 1):
        if n == 0:
            problems.append("page %d is blank" % pno)
        elif n < THIN_WORDS and pno < len(counts):
            warnings.append("page %d has only %d words (inspect it)" % (pno, n))
    if "\ufffd" in raw:
        problems.append("%d U+FFFD replacement character(s) in the PDF text" % raw.count("\ufffd"))

    md_wds, md_lines, headings = markdown_words(md_text)
    pdf_wds, pdf_pages = pdf_words(lines, md_text)
    joined = " %s " % " ".join(pdf_wds)
    for lineno, marker, words in headings:
        if " %s " % " ".join(words) not in joined:
            problems.append("heading missing from the PDF (Summary.md line %d): %s %s"
                            % (lineno, marker, " ".join(words)))
    flat = " ".join(t for _, t in lines)
    for pattern, label in LEFTOVERS:
        for m in pattern.finditer(flat):
            problems.append("leftover %s in the PDF: %r" % (label, flat[max(0, m.start() - 30):m.end() + 30]))

    diffs = 0
    for d in compare(md_wds, pdf_wds):
        i0, i1, j0, j1 = d
        if "".join(md_wds[i0:i1]) == "".join(pdf_wds[j0:j1]):
            warnings.append("spacing differs (text extraction) at "
                            + describe(d, md_wds, md_lines, pdf_wds, pdf_pages))
        else:
            diffs += 1
            problems.append("text differs at " + describe(d, md_wds, md_lines, pdf_wds, pdf_pages))

    print("check_pdf_text: %s: %d pages, %d words (Markdown: %d words)"
          % (pdf_path, len(counts), len(pdf_wds), len(md_wds)))
    for w in warnings:
        print("  warning: %s" % w)
    if problems:
        print("check_pdf_text: FAILED, %d problem(s), %d text difference(s):" % (len(problems), diffs))
        for p in problems:
            print("  " + p)
        return False
    print("check_pdf_text: OK: the PDF text matches the Markdown word for word")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--md", default=MD, help="Markdown file (default: Summary.md)")
    parser.add_argument("--pdf", default=PDF, help="PDF file (default: Summary.pdf)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")  # report any character on any console
    if not check(args.md, args.pdf):
        sys.exit(1)


if __name__ == "__main__":
    main()
