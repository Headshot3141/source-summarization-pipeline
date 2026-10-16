"""Write Work/whole_doc_chunks.txt: the chunks for the whole-document review.

Groups the Introduction (Work/Introduction.md) and the accepted chapter
summaries, in manifest order, into chunks that one fresh-context reviewer
reads as an unfamiliar reader (plan.md Step 11). The Introduction opens
chunk 1 and counts toward its bytes, but not toward its chapters. A chunk
closes when adding the next chapter would pass MAX_BYTES or MAX_CHAPTERS.
Chunks run across source boundaries on purpose, so the reviewers also see
the transitions between parts.

    CHUNK 1: Work/Introduction.md ; Work/Summaries/a/01-x.md ; ...
    CHUNK 2: Work/Summaries/a/04-z.md ; ...

Chunks are small on purpose. A reviewer with a few chapters reads sentence
by sentence; one with many reads for the argument and passes over sentences
that are hard to parse. In one run, a first round with chunks of about eight
chapters (130-165KB) found about 258 problems, and a second round with
three-chapter chunks then found about 320 more in the text already fixed,
nearly all hard-to-parse sentences. The defaults buy that close reading at
about three times the reviewers.

Usage:
    python Work/make_doc_chunks.py [--max-bytes N] [--max-chapters N] [--out PATH]

--out writes the list somewhere other than Work/whole_doc_chunks.txt (a
path relative to the project root), so a second review round keeps the
first round's list.
"""
import json
import sys
from pathlib import Path

from common import ROOT, utf8_output

MANIFEST = ROOT / "Work" / "manifest.json"
OUT = ROOT / "Work" / "whole_doc_chunks.txt"
# The Introduction, relative to the project root (ROOT may be moved).
INTRO = "Work/Introduction.md"
# Small chunks, so the reviewer reads each sentence (see above).
MAX_BYTES = 60_000
MAX_CHAPTERS = 3


def chunks(entries, max_bytes, max_chapters, lead=None):
    """[[path, ...], ...]: entries' paths grouped into chunks. lead, if
    given, is a path that opens the first chunk and counts toward its bytes
    but not its chapters."""
    out, cur, size, count = [], [], 0, 0
    if lead:
        cur, size = [lead], (ROOT / lead).stat().st_size
    for e in entries:
        n = (ROOT / e["path"]).stat().st_size
        if count and (size + n > max_bytes or count >= max_chapters):
            out.append(cur)
            cur, size, count = [], 0, 0
        cur.append(e["path"])
        size += n
        count += 1
    if cur:
        out.append(cur)
    return out


def main():
    utf8_output()
    args = sys.argv[1:]
    opts = {"--max-bytes": MAX_BYTES, "--max-chapters": MAX_CHAPTERS, "--out": None}
    while args:
        if args[0] not in opts or len(args) < 2:
            raise SystemExit(__doc__)
        try:
            opts[args[0]] = args[1] if args[0] == "--out" else int(args[1])
        except ValueError:
            raise SystemExit("%s needs a number" % args[0])
        args = args[2:]
    out = OUT
    if opts["--out"]:
        out = Path(opts["--out"])
        if not out.is_absolute():
            out = ROOT / out
    if not MANIFEST.exists():
        sys.exit("Work/manifest.json not found")
    entries = [e for e in json.loads(MANIFEST.read_text(encoding="utf-8")) if e["status"] == "accepted"]
    missing = [e["path"] for e in entries if not (ROOT / e["path"]).exists()]
    if missing:
        sys.exit("missing summaries:\n  " + "\n  ".join(missing))
    lead = INTRO if (ROOT / INTRO).exists() else None
    if not lead:
        print("note: %s not found; chunk 1 starts without the Introduction" % INTRO)
    groups = chunks(entries, opts["--max-bytes"], opts["--max-chapters"], lead)
    lines = ["CHUNK %d: %s" % (i, " ; ".join(g)) for i, g in enumerate(groups, 1)]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8", newline="\n")
    print("%d accepted chapter(s) in %d chunk(s)%s" % (
        len(entries), len(groups), ", the Introduction first" if lead else ""))


if __name__ == "__main__":
    main()
