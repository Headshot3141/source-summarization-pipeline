"""Write Work/whole_doc_chunks.txt: the chunks for the whole-document review.

Groups the accepted chapter summaries, in manifest order, into chunks that
one fresh-context reviewer reads as an unfamiliar reader (plan.md Step 11).
A chunk closes when adding the next chapter would pass MAX_BYTES or
MAX_CHAPTERS. Chunks run across source boundaries on purpose, so the
reviewers also see the transitions between parts.

    CHUNK 1: Work/Summaries/a/01-x.md ; Work/Summaries/a/02-y.md ; ...

Usage: python Work/make_doc_chunks.py [--max-bytes N] [--max-chapters N]
"""
import json
import sys

from common import ROOT

MANIFEST = ROOT / "Work" / "manifest.json"
OUT = ROOT / "Work" / "whole_doc_chunks.txt"
# Summaries only, no source text, so a chunk can be larger than a source
# part; keep it well inside the reviewer's context with room for its notes.
MAX_BYTES = 150_000
MAX_CHAPTERS = 10


def chunks(entries, max_bytes, max_chapters):
    out, cur, size = [], [], 0
    for e in entries:
        n = (ROOT / e["path"]).stat().st_size
        if cur and (size + n > max_bytes or len(cur) >= max_chapters):
            out.append(cur)
            cur, size = [], 0
        cur.append(e["path"])
        size += n
    if cur:
        out.append(cur)
    return out


def main():
    args = sys.argv[1:]
    opts = {"--max-bytes": MAX_BYTES, "--max-chapters": MAX_CHAPTERS}
    while args:
        if args[0] not in opts or len(args) < 2:
            raise SystemExit(__doc__)
        opts[args[0]] = int(args[1])
        args = args[2:]
    if not MANIFEST.exists():
        sys.exit("Work/manifest.json not found")
    entries = [e for e in json.loads(MANIFEST.read_text(encoding="utf-8")) if e["status"] == "accepted"]
    missing = [e["path"] for e in entries if not (ROOT / e["path"]).exists()]
    if missing:
        sys.exit("missing summaries:\n  " + "\n  ".join(missing))
    groups = chunks(entries, opts["--max-bytes"], opts["--max-chapters"])
    lines = ["CHUNK %d: %s" % (i, " ; ".join(g)) for i, g in enumerate(groups, 1)]
    OUT.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8", newline="\n")
    print("%d accepted chapter(s) in %d chunk(s)" % (len(entries), len(groups)))


if __name__ == "__main__":
    main()
