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
is no record), it has been edited since the merge. If the part summaries
would merge to exactly what was merged before, the chapter is kept and
reported, which is the normal case during transition review. If the parts
have changed, the script refuses to overwrite the edited chapter and exits
1. Use --force with an explicit slug and unit only after a real rework of
the parts, and archive the edited chapter first. The manifest is reread
before each record is written, so a status set meanwhile is kept.

A chapter whose part summaries cannot be merged is reported as NOT MERGED,
the other chapters are still processed, and the script exits 1. A part
summary is refused, and nothing is written for its chapter, if it is
missing or has
YAML frontmatter, an HTML comment (page, overlap, or owned-text marker), or
a heading other than `###`: part summaries are paragraphs, with `###` only
for the source's own section headings, and in one run a reviewer copied its
source's frontmatter and owned-text markers into its summary.
"""
import hashlib
import json
import re
import sys

from common import ROOT, review_ceiling, utf8_output
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
    (a bibliography, say); record it as a scope exception in checks.md and
    settle its UNDER flag in Work/budget_exceptions.json.
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


def normalized(data):
    """File bytes without a UTF-8 BOM and with LF line endings."""
    return data.decode("utf-8-sig").replace("\r\n", "\n").encode("utf-8")


def build_chapter(entry):
    """Return (chapter text, number of non-empty parts) from the reviewed part summaries."""
    texts = part_texts(entry)
    title = entry.get("title") or entry["unit_id"]
    body = "\n\n".join(texts)
    return ("## %s\n\n%s\n" % (title, body) if body else "## %s\n" % title), len(texts)


def report(entry, chapter, nparts):
    words = words_in_text(chapter)
    budget = entry.get("budget")
    # The ceiling split_parts.py stored; recomputed only for a manifest without one.
    ceiling = entry.get("ceiling")
    if ceiling is None and budget is not None and entry.get("words"):
        ceiling = review_ceiling(budget, entry.get("budget_words", entry["words"]))
    flag = "  <-- ABOVE CEILING %d" % ceiling if ceiling is not None and words > ceiling else ""
    print("%s/%s: %d parts, %d words (budget %s)%s" % (
        entry["source_slug"], entry["unit_id"], nparts, words, budget, flag))


def record_merge(key, digest):
    """Store merged_sha on the chapter's entry, rereading the manifest so a
    status change made since this script started is not overwritten."""
    entries = load()
    for e in entries:
        if (e["source_slug"], e["unit_id"]) == key:
            e["merged_sha"] = digest
    PARTS_MANIFEST.write_text(json.dumps(entries, indent=1), encoding="utf-8", newline="\n")


def main():
    utf8_output()
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

    merged = skipped = 0
    kept, refused, problems = [], [], []
    for entry in load():
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
        out = ROOT / entry["summary"]
        # Compare content, not bytes: a BOM or CRLF line endings added by an
        # editor are not edits.
        current = sha(normalized(out.read_bytes())) if out.exists() else None
        edited = current is not None and current != entry.get("merged_sha")
        try:
            chapter, nparts = build_chapter(entry)
        except SystemExit as exc:
            # A missing or leaky part summary: report it and go on with the
            # other chapters. An edited chapter is safe either way.
            problems.append("%s/%s: %s" % (key[0], key[1], exc.code))
            skipped += 1
            continue
        data = chapter.encode("utf-8")
        if edited and not force:
            if sha(data) == entry.get("merged_sha"):
                # Parts unchanged since the last merge; the chapter carries later
                # edits (seam fixes, remediation). Nothing to do.
                kept.append("%s/%s" % key)
            elif sha(data) == current:
                # The chapter already equals a fresh merge; just record it.
                if not dry_run:
                    record_merge(key, current)
                kept.append("%s/%s" % key)
            else:
                refused.append("%s/%s" % key)
            skipped += 1
            continue
        report(entry, chapter, nparts)
        if not dry_run:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            record_merge(key, sha(data))
        merged += 1
    print("%s %d chapter(s); skipped %d" % ("would merge" if dry_run else "merged", merged, skipped))
    for k in kept:
        print("kept %s: the chapter summary stays as it is (its parts are unchanged since the last merge, "
              "or it already equals a fresh merge)" % k)
    for r in refused:
        print("REFUSED %s: the part summaries changed, but the chapter summary was edited after its last merge "
              "(or was not written by this script), and those edits live there. Archive it and rerun with "
              "--force only after reworking the parts." % r)
    for p in problems:
        print("NOT MERGED %s" % p)
    if refused or problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
