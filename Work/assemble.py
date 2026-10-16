"""Assemble Summary.md from the Introduction and the accepted chapter summaries.

The Introduction is Work/Introduction.md, a file like the chapter summaries,
so that whole-document reviewers read it and passes can edit it in place;
it starts with "# Introduction". Then come the units marked accepted in
Work/manifest.json, in manifest order, grouped under the PARTS headings.
Refuses to write anything if:
- a unit is neither accepted nor blocked (the work is unfinished);
- a blocked unit has no LIMITATIONS entry to disclose;
- a manifest path is missing, duplicated, outside the project, or matches
  no part in PARTS;
- Work/Introduction.md is missing, empty, or does not start with
  "# Introduction";
- a chapter summary does not open with exactly one ## heading, or has a
  level-1 heading;
- the Introduction or a chapter summary has two lines that Markdown would
  run together: a lost blank line merges two paragraphs, pulls a heading
  into the text, or swallows a paragraph into a block quotation, and
  neither a word diff nor the PDF text check can see it;
- the assembled text has a leftover marker, page reference, footnote,
  working-file reference, leaked review note, or unfilled placeholder (the
  shipped Introduction stub has one, so an unwritten Introduction blocks).

When blocked units remain, the introduction gets a notice that the summary
is partial, listing the omitted units and their limitations.

Two notes never block: a chapter whose ## heading differs from its title in
the parts manifest (usually an accidental edit by a later pass; a
deliberate rename is fine), and, when QUOTE_STYLE is set, lines holding the
other quotation style's characters.

After writing, prints the compression ratio (chapter summary words / retained
source words) per source and for the document, against DOC_TARGET and
DOC_MAX in Work/common.py.

Usage (from the project root):
    python Work/assemble.py [--out PATH]

--out writes somewhere other than Summary.md, so a report-only run can
reassemble to a scratch file and compare it with the shipped one.
"""
import json
import re
import sys
from pathlib import Path

from common import DOC_MAX, DOC_TARGET, ROOT, paragraph_break_problems, utf8_output
from count_words import words_in_text

SUMS = ROOT / "Work" / "Summaries"
MANIFEST = ROOT / "Work" / "manifest.json"
PARTS_MANIFEST = ROOT / "Work" / "parts_manifest.json"
INTRO_FILE = ROOT / "Work" / "Introduction.md"
OUT = ROOT / "Summary.md"

# One (source_slug, heading) pair per source, in part order. Name the source
# and its author(s) in the heading, e.g. "# Part 1: {Title} by {Author}".
PARTS = [
    ("", "# Part 1: {Title}"),
]

# Pilot mode: when non-empty, assemble only these (source_slug, unit_id)
# accepted units and skip the unfinished-unit check. Empty for the full run.
PILOT_UNITS = []

# The quotation style the summaries use: None (no check), "curly" (“ ” ‘ ’)
# or "straight" (" '). When set, lines holding the other style's characters
# are listed after writing. Never blocking: primes, and quotation marks a
# source prints, can be right in either style.
QUOTE_STYLE = None
QUOTE_CHARS = {"curly": "“”‘’", "straight": "\"'"}
QUOTE_LINES_SHOWN = 10

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


def manifest_titles():
    """{resolved chapter summary path: title} from the parts manifest, for
    units that have a title."""
    if not PARTS_MANIFEST.exists():
        return {}
    return {
        (ROOT / c["summary"]).resolve(): c["title"]
        for c in json.loads(PARTS_MANIFEST.read_text(encoding="utf-8"))
        if c.get("summary") and c.get("title")
    }


def source_words():
    """{resolved chapter summary path: (slug, retained source words)} from the parts manifest."""
    if not PARTS_MANIFEST.exists():
        return {}
    return {
        (ROOT / c["summary"]).resolve(): (c["source_slug"], c["words"])
        for c in json.loads(PARTS_MANIFEST.read_text(encoding="utf-8"))
        if c.get("summary") and c.get("words")
    }


def print_ratios(counted):
    """counted: [(slug, summary words, source words)]."""
    totals = {}
    for slug, words, src in counted:
        t = totals.setdefault(slug, [0, 0])
        t[0] += words
        t[1] += src
    for slug, (words, src) in totals.items():
        print("ratio %s: %.3f (%d / %d words)" % (slug, words / src, words, src))
    words, src = sum(t[0] for t in totals.values()), sum(t[1] for t in totals.values())
    if src:
        r = words / src
        note = "OVER THE MAXIMUM" if r > DOC_MAX else "above target" if r > DOC_TARGET else "ok"
        print("ratio document: %.3f (target %.2f, maximum %.2f): %s" % (r, DOC_TARGET, DOC_MAX, note))


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


def check_breaks(name, text, problems):
    """Problems for adjacent lines that Markdown would run together (a lost
    blank line), numbered as lines of the file as written."""
    for n, message in paragraph_break_problems(text):
        problems.append("%s line %d: %s" % (name, n, message))


def read_intro(problems):
    """The Introduction, stripped, or "" with a problem if
    Work/Introduction.md is missing, empty, or does not start with
    "# Introduction"."""
    name = display(INTRO_FILE)
    if not INTRO_FILE.exists():
        problems.append("%s is missing" % name)
        return ""
    raw = INTRO_FILE.read_text(encoding="utf-8-sig")
    text = raw.strip()
    if not text:
        problems.append("%s is empty" % name)
        return ""
    if text.splitlines()[0].strip() != "# Introduction":
        problems.append('%s: must start with "# Introduction"' % name)
    check_breaks(name, raw, problems)
    return text


def check_chapter(path, text, problems):
    """Structural problems in one chapter summary; text as read from its
    file, so line numbers match it."""
    name = path.relative_to(ROOT).as_posix()
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines or not lines[0].startswith("## "):
        problems.append("%s: does not open with a ## chapter heading" % name)
    if sum(1 for ln in lines if ln.startswith("## ")) > 1:
        problems.append("%s: has more than one ## heading" % name)
    if any(ln.startswith("# ") for ln in lines):
        problems.append("%s: has a level-1 heading" % name)
    check_breaks(name, text, problems)


def heading_note(path, text, title):
    """A note if the chapter's ## heading differs from its title in the parts
    manifest, else None. Never blocking: a pass may rename a heading on
    purpose (making it block forced a cascade of edits for one rename), so
    the note only makes an accidental edit visible."""
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    if not title or not first.startswith("## "):
        return None
    heading = " ".join(first[3:].split())
    if heading == " ".join(title.split()):
        return None
    return "%s: heading %r differs from the parts manifest title %r" % (
        path.relative_to(ROOT).as_posix(), heading, title)


def quote_style_notes(text, name):
    """Notes for lines holding the other quotation style's characters, when
    QUOTE_STYLE is set: a count and the first QUOTE_LINES_SHOWN lines."""
    if QUOTE_STYLE not in QUOTE_CHARS:
        return []
    other_style = "straight" if QUOTE_STYLE == "curly" else "curly"
    other = QUOTE_CHARS[other_style]
    hits = [(n, line) for n, line in enumerate(text.splitlines(), 1) if any(c in line for c in other)]
    if not hits:
        return []
    notes = ["%s: %d line(s) hold %s quotation marks or apostrophes (%s); QUOTE_STYLE is %r:" % (
        name, len(hits), other_style, " ".join(other), QUOTE_STYLE)]
    for n, line in hits[:QUOTE_LINES_SHOWN]:
        at = min(line.find(c) for c in other if c in line)
        notes.append("  line %d: %r" % (n, line[max(0, at - 30):at + 30]))
    if len(hits) > QUOTE_LINES_SHOWN:
        notes.append("  ... and %d more" % (len(hits) - QUOTE_LINES_SHOWN))
    return notes


def check_text(text, problems, name="Summary.md"):
    for n, line in enumerate(text.splitlines(), 1):
        for pattern, label in TEXT_CHECKS:
            m = pattern.search(line)
            if m:
                problems.append("%s line %d: %s: %r" % (name, n, label, line[max(0, m.start() - 30):m.end() + 30]))


def print_notes(notes):
    """Print the non-blocking notes."""
    if notes:
        print("notes (not blocking):")
        for n in notes:
            print("  " + n)


def output_path(argv):
    """The path to write: OUT, or --out PATH (relative to the project root)."""
    args, out = list(argv), OUT
    if "--out" in args:
        i = args.index("--out")
        if i + 1 >= len(args):
            raise SystemExit(__doc__)
        out = Path(args[i + 1])
        if not out.is_absolute():
            out = ROOT / out
        del args[i:i + 2]
    if args:
        raise SystemExit(__doc__)
    return out


def display(path):
    """A path for messages, project-relative where it can be."""
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def main():
    utf8_output()
    out = output_path(sys.argv[1:])
    manifest = load_manifest()
    problems, notes = [], []
    if QUOTE_STYLE not in (None, *QUOTE_CHARS):
        problems.append("QUOTE_STYLE must be None, %s: not %r" % (" or ".join(map(repr, QUOTE_CHARS)), QUOTE_STYLE))

    pilot = {tuple(key) for key in PILOT_UNITS}
    if pilot:
        manifest = [e for e in manifest if (e["source_slug"], e["unit_id"]) in pilot]

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

    intro = read_intro(problems)
    if blocked and not problems:
        intro += "\n\n" + partial_notice(blocked, unit_titles())
    pieces, chapters, used = [intro], [], set()
    sources, counted, titles = source_words(), [], manifest_titles()
    for slug, heading in PARTS:
        folder = (SUMS / slug).resolve()
        files = [p for p in accepted if p.parent == folder]
        if not files:
            continue
        pieces.append(heading)
        for path in files:
            raw = path.read_text(encoding="utf-8-sig")
            body = raw.strip()
            check_chapter(path, raw, problems)
            note = heading_note(path, raw, titles.get(path))
            if note:
                notes.append(note)
            pieces.append(body)
            chapters.append(body)
            used.add(path)
            if path in sources:
                counted.append((sources[path][0], words_in_text(body), sources[path][1]))
            print("%-18s %s" % (slug, path.name))
    unmatched = [p.relative_to(ROOT).as_posix() for p in accepted if p not in used]
    if unmatched:
        problems.append("accepted units matched no part in PARTS: %s" % ", ".join(unmatched))

    text = "\n\n".join(p.strip() for p in pieces if p.strip()) + "\n"
    check_text(text, problems, out.name)
    if problems:
        print("assemble: %s not written. Fix these first:" % display(out))
        for p in problems:
            print("  " + p)
        print_notes(notes)
        sys.exit(1)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    intro_words = words_in_text(intro)
    body_words = sum(words_in_text(c) for c in chapters)
    print("wrote %s" % display(out))
    print("introduction: %d words; chapter summaries: %d words; %d chapter(s)" % (intro_words, body_words, len(chapters)))
    print_ratios(counted)
    if blocked:
        print("PARTIAL: %d blocked unit(s) omitted and listed in the introduction" % len(blocked))
    print_notes(notes + quote_style_notes(text, out.name))


if __name__ == "__main__":
    main()
