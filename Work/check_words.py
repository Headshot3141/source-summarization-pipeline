"""Check summary word counts against the budgets in Work/parts_manifest.json.

Counts come from the shared words_of function. Four checks:

- Drafts (Work/Drafts/...): flags a draft outside its draft range
  (budget +/- 15%; the budget is about 0.40 of the unit's source words).
  A draft is checked only until its unit has a reviewed summary.
- Reviewed summaries (Work/Summaries/...): flags a summary above its ceiling
  (budget + 0.10 of the source words, as stored in the manifest), which
  needs a recorded preservation reason, or below the draft range, which may
  mean over-compression. Once a split chapter is merged, its merged chapter
  is checked against the chapter ceiling and its stale part summaries are
  not.
- Running ratio: reviewed summary words / source words, per source and for
  the whole document, over the units that have a reviewed summary. Source
  words are each unit's budget basis (its words less the text left out in
  Work/budget_exclusions.json). The document aims at 0.50 and must not
  exceed 0.55 (DOC_TARGET, DOC_MAX in Work/common.py). Above the target it
  prints a note; above the maximum it flags.
- Projection: reviewed words plus the stored ceiling of every unit not yet
  reviewed, over the source words of every unit: where the document ends
  if review uses every ceiling. Above the maximum it flags.

A flag the coordinator has settled (a ceiling overage whose record names
the preservation items, a short summary whose record explains it, or an
apparatus-only part that is legitimately empty) goes in
Work/budget_exceptions.json, keyed "slug/unit_id" (an unsplit or merged
chapter) or "slug/unit_id/part k" (a part before the merge):

    {"s/ch-02": {"flag": "ABOVE CEILING", "max_words": 520,
                 "reason": "Restored the reversals the draft dropped; see the record.",
                 "history": ["verify-round2 (2026-10-12): +40 words ..."]}}

"flag" is the kind it settles (ABOVE CEILING, UNDER, DRAFT OVER, or DRAFT
UNDER) and "max_words" the count approved; an exception settles only that
kind, and an ABOVE CEILING or DRAFT OVER exception only up to max_words, so
later growth flags again. An UNDER or DRAFT UNDER exception may set
"min_words", below which it no longer settles. "reason" is one sentence;
"history" (optional, a list of strings, ignored here) logs each later
raise, as Work/raise_exceptions.py writes it. A part's exception does not
carry over to its merged chapter, which needs its own key; once the chapter
is merged its part keys are reported as superseded, to delete. A document
the user has approved above DOC_MAX takes the key "DOCUMENT":
{"flag": "OVER MAXIMUM", "max_words": n, "reason": ...}, which settles the
document ratio and projection while their word totals stay at or under n.
Keys starting with "_" are comments. Settled flags print as EXCEPTION, with
the reason shortened unless --reasons is given.

Usage:
    python Work/check_words.py [--reasons] [--json]

--json prints evaluate()'s result instead of the report. Exits 1 if
anything is flagged, so the result can gate a batch.
"""
import argparse
import json
import sys
from collections import defaultdict

from common import DOC_MAX, DOC_TARGET, ROOT, draft_range, review_ceiling, utf8_output
from count_words import words_of

MANIFEST = ROOT / "Work" / "parts_manifest.json"
EXCEPTIONS = ROOT / "Work" / "budget_exceptions.json"


KINDS = ("ABOVE CEILING", "UNDER", "DRAFT OVER", "DRAFT UNDER")
DOCUMENT_KEY = "DOCUMENT"
DOCUMENT_KIND = "OVER MAXIMUM"
REASON_CHARS = 100


def is_count(v):
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def load_exceptions():
    """The exceptions file as a dict (comment keys included), validated; {} if absent."""
    if not EXCEPTIONS.exists():
        return {}
    try:
        data = json.loads(EXCEPTIONS.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        sys.exit(f"{EXCEPTIONS.name}: not valid JSON: {exc}")
    if not isinstance(data, dict):
        sys.exit(f"{EXCEPTIONS.name}: must be a JSON object keyed by slug/unit_id")

    for key, value in data.items():
        if key.startswith("_"):
            continue  # a comment entry, such as "_about"
        ok = isinstance(value, dict) and isinstance(value.get("reason"), str) and value["reason"].strip()
        if ok and "history" in value:
            ok = isinstance(value["history"], list) and all(isinstance(h, str) for h in value["history"])
        if key == DOCUMENT_KEY:
            if not (ok and value.get("flag") == DOCUMENT_KIND and is_count(value.get("max_words"))):
                sys.exit(f"{EXCEPTIONS.name}: {key}: needs {{\"flag\": \"{DOCUMENT_KIND}\", \"max_words\": n, "
                         f"\"reason\": ...}}, with an optional \"history\" list of strings")
            continue
        ok = ok and value.get("flag") in KINDS
        if ok and value["flag"] in ("ABOVE CEILING", "DRAFT OVER"):
            ok = is_count(value.get("max_words"))
        if ok and "min_words" in value:
            ok = is_count(value["min_words"])
        if not ok:
            sys.exit(f"{EXCEPTIONS.name}: {key}: needs {{\"flag\": one of {', '.join(KINDS)}, "
                     f"\"reason\": ...}}, a whole-number \"max_words\" for ABOVE CEILING or DRAFT OVER, "
                     f"and optionally a whole-number \"min_words\" for UNDER or DRAFT UNDER and a "
                     f"\"history\" list of strings")
    return data


def settles(exception, kind, words):
    if not exception or exception["flag"] != kind:
        return False
    if kind in ("ABOVE CEILING", "DRAFT OVER", DOCUMENT_KIND):
        return words <= exception["max_words"]
    return words >= exception.get("min_words", 0)


def stored_ceiling(unit):
    """The ceiling split_parts.py stored on a manifest part or chapter, or one recomputed from its budget."""
    if unit.get("ceiling") is not None:
        return unit["ceiling"]
    return review_ceiling(unit["budget"], unit.get("budget_words", unit["words"]))


def basis(unit):
    """A unit's budget basis: its words less the text left out of the budget."""
    return unit.get("budget_words", unit["words"])


def evaluate(exceptions=None):
    """Run every check and return the result as data (main() only prints it).

    Returns {"flags", "settled", "unused", "superseded", "missing",
    "totals"}. Each flag is a dict with kind (ABOVE CEILING, UNDER, DRAFT
    OVER, DRAFT UNDER, or OVER MAXIMUM), level (CHAPTER, PART, or
    DOCUMENT), key (its Work/budget_exceptions.json key), path (the file
    checked; None for the document), words, limit (the bound it passed),
    and text (the report line). Settled flags carry the exception's reason
    too. unused lists exception keys that settle nothing; superseded lists
    the unused part keys of merged chapters, to delete. totals holds the
    per-source and document ratios and the projection.
    """
    if not MANIFEST.exists():
        sys.exit("Work/parts_manifest.json not found; run Work/split_parts.py first")
    if exceptions is None:
        exceptions = load_exceptions()
    flags, settled, used = [], [], set()
    missing = {"draft": 0, "summary": 0}
    # slug -> [reviewed summary words, source words of those units]
    ratio = defaultdict(lambda: [0, 0])
    # Words if every unit not yet reviewed reached its ceiling, and of what.
    projected = {"reviewed_words": 0, "pending_ceilings": 0, "pending_units": 0, "source_words": 0}
    merged_part_keys = set()

    def flag(key, kind, level, path, words, limit, text):
        item = {"kind": kind, "level": level, "key": key, "path": path, "words": words, "limit": limit,
                "text": text}
        if settles(exceptions.get(key), kind, words):
            used.add(key)
            item["reason"] = exceptions[key]["reason"]
            settled.append(item)
        else:
            flags.append(item)

    for entry in json.loads(MANIFEST.read_text(encoding="utf-8")):
        slug, unit = entry["source_slug"], entry["unit_id"]
        split = entry["part_count"] > 1
        chapter = ROOT / entry["summary"]
        merged = split and chapter.exists()
        projected["source_words"] += basis(entry)
        reviewed_parts = []
        for p in entry["parts"]:
            level = "PART" if split else "CHAPTER"
            key = f"{slug}/{unit}/part {p['part_index']}" if split else f"{slug}/{unit}"
            if merged:
                merged_part_keys.add(key)
                continue
            summary = ROOT / p["summary"]
            draft = ROOT / p["draft"]
            if not summary.exists():
                missing["summary"] += 1
                projected["pending_ceilings"] += stored_ceiling(p)
                projected["pending_units"] += 1
                if draft.exists():
                    words = words_of(draft)
                    lo, hi = draft_range(p["budget"])
                    if not lo <= words <= hi:
                        kind = "DRAFT OVER" if words > hi else "DRAFT UNDER"
                        flag(key, kind, level, p["draft"], words, hi if words > hi else lo,
                             f"{kind} {level} {p['draft']}: {words} words (budget {p['budget']}, range {lo}-{hi})")
                else:
                    missing["draft"] += 1
            else:
                words = words_of(summary)
                reviewed_parts.append((words, basis(p)))
                for kind, limit, text in check_summary(p["summary"], words, p, level):
                    flag(key, kind, level, p["summary"], words, limit, text)

        if merged:
            words = words_of(chapter)
            for kind, limit, text in check_summary(entry["summary"], words, entry, "CHAPTER"):
                flag(f"{slug}/{unit}", kind, "CHAPTER", entry["summary"], words, limit, text)
            reviewed_parts = [(words, basis(entry))]
        for words, source_words in reviewed_parts:
            ratio[slug][0] += words
            ratio[slug][1] += source_words
            projected["reviewed_words"] += words

    sources = {}
    document = {"words": 0, "source_words": 0, "ratio": None, "target": DOC_TARGET, "maximum": DOC_MAX}
    for slug in sorted(ratio):
        words, source = ratio[slug]
        document["words"] += words
        document["source_words"] += source
        sources[slug] = {"words": words, "source_words": source, "ratio": words / source if source else None}
    if document["source_words"]:
        r = document["words"] / document["source_words"]
        document["ratio"] = r
        if r > DOC_MAX:
            limit = int(DOC_MAX * document["source_words"])
            flag(DOCUMENT_KEY, DOCUMENT_KIND, "DOCUMENT", None, document["words"], limit,
                 "RATIO document: %.3f (target %.2f, maximum %.2f)" % (r, DOC_TARGET, DOC_MAX))
    projected["words"] = projected["reviewed_words"] + projected["pending_ceilings"]
    projected["ratio"] = projected["words"] / projected["source_words"] if projected["source_words"] else None
    if projected["ratio"] is not None and projected["ratio"] > DOC_MAX:
        flag(DOCUMENT_KEY, DOCUMENT_KIND, "DOCUMENT", None, projected["words"],
             int(DOC_MAX * projected["source_words"]), projection_line(projected))

    stale = {k for k in exceptions if not k.startswith("_")} - used
    superseded = sorted(stale & merged_part_keys)
    return {
        "flags": flags,
        "settled": settled,
        "unused": sorted(stale - merged_part_keys),
        "superseded": superseded,
        "missing": missing,
        "totals": {"sources": sources, "document": document, "projected": projected},
    }


def projection_line(projected):
    return ("PROJECTED document: %.3f (%d words: %d reviewed, %d in the ceilings of %d unit(s) not yet "
            "reviewed; %d source words; maximum %.2f)" % (
                projected["ratio"], projected["words"], projected["reviewed_words"], projected["pending_ceilings"],
                projected["pending_units"], projected["source_words"], DOC_MAX))


def shorten(reason, limit=REASON_CHARS):
    """reason cut at a word boundary to about limit characters."""
    reason = " ".join(reason.split())
    if len(reason) <= limit:
        return reason
    cut = reason[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:") + " …"


def document_line(item, full_reasons):
    """The printed form of a document-level flag or settled exception."""
    if "reason" in item:
        reason = item["reason"] if full_reasons else shorten(item["reason"])
        return f"EXCEPTION {DOCUMENT_KIND} {item['text']} -- {reason}"
    if item["text"].startswith("RATIO"):
        return (f"{DOCUMENT_KIND} {item['text']}: lower the Targets of pending units and rerun "
                f"Work/split_parts.py, or ask the user (plan.md Word Budgets)")
    return (f"{DOCUMENT_KIND} {item['text']}: lower the Targets of pending units and rerun "
            f"Work/split_parts.py (plan.md Word Budgets)")


def main():
    utf8_output()
    parser = argparse.ArgumentParser(description="Check summary word counts against their budgets.")
    parser.add_argument("--reasons", action="store_true", help="print settled exceptions' reasons in full")
    parser.add_argument("--json", action="store_true", help="print the result as JSON instead of the report")
    args = parser.parse_args(sys.argv[1:])
    result = evaluate()
    flags, settled = result["flags"], result["settled"]
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        sys.exit(1 if flags else 0)

    unit_flags = [f for f in flags if f["level"] != "DOCUMENT"]
    doc_items = [f for f in flags + settled if f["level"] == "DOCUMENT"]
    for f in unit_flags:
        print(f["text"])
    for s in settled:
        if s["level"] != "DOCUMENT":
            print(f"EXCEPTION {s['text']} -- {s['reason'] if args.reasons else shorten(s['reason'])}")
    for key in result["unused"]:
        print(f"unused exception {key}: it settles nothing now (fixed, or the key or flag is wrong)")
    if result["superseded"]:
        print("%d part exception(s) superseded by merged chapters; delete: %s" % (
            len(result["superseded"]), ", ".join(result["superseded"])))
    missing = result["missing"]
    print("not yet written: %d draft(s), %d reviewed summary(ies)" % (missing["draft"], missing["summary"]))

    totals = result["totals"]
    for slug, t in totals["sources"].items():
        if t["source_words"]:
            print("RATIO %s: %.3f (%d summary words / %d source words)" % (
                slug, t["ratio"], t["words"], t["source_words"]))
    document = totals["document"]
    ratio_item = next((d for d in doc_items if d["text"].startswith("RATIO")), None)
    if ratio_item:
        print(document_line(ratio_item, args.reasons))
    elif document["ratio"] is not None:
        line = "RATIO document: %.3f (target %.2f, maximum %.2f)" % (document["ratio"], DOC_TARGET, DOC_MAX)
        if document["ratio"] > DOC_TARGET:
            line += (": above target; lower the Targets of pending units and rerun Work/split_parts.py "
                     "(plan.md Word Budgets)")
        print(line)
    projected = totals["projected"]
    projection_item = next((d for d in doc_items if d["text"].startswith("PROJECTED")), None)
    if projection_item:
        print(document_line(projection_item, args.reasons))
    elif projected["ratio"] is not None:
        print(projection_line(projected))

    print("%d flag(s), %d settled exception(s)" % (len(flags), len(settled)))
    sys.exit(1 if flags else 0)


def check_summary(rel_path, words, unit, label):
    """Return [(kind, limit, report line)] for a reviewed summary.

    unit: a manifest part or chapter entry with budget, words, and ceiling.
    The ceiling is the one split_parts.py stored, recomputed only if absent.
    """
    budget = unit["budget"]
    lo, _ = draft_range(budget)
    ceiling = stored_ceiling(unit)
    if words > ceiling:
        return [("ABOVE CEILING", ceiling, f"ABOVE CEILING {label} {rel_path}: {words} words (budget {budget}, "
                                           f"ceiling {ceiling}); needs a recorded preservation reason")]
    if words < lo:
        return [("UNDER", lo, f"UNDER {label} {rel_path}: {words} words (budget {budget}, draft floor {lo}); "
                              f"check for dropped content")]
    return []


if __name__ == "__main__":
    main()
