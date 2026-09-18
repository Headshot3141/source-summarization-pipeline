"""Assemble Summary.md from the accepted chapter summaries in Work/manifest.json.

Includes only units marked accepted, in manifest order, grouped under the
PARTS headings. Refuses to write anything if:
- a unit is neither accepted nor blocked (the work is unfinished);
- a blocked unit has no LIMITATIONS entry to disclose;
- a manifest path is missing, duplicated, outside the project, or matches
  no part in PARTS;
- a chapter summary does not open with exactly one ## heading, or has a
  level-1 heading;
- the assembled text has a leftover marker, page reference, footnote,
  working-file reference, leaked review note, or unfilled placeholder.

When blocked units remain, the introduction gets a notice that the summary
is partial, listing the omitted units and their limitations.
"""
import json
import re
import sys

from common import ROOT
from count_words import words_in_text

SUMS = ROOT / "Work" / "Summaries"
MANIFEST = ROOT / "Work" / "manifest.json"
PARTS_MANIFEST = ROOT / "Work" / "parts_manifest.json"
OUT = ROOT / "Summary.md"

PARTS = [
    ("", "# Part 1: {Title}"),
]

INTRO = """# Introduction

{Identify the sources, scope, and organization without adding substantive claims.}
"""

# For each blocked unit, a reader-facing description of the limitation,
# keyed "source_slug/unit_id". Required for every blocked unit.
LIMITATIONS = {}

TEXT_CHECKS = [
    (re.compile(r"<!--|-->"), "leftover HTML comment (page or pipeline marker)"),
    (re.compile(r"\bpp?\. ?\d+|\bpages? \d+|\(p\. ?\d+"), "page reference"),
    (re.compile(r"\[\^[^\]]*\]"), "footnote"),
    (re.compile(r"Work/|\b[\w-]+\.md\b"), "working-file reference"),
    (re.compile(
        r"(?im)^[\s*_>-]*(?:final |measured )?(?:prose )?(?:word count|word budget|budget|deviation|status|"
        r"changelog|review(?:er)? notes?|unresolved(?: issues?)?|source ambiguit(?:y|ies)|"
        r"note to (?:the )?(?:reviewer|coordinator))[*_]*\s*:"), "leaked review note"),
    (re.compile(r"\b(?:TODO|FIXME|TBD|XXX)\b"), "placeholder"),
    (re.compile(r"\{[^{}\n]*\}"), "unfilled template placeholder"),
]


def load_manifest():
    if not MANIFEST.exists():
        sys.exit("Work/manifest.json not found")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def unit_titles():
    """{(slug, unit_id): (source part, title)} from the parts manifest, if present."""
    if not PARTS_MANIFEST.exists():
        return {}
    return {
        (c["source_slug"], c["unit_id"]): (c.get("part"), c.get("title") or c["unit_id"])
        for c in json.loads(PARTS_MANIFEST.read_text(encoding="utf-8"))
    }


def accepted_paths(manifest, problems):
    root = ROOT.resolve()
    seen, paths = set(), []
    for entry in manifest:
        if entry["status"] != "accepted":
            continue
        path = (ROOT / entry["path"]).resolve()
        if not path.is_relative_to(root):
            problems.append("manifest path escapes the project root: %s" % entry["path"])
        elif path in seen:
            problems.append("duplicate manifest entry: %s" % entry["path"])
        elif not path.exists():
            problems.append("accepted unit is missing: %s" % entry["path"])
        else:
            seen.add(path)
            paths.append(path)
    return paths


def partial_notice(blocked, titles):
    lines = [
        "This summary is partial. The following units could not be summarized reliably and are omitted:",
        "",
    ]
    for e in blocked:
        part, title = titles.get((e["source_slug"], e["unit_id"]), (None, e["unit_id"]))
        where = "Part %s, " % part if part else ""
        lines.append("- %s%s: %s" % (where, title, LIMITATIONS[e["source_slug"] + "/" + e["unit_id"]]))
    return "\n".join(lines) + "\n"


def check_chapter(path, text, problems):
    name = path.relative_to(ROOT).as_posix()
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines or not lines[0].startswith("## "):
        problems.append("%s: does not open with a ## chapter heading" % name)
    if sum(1 for ln in lines if ln.startswith("## ")) > 1:
        problems.append("%s: has more than one ## heading" % name)
    if any(ln.startswith("# ") for ln in lines):
        problems.append("%s: has a level-1 heading" % name)


def check_text(text, problems):
    for n, line in enumerate(text.splitlines(), 1):
        for pattern, label in TEXT_CHECKS:
            m = pattern.search(line)
            if m:
                problems.append("Summary.md line %d: %s: %r" % (n, label, line[max(0, m.start() - 30):m.end() + 30]))


def main():
    manifest = load_manifest()
    problems = []

    unfinished = [e for e in manifest if e["status"] not in ("accepted", "blocked")]
    for e in unfinished:
        problems.append("%s/%s is %s: accept it or mark it blocked before assembly" % (e["source_slug"], e["unit_id"], e["status"]))
    blocked = [e for e in manifest if e["status"] == "blocked"]
    for e in blocked:
        if not LIMITATIONS.get(e["source_slug"] + "/" + e["unit_id"]):
            problems.append("%s/%s is blocked: add its limitation to LIMITATIONS" % (e["source_slug"], e["unit_id"]))

    accepted = accepted_paths(manifest, problems)
    if not accepted and not problems:
        problems.append("no accepted units in Work/manifest.json")

    intro = INTRO.strip() + "\n"
    if blocked and not problems:
        intro += "\n" + partial_notice(blocked, unit_titles())
    pieces, chapters, used = [intro], [], set()
    for slug, heading in PARTS:
        folder = (SUMS / slug).resolve()
        files = [p for p in accepted if p.parent == folder]
        if not files:
            continue
        pieces.append(heading)
        for path in files:
            body = path.read_text(encoding="utf-8").strip()
            check_chapter(path, body, problems)
            pieces.append(body)
            chapters.append(body)
            used.add(path)
            print("%-18s %s" % (slug, path.name))
    unmatched = [p.relative_to(ROOT).as_posix() for p in accepted if p not in used]
    if unmatched:
        problems.append("accepted units matched no part in PARTS: %s" % ", ".join(unmatched))

    text = "\n\n".join(pieces).strip() + "\n"
    check_text(text, problems)
    if problems:
        print("assemble: Summary.md not written. Fix these first:")
        for p in problems:
            print("  " + p)
        sys.exit(1)

    OUT.write_text(text, encoding="utf-8", newline="\n")
    intro_words = words_in_text(intro)
    body_words = sum(words_in_text(c) for c in chapters)
    print("wrote %s" % OUT.relative_to(ROOT).as_posix())
    print("introduction: %d words; chapter summaries: %d words; %d chapter(s)" % (intro_words, body_words, len(chapters)))
    if blocked:
        print("PARTIAL: %d blocked unit(s) omitted and listed in the introduction" % len(blocked))


if __name__ == "__main__":
    main()
