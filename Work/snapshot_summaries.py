"""Snapshot canonical chapter summaries before a post-run pass.

Copies Work/Summaries/{slug}/*.md (chapter files only; parts/ is skipped
because it does not feed Summary.md) to Work/Summaries_pre{name}/{slug}/.
Run it once, before the first agent of the pass is dispatched. It refuses
to overwrite an existing snapshot file: a refreshed snapshot silently loses
the only pre-pass copy apart from git history.

Usage:
    python Work/snapshot_summaries.py <name>                  # every chapter
    python Work/snapshot_summaries.py <name> <file.md> ...    # only these

Example: `python Work/snapshot_summaries.py style` writes
Work/Summaries_prestyle/, the archive Work/check_style_pass.py compares with.
"""
import re
import shutil
import sys

from common import ROOT, utf8_output

SUMS = ROOT / "Work" / "Summaries"


def main():
    utf8_output()
    args = sys.argv[1:]
    if not args or not re.fullmatch(r"[a-z0-9-]+", args[0]):
        raise SystemExit(__doc__)
    dest_root = ROOT / "Work" / ("Summaries_pre" + args[0])
    if args[1:]:
        files = [(ROOT / a).resolve() for a in args[1:]]
    else:
        files = sorted(p.resolve() for p in SUMS.glob("*/*.md"))
    existing, copied = [], 0
    for f in files:
        rel = f.relative_to(SUMS.resolve())
        if len(rel.parts) != 2:
            raise SystemExit("not a chapter summary: %s" % f)
        dest = dest_root / rel
        if dest.exists():
            existing.append(rel.as_posix())
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
        copied += 1
    print("copied %d file(s) to %s" % (copied, dest_root.relative_to(ROOT).as_posix()))
    if existing:
        print("kept %d existing snapshot file(s) unchanged:" % len(existing))
        for e in existing:
            print("  " + e)


if __name__ == "__main__":
    main()
