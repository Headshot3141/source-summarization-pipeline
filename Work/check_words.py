"""Check summary word counts against the budgets in Work/parts_manifest.json.

Counts come from the shared words_of function. Three checks:

- Drafts (Work/Drafts/...): flags a draft outside its draft range
  (budget +/- 15%; the budget is about 0.40 of the unit's source words).
  A draft is checked only until its unit has a reviewed summary.
- Reviewed summaries (Work/Summaries/...): flags a summary above its ceiling
  (budget + 0.10 of the source words), which needs a recorded preservation
  reason, or below the draft range, which may mean over-compression. Once a
  split chapter is merged, its merged chapter is checked against the
  chapter ceiling and its stale part summaries are not.
- Running ratio: reviewed summary words / source words, per source and for
  the whole document, over the units that have a reviewed summary. The
  document aims at 0.50 and must not exceed 0.55 (DOC_TARGET, DOC_MAX in
  Work/common.py). Above the target it prints a note; above the maximum it
  flags.

A flag the coordinator has settled (a ceiling overage whose record names
the preservation items, a short summary whose record explains it, or an
apparatus-only part that is legitimately empty) goes in
Work/budget_exceptions.json, keyed "slug/unit_id" (an unsplit or merged
chapter) or "slug/unit_id/part k" (a part before the merge):

    {"s/ch-02": {"flag": "ABOVE CEILING", "max_words": 520, "reason": "restored reversals; see record"}}

"flag" is the kind it settles (ABOVE CEILING, UNDER, DRAFT OVER, or DRAFT
UNDER) and "max_words" the count approved; an exception settles only that
kind, and an ABOVE CEILING or DRAFT OVER exception only up to max_words, so
later growth flags again. An UNDER or DRAFT UNDER exception may set
"min_words", below which it no longer settles. A part's exception does not carry over to its
merged chapter, which needs its own key. Settled flags print as EXCEPTION.
Exits 1 if anything is flagged, so the result can gate a batch.
"""
import json
import sys
from collections import defaultdict

from common import DOC_MAX, DOC_TARGET, ROOT, draft_range, review_ceiling
from count_words import words_of

MANIFEST = ROOT / "Work" / "parts_manifest.json"
EXCEPTIONS = ROOT / "Work" / "budget_exceptions.json"


KINDS = ("ABOVE CEILING", "UNDER", "DRAFT OVER", "DRAFT UNDER")


def load_exceptions():
    if not EXCEPTIONS.exists():
        return {}
    try:
        data = json.loads(EXCEPTIONS.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        sys.exit(f"{EXCEPTIONS.name}: not valid JSON: {exc}")
    if not isinstance(data, dict):
        sys.exit(f"{EXCEPTIONS.name}: must be a JSON object keyed by slug/unit_id")
    def is_count(v):
        return isinstance(v, int) and not isinstance(v, bool) and v >= 0

    for key, value in data.items():
        ok = isinstance(value, dict) and value.get("flag") in KINDS and value.get("reason")
        if ok and value["flag"] in ("ABOVE CEILING", "DRAFT OVER"):
            ok = is_count(value.get("max_words"))
        if ok and "min_words" in value:
            ok = is_count(value["min_words"])
        if not ok:
            sys.exit(f"{EXCEPTIONS.name}: {key}: needs {{\"flag\": one of {', '.join(KINDS)}, "
                     f"\"reason\": ...}}, a whole-number \"max_words\" for ABOVE CEILING or DRAFT OVER, "
                     f"and optionally a whole-number \"min_words\" for UNDER or DRAFT UNDER")
    return data


def settles(exception, kind, words):
    if not exception or exception["flag"] != kind:
        return False
    if kind in ("ABOVE CEILING", "DRAFT OVER"):
        return words <= exception["max_words"]
    return words >= exception.get("min_words", 0)


def main():
    if not MANIFEST.exists():
        sys.exit("Work/parts_manifest.json not found; run Work/split_parts.py first")
    exceptions = load_exceptions()
    flags, settled = [], []
    missing = {"draft": 0, "summary": 0}
    # slug -> [reviewed summary words, source words of those units]
    ratio = defaultdict(lambda: [0, 0])

    used = set()

    def flag(key, kind, words, text):
        if settles(exceptions.get(key), kind, words):
            used.add(key)
            settled.append(f"EXCEPTION {text} -- {exceptions[key]['reason']}")
        else:
            flags.append(text)

    for entry in json.loads(MANIFEST.read_text(encoding="utf-8")):
        slug, unit = entry["source_slug"], entry["unit_id"]
        split = entry["part_count"] > 1
        chapter = ROOT / entry["summary"]
        merged = split and chapter.exists()
        reviewed_parts = []
        for p in entry["parts"]:
            label = "PART" if split else "CHAPTER"
            key = f"{slug}/{unit}/part {p['part_index']}" if split else f"{slug}/{unit}"
            summary = ROOT / p["summary"]
            draft = ROOT / p["draft"]
            if not summary.exists() and not merged:
                missing["summary"] += 1
                if draft.exists():
                    words = words_of(draft)
                    lo, hi = draft_range(p["budget"])
                    if not lo <= words <= hi:
                        kind = "DRAFT OVER" if words > hi else "DRAFT UNDER"
                        flag(key, kind, words,
                             f"{kind} {label} {p['draft']}: {words} words (budget {p['budget']}, range {lo}-{hi})")
                else:
                    missing["draft"] += 1
            elif summary.exists() and not merged:
                words = words_of(summary)
                reviewed_parts.append((words, p["words"]))
                for kind, text in check_summary(p["summary"], words, p, label):
                    flag(key, kind, words, text)

        if merged:
            words = words_of(chapter)
            for kind, text in check_summary(entry["summary"], words, entry, "CHAPTER"):
                flag(f"{slug}/{unit}", kind, words, text)
            ratio[slug][0] += words
            ratio[slug][1] += entry["words"]
        else:
            for words, source_words in reviewed_parts:
                ratio[slug][0] += words
                ratio[slug][1] += source_words

    for f in flags:
        print(f)
    for s in settled:
        print(s)
    for key in sorted(set(exceptions) - used):
        print(f"unused exception {key}: it settles nothing now (fixed, or the key or flag is wrong)")
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
            line += (": above target; review the remaining units with CEILING set to their budget, "
                     "or their current count where higher (plan.md Step 6)")
        print(line)

    print("%d flag(s), %d settled exception(s)" % (len(flags), len(settled)))
    sys.exit(1 if flags else 0)


def check_summary(rel_path, words, unit, label):
    """unit: a manifest part or chapter entry with budget, words, and ceiling."""
    budget = unit["budget"]
    lo, _ = draft_range(budget)
    ceiling = unit.get("ceiling") or review_ceiling(budget, unit["words"])
    if words > ceiling:
        return [("ABOVE CEILING", f"ABOVE CEILING {label} {rel_path}: {words} words (budget {budget}, "
                                  f"ceiling {ceiling}); needs a recorded preservation reason")]
    if words < lo:
        return [("UNDER", f"UNDER {label} {rel_path}: {words} words (budget {budget}, draft floor {lo}); "
                          f"check for dropped content")]
    return []


if __name__ == "__main__":
    main()
