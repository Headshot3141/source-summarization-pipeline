"""Fill the Final words column of plan.md's Word Budgets tables from the summaries.

Each budget row is read by the rules Work/split_parts.py reads the tables
by (split_parts.word_budget_lines): Source slug, Unit ID, Title, Source
words, Target, Ceiling, Final words, Reason for deviation. Its Final words
becomes the word count of the unit's chapter summary (the merged or
unsplit summary named in Work/parts_manifest.json). A unit above its
ceiling (the one stored in the manifest) gets "above ceiling:
Work/budget_exceptions.json" in its Reason for deviation, once; the note
goes again if the unit is back under. Each "Source total: ...; final: {n}
words (ratio {r})." line after a table gets that table's final words and
their ratio to its units' source words (each unit's budget basis), and the
"Grand total: ...; final: {n} words (ratio {r}...)" line the same over
every table. A total whose table has a unit with no summary yet is left as
it is and reported.

Usage:
    python Work/fill_final_words.py [--dry-run]
"""
import argparse
import json
import re
import sys

from common import ROOT, utf8_output
from count_words import words_of
from split_parts import word_budget_lines

PLAN = ROOT / "plan.md"
MANIFEST = ROOT / "Work" / "parts_manifest.json"
NOTE = "above ceiling: Work/budget_exceptions.json"
FINAL_RE = re.compile(r"(final: )(\{n\}|\d[\d,]*)( words \(ratio )(\{r\}|\d*\.?\d+)")
FINAL_CELL, REASON_CELL = 6, 7


def set_cell(line, index, value):
    """line with its index-th table cell (counted as word_budget_lines counts) set to value."""
    pieces = line.split("|")
    pieces[index + 1] = f" {value} " if value else " "
    return "|".join(pieces)


def with_note(reason, over):
    """The reason with the above-ceiling note added (once) or removed."""
    items = [r.strip() for r in reason.split(";") if r.strip()]
    if over and NOTE not in items:
        items.append(NOTE)
    if not over:
        items = [r for r in items if r != NOTE]
    return "; ".join(items)


def fill_total(line, total):
    """line with its final words and ratio set from total = [words, source words, units missing]."""
    words, source, _ = total
    ratio = "%.3f" % (words / source) if source else "0"
    return FINAL_RE.sub(lambda m: f"{m.group(1)}{words:,}{m.group(3)}{ratio}", line, count=1)


def main():
    utf8_output()
    parser = argparse.ArgumentParser(description="Fill Final words in plan.md's Word Budgets tables.")
    parser.add_argument("--dry-run", action="store_true", help="report without writing plan.md")
    args = parser.parse_args(sys.argv[1:])
    if not PLAN.exists() or not MANIFEST.exists():
        sys.exit("plan.md and Work/parts_manifest.json are needed; run Work/split_parts.py first")
    manifest = {(e["source_slug"], e["unit_id"]): e for e in json.loads(MANIFEST.read_text(encoding="utf-8"))}
    lines = PLAN.read_text(encoding="utf-8").split("\n")

    table, grand = [0, 0, 0], [0, 0, 0]  # [final words, source words, units without a summary]
    filled = over = 0
    problems, totals = [], []
    for i, _part, cells in word_budget_lines(lines):
        line = lines[i]
        if line.startswith("### "):
            table = [0, 0, 0]
        elif cells is not None:
            key = "%s/%s" % (cells[0], cells[1])
            e = manifest.get((cells[0], cells[1]))
            if e is None:
                problems.append(f"plan.md line {i + 1}: {key} is not in the parts manifest")
                table[2] += 1
                grand[2] += 1
                continue
            if len(cells) <= REASON_CELL:
                problems.append(f"plan.md line {i + 1}: {key} has no Final words and Reason columns")
                continue
            summary = ROOT / e["summary"]
            if not summary.exists():
                problems.append(f"{key}: no summary yet ({e['summary']})")
                table[2] += 1
                grand[2] += 1
                continue
            words = words_of(summary)
            above = e.get("ceiling") is not None and words > e["ceiling"]
            line = set_cell(line, FINAL_CELL, f"{words:,}")
            lines[i] = set_cell(line, REASON_CELL, with_note(cells[REASON_CELL], above))
            source = e.get("budget_words", e["words"])
            for t in (table, grand):
                t[0] += words
                t[1] += source
            filled += 1
            over += above
        elif line.startswith(("Source total:", "Grand total:")):
            total = grand if line.startswith("Grand") else table
            label = line.split(":", 1)[0]
            if not FINAL_RE.search(line):
                problems.append(f"plan.md line {i + 1}: {label} line has no \"final: {{n}} words (ratio {{r}})\"")
            elif total[2]:
                problems.append(f"plan.md line {i + 1}: {label} left as it is: {total[2]} unit(s) have no summary")
            else:
                lines[i] = fill_total(line, total)
                totals.append(f"{label} (line {i + 1}): {total[0]:,} words, ratio "
                              + ("%.3f" % (total[0] / total[1]) if total[1] else "-"))
            if total is table:
                table = [0, 0, 0]

    for t in totals:
        print(t)
    for p in problems:
        print(p)
    print(f"filled {filled} row(s), {over} above ceiling")
    if args.dry_run:
        print("dry run: plan.md not written")
    else:
        PLAN.write_text("\n".join(lines), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
