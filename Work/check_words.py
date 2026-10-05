"""Check summary word counts against the budgets in Work/parts_manifest.json.

Counts come from the shared words_of function. Three checks:

- Drafts (Work/Drafts/...): flags a draft outside its draft range
  (budget +/- 15%; the budget is about 0.40 of the unit's source words).
- Reviewed summaries (Work/Summaries/...): flags a summary above its ceiling
  (budget + 0.10 of the source words), which needs a recorded preservation
  reason, or below the draft range, which may mean over-compression. A merged
  split chapter is checked against the chapter ceiling.
- Running ratio: reviewed summary words / source words, per source and for
  the whole document, over the units that have a reviewed summary. The
  document aims at 0.50 and must not exceed 0.55 (DOC_TARGET, DOC_MAX in
  Work/common.py). Above the target it prints a note; above the maximum it
  flags.

Units with no file yet are counted, not listed. Exits 1 if anything is
flagged, so the result can gate a batch.
"""
import json
import sys
from collections import defaultdict

from common import DOC_MAX, DOC_TARGET, ROOT, draft_range, review_ceiling
from count_words import words_of

MANIFEST = ROOT / "Work" / "parts_manifest.json"


def main():
    if not MANIFEST.exists():
        sys.exit("Work/parts_manifest.json not found; run Work/split_parts.py first")
    flags = []
    missing = {"draft": 0, "summary": 0}
    # slug -> [reviewed summary words, source words of those units]
    ratio = defaultdict(lambda: [0, 0])

    for entry in json.loads(MANIFEST.read_text(encoding="utf-8")):
        split = entry["part_count"] > 1
        reviewed_parts = []
        for p in entry["parts"]:
            label = "PART" if split else "CHAPTER"
            draft = ROOT / p["draft"]
            if draft.exists():
                words = words_of(draft)
                lo, hi = draft_range(p["budget"])
                if not lo <= words <= hi:
                    kind = "DRAFT OVER" if words > hi else "DRAFT UNDER"
                    flags.append(f"{kind} {label} {p['draft']}: {words} words (budget {p['budget']}, range {lo}-{hi})")
            else:
                missing["draft"] += 1
            summary = ROOT / p["summary"]
            if summary.exists():
                words = words_of(summary)
                reviewed_parts.append((words, p["words"]))
                flags.extend(check_summary(p["summary"], words, p["budget"], p["words"], label))
            else:
                missing["summary"] += 1

        chapter = ROOT / entry["summary"]
        if split and chapter.exists():
            words = words_of(chapter)
            flags.extend(check_summary(entry["summary"], words, entry["budget"], entry["words"], "CHAPTER"))
            ratio[entry["source_slug"]][0] += words
            ratio[entry["source_slug"]][1] += entry["words"]
        else:
            for words, source_words in reviewed_parts:
                ratio[entry["source_slug"]][0] += words
                ratio[entry["source_slug"]][1] += source_words

    for f in flags:
        print(f)
    print("not yet written: %d draft(s), %d reviewed summary(ies)" % (missing["draft"], missing["summary"]))

    total = [0, 0]
    for slug in sorted(ratio):
        words, source = ratio[slug]
        total[0] += words
        total[1] += source
        if source:
            print("RATIO %s: %.3f (%d summary words / %d source words)" % (slug, words / source, words, source))
    if total[1]:
        r = total[0] / total[1]
        line = "RATIO document: %.3f (target %.2f, maximum %.2f)" % (r, DOC_TARGET, DOC_MAX)
        if r > DOC_MAX:
            flags.append(line)
            line = "OVER MAXIMUM " + line + ": tighten pending or reviewed units"
        elif r > DOC_TARGET:
            line += ": above target; keep remaining units at or under their budgets"
        print(line)

    print("%d flag(s)" % len(flags))
    sys.exit(1 if flags else 0)


def check_summary(rel_path, words, budget, source_words, label):
    lo, _ = draft_range(budget)
    ceiling = review_ceiling(budget, source_words)
    if words > ceiling:
        return [f"ABOVE CEILING {label} {rel_path}: {words} words (budget {budget}, ceiling {ceiling}); "
                f"needs a recorded preservation reason"]
    if words < lo:
        return [f"UNDER {label} {rel_path}: {words} words (budget {budget}, draft floor {lo}); check for dropped content"]
    return []


if __name__ == "__main__":
    main()
