"""Write Work/transition_queue.txt: one line per merged multi-part chapter.

Each line drives one transition-review task (plan.md Step 7):

    slug|unit_id|part_count|chapter_summary|title|part_source_1;part_source_2;...

The reviewer reads the merged chapter summary and, for each seam, the end of
part k and the start of part k+1 in the listed part sources. Only chapters
whose parts are all accepted and whose chapter status is not yet accepted
are listed, so rerunning after acceptance shrinks the queue.
"""
import json
import sys

from common import ROOT

MANIFEST = ROOT / "Work" / "parts_manifest.json"
QUEUE = ROOT / "Work" / "transition_queue.txt"


def main():
    if not MANIFEST.exists():
        sys.exit("Work/parts_manifest.json not found; run Work/split_parts.py first")
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    lines, waiting = [], []
    for e in entries:
        parts = sorted(e["parts"], key=lambda p: p["part_index"])
        if len(parts) < 2 or e["status"] == "accepted":
            continue
        if any(p["status"] != "accepted" for p in parts):
            waiting.append("%s/%s" % (e["source_slug"], e["unit_id"]))
            continue
        if not (ROOT / e["summary"]).exists():
            waiting.append("%s/%s (not merged)" % (e["source_slug"], e["unit_id"]))
            continue
        lines.append("|".join([
            e["source_slug"], e["unit_id"], str(len(parts)), e["summary"],
            e.get("title") or e["unit_id"], ";".join(p["source"] for p in parts),
        ]))
    QUEUE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8", newline="\n")
    print("%d chapter(s) ready for transition review" % len(lines))
    for w in waiting:
        print("waiting:", w)


if __name__ == "__main__":
    main()
