"""Merge accepted part summaries into chapter summaries.

For every chapter in Work/parts_manifest.json whose parts are all accepted,
concatenate the reviewed part summaries in part order under a single
`## {title}` heading and write the result to the chapter summary path.

Usage:
    python Work/merge_chapters.py            # merge every ready chapter
    python Work/merge_chapters.py <slug> <unit_id> [<slug> <unit_id> ...]
    python Work/merge_chapters.py --dry-run  # report without writing

A chapter is ready when every part has status `accepted`. Chapters already
marked accepted, and unsplit chapters, are skipped. The script does not change part or chapter
status; set those with Work/set_status.py after the transition review.

A part summary is refused, and nothing is written for its chapter, if it has
YAML frontmatter, an HTML comment (page, overlap, or owned-text marker), or
a heading: part summaries are plain paragraphs, and in one run a reviewer
copied its source's frontmatter and owned-text markers into its summary.
"""
import json
import re
import sys

from common import ROOT
from count_words import words_in_text

PARTS_MANIFEST = ROOT / "Work" / "parts_manifest.json"


def load():
    return json.loads(PARTS_MANIFEST.read_text(encoding="utf-8"))


LEAKS = [
    (re.compile(r"\A---\n"), "YAML frontmatter"),
    (re.compile(r"<!--|-->"), "HTML comment (page or pipeline marker)"),
    (re.compile(r"(?m)^#{1,6} "), "heading"),
]


def leaks(text):
    """Names of structural artifacts that must not appear in a part summary."""
    return [name for pattern, name in LEAKS if pattern.search(text)]


def part_texts(entry):
    """Reviewed part summary texts, in part order, with empties dropped.

    An empty part summary is allowed only for a part that is pure apparatus
    (a bibliography, say); record it as a scope exception in checks.md.
    """
    texts = []
    for p in sorted(entry["parts"], key=lambda x: x["part_index"]):
        path = ROOT / p["summary"]
        if not path.exists():
            raise SystemExit("missing part summary: %s" % p["summary"])
        text = path.read_text(encoding="utf-8-sig").strip()
        found = leaks(text)
        if found:
            raise SystemExit("%s: %s; clean the part summary before merging" % (p["summary"], ", ".join(found)))
        if text:
            texts.append(text)
    return texts


def merge_one(entry, dry_run):
    slug, unit = entry["source_slug"], entry["unit_id"]
    texts = part_texts(entry)
    title = entry.get("title") or unit
    body = "\n\n".join(texts)
    chapter = "## %s\n\n%s\n" % (title, body) if body else "## %s\n" % title
    out = ROOT / entry["summary"]
    words = words_in_text(chapter)
    budget = entry.get("budget")
    lo, hi = (round(budget * 0.85), round(budget * 1.15)) if budget else (None, None)
    flag = ""
    if budget and not (lo <= words <= hi):
        flag = "  <-- OUTSIDE %d-%d" % (lo, hi)
    if not dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(chapter, encoding="utf-8", newline="\n")
    print("%s/%s: %d parts, %d words (budget %s)%s" % (slug, unit, len(texts), words, budget, flag))
    return words


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]
    wanted = set()
    if args:
        if len(args) % 2:
            raise SystemExit(__doc__)
        for i in range(0, len(args), 2):
            wanted.add((args[i], args[i + 1]))

    entries = load()
    merged = skipped = 0
    for entry in entries:
        key = (entry["source_slug"], entry["unit_id"])
        if wanted and key not in wanted:
            continue
        if len(entry.get("parts", [])) == 1:
            # Unsplit chapter: its reviewed summary is already the chapter file.
            if wanted:
                print("%s/%s: unsplit, nothing to merge" % key)
            skipped += 1
            continue
        statuses = [p["status"] for p in entry.get("parts", [])]
        if not statuses or not all(s == "accepted" for s in statuses):
            if wanted:
                print("%s/%s: not ready (part statuses %s)" % (key[0], key[1], statuses))
            skipped += 1
            continue
        if entry.get("status") == "accepted":
            skipped += 1
            continue
        merge_one(entry, dry_run)
        merged += 1
    print("%s %d chapter(s); skipped %d" % ("would merge" if dry_run else "merged", merged, skipped))


if __name__ == "__main__":
    main()
