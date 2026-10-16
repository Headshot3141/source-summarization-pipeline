"""Apply the coordinator's own text edits from a list, checking each first.

Some fixes are the coordinator's to make: whole-document findings it
accepts, rulings the user gives on several chapters at once, wording in
the Introduction. Making them one hand edit at a time is slow and leaves
no list of what changed; writing them as a list lets each be checked
before any is applied, and the list is the record.

edits.json is a list of edits:

    [{"id": "W-3", "path": "Work/Summaries/penhale-grey-harbour/02-the-tide-tables.md",
      "old": "exact text now in the file", "new": "its replacement"}, ...]

Paths are relative to the project root. Edits to one file apply in list
order, each to the text the earlier ones left, so two edits may touch
neighbouring words.

Dry run (the default): each "old" must occur exactly once in its file, and
each change's word count (new minus old, by the shared counter in
Work/count_words.py) is printed; with --max-delta N a change that adds more
than N words is flagged too. --apply writes every file, UTF-8 with LF line
endings, and only when nothing is flagged: a list is applied whole or not
at all.

Usage (from the project root):
    python Work/apply_replacements.py <edits.json> [--apply] [--max-delta N]
"""
import argparse
import json
import sys
from pathlib import Path

from common import ROOT, utf8_output
from count_words import words_in_text


def load_edits(path):
    """The edit list, checked for shape; exits with a message on a malformed one."""
    p = Path(path)
    p = p if p.is_absolute() else ROOT / p
    if not p.exists():
        sys.exit("not found: %s" % path)
    try:
        edits = json.loads(p.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        sys.exit("%s: not valid JSON: %s" % (path, exc))
    if not isinstance(edits, list):
        sys.exit("%s: must be a JSON list of {\"id\", \"path\", \"old\", \"new\"}" % path)
    for i, e in enumerate(edits, 1):
        ok = isinstance(e, dict) and all(isinstance(e.get(k), str) for k in ("id", "path", "old", "new"))
        if not ok or not e["old"]:
            sys.exit("%s: edit %d needs string fields id, path, old (not empty), and new" % (path, i))
    return edits


def target(path):
    """The file an edit names, refused if it is outside the project."""
    p = (ROOT / path).resolve()
    try:
        p.relative_to(ROOT.resolve())
    except ValueError:
        return None
    return p


def main(argv=None):
    utf8_output()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edits")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--max-delta", type=int)
    args = ap.parse_args(argv)

    texts, flagged = {}, 0
    for e in load_edits(args.edits):
        path = e["path"]
        p = target(path)
        if p is None or not p.is_file():
            print("%-10s       %s  <-- %s" % (e["id"], path, "OUTSIDE THE PROJECT" if p is None else "FILE NOT FOUND"))
            flagged += 1
            continue
        if path not in texts:
            texts[path] = p.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        old, new = e["old"].replace("\r\n", "\n"), e["new"].replace("\r\n", "\n")
        count = texts[path].count(old)
        delta = words_in_text(new) - words_in_text(old)
        flags = []
        if count != 1:
            flags.append("FOUND %d TIMES" % count)
        if args.max_delta is not None and delta > args.max_delta:
            flags.append("OVER +%d" % args.max_delta)
        if old == new:
            flags.append("NO CHANGE")
        flagged += bool(flags)
        print("%-10s %+4d  %s%s" % (e["id"], delta, path, "  <-- " + "; ".join(flags) if flags else ""))
        if count == 1:
            texts[path] = texts[path].replace(old, new)

    if flagged:
        print("%d edit(s) flagged; %s" % (flagged, "nothing applied" if args.apply else "fix them before --apply"))
        return 1
    if not args.apply:
        print("dry run: every edit checks out; rerun with --apply to write %d file(s)" % len(texts))
        return 0
    for path, text in texts.items():
        target(path).write_text(text, encoding="utf-8", newline="\n")
    print("applied to %d file(s)" % len(texts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
