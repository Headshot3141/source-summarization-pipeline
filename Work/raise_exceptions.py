"""Raise Work/budget_exceptions.json to the counts a gated later pass left.

After a post-run pass (verification, a fix pass, a style pass) the
coordinator has checked every edit, and the chapters that grew past their
ceilings or their approved max_words now flag ABOVE CEILING. For each such
unsettled flag on a summary that differs from the pass's snapshot, this
sets the exception's max_words to the current count and appends a history
entry:

    {pass} ({date}): {+d} words against {snapshot} ({pre} -> {now}); records in Work/Reviews/{slug}/{pass}/. {note}

creating the entry, with a one-sentence reason, if there is none. An
existing reason is kept: the reason says why the unit is approved above
its ceiling, the history what each pass added. It reports, and leaves
untouched: flags on summaries unchanged since the snapshot (the pass did
not cause them), summaries with no snapshot copy, keys holding an
exception of another kind, and every other flag (UNDER, draft flags, and
the document maximum, which needs the user's approval). --prune-stale also
deletes the part keys of merged chapters, which no longer settle anything.

The flags come from check_words.evaluate(), not from its printed report.

Usage:
    python Work/raise_exceptions.py <pass> [--snapshot DIR] [--note TEXT] [--dry-run] [--prune-stale]

<pass> names the pass as in its snapshot and records (verify-round2 compares
with Work/Summaries_preverify-round2/ and points to
Work/Reviews/{slug}/verify-round2/);
--snapshot DIR gives another snapshot folder, relative to the project root.
Prints "key old new" for each change (old is "-" for a new entry).
"""
import argparse
import datetime
import json
import re
import sys

import check_words
from common import ROOT, utf8_output
from count_words import words_of

SUMS = ROOT / "Work" / "Summaries"
NEW_REASON = ("Approved above its ceiling for confirmed fixes and restorations in later passes; "
              "the history gives each pass's growth.")


def shown(path):
    """A path relative to the project root, with forward slashes, for messages and history."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def normalized(path):
    """File text without a UTF-8 BOM and with LF line endings, so an editor's re-save is no change."""
    return path.read_bytes().decode("utf-8-sig").replace("\r\n", "\n")


def snapshot_copy(summary, snapshot):
    """The snapshot's copy of a summary path ("Work/Summaries/..."), or None if it lies elsewhere."""
    path = ROOT / summary
    try:
        inner = path.relative_to(SUMS)
    except ValueError:
        return None
    return snapshot / inner


def history_entry(pass_name, delta, snapshot, pre, now, slug, note):
    line = "%s (%s): %+d words against %s/ (%d -> %d); records in Work/Reviews/%s/%s/." % (
        pass_name, datetime.date.today().isoformat(), delta, shown(snapshot), pre, now, slug, pass_name)
    return line + (" " + note.strip() if note and note.strip() else "")


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Raise budget exceptions to the counts a gated pass left.")
    parser.add_argument("pass_name", metavar="pass", help="the pass name, as in its snapshot and records")
    parser.add_argument("--snapshot", help="snapshot folder (default Work/Summaries_pre<pass>/)")
    parser.add_argument("--note", default="", help="text added to each history entry")
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    parser.add_argument("--prune-stale", action="store_true", help="delete the part keys of merged chapters")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-z0-9-]+", args.pass_name):
        parser.error("pass must be lowercase letters, digits, and hyphens, as in its snapshot name")
    return args


def main():
    utf8_output()
    args = parse_args(sys.argv[1:])
    snapshot = ROOT / (args.snapshot or "Work/Summaries_pre" + args.pass_name)
    if not snapshot.is_dir():
        sys.exit(f"snapshot folder {snapshot} not found; give it with --snapshot")
    exceptions = check_words.load_exceptions()
    result = check_words.evaluate(exceptions)

    changes, left = [], []
    for f in result["flags"]:
        key, kind = f["key"], f["kind"]
        if kind == check_words.DOCUMENT_KIND:
            left.append(f"{key}: {f['text']}: above the maximum only with the user's approval, recorded by hand")
            continue
        if kind != "ABOVE CEILING":
            left.append(f"{key}: {kind} flag, not raised here: {f['text']}")
            continue
        current = exceptions.get(key)
        if current and current.get("flag") != kind:
            left.append(f"{key}: holds a {current.get('flag')} exception, not ABOVE CEILING; settle it by hand")
            continue
        copy = snapshot_copy(f["path"], snapshot)
        if copy is None or not copy.exists():
            left.append(f"{key}: {f['path']} has no copy in {shown(snapshot)}/; settle it by hand")
            continue
        if normalized(copy) == normalized(ROOT / f["path"]):
            left.append(f"{key}: {f['path']} is unchanged since {shown(snapshot)}/; this pass did not cause the flag")
            continue
        pre, now = words_of(copy), f["words"]
        entry = dict(current) if current else {"flag": kind, "max_words": now, "reason": NEW_REASON}
        old = current["max_words"] if current else None
        entry["max_words"] = now
        slug = key.split("/", 1)[0]
        entry["history"] = list(entry.get("history", [])) + [
            history_entry(args.pass_name, now - pre, snapshot, pre, now, slug, args.note)]
        exceptions[key] = entry
        changes.append((key, "-" if old is None else old, now))

    pruned = []
    if args.prune_stale:
        for key in result["superseded"]:
            del exceptions[key]
            pruned.append(key)

    for key, old, new in changes:
        print(key, old, new)
    for key in pruned:
        print(f"pruned {key}: a part key of a merged chapter")
    for line in left:
        print("left " + line)
    if result["superseded"] and not args.prune_stale:
        print("%d part exception(s) superseded by merged chapters; --prune-stale deletes them" %
              len(result["superseded"]))
    if not (changes or pruned):
        print("nothing to change")
    elif args.dry_run:
        print("dry run: nothing written (%d change(s), %d pruned)" % (len(changes), len(pruned)))
    else:
        check_words.EXCEPTIONS.write_text(json.dumps(exceptions, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8", newline="\n")
        print("wrote %d change(s), %d pruned, to %s" % (len(changes), len(pruned), shown(check_words.EXCEPTIONS)))


if __name__ == "__main__":
    main()
