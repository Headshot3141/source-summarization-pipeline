"""Merge accepted part summaries into chapter summaries.

For every chapter in Work/parts_manifest.json whose parts are all accepted,
concatenate the reviewed part summaries in part order under a single
`## {title}` heading and write the result to the chapter summary path.

Usage:
    python Work/merge_chapters.py            # merge every ready chapter
    python Work/merge_chapters.py <slug> <unit_id> [<slug> <unit_id> ...]
    python Work/merge_chapters.py --dry-run  # report without writing
    python Work/merge_chapters.py --force <slug> <unit_id>   # overwrite an edited chapter

A chapter is ready when every part has status `accepted`. Chapters already
marked accepted, and unsplit chapters, are skipped. The script does not
change part or chapter status; set those with Work/set_status.py after the
transition review.

The chapter summary is canonical once merged: transition review,
verification, and later passes edit it, never the part summaries. Each merge
records the SHA-256 of what it wrote as `merged_sha` in the parts manifest.
If the chapter file already exists and differs from that record (or there
is no record), it has been edited since the merge, and the script refuses to
overwrite it. Use --force with an explicit slug and unit only after a real
rework of the parts, and archive the edited chapter first.

A part summary is refused, and nothing is written for its chapter, if it has
YAML frontmatter, an HTML comment (page, overlap, or owned-text marker), or
a heading other than `###`: part summaries are paragraphs, with `###` only
for the source's own section headings, and in one run a reviewer copied its
source's frontmatter and owned-text markers into its summary.
"""
import hashlib
import json
import re
import sys

from common import ROOT, review_ceiling
from count_words import words_in_text

PARTS_MANIFEST = ROOT / "Work" / "parts_manifest.json"


def load():
    return json.loads(PARTS_MANIFEST.read_text(encoding="utf-8"))


LEAKS = [
    (re.compile(r"\A---\n"), "YAML frontmatter"),
    (re.compile(r"<!--|-->"), "HTML comment (page or pipeline marker)"),
    (re.compile(r"(?m)^(#{1,2}|#{4,6}) "), "heading other than ###"),
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


def sha(data):
    return hashlib.sha256(data).hexdigest()


def edited_since_merge(entry):
    """True if the chapter file exists and is not exactly what the last merge wrote."""
    out = ROOT / entry["summary"]
    return out.exists() and sha(out.read_bytes()) != entry.get("merged_sha")


def merge_one(entry, dry_run):
    """Write the merged chapter; return its SHA-256, or None on a dry run."""
    slug, unit = entry["source_slug"], entry["unit_id"]
    texts = part_texts(entry)
    title = entry.get("title") or unit
    body = "\n\n".join(texts)
    chapter = "## %s\n\n%s\n" % (title, body) if body else "## %s\n" % title
    out = ROOT / entry["summary"]
    words = words_in_text(chapter)
    budget = entry.get("budget")
    flag = ""
    if budget and entry.get("words"):
        ceiling = review_ceiling(budget, entry["words"])
        if words > ceiling:
            flag = "  <-- ABOVE CEILING %d" % ceiling
    print("%s/%s: %d parts, %d words (budget %s)%s" % (slug, unit, len(texts), words, budget, flag))
    if dry_run:
        return None
    data = chapter.encode("utf-8")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return sha(data)


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    force = "--force" in args
    args = [a for a in args if a not in ("--dry-run", "--force")]
    if force and not args:
        raise SystemExit("--force needs an explicit <slug> <unit_id>")
    wanted = set()
    if args:
        if len(args) % 2:
            raise SystemExit(__doc__)
        for i in range(0, len(args), 2):
            wanted.add((args[i], args[i + 1]))

    entries = load()
    merged = skipped = 0
    refused = []
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
        if edited_since_merge(entry) and not force:
            refused.append("%s/%s" % key)
            continue
        digest = merge_one(entry, dry_run)
        if digest:
            entry["merged_sha"] = digest
            PARTS_MANIFEST.write_text(json.dumps(entries, indent=1), encoding="utf-8", newline="\n")
        merged += 1
    print("%s %d chapter(s); skipped %d" % ("would merge" if dry_run else "merged", merged, skipped))
    for r in refused:
        print("REFUSED %s: the chapter summary was edited after its last merge (or was not written by this "
              "script); later edits live there. Archive it and rerun with --force only after reworking the parts." % r)
    if refused:
        sys.exit(1)


if __name__ == "__main__":
    main()
