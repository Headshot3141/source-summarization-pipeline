"""Helpers for the per-source config files in Work/SourceConfigs/.

A config file imports what it needs from here (from source_helpers import
build_line_edits); extract.py puts Work/ on the import path when it loads
them. A config never reads a file when it is imported, so every helper that
reads the source is called from a zero-argument callable that extract.py
resolves only for the sources it extracts (resolve_config):

    "line_edits": lambda: build_line_edits(MD, quotes=[212, 214]),

Line-numbered edits (line_edits) replace line_fixes keyed by text when a
repair belongs to one line of a docling Markdown file: a line number names
the place exactly, even where the same text occurs twice, and each helper
checks that the line still holds what the edit expects, so a re-exported
file stops the run instead of being edited in the wrong place. Lines
Work/rebuild_from_pdf.py rebuilt from the PDF come in through
build_line_edits(MD, rebuilt=rebuilt_lines(SLUG)).

Run as a script to write a proofreading listing (see passes/proofread.md):

    python Work/source_helpers.py preproof <slug> <md file> <first line> <last line>
"""
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = os.path.join(ROOT, "Sources")
PROOF = os.path.join(ROOT, "Work", "Proof")
# An HTML entity in a docling export, as extract.py's md_unescape reads it.
MD_ENTITY = re.compile(r"&(?:#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);")


def md_lines(md_name):
    """The lines of Sources/<md_name>, trailing whitespace removed; line n is item n - 1.

    Read with utf-8-sig, as extract.py reads the file, so line numbers and
    text are the ones line_edits are applied to.
    """
    path = os.path.join(SOURCES, md_name)
    if not os.path.exists(path):
        raise SystemExit("%s: not found (line edits are built from the source file)" % path)
    with open(path, encoding="utf-8-sig") as f:
        return [ln.rstrip() for ln in f.read().splitlines()]


def skeleton(s):
    """s reduced to its lowercase letters and digits, the words a rebuilt line must keep."""
    return "".join(c.lower() for c in s if c.isalnum())


def md_entities(text):
    """text with each HTML entity ("&amp;", "&lt;") read as its character, as extract.py reads the export."""
    return MD_ENTITY.sub(lambda m: html.unescape(m.group(0)), text)


def build_line_edits(md_name, *, rebuilt=None, replace=None, edits=None, swaps=(), joins=(), moves=(),
                     drops=None, quotes=()):
    """line_edits {line number: new text} for a docling Markdown source, each one checked.

    The operations apply in this order, each to the text the earlier ones
    left (so a quotation mark goes on a rebuilt line, and a join takes the
    joined line's corrected text):

      rebuilt  {n: text}: line n rebuilt from a better text layer (the PDF's
               own quotation marks, dashes, and spaces), usually
               rebuilt=rebuilt_lines(slug) from Work/rebuild_from_pdf.py.
               It must keep the line's letters and digits exactly
               (skeleton; an entity in the export, "&amp;", reads as its
               character), so a rebuild changes no word.
      replace  {n: text} or {n: (start, text)}: line n becomes text, for
               repairs that change words (OCR misreads, a proofreading pass:
               replace=proof_fixes(...)). With start, the line as exported
               must begin with it. A blank line cannot be replaced.
      edits    {n: [(old, new), (old, new, count), ...]}: old must occur
               exactly count times in the line (default once); each
               occurrence becomes new. new may contain "\\n\\n" to split a
               paragraph the export ran together.
      swaps    [(a, b)]: the texts of lines a and b are exchanged (footnotes
               the export put out of printed order).
      joins    [(a, b)]: line b's text is appended to line a's with one
               space and line b becomes empty (a paragraph split at a page
               break). Line b must not be blank.
      moves    [(src, dst)]: line src's text goes after line dst's as a
               paragraph of its own and line src becomes empty (a footnote
               docling put after the next section's heading). Line src must
               not be blank.
      drops    {n: must_contain}: line n becomes empty; it must contain
               must_contain, so a shifted line number is caught.
      quotes   [n]: each non-blank line of line n's text gets the block-
               quotation prefix "> ". A blank line is added first when the
               line above is not blank (an item of a list docling wrote
               without blank lines), so the quotation is a block of its own.

    Every check that fails stops the run, naming the file and line. Only
    lines an operation touched are returned. extract.py applies the result
    to the raw lines, by number, before anything else.
    """
    lines = md_lines(md_name)
    new = {}

    def stop(no, message):
        raise SystemExit("%s: line %d: %s" % (md_name, no, message))

    def original(no):
        if not isinstance(no, int) or isinstance(no, bool) or not 1 <= no <= len(lines):
            raise SystemExit("%s: line %r is not a line of the file (1-%d)" % (md_name, no, len(lines)))
        return lines[no - 1]

    def current(no):
        return new[no] if no in new else original(no)

    for no, text in (rebuilt or {}).items():
        if skeleton(text) != skeleton(md_entities(original(no))):
            stop(no, "rebuilt text changes letters or digits")
        new[no] = text
    for no, value in (replace or {}).items():
        start, text = value if isinstance(value, tuple) else (None, value)
        if not original(no).strip():
            stop(no, "is blank; a replacement needs a line of text")
        if start is not None and not original(no).strip().startswith(start):
            stop(no, "does not start with %r" % start)
        new[no] = text
    for no, pairs in (edits or {}).items():
        text = current(no)
        for pair in pairs:
            old, rep, count = (tuple(pair) + (1,))[:3]
            if text.count(old) != count:
                stop(no, "%r occurs %d times, expected %d" % (old, text.count(old), count))
            text = text.replace(old, rep)
        new[no] = text
    for a, b in swaps:
        new[a], new[b] = current(b), current(a)
    for a, b in joins:
        if not original(b).strip():
            stop(b, "is blank; a joined line needs text")
        new[a] = current(a) + " " + current(b)
        new[b] = ""
    for src, dst in moves:
        if not original(src).strip():
            stop(src, "is blank; a moved line needs text")
        new[dst] = current(dst) + "\n\n" + current(src)
        new[src] = ""
    for no, must in (drops or {}).items():
        if must not in original(no):
            stop(no, "dropped line does not contain %r" % must)
        new[no] = ""
    for no in quotes:
        text = current(no)
        if not text.strip():
            stop(no, "quoted line is blank")
        quoted = "\n".join("> " + ln if ln.strip() else ln for ln in text.split("\n"))
        above = current(no - 1) if no > 1 else ""
        new[no] = ("\n" if above.strip() else "") + quoted
    return new


def rebuilt_lines(slug):
    """Lines rebuilt from the PDF's text layer, {line number: text}, for build_line_edits(rebuilt=...).

    Reads Work/Proof/<slug>.rebuilt.json, written by Work/rebuild_from_pdf.py
    (only the lines the rebuild changed). build_line_edits checks each one
    against the line it replaces, so a file built from another export of
    the source stops the run. A missing file stops the run too: extracting
    without it would silently keep the export's damaged lines.
    """
    path = os.path.join(PROOF, slug + ".rebuilt.json")
    if not os.path.exists(path):
        raise SystemExit("%s: not found (write it with python Work/rebuild_from_pdf.py ... --out %s)"
                         % (path, "Work/Proof/%s.rebuilt.json" % slug))
    with open(path, encoding="utf-8") as f:
        return {int(n): text for n, text in json.load(f).items()}


def _proof_paths(slug):
    """The proofreading listing of a source, and its single fixes file (see proof_fix_files)."""
    return os.path.join(PROOF, slug + ".preproof.json"), os.path.join(PROOF, slug + ".fixes.json")


def proof_fix_files(slug):
    """The fixes files of a source's proofreading: <slug>.fixes.json and <slug>.<unit>.fixes.json, sorted.

    One proofreader per unit writes its own file, so agents working on one
    source in parallel never edit the same file.
    """
    if not os.path.isdir(PROOF):
        return []
    return sorted(os.path.join(PROOF, n) for n in os.listdir(PROOF)
                  if n == slug + ".fixes.json" or (n.startswith(slug + ".") and n.endswith(".fixes.json")
                                                   and "." not in n[len(slug) + 1:-len(".fixes.json")]))


def proof_fixes(slug, md_name):
    """Line edits from a proofreading pass against the page images: {line number: text}.

    Work/Proof/<slug>.preproof.json lists the lines that were proofread,
    [{"line": n, "text": ...}], each line's text exactly as it is in the
    Markdown file. Each fixes file (proof_fix_files) maps a line number (a
    string) to its corrected text ("" drops the line; "\\n\\n" inside splits
    a paragraph). Pass the result to build_line_edits as replace, so other
    edits can apply on top.

    Stops the run if a fix names a line the listing does not hold, if two
    files fix one line differently, or if a listed line no longer reads as
    it did when it was proofread (the source file changed: its line numbers
    may have moved). No listing or no fixes file gives no fixes.
    """
    pre_path, _ = _proof_paths(slug)
    paths = proof_fix_files(slug)
    if not (os.path.exists(pre_path) and paths):
        return {}
    with open(pre_path, encoding="utf-8") as f:
        listed = {int(e["line"]): e["text"] for e in json.load(f)}
    fixes, origin = {}, {}
    for fix_path in paths:
        with open(fix_path, encoding="utf-8") as f:
            for n, text in json.load(f).items():
                no = int(n)
                if no in fixes and fixes[no] != text:
                    raise SystemExit("%s: line %d is fixed differently in %s" % (fix_path, no, origin[no]))
                fixes[no], origin[no] = text, fix_path
        unknown = sorted(n for n, path in origin.items() if path == fix_path and n not in listed)
        if unknown:
            raise SystemExit("%s: fixes for lines not in the pre-proof listing: %s"
                             % (fix_path, ", ".join(map(str, unknown))))
    lines = md_lines(md_name)
    for no, text in sorted(listed.items()):
        if no > len(lines) or lines[no - 1].strip() != text.strip():
            raise SystemExit("%s: line %d of %s no longer reads as it did when it was proofread (source "
                             "changed): listed %r, now %r" % (pre_path, no, md_name, text[:60],
                                                             lines[no - 1][:60] if no <= len(lines) else "(past the end)"))
    return fixes


def write_preproof(slug, md_name, first, last):
    """Add the non-blank lines first..last of the Markdown file to Work/Proof/<slug>.preproof.json.

    Entries already listed are kept (a source proofread one excerpt at a
    time); a line listed again must still read the same. Returns the number
    of lines added.
    """
    lines = md_lines(md_name)
    if not 1 <= first <= last <= len(lines):
        raise SystemExit("%s: lines %d-%d are not in the file (1-%d)" % (md_name, first, last, len(lines)))
    pre_path, _ = _proof_paths(slug)
    entries = []
    if os.path.exists(pre_path):
        with open(pre_path, encoding="utf-8") as f:
            entries = json.load(f)
    listed = {int(e["line"]): e["text"] for e in entries}
    added = 0
    for no in range(first, last + 1):
        text = lines[no - 1]
        if not text.strip():
            continue
        if no in listed:
            if listed[no].strip() != text.strip():
                raise SystemExit("%s: line %d is listed with other text; the source changed" % (pre_path, no))
            continue
        entries.append({"line": no, "text": text})
        added += 1
    entries.sort(key=lambda e: int(e["line"]))
    os.makedirs(PROOF, exist_ok=True)
    with open(pre_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(entries, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return added


def main(argv):
    from common import utf8_output
    utf8_output()
    if len(argv) != 5 or argv[0] != "preproof":
        raise SystemExit("usage: python Work/source_helpers.py preproof <slug> <md file> <first line> <last line>")
    _, slug, md_name, first, last = argv
    added = write_preproof(slug, md_name, int(first), int(last))
    print("%d lines added -> %s" % (added, _proof_paths(slug)[0]))


if __name__ == "__main__":
    main(sys.argv[1:])
