"""Coordinator helper: update statuses in Work/parts_manifest.json and Work/manifest.json.

Usage:
    python Work/set_status.py part <status> <slug> <unit_id> <part_index> [<part_index> ...]
    python Work/set_status.py chapter <status> <slug> <unit_id>
    python Work/set_status.py pending            # list units not yet accepted

<status> is one of pending, drafted, accepted, blocked.

`part` sets the listed part statuses. For an unsplit chapter (one part) it
also sets the chapter status in both manifests, keeping them in sync.
`chapter` sets the chapter status in the parts manifest and the matching
entry in the chapter manifest. Setting a chapter to `accepted` is refused
while any of its parts is not accepted. Only the coordinator runs this,
after checking the output and review record.
"""
import json
import sys

from common import ROOT

PARTS = ROOT / "Work" / "parts_manifest.json"
MANIFEST = ROOT / "Work" / "manifest.json"
STATUSES = ("pending", "drafted", "accepted", "blocked")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, data):
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def find(parts, slug, unit):
    for entry in parts:
        if entry["source_slug"] == slug and entry["unit_id"] == unit:
            return entry
    raise SystemExit("no such unit: %s/%s" % (slug, unit))


def set_chapter(parts, entry, status):
    if status == "accepted":
        open_parts = [p["part_index"] for p in entry["parts"] if p["status"] != "accepted"]
        if open_parts:
            raise SystemExit("%s/%s: parts %s are not accepted" % (entry["source_slug"], entry["unit_id"], open_parts))
    entry["status"] = status
    manifest = load(MANIFEST)
    found = False
    for m in manifest:
        if m["source_slug"] == entry["source_slug"] and m["unit_id"] == entry["unit_id"]:
            m["status"] = status
            found = True
    if not found:
        raise SystemExit("%s/%s is not in Work/manifest.json" % (entry["source_slug"], entry["unit_id"]))
    save(PARTS, parts)
    save(MANIFEST, manifest)


def list_pending(parts):
    for entry in parts:
        open_parts = [p["part_index"] for p in entry["parts"] if p["status"] != "accepted"]
        if open_parts or entry["status"] != "accepted":
            print("%s %s chapter=%s parts=%s budget=%s" % (
                entry["source_slug"], entry["unit_id"], entry["status"],
                ",".join("%d:%s" % (p["part_index"], p["status"]) for p in entry["parts"]),
                entry.get("budget")))


def main():
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    parts = load(PARTS)
    cmd = args[0]
    if cmd == "pending":
        list_pending(parts)
        return
    if len(args) < 4 or args[1] not in STATUSES:
        raise SystemExit(__doc__)
    status, slug, unit = args[1], args[2], args[3]
    entry = find(parts, slug, unit)
    if cmd == "part":
        try:
            indexes = {int(i) for i in args[4:]}
        except ValueError:
            raise SystemExit(__doc__)
        known = {p["part_index"] for p in entry["parts"]}
        if not indexes or indexes - known:
            raise SystemExit("%s/%s: part indexes must be among %s" % (slug, unit, sorted(known)))
        for p in entry["parts"]:
            if p["part_index"] in indexes:
                p["status"] = status
        if len(entry["parts"]) == 1:
            set_chapter(parts, entry, status)
        else:
            if status != "accepted" and entry["status"] == "accepted":
                # A split chapter loses acceptance when any part reopens.
                set_chapter(parts, entry, "drafted")
            save(PARTS, parts)
        print("set %s/%s parts %s -> %s" % (slug, unit, sorted(indexes), status))
    elif cmd == "chapter":
        set_chapter(parts, entry, status)
        print("set chapter %s/%s -> %s" % (slug, unit, status))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
