"""Write Work/verify_queue.txt: one verification task per processing unit.

Each line drives one verifier or remediation task (passes/verification-pass.md):

    slug|unit_id|part_index|part_count|source|prev|next|summary|record

source is the part file the summarizer worked from (the chapter file for an
unsplit chapter). prev and next are the neighbouring part files, given as
context so the verifier can follow references across the boundary without
reading the whole chapter; "-" where there is none. summary is the canonical
chapter summary; the verifier checks only the stretch that covers source's
owned text. record is Work/Reviews/{slug}/verify-round{N}/{part file name}.

Only accepted chapters are listed (verification runs after acceptance).

Usage:
    python Work/make_verify_queue.py [--round N] [<slug> <unit_id> ...]
"""
import json
import sys
from pathlib import PurePosixPath

from common import ROOT

MANIFEST = ROOT / "Work" / "parts_manifest.json"
QUEUE = ROOT / "Work" / "verify_queue.txt"


def main():
    args = sys.argv[1:]
    round_no = 1
    if "--round" in args:
        i = args.index("--round")
        try:
            round_no = int(args[i + 1])
        except (IndexError, ValueError):
            raise SystemExit("--round needs a number")
        del args[i:i + 2]
    if len(args) % 2:
        raise SystemExit(__doc__)
    wanted = {(args[i], args[i + 1]) for i in range(0, len(args), 2)}
    if not MANIFEST.exists():
        sys.exit("Work/parts_manifest.json not found; run Work/split_parts.py first")

    lines = []
    for e in json.loads(MANIFEST.read_text(encoding="utf-8")):
        key = (e["source_slug"], e["unit_id"])
        if (wanted and key not in wanted) or e["status"] != "accepted":
            continue
        parts = sorted(e["parts"], key=lambda p: p["part_index"])
        for i, p in enumerate(parts):
            prev = parts[i - 1]["source"] if i > 0 else "-"
            nxt = parts[i + 1]["source"] if i + 1 < len(parts) else "-"
            record = "Work/Reviews/%s/verify-round%d/%s" % (key[0], round_no, PurePosixPath(p["source"]).name)
            lines.append("|".join([key[0], key[1], str(p["part_index"]), str(len(parts)),
                                   p["source"], prev, nxt, e["summary"], record]))
    QUEUE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8", newline="\n")
    print("%d verification task(s)" % len(lines))


if __name__ == "__main__":
    main()
