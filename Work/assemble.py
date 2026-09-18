import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUMS = os.path.join(ROOT, "Work", "Summaries")
MANIFEST = os.path.join(ROOT, "Work", "manifest.json")
OUT = os.path.join(ROOT, "Summary.md")

PARTS = [
    ("", "# Part 1: {Title}"),
]

INTRO = """# Introduction

{Identify the sources, scope, and organization without adding substantive claims.}
"""


def accepted_paths():
    if not os.path.exists(MANIFEST):
        raise SystemExit("Work/manifest.json not found")
    with open(MANIFEST, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    root = os.path.normcase(os.path.normpath(ROOT))
    seen = set()
    paths = []
    for entry in manifest:
        if entry["status"] != "accepted":
            continue
        path = os.path.normpath(os.path.join(ROOT, entry["path"]))
        if not os.path.normcase(path).startswith(root):
            raise SystemExit("manifest path escapes the project root: %s" % entry["path"])
        if os.path.normcase(path) in seen:
            raise SystemExit("duplicate manifest entry: %s" % entry["path"])
        if not os.path.exists(path):
            raise SystemExit("accepted unit is missing: %s" % entry["path"])
        seen.add(os.path.normcase(path))
        paths.append(path)
    return paths


def main():
    accepted = accepted_paths()
    if not accepted:
        raise SystemExit("no accepted units in Work/manifest.json")
    pieces = [INTRO]
    total = 0
    used = []
    for slug, heading in PARTS:
        folder = os.path.normcase(os.path.normpath(os.path.join(SUMS, slug)))
        files = [p for p in accepted if os.path.normcase(os.path.dirname(p)) == folder]
        if not files:
            continue
        pieces.append(heading)
        for path in files:
            with open(path, "r", encoding="utf-8") as fh:
                body = fh.read().strip()
            pieces.append(body)
            total += len(body.split())
            used.append(path)
            print("%-18s %s" % (slug, os.path.basename(path)))
    unmatched = [os.path.relpath(p, ROOT) for p in accepted if p not in used]
    if unmatched:
        raise SystemExit("accepted units matched no part in PARTS: %s" % ", ".join(unmatched))
    text = "\n\n".join(pieces).strip() + "\n"
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("wrote %s: %d words" % (OUT, len(text.split())))


if __name__ == "__main__":
    main()
