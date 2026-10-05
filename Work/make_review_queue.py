"""Write Work/review_queue.txt from Work/parts_manifest.json.

One line per processing unit still to review:

    source|draft|summary|record|budget|lower|upper|ceiling

budget, lower, and upper are the draft target and range (DRAFT TARGET and
RANGE in the prompts); ceiling is what review may grow the unit to where
clarity or fidelity needs it (Work/common.py). Accepted units are left out,
so rerunning after a batch shrinks the queue; set a unit back to drafted to
review it again. Blocked units are left out and listed, because they must not
be assigned.
"""
import json
import sys

from common import ROOT, draft_range, review_ceiling

MANIFEST = ROOT / "Work" / "parts_manifest.json"
QUEUE = ROOT / "Work" / "review_queue.txt"


def main():
    if not MANIFEST.exists():
        sys.exit("Work/parts_manifest.json not found; run Work/split_parts.py first")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    lines, skipped = [], []
    for entry in manifest:
        for p in entry["parts"]:
            if p["status"] == "blocked" or entry["status"] == "blocked":
                skipped.append(p["source"])
                continue
            if p["status"] == "accepted":
                continue
            lo, hi = draft_range(p["budget"])
            fields = [p["source"], p["draft"], p["summary"], p["record"], p["budget"], lo, hi,
                      review_ceiling(p["budget"], p["words"])]
            lines.append("|".join(str(f) for f in fields))
    QUEUE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8", newline="\n")
    print(len(lines), "entries")
    for s in skipped:
        print("skipped blocked unit:", s)


if __name__ == "__main__":
    main()
