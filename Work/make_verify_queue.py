"""Write Work/verify_queue.txt: one verification task per processing unit.

Each line drives one verifier or remediation task (passes/verification-pass.md):

    slug|unit_id|part_index|part_count|source|prev|next|summary|record

source is the part file the summarizer worked from (the chapter file for an
unsplit chapter). prev and next are the neighbouring part files, given as
context so the verifier can follow references across the boundary without
reading the whole chapter; "-" where there is none. summary is the canonical
chapter summary; the verifier checks only the stretch that covers source's
owned text. record is Work/Reviews/{slug}/verify-round{N}/{part file name}.

With --whole, each chapter is one task instead, whatever its parts:
part_index and part_count are 1, source is the chapter file
(Work/Chapters/{slug}/{file}), prev and next are "-", summary is the
canonical chapter summary, checked whole, and record is
Work/Reviews/{slug}/verify-round{N}/{chapter file name}, without a part
suffix. One verifier then reads the whole chapter, so the seams between
parts are covered and there is one writer per summary with no part order to
keep. Use it for chapters whose source one verifier reads comfortably (one
run verified whole chapters of up to 92KB); a chapter file larger than
WHOLE_MAX_BYTES is still listed part by part, with a note.

Only accepted chapters are listed (verification runs after acceptance).

The queue is Work/verify_queue.txt, or Work/verify_queue_round{N}.txt when
--round N is given, so each round keeps its own list; --out PATH (relative
to the project root) writes it elsewhere.

Usage:
    python Work/make_verify_queue.py [--round N] [--whole] [--out PATH] [<slug> <unit_id> ...]
"""
import json
import sys
from pathlib import Path, PurePosixPath

from common import ROOT, utf8_output

MANIFEST = ROOT / "Work" / "parts_manifest.json"
QUEUE = ROOT / "Work" / "verify_queue.txt"
# --whole lists a chapter part by part when its file is larger than this.
WHOLE_MAX_BYTES = 100_000


def take_option(args, name, convert=str):
    """The value after option name in args (removing both), or None."""
    if name not in args:
        return None
    i = args.index(name)
    try:
        value = convert(args[i + 1])
    except (IndexError, ValueError):
        raise SystemExit("%s needs a %s" % (name, "number" if convert is int else "value"))
    del args[i:i + 2]
    return value


def chapter_source(e):
    """The chapter file a unit was split from."""
    if e.get("chapter_source"):
        return e["chapter_source"]
    if len(e["parts"]) == 1:
        return e["parts"][0]["source"]
    return "Work/Chapters/%s/%s" % (e["source_slug"], PurePosixPath(e["summary"]).name)


def part_lines(e, round_no):
    """One task line per part of chapter entry e."""
    key = (e["source_slug"], e["unit_id"])
    parts = sorted(e["parts"], key=lambda p: p["part_index"])
    lines = []
    for i, p in enumerate(parts):
        prev = parts[i - 1]["source"] if i > 0 else "-"
        nxt = parts[i + 1]["source"] if i + 1 < len(parts) else "-"
        record = "Work/Reviews/%s/verify-round%d/%s" % (key[0], round_no, PurePosixPath(p["source"]).name)
        lines.append("|".join([key[0], key[1], str(p["part_index"]), str(len(parts)),
                               p["source"], prev, nxt, e["summary"], record]))
    return lines


def whole_line(e, round_no, source):
    """One task line for chapter entry e, verified whole."""
    record = "Work/Reviews/%s/verify-round%d/%s" % (e["source_slug"], round_no, PurePosixPath(source).name)
    return "|".join([e["source_slug"], e["unit_id"], "1", "1", source, "-", "-", e["summary"], record])


def main():
    utf8_output()
    args = sys.argv[1:]
    round_no = take_option(args, "--round", int)
    out = take_option(args, "--out")
    whole = "--whole" in args
    if whole:
        args.remove("--whole")
    if len(args) % 2 or any(a.startswith("--") for a in args):
        raise SystemExit(__doc__)
    wanted = {(args[i], args[i + 1]) for i in range(0, len(args), 2)}
    if not MANIFEST.exists():
        sys.exit("Work/parts_manifest.json not found; run Work/split_parts.py first")
    if out:
        queue = Path(out) if Path(out).is_absolute() else ROOT / out
    elif round_no is not None:
        queue = QUEUE.with_name("%s_round%d%s" % (QUEUE.stem, round_no, QUEUE.suffix))
    else:
        queue = QUEUE

    lines, notes = [], []
    for e in json.loads(MANIFEST.read_text(encoding="utf-8")):
        key = (e["source_slug"], e["unit_id"])
        if (wanted and key not in wanted) or e["status"] != "accepted":
            continue
        if whole:
            source = chapter_source(e)
            path = ROOT / source
            size = path.stat().st_size if path.exists() else 0
            if not path.exists():
                notes.append("%s/%s: chapter file %s not found" % (key[0], key[1], source))
            if size <= WHOLE_MAX_BYTES:
                lines.append(whole_line(e, round_no or 1, source))
                continue
            notes.append("%s/%s: %s is %d bytes, over WHOLE_MAX_BYTES (%d); listed part by part"
                         % (key[0], key[1], source, size, WHOLE_MAX_BYTES))
        lines += part_lines(e, round_no or 1)
    queue.parent.mkdir(parents=True, exist_ok=True)
    queue.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8", newline="\n")
    try:
        name = queue.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        name = queue.as_posix()
    print("%d verification task(s) in %s" % (len(lines), name))
    for n in notes:
        print("note: " + n)


if __name__ == "__main__":
    main()
