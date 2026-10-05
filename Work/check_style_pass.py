"""Verify prose-only edits to chapter summaries against a pre-pass snapshot.

Used as the gate for a style pass (see passes/style-pass.md). A style pass may
change wording but never meaning, so this checks only what it must not change:

  quotes   every quoted span, in order, identical (trailing .,;: ignored)
  numbers  every numeric token identical; a reorder of the same numbers is
           reported separately as a softer "NUMBER ORDER" flag
  headings ## / ### heading text identical
  blocks   block-quotation lines ("> ") identical
  paras    paragraph count unchanged
  markers  counts of protected hedge, contrast and attribution markers not
           reduced (whole-word matches)

Word count is deliberately NOT checked; a style pass may grow the text.

Usage (from the project root):
    python Work/check_style_pass.py                       # every edited summary
    python Work/check_style_pass.py Work/Summaries/<slug>/<file>.md ...
    python Work/check_style_pass.py --archive Work/Summaries_prestyle ...

Exit status is 1 when any file is flagged.
"""
import re
import sys
from collections import Counter
from pathlib import Path

from common import ROOT

DEFAULT_ARCHIVE = ROOT / "Work" / "Summaries_prestyle"
CURRENT = ROOT / "Work" / "Summaries"

QUOTE = re.compile(r'"([^"]*)"|“([^”]*)”')
# A number ends in a digit, so a comma or period after it is not absorbed.
NUMBER = re.compile(r"\d(?:[\d,.]*\d)?")
HEADING = re.compile(r"^#{2,3} .*$", re.M)
# A block quotation reproduces the source exactly, so a style pass never touches it.
BLOCK_QUOTE = re.compile(r"^>.*$", re.M)

# Markers whose loss changes meaning (preservation rule (a)-(c) in writing-rules.md).
# Extend per project with source-specific hedges or attribution phrases.
PROTECTED = [
    "perhaps", "probably", "possibly", "seemingly", "apparently", "tended to",
    "often", "usually", "sometimes", "not necessarily", "may have", "might have",
    "would have", "could have", "it is reckoned", "it is estimated",
    "according to", "purportedly", "reportedly", "allegedly", "arguably",
    "claimed", "in his view", "in her view", "in their view",
    "but", "yet", "however", "even so", "nevertheless", "in truth", "although",
    "on the other hand", "though", "while", "whereas",
]
# Markers whose sense varies; a drop is reported with a reminder to check it.
ADVISORY = {
    "according to": "'according to X' is attribution; 'according to <measure>' is not",
    "while": "'while' may be temporal rather than concessive",
    "yet": "'yet' may mean 'so far' rather than a contrast",
    "in his view": "dropping it is right if it only prefaced the author's own view",
    "in her view": "dropping it is right if it only prefaced the author's own view",
    "in their view": "dropping it is right if it only prefaced the author's own view",
}
MARKER_PATTERNS = {m: re.compile(r"\b" + re.escape(m) + r"\b") for m in PROTECTED}


def quotes(text):
    # Trailing sentence punctuation may sit inside the quote in American style
    # but belongs to the sentence, so recasting may legitimately move it out.
    return [(a or b).rstrip(".,;:") for a, b in QUOTE.findall(text)]


def paragraphs(text):
    return len([p for p in re.split(r"\n\s*\n", text) if p.strip()])


def check(old, new):
    problems = []

    oq, nq = quotes(old), quotes(new)
    if oq != nq:
        for a, b in zip(oq, nq):
            if a != b:
                problems.append('QUOTE CHANGED: "%s" -> "%s"' % (a, b))
        if len(oq) != len(nq):
            problems.append("QUOTE COUNT %d -> %d" % (len(oq), len(nq)))

    on, nn = NUMBER.findall(old), NUMBER.findall(new)
    if on != nn:
        if Counter(on) == Counter(nn):
            problems.append("NUMBER ORDER changed (same numbers); confirm each still attaches to the right claim")
        else:
            lost = Counter(on) - Counter(nn)
            added = Counter(nn) - Counter(on)
            if lost:
                problems.append("NUMBER REMOVED: %s" % ", ".join(sorted(lost.elements())))
            if added:
                problems.append("NUMBER ADDED: %s" % ", ".join(sorted(added.elements())))

    ob, nb = BLOCK_QUOTE.findall(old), BLOCK_QUOTE.findall(new)
    if ob != nb:
        problems.append("BLOCK QUOTE CHANGED: %d block-quote lines before, %d after; they must match exactly" % (len(ob), len(nb)))

    oh, nh = HEADING.findall(old), HEADING.findall(new)
    if oh != nh:
        problems.append("HEADINGS CHANGED: %s -> %s" % (oh, nh))

    op, np_ = paragraphs(old), paragraphs(new)
    if op != np_:
        problems.append("PARAGRAPH COUNT %d -> %d" % (op, np_))

    lo, ln = old.lower(), new.lower()
    for marker, pat in MARKER_PATTERNS.items():
        a, b = len(pat.findall(lo)), len(pat.findall(ln))
        if b < a:
            note = "  (check sense: %s)" % ADVISORY[marker] if marker in ADVISORY else ""
            problems.append('PROTECTED MARKER "%s" %d -> %d%s' % (marker, a, b, note))
    return problems


def main():
    args = sys.argv[1:]
    archive = DEFAULT_ARCHIVE
    if "--archive" in args:
        i = args.index("--archive")
        if i + 1 >= len(args):
            raise SystemExit(__doc__)
        archive = Path(args[i + 1])
        if not archive.is_absolute():
            archive = ROOT / archive
        del args[i:i + 2]
    if not archive.is_dir():
        raise SystemExit("archive not found: %s (snapshot the summaries before the pass)" % archive)

    if args:
        targets = [Path(t) if Path(t).is_absolute() else ROOT / t for t in args]
    else:
        # Canonical chapter summaries only; parts/ files do not feed Summary.md.
        targets = sorted(CURRENT.glob("*/*.md"))

    clean = flagged = 0
    for cur in targets:
        rel = cur.resolve().relative_to(CURRENT.resolve())
        old = archive / rel
        if not old.exists():
            print("[skip] no archive for %s" % rel.as_posix())
            continue
        o, n = old.read_text(encoding="utf-8"), cur.read_text(encoding="utf-8")
        if o == n:
            print("[unchanged] %s" % rel.as_posix())
            continue
        problems = check(o, n)
        if problems:
            flagged += 1
            print("[FLAG] %s" % rel.as_posix())
            for p in problems:
                print("    %s" % p)
        else:
            clean += 1
            print("[ok] %s" % rel.as_posix())
    print("\n%d edited file(s) passed all checks; %d flagged." % (clean, flagged))
    sys.exit(1 if flagged else 0)


if __name__ == "__main__":
    main()
