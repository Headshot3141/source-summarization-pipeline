"""Check summary word counts against the budgets in Work/parts_manifest.json.

Counts come from the shared words_of function. Flags every summary
outside 0.85-1.15 of its budget and every missing summary. For split
chapters it also checks the merged chapter summary against the chapter
budget.
"""
import json
import sys

from common import ROOT
from count_words import words_of

MANIFEST = ROOT / "Work" / "parts_manifest.json"


def check(rel_path, budget, label):
    path = ROOT / rel_path
    if not path.exists():
        print("MISSING", label, rel_path)
        return
    words = words_of(path)
    cap = round(budget * 1.15)
    floor = round(budget * 0.85)
    flag = "OVER" if words > cap else "UNDER" if words < floor else ""
    if flag:
        print(f"{flag} {label} {rel_path}: {words} words (budget {budget}, range {floor}-{cap})")


if not MANIFEST.exists():
    sys.exit("Work/parts_manifest.json not found; run Work/split_parts.py first")
for entry in json.loads(MANIFEST.read_text(encoding="utf-8")):
    split = entry["part_count"] > 1
    for p in entry["parts"]:
        check(p["summary"], p["budget"], "PART" if split else "CHAPTER")
    if split:
        check(entry["summary"], entry["budget"], "CHAPTER")
print("check complete")
