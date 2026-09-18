"""Write Work/review_queue.txt from Work/parts_manifest.json.

One line per processing unit: source|draft|summary|record|budget.
Blocked units are left out and listed, because they must not be assigned.
"""
import json
import sys

from common import ROOT

MANIFEST = ROOT / "Work" / "parts_manifest.json"
QUEUE = ROOT / "Work" / "review_queue.txt"

if not MANIFEST.exists():
    sys.exit("Work/parts_manifest.json not found; run Work/split_parts.py first")
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
lines, skipped = [], []
for entry in manifest:
    for p in entry["parts"]:
        if p["status"] == "blocked" or entry["status"] == "blocked":
            skipped.append(p["source"])
            continue
        lines.append(f"{p['source']}|{p['draft']}|{p['summary']}|{p['record']}|{p['budget']}")
QUEUE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8", newline="\n")
print(len(lines), "entries")
for s in skipped:
    print("skipped blocked unit:", s)
