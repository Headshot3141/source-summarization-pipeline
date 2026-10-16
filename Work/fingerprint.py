"""Hash every project file, to prove that a report-only run changed nothing.

A report-only run (passes/validation-run.md) promises the user that no
summary, source, or record was touched. Instructions alone do not prove it:
hash every file before the run and compare afterwards. In one run, 276
agents read the whole project and the comparison showed no file changed.

save     SHA-256 of every file under the project root, tracked, untracked,
         and ignored alike, except .git/, __pycache__/, the output file
         itself, and each --exclude path (a file, or a folder and everything
         under it, relative to the project root). Writes JSON to --out.
compare  Hashes the files again, skipping the excludes given now and those
         recorded at save time, and lists every added, removed, and changed
         file. Exits 1 if anything changed, 0 if nothing did.

Exclude only what the run is allowed to write, normally its own prompt
folder (Work/Prompts/<run>/): the assignment files, the agents' outputs on
the Agent-tool route, and the workflow result.

Usage (from the project root):
    python Work/fingerprint.py save [--out FILE] [--exclude PATH ...]
    python Work/fingerprint.py compare [--out FILE] [--exclude PATH ...]

--out defaults to Work/fingerprint.json; a path inside the project is
excluded from the hashes automatically.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath

from common import ROOT, utf8_output

DEFAULT_OUT = "Work/fingerprint.json"
SKIP_PARTS = {".git", "__pycache__"}


def norm_exclude(path, root):
    """An exclude as a project-relative POSIX path without a trailing slash."""
    p = Path(path)
    if p.is_absolute():
        try:
            p = p.resolve().relative_to(Path(root).resolve())
        except ValueError:
            return None
    text = PurePosixPath(p.as_posix()).as_posix().strip("/")
    return None if text in ("", ".") else text


def excluded(rel, excludes):
    """True if rel (POSIX, relative) is an exclude or lies under one."""
    return any(rel == e or rel.startswith(e + "/") for e in excludes)


def snapshot(root, excludes=()):
    """{relative POSIX path: sha256 hex} for every file under root, minus skips."""
    root = Path(root)
    excludes = [e for e in excludes if e]
    out = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in SKIP_PARTS for part in rel.parts) or not p.is_file():
            continue
        key = rel.as_posix()
        if excluded(key, excludes):
            continue
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        out[key] = h.hexdigest()
    return out


def differences(before, now):
    """(added, removed, changed): sorted lists of paths."""
    added = sorted(set(now) - set(before))
    removed = sorted(set(before) - set(now))
    changed = sorted(k for k in set(now) & set(before) if now[k] != before[k])
    return added, removed, changed


def out_path(value, root):
    p = Path(value)
    return p if p.is_absolute() else Path(root) / p


def save(root, out, excludes):
    excludes = sorted({e for e in excludes if e})
    files = snapshot(root, excludes)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = {"excludes": excludes, "files": files}
    out.write_text(json.dumps(data, indent=0, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print("%d file(s) hashed; excluded: %s" % (len(files), ", ".join(excludes) or "nothing"))
    return 0


def compare(root, out, excludes):
    if not out.exists():
        sys.exit("%s not found; run `python Work/fingerprint.py save` before the run" % out)
    data = json.loads(out.read_text(encoding="utf-8"))
    before = data.get("files", data)
    excludes = sorted({e for e in list(excludes) + list(data.get("excludes", [])) if e})
    before = {k: v for k, v in before.items() if not excluded(k, excludes)}
    now = snapshot(root, excludes)
    added, removed, changed = differences(before, now)
    print("%d file(s) now, %d before; excluded: %s" % (len(now), len(before), ", ".join(excludes) or "nothing"))
    for label, items in (("ADDED", added), ("REMOVED", removed), ("CHANGED", changed)):
        print("%s: %d" % (label, len(items)))
        for k in items:
            print("  " + k)
    if added or removed or changed:
        return 1
    print("no file changed")
    return 0


def main(argv=None):
    utf8_output()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["save", "compare"])
    ap.add_argument("--out", default=DEFAULT_OUT, help="the hash file (default %(default)s)")
    ap.add_argument("--exclude", action="append", default=[], metavar="PATH",
                    help="a file or folder, relative to the project root, that the run may write")
    args = ap.parse_args(argv)
    out = out_path(args.out, ROOT)
    excludes = [norm_exclude(e, ROOT) for e in args.exclude]
    own = norm_exclude(out, ROOT)
    if own:
        excludes.append(own)
    code = (save if args.mode == "save" else compare)(ROOT, out, excludes)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
