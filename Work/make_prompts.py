"""Fill agent prompts from prompts.md or a pass brief: one prompt file per task.

Every agent is dispatched with one line, "Read Work/Prompts/<out>/<file> and
follow it exactly.", so the coordinator never types a path, a budget, or a
command into a prompt, and the files stay in the project as the record of
what each agent was told. In one run the coordinator wrote some forty
one-off generators, each copied from the last; one forgot to check for
unfilled placeholders, another patched templates with unchecked string
replacements, and transition prompts named by slug overwrote each other.

Usage (from the project root):
    python Work/make_prompts.py <out> <role> (<key> ... | --all) [options]
    python Work/make_prompts.py <out> --ready

<out> is the folder Work/Prompts/<out>/. <role> names the files
(<role>-<n>.txt). The template is the first ```text block under a heading:

  prompts.md      summarizer -> "## Summarizer", reviewer -> "## Reviewer",
                  merger -> "## Merger", transition -> "## Transition
                  reviewer", whole-doc -> "## Whole-document reviewer",
                  boundary -> "## Boundary inspector"
  a pass brief    any role name with --brief FILE and/or --section NAME
                  (default "Agent prompt"). FILE is looked up in the project
                  root (the brief copied for the pass), then in passes/.
                  Without --brief: <role>.md, then <out>.md, in the root
                  and then in passes/.

Headings match by prefix, ignoring case ("Re-verification" finds "## Re-
verification after an editing pass (Mode A with DIFF)"; a trailing
" prompt" that matches nothing is dropped and tried again). Only the
template block is filled: placeholders elsewhere in a brief are the
coordinator's to fill by hand when copying it.

Units, one task each, chosen by the template and options, not by the role:

  --queue FILE    a review queue (8 fields, Work/make_review_queue.py) or a
                  verify queue (9 fields, Work/make_verify_queue.py)
  --chunks FILE   whole-document chunks (Work/make_doc_chunks.py)
  otherwise       Summarizer, Reviewer: Work/review_queue.txt; Merger:
                  split chapters whose parts are all accepted; Transition
                  reviewer: Work/transition_queue.txt; Whole-document
                  reviewer: Work/whole_doc_chunks.txt; Boundary inspector:
                  one task, from --set; a brief: every chapter in
                  Work/parts_manifest.json whose summary exists
  --items DIR     only units whose chapter has a non-empty item file in DIR
                  (Work/collect_items.py), which fills ITEMS

Keys select units: slug/unit_id (a chapter, with all its parts),
slug/unit_id/k (part k), a source slug, chunkN (a chunk), or --all.

Fields (placeholders are {UPPER_SNAKE}; <angle text> is the agent's and is
left alone). Each is computed; --set KEY=VALUE supplies or overrides any
field (repeatable; VALUE may be @file to read it from a file, and may hold
other placeholders, such as --set RECORD=Work/Reviews/wd2/chunk{CHUNK}.md):

  paths     ROOT, SOURCE, DRAFT, SUMMARY, WRITE, RECORD, PREV, NEXT ("none"
            where there is none), EARLIER (the snapshot copy; the line is
            dropped without --snapshot), ROUND1 (a verify unit's round-1
            record; the line is dropped where there is none), ITEMS, BRIEF,
            SETTLED (settled.md)
  labels    CHAPTER_TITLE, UNIT_LABEL ("slug unit_id[, part k of n]"), SLUG,
            UNIT_ID, CHUNK, MODE (B where a round-1 record exists, else A), MODEL
            (--model), DATE (--date), RECORD_HEADING ("# <label>: title
            (unit)" and "Model: ... Date: ..."), PART_SUMMARIES,
            PART_SOURCES, CHAPTERS ("; "-joined; the Introduction first; a
            chapter whose register is modern followed by " (REGISTER
            modern)"), REGISTER ("modern" or "source": the chapter file's
            frontmatter register, which extraction writes from the source's
            config; a part takes its chapter's, and a chunk has none;
            "source" where the file has none, and any other value is an
            error),
            SCOPE_EXCLUSIONS (--scope-file, verbatim), AUTHOR_CONVENTION
            (Work/author_refs.json "conventions": a "<slug>/<file stem>"
            key overrides the slug's; one line per source for a chunk; a
            missing convention is an error)
  budgets   BUDGET, LOWER, UPPER, CEILING (review units: the queue's;
            otherwise the chapter's ceiling or its ABOVE CEILING exception's
            max_words in Work/budget_exceptions.json, whichever is higher),
            CHAPTER_BUDGET, CHAPTER_CEILING, WORDS (the summary's count now),
            CAP (round(--cap-ratio x the snapshot copy's words), else
            CEILING), RATIO (summary words / the chapter's budget_words or
            words, two decimals)
  commands  WORD_COUNT_COMMAND, AUTHOR_CHECK_COMMAND, FIDELITY_CHECK_COMMAND,
            QUALIFIER_CHECK_COMMAND, DIFF_COMMAND (needs --snapshot): complete,
            on the file the agent writes (or SUMMARY), run from the project
            root; --python PATH replaces "python", which is PYTHON_COMMAND
  --set     BOUNDARY_LIST, PROPOSALS (Boundary inspector), and anything else
            a brief asks for (a PDF, its pages, a scratch folder)

The fragments under "## Prompt fragments" in prompts.md (HEADING_RULE,
PART_RULES) are fields too: the "(part)" text for one part of a split
chapter, the "(unsplit)" text otherwise, empty where a variant is absent. A
placeholder alone on its line whose value is empty takes the line with it.
Filling repeats until nothing changes, and a prompt with any {UPPER_SNAKE}
left is an error: nothing is written.

Output: Work/Prompts/<out>/<role>-<n>.txt and index.txt

    n|key|summary|source|record|words|cap|items

(n is fixed when a task is first generated, never a queue line number,
which shifts when a queue is rebuilt). Work/gate_pass.py reads the index. A
folder that already holds prompts is refused without --force, because the
prompts are part of the record; with --force a task already in the index
keeps its number and its file is rewritten, and new tasks are numbered on.
Per-task notes from <out>/notes.json (or --notes FILE), {"slug/unit_id":
"text"} (a part key "slug/unit_id/k" or a chunk key also works), and a
pass-wide --append FILE are added after the template under "Coordinator
notes:".

--ready lists the tasks to dispatch next: record not yet written, n not in
<out>/dispatched.txt (numbers you have dispatched, separated by spaces or
lines), and, for part tasks that edit the same summary, the previous part's
record written (one writer per file at a time).
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path, PurePosixPath

import collect_items
from common import DEFAULT_REGISTER, REGISTERS, ROOT, draft_range, parse_frontmatter, utf8_output
from count_words import words_of

PROMPTS = ROOT / "Work" / "Prompts"
PROMPTS_MD = ROOT / "prompts.md"
PASSES = ROOT / "passes"
PARTS_MANIFEST = ROOT / "Work" / "parts_manifest.json"
REVIEW_QUEUE = ROOT / "Work" / "review_queue.txt"
TRANSITION_QUEUE = ROOT / "Work" / "transition_queue.txt"
CHUNKS = ROOT / "Work" / "whole_doc_chunks.txt"
AUTHOR_REFS = ROOT / "Work" / "author_refs.json"
EXCEPTIONS = ROOT / "Work" / "budget_exceptions.json"

INTRO = "Work/Introduction.md"
SETTLED = "settled.md"
DEFAULT_MODEL = "Claude Opus 5.5"
# A chapter's register (extract.py, "register"): the values a chapter file's
# frontmatter may give, and the one a file without it gets.
INDEX = "index.txt"
INDEX_FIELDS = ("n", "key", "summary", "source", "record", "words", "cap", "items")
DISPATCHED = "dispatched.txt"
NOTES = "notes.json"

# Role name -> prompts.md heading.
ROLES = {
    "summarizer": "Summarizer",
    "reviewer": "Reviewer",
    "merger": "Merger",
    "transition": "Transition reviewer",
    "whole-doc": "Whole-document reviewer",
    "boundary": "Boundary inspector",
}
# The first words of RECORD_HEADING for a prompts.md template.
RECORD_LABELS = {
    "Summarizer": "Summary",
    "Reviewer": "Review",
    "Merger": "Merge",
    "Transition reviewer": "Transition review",
    "Whole-document reviewer": "Whole-document review",
    "Boundary inspector": "Boundary inspection",
}
FRAGMENTS = "Prompt fragments"
# Every field this script computes (for some kind of unit), and the fragment
# names; anything else in a template comes from --set.
FIELDS = (
    "ROOT", "SOURCE", "DRAFT", "SUMMARY", "WRITE", "RECORD", "PREV", "NEXT", "EARLIER", "ROUND1", "ITEMS",
    "BRIEF", "SETTLED", "CHAPTER_TITLE", "UNIT_LABEL", "SLUG", "UNIT_ID", "CHUNK", "MODE", "MODEL", "DATE",
    "RECORD_HEADING", "PART_SUMMARIES", "PART_SOURCES", "CHAPTERS", "REGISTER", "SCOPE_EXCLUSIONS",
    "AUTHOR_CONVENTION", "BUDGET", "LOWER", "UPPER", "CEILING", "CHAPTER_BUDGET", "CHAPTER_CEILING", "WORDS",
    "CAP", "RATIO", "PYTHON_COMMAND", "WORD_COUNT_COMMAND", "AUTHOR_CHECK_COMMAND", "FIDELITY_CHECK_COMMAND",
    "QUALIFIER_CHECK_COMMAND", "DIFF_COMMAND", "HEADING_RULE", "PART_RULES",
)
# Fields only --set supplies (the coordinator's lists for a one-off task).
SET_FIELDS = ("BOUNDARY_LIST", "PROPOSALS")
HINTS = {
    "EARLIER": "--snapshot NAME", "DIFF_COMMAND": "--snapshot NAME", "ITEMS": "--items DIR",
    "BOUNDARY_LIST": "--set BOUNDARY_LIST=@file", "PROPOSALS": "--set PROPOSALS=<path>",
    "SCOPE_EXCLUSIONS": "--scope-file FILE",
}

PLACEHOLDER = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")
PART_SUFFIX = re.compile(r"-part\d+-of-\d+$")
PROMPT_FILE = re.compile(r"^.+-(\d+)\.txt$")
FENCE = re.compile(r"^(`{3,}|~{3,})\s*([\w-]*)")


class Drop:
    """A field value that removes every template line its placeholder is on."""


DROP = Drop()


def fail(message):
    raise SystemExit(message)


def rel(path):
    """Project-root-relative POSIX path (or the path unchanged if outside the root)."""
    try:
        return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        fail("%s: not valid JSON: %s" % (rel(path), exc))


def data_lines(path):
    """Non-empty lines of a queue file."""
    if not path.exists():
        fail("%s not found" % rel(path))
    return [line for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


# ------------------------------------------------------------------ templates

def outline(text):
    """(headings, fences) of a Markdown file, ignoring headings inside fences.

    headings: [(line index, level, text)]; fences: [(start line, end line,
    language, content)].
    """
    headings, fences, lines = [], [], text.split("\n")
    i = 0
    while i < len(lines):
        m = FENCE.match(lines[i])
        if m:
            j = i + 1
            while j < len(lines) and not lines[j].startswith(m.group(1)):
                j += 1
            fences.append((i, j, m.group(2).lower(), "\n".join(lines[i + 1:j])))
            i = j + 1
            continue
        h = re.match(r"(#{1,6})\s+(.*?)\s*#*\s*$", lines[i])
        if h:
            headings.append((i, len(h.group(1)), h.group(2)))
        i += 1
    return headings, fences


def find_heading(headings, name, levels=(2, 3)):
    """The heading whose text starts with name (ignoring case): exact first, else the only prefix match."""
    for level in levels:
        cands = [h for h in headings if h[1] == level and h[2].lower().startswith(name.lower())]
        exact = [h for h in cands if h[2].lower() == name.lower()]
        if exact or len(cands) == 1:
            return (exact or cands)[0]
        if len(cands) > 1:
            fail('"%s" matches several headings: %s' % (name, "; ".join(h[2] for h in cands)))
    return None


def section_template(path, name):
    """(heading text, template) for the first ```text block under the heading named name."""
    if not path.exists():
        fail("%s not found" % rel(path))
    headings, fences = outline(path.read_text(encoding="utf-8-sig").replace("\r\n", "\n"))
    h = find_heading(headings, name)
    if h is None and name.lower().endswith(" prompt"):
        h = find_heading(headings, name[:-len(" prompt")])
    if h is None:
        fail('no heading "%s" in %s' % (name, rel(path)))
    end = next((i for i, level, _ in headings if i > h[0] and level <= h[1]), float("inf"))
    block = next((f for f in fences if h[0] < f[0] < end and f[2] == "text"), None)
    if block is None:
        fail('no ```text block under "%s" in %s' % (h[2], rel(path)))
    return h[2], block[3]


def fragments(path=None):
    """{NAME: {"unsplit": text, "part": text}} from the "## Prompt fragments" section of prompts.md."""
    path = path or PROMPTS_MD
    if not path.exists():
        return {}
    headings, fences = outline(path.read_text(encoding="utf-8-sig").replace("\r\n", "\n"))
    top = find_heading(headings, FRAGMENTS, levels=(2,))
    if top is None:
        return {}
    end = next((i for i, level, _ in headings if i > top[0] and level <= 2), float("inf"))
    subs = [h for h in headings if top[0] < h[0] < end and h[1] == 3]
    out = {}
    for n, (i, _, text) in enumerate(subs):
        m = re.match(r"([A-Z][A-Z0-9_]*)\s*\((unsplit|part)\)", text)
        if not m:
            continue
        stop = subs[n + 1][0] if n + 1 < len(subs) else end
        block = next((f for f in fences if i < f[0] < stop and f[2] == "text"), None)
        if block:
            out.setdefault(m.group(1), {})[m.group(2)] = block[3]
    return out


def brief_path(name):
    """A brief given by name or path: the project root first, then passes/."""
    p = Path(name)
    cands = [p] if p.is_absolute() else [ROOT / p, PASSES / p, PASSES / p.name]
    found = next((c for c in cands if c.exists()), None)
    if not found:
        fail("brief not found: %s (looked in the project root and passes/)" % name)
    return found


def choose_template(args):
    """(template file, heading, template text, is prompts.md)."""
    if args.brief:
        path = brief_path(args.brief)
    elif args.role in ROLES and not args.section:
        heading, text = section_template(PROMPTS_MD, ROLES[args.role])
        return PROMPTS_MD, heading, text, True
    else:
        cands = [d / ("%s.md" % n) for n in (args.role, args.out) for d in (ROOT, PASSES)]
        path = next((c for c in cands if c.exists()), None)
        if path is None and args.role in ROLES:
            path = PROMPTS_MD
        if path is None:
            fail("no brief named %s.md or %s.md in the project root or passes/: give --brief FILE"
                 % (args.role, args.out))
    heading, text = section_template(path, args.section or "Agent prompt")
    return path, heading, text, path.resolve() == PROMPTS_MD.resolve()


def prompts_role(heading):
    """The prompts.md heading (a ROLES value) that heading starts with, or None."""
    return next((r for r in ROLES.values() if heading.lower().startswith(r.lower())), None)


def record_label(path, heading, is_prompts):
    """The first words of RECORD_HEADING for a template."""
    role = prompts_role(heading) if is_prompts else None
    if role:
        return RECORD_LABELS[role]
    label = re.sub(r"\s*\(.*\)\s*$", "", heading)
    label = re.sub(r"(?i)\s+prompt$", "", label).strip()
    if label.lower() == "agent":
        m = re.search(r"(?m)^#\s+(.+?)\s*$", path.read_text(encoding="utf-8-sig"))
        label = m.group(1) if m else path.stem
    return label


# ------------------------------------------------------------------ filling

def substitute(text, fields, cache):
    """One pass of filling: each known placeholder replaced, DROP lines removed."""
    out = []
    for line in text.split("\n"):
        names = [n for n in PLACEHOLDER.findall(line) if n in fields]
        if not names:
            out.append(line)
            continue
        values = {n: value(n, fields, cache) for n in names}
        if any(v is DROP for v in values.values()):
            continue
        stripped = line.strip()
        if len(names) == 1 and stripped == "{%s}" % names[0] and values[names[0]] == "":
            continue
        indent = re.match(r"\s*", line).group(0)

        def repl(m):
            if m.group(1) not in values:
                return m.group(0)
            v = values[m.group(1)]
            # A multi-line value keeps the indentation of a placeholder that starts its line.
            if "\n" in v and line[:m.start()].strip() == "":
                v = v.replace("\n", "\n" + indent)
            return v
        out.append(PLACEHOLDER.sub(repl, line))
    return "\n".join(out)


def value(name, fields, cache):
    """A field's value: computed on first use, so a field the template does not use cannot fail."""
    if name not in cache:
        v = fields[name]
        v = v() if callable(v) else v
        cache[name] = v if v is DROP else str(v)
    return cache[name]


def fill(template, fields):
    """(filled text, [unfilled placeholder names])."""
    cache, text = {}, template
    for _ in range(20):
        new = substitute(text, fields, cache)
        if new == text:
            break
        text = new
    else:
        fail("placeholders keep expanding: %s" % ", ".join(sorted(set(PLACEHOLDER.findall(text)))))
    text = "\n".join(line.rstrip() for line in text.split("\n")).strip("\n") + "\n"
    # A dropped or empty fragment set off by blank lines leaves two in a row.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text, sorted(set(PLACEHOLDER.findall(text)))


# ------------------------------------------------------------------ project data

def manifest():
    if not PARTS_MANIFEST.exists():
        fail("Work/parts_manifest.json not found; run Work/split_parts.py first")
    return load_json(PARTS_MANIFEST, [])


def chapter_source(e):
    """The chapter file a unit was split from."""
    if e.get("chapter_source"):
        return e["chapter_source"]
    if len(e["parts"]) == 1:
        return e["parts"][0]["source"]
    return "Work/Chapters/%s/%s" % (e["source_slug"], PurePosixPath(e["summary"]).name)


def sorted_parts(e):
    return sorted(e["parts"], key=lambda p: p["part_index"])


def snapshot_copy(summary, name):
    """Work/Summaries/<rest> -> Work/Summaries_pre<name>/<rest>."""
    p = PurePosixPath(summary)
    if p.parts[:2] != ("Work", "Summaries"):
        fail("not a canonical summary, so it has no snapshot copy: %s" % summary)
    return PurePosixPath("Work", "Summaries_pre" + name, *p.parts[2:]).as_posix()


def chapter_ceiling(e, exceptions):
    """The chapter's ceiling, or the max_words of its ABOVE CEILING exception where higher."""
    ceiling = e.get("ceiling") or 0
    x = exceptions.get("%s/%s" % (e["source_slug"], e["unit_id"]))
    if isinstance(x, dict) and x.get("flag") == "ABOVE CEILING" and isinstance(x.get("max_words"), int):
        ceiling = max(ceiling, x["max_words"])
    return ceiling


def conventions():
    data = load_json(AUTHOR_REFS, {})
    return data.get("conventions", {}) if isinstance(data, dict) else {}


def convention(slug, path):
    """The author convention for a unit: "<slug>/<file stem>" first, then the slug."""
    conv = conventions()
    stem = PART_SUFFIX.sub("", PurePosixPath(path).stem)
    for key in ("%s/%s" % (slug, stem), slug):
        if conv.get(key):
            return conv[key]
    fail("no author convention for %s/%s in Work/author_refs.json \"conventions\" "
         "(prompts.md: never dispatch without it)" % (slug, stem))


def register_of(path):
    """The register a chapter file's frontmatter gives: "modern" or "source".

    Extraction writes it from the source's config (extract.py, "register"),
    and a part file carries none, so a part takes its chapter's. A chapter
    file without one (extracted before the key existed) gets "source", the
    normal clarity rules. Any other value is an error: an agent given an
    unknown register would have to guess which rules apply.
    """
    p = ROOT / path
    if not p.exists():
        fail("%s not found, so its register (REGISTER) cannot be read" % path)
    meta, _ = parse_frontmatter(p.read_text(encoding="utf-8-sig").replace("\r\n", "\n"))
    register = meta.get("register", DEFAULT_REGISTER)
    if register not in REGISTERS:
        fail('%s: frontmatter register %r must be "modern" or "source" (set "register" in the source\'s '
             "config in Work/SourceConfigs and extract again)" % (path, register))
    return register


def chunk_chapters(paths, entries):
    """CHAPTERS for a chunk: the paths "; "-joined, each modern chapter's followed by " (REGISTER modern)".

    A chunk mixes chapters, so it has no one REGISTER; the reviewer reads
    each chapter's here. A summary path that is no chapter's or part's in
    the manifest is an error, since its register cannot be known.
    """
    by_summary = {}
    for e in entries:
        by_summary[e["summary"]] = e
        for p in e["parts"]:
            by_summary.setdefault(p["summary"], e)
    out = []
    for path in paths:
        e = by_summary.get(path)
        if e is None and PurePosixPath(path).parts[:2] == ("Work", "Summaries"):
            fail("%s is in a chunk but not in Work/parts_manifest.json, so its register is unknown" % path)
        out.append(path + (" (REGISTER modern)" if e and register_of(chapter_source(e)) == "modern" else ""))
    return "; ".join(out)


def read_index(out_dir):
    """[{field: value}] for the rows of <out>/index.txt (empty when there is none)."""
    path = Path(out_dir) / INDEX
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = line.split("|")
        if not line.strip() or cells[0] == INDEX_FIELDS[0]:
            continue
        cells += ["-"] * (len(INDEX_FIELDS) - len(cells))
        rows.append(dict(zip(INDEX_FIELDS, cells)))
    return rows


def split_paths(cell):
    """The paths in an index cell ("-" for none; several joined with ";")."""
    return [p.strip() for p in (cell or "").split(";") if p.strip() and p.strip() != "-"]


# ------------------------------------------------------------------ units

def unit_key(e, k=None):
    key = "%s/%s" % (e["source_slug"], e["unit_id"])
    return "%s/%d" % (key, k) if k else key


def neighbours(e, k):
    """(previous part source, next part source), "none" where there is none."""
    parts = sorted_parts(e)
    i = [p["part_index"] for p in parts].index(k)
    return (parts[i - 1]["source"] if i > 0 else "none",
            parts[i + 1]["source"] if i + 1 < len(parts) else "none")


def queue_units(path, entries):
    """Units from a review queue (8 fields) or a verify queue (9 fields)."""
    by_source = {p["source"]: (e, p) for e in entries for p in e["parts"]}
    by_key = {(e["source_slug"], e["unit_id"]): e for e in entries}
    units = []
    for line in data_lines(path):
        f = line.split("|")
        if len(f) == 8:
            if f[0] not in by_source:
                fail("%s: %s is not a unit in Work/parts_manifest.json" % (rel(path), f[0]))
            e, p = by_source[f[0]]
            n, k = len(e["parts"]), p["part_index"]
            prev, nxt = neighbours(e, k) if n > 1 else ("none", "none")
            units.append(dict(key=unit_key(e, k if n > 1 else None), entry=e, k=k, n=n, source=f[0],
                              draft=f[1], summary=f[2], record=f[3], budget=f[4], lower=f[5], upper=f[6],
                              ceiling=f[7], prev=prev, next=nxt, queue="review"))
        elif len(f) == 9:
            slug, unit, k, n, source, prev, nxt, summary, record = f
            e = by_key.get((slug, unit))
            if e is None:
                fail("%s: %s/%s is not in Work/parts_manifest.json" % (rel(path), slug, unit))
            k, n = int(k), int(n)
            units.append(dict(key=unit_key(e, k if n > 1 else None), entry=e, k=k, n=n, source=source,
                              summary=summary, record=record, queue="verify",
                              prev="none" if prev == "-" else prev, next="none" if nxt == "-" else nxt))
        else:
            fail("%s: a queue line needs 8 fields (review) or 9 (verify): %s" % (rel(path), line))
    return units


def transition_units(entries):
    by_key = {(e["source_slug"], e["unit_id"]): e for e in entries}
    units = []
    for line in data_lines(TRANSITION_QUEUE):
        slug, unit, n, summary, _title, sources = line.split("|")
        e = by_key[(slug, unit)]
        units.append(dict(key=unit_key(e), entry=e, k=1, n=1, summary=summary, source=chapter_source(e),
                          part_sources=sources.split(";"),
                          record="Work/Reviews/%s/transitions/%s" % (slug, PurePosixPath(summary).name)))
    return units


def merger_units(entries):
    """Split chapters whose parts are all accepted and whose chapter is not."""
    units = []
    for e in entries:
        parts = sorted_parts(e)
        if len(parts) < 2 or e.get("status") == "accepted" or any(p["status"] != "accepted" for p in parts):
            continue
        units.append(dict(key=unit_key(e), entry=e, k=1, n=1, summary=e["summary"], source=chapter_source(e),
                          part_summaries=[p["summary"] for p in parts], record=None))
    return units


def chunk_units(path, out):
    units = []
    for k, paths in sorted(collect_items.read_chunks(path).items()):
        paths = [p for p in paths if p == INTRO] + [p for p in paths if p != INTRO]
        units.append(dict(key="chunk%d" % k, entry=None, chunk=k, chapters=paths,
                          record="Work/Reviews/whole-document/chunk%d.md" % k))
    if not units:
        fail("no CHUNK lines in %s" % rel(Path(path) if Path(path).is_absolute() else ROOT / path))
    return units


def chapter_units(entries, out):
    units, skipped = [], []
    for e in entries:
        if not (ROOT / e["summary"]).exists():
            skipped.append(unit_key(e))
            continue
        units.append(dict(key=unit_key(e), entry=e, k=1, n=1, summary=e["summary"], source=chapter_source(e),
                          prev="none", next="none",
                          record="Work/Reviews/%s/%s/%s" % (e["source_slug"], out, PurePosixPath(e["summary"]).name)))
    for s in skipped:
        print("skipped %s: no summary yet" % s)
    return units


def build_units(args, role, entries):
    if args.queue:
        return queue_units(ROOT / args.queue, entries)
    if args.chunks:
        return chunk_units(args.chunks, args.out)
    if role in ("Summarizer", "Reviewer"):
        return queue_units(REVIEW_QUEUE, entries)
    if role == "Merger":
        return merger_units(entries)
    if role == "Transition reviewer":
        return transition_units(entries)
    if role == "Whole-document reviewer":
        return chunk_units(CHUNKS, args.out)
    if role == "Boundary inspector":
        record = dict(s.split("=", 1) for s in args.set or [] if "=" in s).get("RECORD", "")
        return [dict(key="boundary/%s" % (PurePosixPath(record).stem or "1"), entry=None)]
    return chapter_units(entries, args.out)


def select(units, keys, use_all):
    if use_all:
        return units
    if not keys:
        fail("name the units (slug/unit_id, slug/unit_id/k, a slug, chunkN) or give --all")
    chosen = []
    for key in keys:
        k = "chunk" + key if key.isdigit() else key
        hits = [u for u in units if u["key"] == k or u["key"].startswith(k + "/")]
        if not hits:
            fail("no unit %s among the %d unit(s) for this template" % (key, len(units)))
        chosen += [u for u in hits if u not in chosen]
    return chosen


# ------------------------------------------------------------------ fields

def fields_for(u, ctx):
    """{placeholder: value or zero-argument function} for one unit."""
    e, args = u.get("entry"), ctx["args"]
    python = args.python or "python"
    f = {
        "ROOT": str(ROOT),
        "PYTHON_COMMAND": python,
        "SETTLED": SETTLED,
        "MODEL": args.model,
        "DATE": args.date,
        "BRIEF": rel(ctx["path"]),
        "SCOPE_EXCLUSIONS": ctx["scope"],
    }
    for name, variants in ctx["fragments"].items():
        f[name] = variants.get("part" if u.get("n", 1) > 1 else "unsplit", "")

    if u.get("chunk"):
        chapters = u["chapters"]
        f["CHUNK"] = u["chunk"]
        f["CHAPTERS"] = lambda: chunk_chapters(chapters, ctx["entries"])
        f["UNIT_LABEL"] = "chunk %d" % u["chunk"]
        f["RECORD"] = u["record"]
        f["AUTHOR_CONVENTION"] = lambda: chunk_conventions(chapters)
        f["RECORD_HEADING"] = "# %s: {UNIT_LABEL}\nModel: {MODEL}. Date: {DATE}." % ctx["label"]
    if e is None:
        if not u.get("chunk"):
            f["RECORD_HEADING"] = "# %s\nModel: {MODEL}. Date: {DATE}." % ctx["label"]
        return f

    slug, k, n = e["source_slug"], u["k"], u["n"]
    summary = u.get("summary")
    write = u.get("draft") if ctx["role"] == "Summarizer" else summary
    target = write or summary
    source = u.get("source") or chapter_source(e)
    # A chapter summary is checked against its chapter; a part summary or draft against its part file.
    check_source = chapter_source(e) if target == e["summary"] else source
    f.update({
        "SLUG": slug,
        "UNIT_ID": e["unit_id"],
        "CHAPTER_TITLE": e.get("title") or e["unit_id"],
        "UNIT_LABEL": "%s %s" % (slug, e["unit_id"]) + (", part %d of %d" % (k, n) if n > 1 else ""),
        "SOURCE": source,
        "SUMMARY": summary,
        "WRITE": write,
        "PREV": u.get("prev", "none"),
        "NEXT": u.get("next", "none"),
        "RECORD_HEADING": "# %s: {CHAPTER_TITLE} ({UNIT_LABEL})\nModel: {MODEL}. Date: {DATE}." % ctx["label"],
        "CHAPTER_BUDGET": e.get("budget"),
        "CHAPTER_CEILING": e.get("ceiling"),
        "WORD_COUNT_COMMAND": "%s Work/count_words.py %s" % (python, target),
        "AUTHOR_CHECK_COMMAND": "%s Work/check_author_refs.py %s" % (python, target),
        "FIDELITY_CHECK_COMMAND": "%s Work/check_fidelity.py %s %s" % (python, target, check_source),
        "QUALIFIER_CHECK_COMMAND": "%s Work/check_qualifiers.py %s %s" % (python, target, check_source),
        "AUTHOR_CONVENTION": lambda: convention(slug, chapter_source(e)),
        # A part's register is its chapter's: part files carry none.
        "REGISTER": lambda: register_of(chapter_source(e)),
    })
    if u.get("draft"):
        f["DRAFT"] = u["draft"]
    if u.get("record") and ctx["role"] != "Summarizer":
        # A summarizer writes no record: its task is done when the draft exists.
        f["RECORD"] = u["record"]
    if u.get("part_summaries"):
        f["PART_SUMMARIES"] = "; ".join(u["part_summaries"])
    f["PART_SOURCES"] = "; ".join(u.get("part_sources") or [p["source"] for p in sorted_parts(e)])

    if u.get("queue") == "review":
        f.update({"BUDGET": u["budget"], "LOWER": u["lower"], "UPPER": u["upper"], "CEILING": u["ceiling"]})
    else:
        lo, hi = draft_range(e["budget"])
        f.update({"BUDGET": e["budget"], "LOWER": lo, "UPPER": hi,
                  "CEILING": chapter_ceiling(e, ctx["exceptions"])})

    if u.get("queue") == "verify":
        round1 = re.sub(r"/verify-round\d+/", "/verify-round1/", u["record"])
        has_round1 = round1 != u["record"] and (ROOT / round1).exists()
        f["ROUND1"] = round1 if has_round1 else DROP
        f["MODE"] = "B" if has_round1 else "A"

    def snap():
        if not args.snapshot:
            fail("%s: CAP with --cap-ratio, EARLIER, and DIFF_COMMAND need --snapshot NAME" % u["key"])
        earlier = snapshot_copy(summary, args.snapshot)
        if not (ROOT / earlier).exists():
            fail("snapshot copy not found: %s (run Work/snapshot_summaries.py %s first)" % (earlier, args.snapshot))
        return earlier

    if args.snapshot and summary:
        f["EARLIER"] = snap
        f["DIFF_COMMAND"] = lambda: "git diff --no-index --word-diff=plain %s %s" % (snap(), summary)
    else:
        f["EARLIER"] = DROP

    def words():
        if not summary or not (ROOT / summary).exists():
            fail("%s: summary not found, so WORDS cannot be counted: %s" % (u["key"], summary))
        return words_of(ROOT / summary)

    def cap():
        if args.cap_ratio is None:
            return value("CEILING", f, {})
        return round(args.cap_ratio * words_of(ROOT / snap()))

    f["WORDS"] = words
    f["CAP"] = cap
    f["RATIO"] = lambda: "%.2f" % (words() / (e.get("budget_words") or e["words"]))
    if u.get("items"):
        f["ITEMS"] = u["items"]
    return {k: v for k, v in f.items() if v is not None}


def chunk_conventions(paths):
    """One "- key: convention" line per source (or unit with its own convention) in a chunk."""
    conv, lines, seen = conventions(), [], set()
    for path in paths:
        p = PurePosixPath(path)
        if path == INTRO or p.parts[:2] != ("Work", "Summaries") or len(p.parts) < 4:
            continue
        slug, stem = p.parts[2], PART_SUFFIX.sub("", p.stem)
        key = "%s/%s" % (slug, stem) if conv.get("%s/%s" % (slug, stem)) else slug
        if key in seen:
            continue
        seen.add(key)
        lines.append("- %s: %s" % (key, convention(slug, path)))
    return "\n" + "\n".join(lines) if lines else ""


# ------------------------------------------------------------------ output

def existing_prompts(out_dir):
    if not out_dir.exists():
        return []
    return [p for p in out_dir.iterdir() if p.is_file() and (PROMPT_FILE.match(p.name) or p.name == INDEX)]


def read_text_arg(value):
    """A --set value: "@path" reads the file (relative to the project root)."""
    if not value.startswith("@"):
        return value
    p = Path(value[1:])
    p = p if p.is_absolute() else ROOT / p
    if not p.exists():
        fail("--set file not found: %s" % value[1:])
    return p.read_text(encoding="utf-8-sig").replace("\r\n", "\n").rstrip("\n")


def item_cell(u):
    if not u.get("items"):
        return "-"
    ids = collect_items.item_ids((ROOT / u["items"]).read_text(encoding="utf-8-sig"))
    return ",".join(ids) or "-"


def index_row(n, u, f):
    def safe(name):
        if name not in f:
            return "-"
        try:
            text, left = fill("{%s}" % name, f)
        except SystemExit:
            return "-"
        return (text.strip() or "-") if not left else "-"

    summary = safe("WRITE") if safe("WRITE") != "-" else safe("SUMMARY")
    if u.get("chunk"):
        summary = ";".join(u["chapters"])
    words = "-"
    if summary != "-" and ";" not in summary and (ROOT / summary).exists():
        words = str(words_of(ROOT / summary))
    source = safe("SOURCE") if not u.get("part_sources") else ";".join(u["part_sources"])
    return [str(n), u["key"], summary, source, safe("RECORD"), words, safe("CAP"), item_cell(u)]


def ready(out):
    """Print the tasks to dispatch next; return 0."""
    out_dir = PROMPTS / out
    rows = read_index(out_dir)
    if not rows:
        fail("no %s in %s" % (INDEX, rel(out_dir)))
    dispatched = set()
    if (out_dir / DISPATCHED).exists():
        dispatched = set(re.findall(r"\d+", (out_dir / DISPATCHED).read_text(encoding="utf-8")))

    def done(row):
        files = split_paths(row["record"]) or split_paths(row["summary"])
        return bool(files) and all((ROOT / p).exists() for p in files)

    # Part tasks that edit the same summary go one after another.
    groups = {}
    for row in rows:
        parts = row["key"].split("/")
        if len(parts) == 3 and parts[2].isdigit():
            groups.setdefault(row["summary"], []).append((int(parts[2]), row))
    before = {}
    for members in groups.values():
        members.sort(key=lambda m: m[0])
        for (_, prev), (_, row) in zip(members, members[1:]):
            before[row["n"]] = prev

    finished = [r for r in rows if done(r)]
    waiting, out_rows, running = [], [], []
    for row in rows:
        if done(row):
            continue
        if row["n"] in dispatched:
            running.append(row["n"])
        elif row["n"] in before and not done(before[row["n"]]):
            waiting.append("%s (after %s)" % (row["n"], before[row["n"]]["n"]))
        else:
            out_rows.append(row)
    print("done: %d of %d" % (len(finished), len(rows)))
    print("dispatched, not done: %s" % (" ".join(running) or "none"))
    print("waiting: %s" % (" ".join(waiting) or "none"))
    print("ready: %s" % (" ".join(r["n"] for r in out_rows) or "none"))
    for r in out_rows:
        files = sorted(p.name for p in out_dir.glob("*-%s.txt" % r["n"]))
        print("  %s %s %s" % (r["n"], r["key"], files[0] if files else ""))
    return 0


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("role", nargs="?")
    ap.add_argument("keys", nargs="*")
    ap.add_argument("--ready", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--brief")
    ap.add_argument("--section")
    ap.add_argument("--queue")
    ap.add_argument("--chunks")
    ap.add_argument("--items")
    ap.add_argument("--snapshot")
    ap.add_argument("--cap-ratio", type=float)
    ap.add_argument("--notes")
    ap.add_argument("--append")
    ap.add_argument("--scope-file")
    ap.add_argument("--set", action="append", metavar="KEY=VALUE")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--python")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9._-]+", args.out):
        ap.error("<out> is a folder name under Work/Prompts/: letters, digits, '.', '_', '-'")
    if not args.ready and not args.role:
        ap.error("give a role, or --ready")
    return args


def main(argv=None):
    utf8_output()
    args = parse_args(argv)
    if args.ready:
        return ready(args.out)
    out_dir = PROMPTS / args.out
    if existing_prompts(out_dir) and not args.force:
        fail("%s already holds prompts, which are part of the record. Use a new <out>, or --force "
             "to rewrite tasks in place (each keeps its number)." % rel(out_dir))

    path, heading, template, is_prompts = choose_template(args)
    role = prompts_role(heading) if is_prompts else None
    sets = {}
    for s in args.set or []:
        if "=" not in s or not re.fullmatch(r"[A-Z][A-Z0-9_]*", s.split("=", 1)[0]):
            fail("--set needs KEY=VALUE with an UPPER_SNAKE key: %s" % s)
        key, val = s.split("=", 1)
        sets[key] = read_text_arg(val)
    scope = ""
    if args.scope_file:
        p = Path(args.scope_file)
        scope = (p if p.is_absolute() else ROOT / p).read_text(encoding="utf-8-sig").rstrip("\n")
    entries = manifest() if role != "Boundary inspector" or args.queue or args.chunks else []
    ctx = {"args": args, "path": path, "role": role, "label": record_label(path, heading, is_prompts),
           "fragments": fragments(), "scope": scope, "exceptions": load_json(EXCEPTIONS, {}), "entries": entries}

    units = build_units(args, role, entries)
    if args.items:
        items_dir = ROOT / args.items
        kept = []
        for u in units:
            summary = (u.get("entry") or {}).get("summary")
            p = items_dir / collect_items.item_file_name(summary) if summary else None
            if p and p.exists() and collect_items.item_ids(p.read_text(encoding="utf-8-sig")):
                u["items"] = rel(p)
                kept.append(u)
        units = kept
    chosen = select(units, args.keys, args.all or role == "Boundary inspector")

    notes_path = out_dir / NOTES
    if args.notes:
        notes_path = Path(args.notes) if Path(args.notes).is_absolute() else ROOT / args.notes
        if not notes_path.exists():
            fail("--notes file not found: %s" % args.notes)
    notes = load_json(notes_path, {})
    for key in notes:
        if not any(u["key"] == key or u["key"].startswith(key + "/") for u in units):
            print("warning: the note for %s matches no unit" % key)
    append = ""
    if args.append:
        p = Path(args.append)
        append = (p if p.is_absolute() else ROOT / p).read_text(encoding="utf-8-sig").strip()

    # Fill every prompt before writing any.
    filled, problems = [], []
    for u in chosen:
        f = fields_for(u, ctx)
        f.update(sets)
        extra = [append] if append else []
        chapter_key = "/".join(u["key"].split("/")[:2])
        extra += [notes[k] for k in dict.fromkeys([chapter_key, u["key"]]) if k in notes]
        text = template + ("\n\nCoordinator notes:\n\n" + "\n\n".join(x.strip() for x in extra) if extra else "")
        text, left = fill(text, f)
        if left:
            problems.append("%s: unfilled %s" % (u["key"], ", ".join(
                "{%s}%s" % (n, " (%s)" % HINTS[n] if n in HINTS else "") for n in left)))
        filled.append((u, f, text))
    if problems:
        fail("nothing written; %d prompt(s) have unfilled placeholders:\n  %s" % (len(problems), "\n  ".join(problems)))

    old = {r["key"]: r for r in read_index(out_dir)}
    rows = {r["n"]: r for r in old.values()}
    next_n = max([int(n) for n in rows] + [0]) + 1
    out_dir.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", args.role)
    for u, f, text in filled:
        if u["key"] in old:
            n = int(old[u["key"]]["n"])
        else:
            n, next_n = next_n, next_n + 1
        target = out_dir / ("%s-%d.txt" % (name, n))
        target.write_text(text, encoding="utf-8", newline="\n")
        row = index_row(n, u, f)
        rows[str(n)] = dict(zip(INDEX_FIELDS, row))
        print("%s  %d words  %s" % (rel(target), len(text.split()), u["key"]))
        for rec in split_paths(row[4]):
            if (ROOT / rec).exists():
                print("   note: its record already exists: %s" % rec)
    lines = ["|".join(INDEX_FIELDS)] + ["|".join(rows[n][k] for k in INDEX_FIELDS)
                                        for n in sorted(rows, key=int)]
    (out_dir / INDEX).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print('%d prompt(s). Dispatch each with one line: "Read Work/Prompts/%s/<file> and follow it exactly."'
          % (len(filled), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
