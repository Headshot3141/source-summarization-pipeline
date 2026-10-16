"""Split validated chapters into processing parts and build both manifests.

Reads chapter budgets from the Word Budgets tables in plan.md, keyed on
(source slug, unit ID). Rejects duplicate rows, retained units with no
row, rows that match no retained unit, and chapters whose frontmatter part
differs from their row's Part, and writes nothing if any of these are
found. A row whose Title or numeric Source words cell no longer matches
the chapter (a stale table after re-extraction) is noted in the report.

Chapters whose complete file is at or under the hard cap stay whole and
are listed with their own path. Larger chapters are cut into parts. Each
part owns an exact slice of the chapter body, stored between owned-text
markers, so the ordered slices rebuild the chapter byte for byte. Text is
never rewritten here; repairs belong in extraction. A page marker stays
with the text that follows it. Three hand-edited files keep the
coordinator's decisions across reruns: extra context for weak boundaries
(Work/part_context.json, see CONTEXT_CONFIG), part boundaries set by hand
(Work/part_boundaries.json, see BOUNDARIES_CONFIG), and text kept in the
chapter but left out of its budget basis (Work/budget_exclusions.json, see
EXCLUSIONS_CONFIG). An error in either of the last two writes nothing.

Writes Work/parts_manifest.json, Work/manifest.json, and
Work/parts_report.txt. Statuses from a previous run are kept for units
whose files are unchanged, and reset to pending otherwise. In the report,
"!!" lines are problems to look at and "--" lines are information.

Usage:
    python Work/split_parts.py
    python Work/split_parts.py --dry-run [--context FILE] [--boundaries FILE]

--dry-run runs everything and writes nothing: it prints the report, with
each part's bytes, headroom under the cap, overlap, and context, so a
proposed boundary or context entry can be tested with the real splitter.
--context FILE adds FILE's entries (a list in the part_context.json format)
to those in Work/part_context.json; --boundaries FILE gives each chapter it
names those boundaries in place of the chapter's entry in
Work/part_boundaries.json. Both need --dry-run: a real run reads only the
two Work/ files, so a rerun never loses a decision.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from common import (
    ABBREVIATIONS,
    DRAFT_RATIO,
    HARD_CAP,
    NOTES_LABELS,
    OWNED_END,
    OWNED_START,
    PAGE_MARKER_RE,
    ROOT,
    chapter_body,
    ends_sentence,
    is_heading,
    rel,
    review_ceiling,
    strip_comments,
    utf8_output,
    yaml_value,
)
from count_words import words_in_text

CHAPTERS = ROOT / "Work" / "Chapters"
PLAN = ROOT / "plan.md"
REPORT = ROOT / "Work" / "parts_report.txt"
PARTS_MANIFEST = ROOT / "Work" / "parts_manifest.json"
CHAPTER_MANIFEST = ROOT / "Work" / "manifest.json"

TARGET = 29_000
PREFER_HEADING_AT = 20_000
MIN_REMAINING = 6_000
FILE_OVERHEAD = 1_500  # room for frontmatter, heading, and markers

# Each part after the first opens with the end of the previous part, so its
# summarizer can follow references back into it: at least OVERLAP_BLOCKS
# paragraphs, extended backwards until they hold OVERLAP_MIN_WORDS words.
# Overlap that would push a part over the hard cap is dropped, oldest first.
OVERLAP_BLOCKS = 1
OVERLAP_MIN_WORDS = 250
OVERLAP_START = "<!-- overlap context from the end of the previous part: use for reference only, do not re-summarize it, excluded from word_count and word_budget -->"
OVERLAP_END = "<!-- end overlap context -->"

# Extra original-source context for a part, added by the coordinator where a
# boundary separates a term from its definition, a claim from its evidence,
# and so on. Kept out of the part files so a rerun never loses it. Each entry:
#   {"source_slug": ..., "unit_id": ..., "part_index": 2, "part_count": 3,
#    "text": "exact chapter text", "reason": "optional note", "fold": false}
# or, naming the receiving part by its text so the entry survives a resplit:
#   {"source_slug": ..., "unit_id": ..., "receiver": "text the receiving
#    part owns", "text": "exact chapter text", ...}
# The receiver text must occur once in the chapter, inside one part's owned
# text; the entry goes to that part, whatever the split.
# "fold": true marks a note from the chapter's notes block given to the part
# that holds its reference number: its block tells that part to fold the note
# in rather than only use it for reference.
# The text must appear verbatim in the chapter body. The splitter finds the
# part that owns it and places it before the owned text (earlier parts) or
# after it (later parts). Entries whose part_index/part_count no longer exist
# after a resplit, or whose receiver matches no single part, are reported,
# not applied.
CONTEXT_CONFIG = ROOT / "Work" / "part_context.json"
CONTEXT_START = "<!-- context from {owner}, owned there: use for reference only, do not summarize it, excluded from word_count and word_budget -->"
CONTEXT_END = "<!-- end context -->"
# A note from the chapter's notes block, given to the part that holds its
# reference number (entry key "fold": true). That part folds it in. The same
# "context from" prefix keeps check_parts.py's CONTEXT_RE matching it.
NOTE_CONTEXT_START = ("<!-- context from {owner}, a note owned there: fold its substance in where its "
                      "number appears in the owned text, excluded from word_count and word_budget -->")

# Part boundaries set by hand after the boundary inspection (plan.md Step 3):
#   {"_about": "...", "slug/unit_id": ["first words of the paragraph a part
#    must start with", ...]}
# Each prefix must start exactly one paragraph of the chapter body (page
# markers aside; a block quotation's "> " may be left out), not the first,
# and a part must be able to start there: the paragraph before ends a
# sentence, the paragraph does not start in lowercase, and the two are not
# both block quotation. The usual size rules still apply between these
# boundaries. A chapter at or under the hard cap is never split, so its
# entry is ignored (and reported). Keys starting with "_" are comments.
BOUNDARIES_CONFIG = ROOT / "Work" / "part_boundaries.json"

# Text kept in the chapter but left out of its budget basis (plan.md, Word
# Budgets): citation-only notes, a further-reading list, and other in-chapter
# apparatus the summary omits.
#   {"_about": "...", "slug/unit_id": {"notes": ["11", "12"],
#    "paragraphs": ["Further reading", ...], "reason": "..."}}
# "notes" names notes in the chapter's notes block by their label (a number,
# or a single lowercase letter); a note runs from its labelled paragraph to
# just before the next one. "paragraphs" names other paragraphs by a prefix,
# matched as for BOUNDARIES_CONFIG. When every note in the block is listed,
# the notes label goes too. The basis (chapter words less these) sets the
# expected Target, the ceiling, and each part's share of the budget.
EXCLUSIONS_CONFIG = ROOT / "Work" / "budget_exclusions.json"

# A paragraph in the notes block that starts a note: its label (one to three
# digits, or a single lowercase letter), an optional period or parenthesis,
# a space. Not a capital: "A" and "I" start ordinary sentences, and a note's
# second paragraph read as a new note would end the note early.
NOTE_START_RE = re.compile(r"^(\d{1,3}|[a-z])[.)]?\s")

SCRIPT_BLOCK_REASON = "part over hard cap"
SENTENCE_GAP = re.compile(r"(?<=[.!?…”\")])\s+")


def size(text):
    return len(text.encode("utf-8"))


def sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- budgets

def word_budget_lines(lines):
    """Yield (index, part, cells) for each line of plan.md's Word Budgets section.

    part is the number of the enclosing "### Part N:" table, or None before
    the first. cells is the stripped cell list of a budget row (Source slug,
    Unit ID, Title, Source words, Target, Ceiling, Final words, Reason for
    deviation), or None for any other line: prose, headings, a header or
    separator row, an unfilled template row. Shared with
    Work/fill_final_words.py, so both read the tables by the same rules.
    """
    in_section = False
    current_part = None
    for i, line in enumerate(lines):
        if line.startswith("## "):
            in_section = line.strip() == "## Word Budgets"
            current_part = None
            continue
        if not in_section:
            continue
        m = re.match(r"^###\s+Part\s+(\d+):", line)
        if m:
            current_part = int(m.group(1))
            yield i, current_part, None
            continue
        cells = None
        if current_part is not None and line.lstrip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 5:
                cells = None
            elif cells[0].lower() == "source slug" or re.fullmatch(r"[-: ]*", cells[0] + cells[1]):
                cells = None  # header or separator row
            elif not cells[0] and not cells[4]:
                cells = None  # unfilled template row
        yield i, current_part, cells


def parse_plan_budgets():
    """Return ({(slug, unit_id): row}, [errors]) from the Word Budgets section."""
    budgets, errors = {}, []
    if not PLAN.exists():
        return budgets, ["plan.md not found"]
    lines = PLAN.read_text(encoding="utf-8").splitlines()
    for i, current_part, cells in word_budget_lines(lines):
        if cells is None:
            continue
        n = i + 1
        slug, unit, title, source_words, target = cells[:5]
        if not slug or not unit:
            errors.append(f"plan.md line {n}: budget row needs both a source slug and a unit ID")
            continue
        if not re.fullmatch(r"\d[\d,]*", target):
            errors.append(f"plan.md line {n}: {slug}/{unit} has no numeric Target")
            continue
        key = (slug, unit)
        if key in budgets:
            errors.append(f"plan.md line {n}: duplicate budget row for {slug}/{unit}")
            continue
        reason = cells[7] if len(cells) >= 8 else ""
        numeric = re.fullmatch(r"\d[\d,]*", source_words)
        budgets[key] = {"target": int(target.replace(",", "")), "title": title, "plan_part": current_part,
                        "reason": reason,
                        "source_words": int(source_words.replace(",", "")) if numeric else None}
    return budgets, errors


# ---------------------------------------------------------------- slicing

def paragraph_units(body):
    """Contiguous (start, end) spans covering body, one per paragraph.

    Each span includes the blank-line separator that follows it.
    """
    starts = [0] + [m.end() for m in re.finditer(r"\n[ \t]*\n\s*", body)]
    starts = sorted({s for s in starts if s < len(body)})
    spans = list(zip(starts, starts[1:] + [len(body)]))
    merged = []
    for a, b in spans:  # fold whitespace-only spans into the previous span
        if merged and not body[a:b].strip():
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    # A marker-only span (a page marker set apart by a blank line) belongs to
    # the text that follows it, so a part boundary never separates them.
    out = []
    pending = None
    for a, b in merged:
        if not strip_comments(body[a:b]).strip():
            pending = a if pending is None else pending
            continue
        out.append((a if pending is None else pending, b))
        pending = None
    if pending is not None:
        if out:
            out[-1] = (out[-1][0], len(body))
        else:
            out.append((pending, len(body)))
    return out


def is_block_quote(text):
    """True if a paragraph is a block quotation (Markdown "> ", after any page marker)."""
    return strip_comments(text).lstrip().startswith(">")


def sentence_units(body, a, b):
    """Split one paragraph span at sentence boundaries, keeping whitespace."""
    cuts = [a]
    for m in SENTENCE_GAP.finditer(body, a, b):
        pos = m.end()
        if pos >= b or strip_comments(body[pos:min(b, pos + 200)]).lstrip()[:1].islower():
            continue
        last = re.search(r"(\S+)$", body[a:m.start()])
        word = last.group(1) if last else ""
        core = re.sub(r"[^A-Za-z]", "", word).lower()
        if word.endswith(".") and (core in ABBREVIATIONS or len(core) == 1):
            continue  # abbreviation or initial, not a sentence end
        cuts.append(pos)
    return list(zip(cuts, cuts[1:] + [b]))


def make_parts(body, limit, breaks=()):
    """Return (part spans, oversized unit count).

    breaks: body offsets of paragraph starts where a new part must begin
    (from BOUNDARIES_CONFIG). Between them the usual size rules apply, with
    the text still to come measured to the next forced break rather than
    the chapter's end, so a size break never leaves a sliver of a part just
    before a forced one. A chapter's notes label starts a new part when
    the current part has passed PREFER_HEADING_AT and the notes block will
    not fit in it, so the block is not cut in two where that can be helped.
    """
    breaks = set(breaks)
    units = []
    oversized = 0
    for a, b in paragraph_units(body):
        if size(body[a:b]) > limit and is_block_quote(body[a:b]):
            oversized += 1  # a block quotation is never split mid-quotation
            units.append((a, b))
        elif size(body[a:b]) > limit:
            pieces = sentence_units(body, a, b)
            oversized += sum(1 for x, y in pieces if size(body[x:y]) > limit)
            units.extend(pieces)
        else:
            units.append((a, b))
    if not units:
        return [], 0

    sizes = [size(body[a:b]) for a, b in units]
    # The bytes from each unit to the next forced break (or the body's end).
    remaining_at = [0] * len(units)
    run = 0
    for i in range(len(units) - 1, -1, -1):
        run += sizes[i]
        remaining_at[i] = run
        if units[i][0] in breaks:
            run = 0
    parts = []
    cur_start, cur_size = units[0][0], 0
    for i, (a, b) in enumerate(units):
        s = sizes[i]
        text = strip_comments(body[a:b]).strip()
        remaining = remaining_at[i]
        prev = body[units[i - 1][0]:units[i - 1][1]] if i else ""
        can_break = (
            cur_size > 0
            and ends_sentence(prev)
            and not text[:1].islower()
            # Keep a multi-paragraph block quotation (verse) in one part.
            and not (is_block_quote(text) and is_block_quote(prev))
        )
        forced = cur_size > 0 and a in breaks
        if forced or can_break and (
            cur_size + s > limit
            or (cur_size + s > TARGET and remaining >= MIN_REMAINING)
            or (is_heading(text) and cur_size >= PREFER_HEADING_AT and remaining >= MIN_REMAINING)
            or (text in NOTES_LABELS and cur_size >= PREFER_HEADING_AT and cur_size + remaining > limit)
        ):
            parts.append((cur_start, a))
            cur_start, cur_size = a, 0
        cur_size += s
    parts.append((cur_start, len(body)))
    return parts, oversized


def part_pages(body, a, b, fallback):
    """PDF page range "first-last" of body[a:b] from its page markers.

    The first page is the marker at or before a, so a part that starts
    mid-page gets that page. Falls back to the chapter's range when the
    chapter has no markers.
    """
    marks = [(m.start(), int(m.group(1))) for m in PAGE_MARKER_RE.finditer(body)]
    before = [n for pos, n in marks if pos <= a]
    inside = [n for pos, n in marks if a < pos < b]
    if not before and not inside:
        return fallback
    first = before[-1] if before else inside[0]
    last = inside[-1] if inside else first
    return "%d-%d" % (first, last)


def overlap_blocks(body, prev_span, count, min_words=0):
    if count <= 0:
        return []
    spans = [(a, b) for a, b in paragraph_units(body) if a >= prev_span[0] and b <= prev_span[1]]
    take = min(count, len(spans))
    while take < len(spans) and sum(words_in_text(body[a:b]) for a, b in spans[-take:]) < min_words:
        take += 1
    return [body[a:b].strip() for a, b in spans[-take:]]


def context_block(owner, text, fold=False):
    start = NOTE_CONTEXT_START if fold else CONTEXT_START
    return start.format(owner=owner) + "\n\n" + text + "\n\n" + CONTEXT_END


def render_part(fields, heading, overlap, owned, before=(), after=()):
    """before/after: [(owner label, text)] extra context from other parts."""
    head = "---\n" + "".join(f"{k}: {yaml_value(v)}\n" for k, v in fields) + "---\n\n" + heading + "\n\n"
    context = ""
    if overlap:
        context = OVERLAP_START + "\n\n" + "\n\n".join(overlap) + "\n\n" + OVERLAP_END + "\n\n"
    context += "".join(context_block(o, t, f) + "\n\n" for o, t, f in before)
    tail = "".join("\n\n" + context_block(o, t, f) for o, t, f in after)
    return head + context + OWNED_START + owned + OWNED_END + tail + "\n"


# ---------------------------------------------------------------- paragraphs and notes

def paragraph_texts(body):
    """(paragraph spans, their text with page markers removed and stripped)."""
    units = paragraph_units(body)
    return units, [strip_comments(body[a:b]).strip() for a, b in units]


def _unquoted(text):
    return re.sub(r"^(?:>\s?)+", "", text)


def paragraphs_starting(texts, prefix):
    """Indexes of the paragraphs whose text starts with prefix.

    Page markers are ignored on both sides, and a block quotation's "> "
    may be left out of the prefix.
    """
    prefix = strip_comments(prefix).lstrip()
    want = _unquoted(prefix)
    return [i for i, t in enumerate(texts) if want and (t.startswith(prefix) or _unquoted(t).startswith(want))]


def notes_block(texts):
    """(label index, block end index, [(note start index, label)]) or None.

    The notes block starts at the first paragraph that is one of
    NOTES_LABELS and runs to the next label or the chapter's end.
    """
    labels = [i for i, t in enumerate(texts) if t in NOTES_LABELS]
    if not labels:
        return None
    first = labels[0]
    end = labels[1] if len(labels) > 1 else len(texts)
    starts = []
    for i in range(first + 1, end):
        m = NOTE_START_RE.match(texts[i])
        if m:
            starts.append((i, m.group(1)))
    return first, end, starts


def excluded_paragraphs(body, notes, prefixes):
    """Paragraph indexes left out of the budget basis, and [problems]."""
    units, texts = paragraph_texts(body)
    picked, problems = set(), []
    if notes:
        block = notes_block(texts)
        if block is None:
            problems.append("no notes block (a paragraph reading %r or %r)" % NOTES_LABELS)
        else:
            label, end, starts = block
            listed = set()
            for n in notes:
                hits = [j for j, (_, lab) in enumerate(starts) if lab == n]
                if not hits:
                    problems.append(f"note {n} not found in the notes block")
                elif len(hits) > 1:
                    problems.append(f"note {n} starts {len(hits)} paragraphs in the notes block")
                else:
                    j = hits[0]
                    stop = starts[j + 1][0] if j + 1 < len(starts) else end
                    picked.update(range(starts[j][0], stop))
                    listed.add(j)
            if starts and len(listed) == len(starts):
                picked.add(label)  # nothing left under the label
    for prefix in prefixes:
        hits = paragraphs_starting(texts, prefix)
        if len(hits) != 1:
            problems.append(f"paragraph {prefix[:50]!r} starts {len(hits)} paragraphs, not 1")
        else:
            picked.add(hits[0])
    return sorted(picked), problems


def forced_breaks(body, prefixes):
    """Body offsets of the paragraphs that start with each prefix: ([offsets], [problems]).

    Each must be a place a part can start (see BOUNDARIES_CONFIG), the same
    rules check_parts.py applies to every boundary.
    """
    units, texts = paragraph_texts(body)
    offsets, problems = [], []
    for prefix in prefixes:
        hits = paragraphs_starting(texts, prefix)
        label = f"boundary {prefix[:50]!r}"
        if len(hits) != 1:
            problems.append(f"{label} starts {len(hits)} paragraphs, not 1")
            continue
        i = hits[0]
        a, b = units[i]
        prev = body[units[i - 1][0]:units[i - 1][1]] if i else ""
        if i == 0:
            problems.append(f"{label} is the chapter's first paragraph, where part 1 starts anyway")
        elif a in offsets:
            problems.append(f"{label} names a paragraph another boundary already names")
        elif not ends_sentence(prev):
            problems.append(f"{label}: the paragraph before it ends mid-sentence: ...{prev.rstrip()[-50:]!r}")
        elif texts[i][:1].islower():
            problems.append(f"{label}: the paragraph starts in lowercase")
        elif is_block_quote(body[a:b]) and is_block_quote(prev):
            problems.append(f"{label} falls inside a block quotation")
        else:
            offsets.append(a)
    return sorted(offsets), problems


def notes_block_problems(body, spans, boundaries_name):
    """Report lines for parts that start inside the notes block or hold only notes.

    The plan expects a chapter's notes block whole in its last part, with
    the body text that refers to it; the splitter can cut it like any text.
    """
    units, texts = paragraph_texts(body)
    block = notes_block(texts)
    if block is None:
        return []
    label, _, starts = block
    label_at = units[label][0]
    out = []
    for k, (a, _) in enumerate(spans, 1):
        if k == 1 or a < label_at:
            continue
        if a > label_at:
            earlier = [(units[i][0], lab) for i, lab in starts if units[i][0] <= a]
            if earlier and earlier[-1][0] == a and len(earlier) > 1:
                where = f"after note {earlier[-2][1]}"
            elif earlier and earlier[-1][0] != a:
                where = f"inside note {earlier[-1][1]}"
            else:
                where = "between the label and the first note"
            out.append(f"part {k} starts inside the notes block ({where}): set a boundary at the label "
                       f"or earlier in {boundaries_name}")
        out.append(f"part {k} holds only notes (apparatus-only part)")
    return out


# ---------------------------------------------------------------- configuration

def read_config(path, errors, kind=dict):
    """The JSON value in path, or None if the file is absent; errors are appended."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        errors.append(f"{path.name}: not valid JSON: {exc}")
        return None
    if not isinstance(data, kind):
        errors.append(f"{path.name}: must be a JSON {'object' if kind is dict else 'list'}")
        return None
    return data


def load_context(path=None):
    """Return ({(slug, unit_id): [entry]}, [problems]) from a part_context.json file."""
    path = path or CONTEXT_CONFIG
    problems = []
    entries = read_config(path, problems, list)
    grouped = {}
    def whole(v):
        return isinstance(v, int) and not isinstance(v, bool) and v > 0

    for n, e in enumerate(entries or [], 1):
        by_index = isinstance(e, dict) and whole(e.get("part_index")) and whole(e.get("part_count"))
        if (not isinstance(e, dict) or any(not e.get(k) for k in ("source_slug", "unit_id", "text"))
                or not (by_index or isinstance(e.get("receiver"), str) and e["receiver"])):
            problems.append(f"{path.name} entry {n}: needs source_slug, unit_id, text, and either "
                            f"part_index and part_count or receiver")
            continue
        grouped.setdefault((e["source_slug"], e["unit_id"]), []).append(e)
    return grouped, problems


def assign_context(entries, body, spans, label, config_name):
    """Return ({part index: [entry]}, [problems]) for one chapter's context entries.

    An entry keyed by part_index and part_count applies when the chapter has
    that many parts; one with a receiver goes to the part that owns the
    receiver text.
    """
    m = len(spans)
    by_part, problems, unmatched = {}, [], set()
    for e in entries:
        if e.get("receiver"):
            r = e["receiver"]
            hits = body.count(r)
            if m == 1:
                problems.append(f"{config_name}: context for {label} with receiver {r[:50]!r} matches no part "
                                f"(the chapter is unsplit)")
                continue
            if hits != 1:
                problems.append(f"{config_name}: context for {label}: receiver {r[:50]!r} occurs {hits} times "
                                f"in the chapter, not once; not added")
                continue
            pos = body.index(r)
            owners = [k for k, (a, b) in enumerate(spans, 1) if a < pos + len(r) and pos < b]
            if len(owners) != 1:
                problems.append(f"{config_name}: context for {label}: receiver {r[:50]!r} spans parts "
                                f"{owners[0]}-{owners[-1]}; not added")
                continue
            by_part.setdefault(owners[0], []).append(e)
        elif e["part_count"] == m and 1 <= e["part_index"] <= m and m > 1:
            by_part.setdefault(e["part_index"], []).append(e)
        else:
            unmatched.add((e["part_index"], e["part_count"]))
    for k, count in sorted(unmatched):
        problems.append(f"{config_name}: context for {label} part {k} of {count} matches no part (the chapter "
                        f"was resplit or is unsplit); re-inspect its boundaries and update the entry")
    return by_part, problems


def place_context(entries, body, spans, k, unit, notes):
    """Return (before, after) context blocks for part k from config entries."""
    before, after = [], []
    for e in entries:
        text = e["text"]
        pos = body.find(text)
        if pos < 0:
            notes.append(f"part {k}: context text not found verbatim in the chapter, not added: {text[:60]!r}")
            continue
        if body.count(text) > 1:
            notes.append(f"part {k}: context text occurs more than once in the chapter; used the first: {text[:60]!r}")
        end = pos + len(text)
        owners = [j for j, (a, b) in enumerate(spans, 1) if a < end and pos < b]
        if k in owners:
            notes.append(f"part {k}: context text overlaps this part's own text, not added: {text[:60]!r}")
            continue
        label = f"{unit} part {owners[0]}" if len(owners) == 1 else f"{unit} parts {owners[0]}-{owners[-1]}"
        (before if owners[-1] < k else after).append((label, text.strip(), bool(e.get("fold"))))
    return before, after


def load_boundaries(chapters, errors, extra=None):
    """Attach forced break offsets (ch["breaks"]) from BOUNDARIES_CONFIG to the chapters.

    extra: a file whose chapter entries stand in for BOUNDARIES_CONFIG's (dry runs).
    """
    data = {}
    for path in (BOUNDARIES_CONFIG, extra):
        if path is not None:
            data.update(read_config(path, errors) or {})
    name = BOUNDARIES_CONFIG.name
    by_key = {"/".join(ch["key"]): ch for ch in chapters}
    for key, prefixes in data.items():
        if key.startswith("_"):
            continue  # a comment entry, such as "_about"
        ch = by_key.get(key)
        if (ch is None or not isinstance(prefixes, list) or not prefixes
                or not all(isinstance(p, str) and p.strip() for p in prefixes)):
            errors.append(f"{name}: entry {key!r} needs a chapter's slug/unit_id key and a list of "
                          f"paragraph prefixes")
            continue
        if ch["bytes"] <= HARD_CAP:
            ch["ignored_breaks"] = len(prefixes)
            continue
        offsets, problems = forced_breaks(ch["body"], prefixes)
        errors.extend(f"{name}: {key}: {p}" for p in problems)
        ch["breaks"] = offsets


def load_exclusions(chapters, errors):
    """Attach the spans left out of each chapter's budget basis (ch["excluded"]) from EXCLUSIONS_CONFIG."""
    data = read_config(EXCLUSIONS_CONFIG, errors) or {}
    name = EXCLUSIONS_CONFIG.name
    by_key = {"/".join(ch["key"]): ch for ch in chapters}
    for key, entry in data.items():
        if key.startswith("_"):
            continue
        ch = by_key.get(key)
        if ch is None:
            errors.append(f"{name}: entry {key!r} matches no chapter file (key it slug/unit_id)")
            continue
        notes = entry.get("notes", []) if isinstance(entry, dict) else None
        paras = entry.get("paragraphs", []) if isinstance(entry, dict) else None
        ok = (isinstance(notes, list) and isinstance(paras, list) and (notes or paras)
              and all(isinstance(n, (str, int)) and not isinstance(n, bool) and str(n).strip() for n in notes)
              and all(isinstance(p, str) and p.strip() for p in paras)
              and isinstance(entry.get("reason"), str) and entry["reason"].strip())
        if not ok:
            errors.append(f"{name}: {key}: needs a \"notes\" list (note labels) or a \"paragraphs\" list "
                          f"(paragraph prefixes), or both, and a \"reason\"")
            continue
        indexes, problems = excluded_paragraphs(ch["body"], [str(n).strip() for n in notes], paras)
        errors.extend(f"{name}: {key}: {p}" for p in problems)
        units = paragraph_units(ch["body"])
        ch["excluded"] = [(units[i][0], units[i][1], words_in_text(ch["body"][units[i][0]:units[i][1]]))
                          for i in indexes]
        if sum(w for _, _, w in ch["excluded"]) >= ch["words"]:
            errors.append(f"{name}: {key}: leaves no words in the budget basis")


# ---------------------------------------------------------------- main

def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def collect_chapters(budgets, errors):
    chapters = []
    seen = {}
    if not CHAPTERS.exists():
        return chapters
    for slug_dir in sorted(d for d in CHAPTERS.iterdir() if d.is_dir()):
        for path in sorted(slug_dir.glob("*.md")):
            raw_bytes = path.read_bytes()
            raw = raw_bytes.decode("utf-8")
            meta, body = chapter_body(raw)
            slug, unit = meta.get("source_slug"), meta.get("unit_id")
            name = rel(path)
            if not slug or not unit:
                errors.append(f"{name}: frontmatter needs source_slug and unit_id")
                continue
            if slug != slug_dir.name:
                errors.append(f"{name}: source_slug {slug!r} does not match its folder")
            key = (slug, unit)
            if key in seen:
                errors.append(f"{name}: duplicate unit {slug}/{unit} (also {seen[key]})")
                continue
            seen[key] = name
            if key not in budgets:
                errors.append(f"{name}: no budget row for {slug}/{unit} in plan.md")
                continue
            if meta.get("part") != budgets[key]["plan_part"]:
                errors.append(f"{name}: frontmatter part {meta.get('part')!r} differs from its plan.md row's "
                              f"Part {budgets[key]['plan_part']}")
            words = words_in_text(body)
            if words == 0:
                errors.append(f"{name}: chapter body has no words")
                continue
            chapters.append({
                "path": path, "meta": meta, "body": body, "key": key,
                "bytes": len(raw_bytes), "sha": sha(raw_bytes), "words": words,
            })
    for key in budgets:
        if key not in seen:
            errors.append(f"plan.md: budget row {key[0]}/{key[1]} matches no chapter file")
    return chapters


def opening(text, n=50):
    """The first n characters of a part's text, page markers removed, on one line."""
    return " ".join(strip_comments(text).split())[:n]


def split_chapter(ch, row, entries, old_parts, old_status, context_name):
    """Plan one chapter's processing units.

    Returns (parts manifest entry, chapter manifest entry, report lines,
    {part file name: bytes}). Nothing is written here.
    """
    path, meta, body = ch["path"], ch["meta"], ch["body"]
    slug, unit = ch["key"]
    label = f"{slug}/{unit}"
    budget = row["target"]
    stem = path.stem
    excluded = ch.get("excluded", [])
    # The budget basis: the chapter's words less the text left out of it.
    basis = ch["words"] - sum(w for _, _, w in excluded)
    expected = round(basis * DRAFT_RATIO)
    summary = f"Work/Summaries/{slug}/{stem}.md"
    notes, info = [], []  # report lines: problems ("!!") and information ("--")
    if meta.get("word_count") != ch["words"]:
        notes.append(f"frontmatter word_count {meta.get('word_count')} differs from measured {ch['words']}")
    if row["title"] != meta.get("title", ""):
        notes.append(f"Title {row['title']!r} in plan.md differs from the chapter's title {meta.get('title', '')!r}")
    if excluded:
        info.append(f"budget basis {basis}: {ch['words'] - basis} words in {len(excluded)} paragraph(s) left out "
                    f"({EXCLUSIONS_CONFIG.name})")
    if row["source_words"] is not None and row["source_words"] != basis:
        notes.append(f"Source words {row['source_words']} in plan.md differ from the budget basis {basis}")
    if abs(budget - expected) > max(5, 0.05 * expected) and not row["reason"]:
        notes.append(f"Target {budget} differs from {DRAFT_RATIO} x {basis} source words ({expected}) "
                     f"with no reason for deviation recorded in plan.md")

    files = {}
    units = []
    part_lines = []
    context_problems = []
    if ch["bytes"] <= HARD_CAP:
        if ch.get("ignored_breaks"):
            notes.append(f"{ch['ignored_breaks']} boundary(ies) in {BOUNDARIES_CONFIG.name} ignored: the chapter "
                         f"is at or under the hard cap and stays whole; remove the entry")
        _, context_problems = assign_context(entries, body, [(0, len(body))], label, context_name)
        units.append({
            "part_index": 1, "part_count": 1,
            "source": rel(path),
            "draft": f"Work/Drafts/{slug}/{stem}.md",
            "summary": summary,
            "record": f"Work/Reviews/{slug}/{stem}.md",
            "words": ch["words"], "budget_words": basis, "budget": budget,
            "ceiling": review_ceiling(budget, basis), "bytes": ch["bytes"],
            "sha": ch["sha"], "status": "pending", "context_from": [],
        })
    else:
        breaks = ch.get("breaks", [])
        spans, oversized = make_parts(body, HARD_CAP - FILE_OVERHEAD, breaks)
        if breaks:
            info.append(f"{len(breaks)} boundary(ies) set in {BOUNDARIES_CONFIG.name}")
        if oversized:
            notes.append(f"{oversized} sentence(s) too long to fit any part: resegment in extraction or block the unit")
        notes.extend(notes_block_problems(body, spans, BOUNDARIES_CONFIG.name))
        by_part, context_problems = assign_context(entries, body, spans, label, context_name)
        m = len(spans)
        words = [words_in_text(body[a:b]) for a, b in spans]
        # Each part's budget basis: its words less the excluded text that starts in it.
        effs = [w - sum(n for s, _, n in excluded if a <= s < b) for (a, b), w in zip(spans, words)]
        shares = [int(round(budget * e / basis)) for e in effs]
        shares[effs.index(max(effs))] += budget - sum(shares)
        for k, ((a, b), w, eff, share) in enumerate(zip(spans, words, effs, shares), 1):
            pname = f"{stem}-part{k}-of-{m}.md"
            fields = [
                ("source", meta.get("source", "")),
                ("source_slug", slug),
                ("unit_id", unit),
                ("part", meta.get("part")),
                ("chapter", meta.get("chapter")),
                ("title", meta.get("title", "")),
                ("pdf_pages", part_pages(body, a, b, meta.get("pdf_pages", ""))),
                ("printed_pages", meta.get("printed_pages", "")),
                ("part_index", k),
                ("part_count", m),
                ("word_count", w),
                ("word_budget", share),
            ]
            heading = f"# {meta.get('title') or unit} (Part {k} of {m})"
            owned = body[a:b]
            overlap = overlap_blocks(body, spans[k - 2], OVERLAP_BLOCKS, OVERLAP_MIN_WORDS) if k > 1 else []
            want = len(overlap)
            before, after = place_context(by_part.get(k, []), body, spans, k, unit, notes)
            content = render_part(fields, heading, overlap, owned, before, after)
            while overlap and size(content) > HARD_CAP:
                overlap = overlap[1:]
                content = render_part(fields, heading, overlap, owned, before, after)
            if k > 1 and len(overlap) < want:
                notes.append(f"part {k}: overlap dropped to {len(overlap)} block(s) to stay under the cap; inspect this boundary")
            data = content.encode("utf-8")
            files[pname] = data
            status = "pending"
            if len(data) > HARD_CAP:
                status = "blocked"
                fix = "; shorten the added context or move the boundary" if before or after else ""
                notes.append(f"part {k}: {len(data)} bytes is over the {HARD_CAP}-byte cap; not assignable{fix}")
            # One line per part, so a boundary inspector sees each file's headroom.
            room = HARD_CAP - len(data)
            headroom = f"{room} under the cap" if room >= 0 else f"{-room} OVER the cap"
            basis_note = f" (basis {eff})" if eff != w else ""
            part_lines.append(
                f"  part {k}: {len(data)} bytes ({headroom}), {w} words{basis_note}, budget {share}, "
                f"ceiling {review_ceiling(share, eff)}, overlap {len(overlap)} block(s), context {len(before)} "
                f"before and {len(after)} after; starts {opening(owned)!r}")
            units.append({
                "part_index": k, "part_count": m,
                "source": f"Work/Chapters/{slug}/parts/{pname}",
                "draft": f"Work/Drafts/{slug}/parts/{pname}",
                "summary": f"Work/Summaries/{slug}/parts/{pname}",
                "record": f"Work/Reviews/{slug}/parts/{pname}",
                "words": w, "budget_words": eff, "budget": share, "ceiling": review_ceiling(share, eff),
                "bytes": len(data), "sha": sha(data), "status": status,
                "context_from": [o for o, _, _ in before + after],
            })
    notes.extend(context_problems)

    # Keep earlier statuses only where the unit's file is unchanged.
    prev = old_parts.get(ch["key"])
    prev_units = {(p["part_index"], p["part_count"]): p for p in (prev or {}).get("parts", [])}
    for u in units:
        p = prev_units.get((u["part_index"], u["part_count"]))
        if u["status"] != "blocked" and p and p.get("sha") == u["sha"] and p.get("status"):
            u["status"] = p["status"]

    script_blocked = any(u["status"] == "blocked" and u["bytes"] > HARD_CAP for u in units)
    unchanged = prev is not None and prev.get("chapter_sha") == ch["sha"]
    if script_blocked:
        status = "blocked"
    elif unchanged and ch["key"] in old_status and not (
        old_status[ch["key"]] == "blocked" and prev.get("blocked_reason") == SCRIPT_BLOCK_REASON
    ):
        status = old_status[ch["key"]]
    else:
        status = "pending"
    if status == "accepted" and any(u["status"] != "accepted" for u in units):
        status = "drafted"

    entry = {
        "source_slug": slug,
        "unit_id": unit,
        "part": meta.get("part"),
        "chapter": meta.get("chapter"),
        "title": meta.get("title", ""),
        "chapter_source": rel(path),
        "chapter_sha": ch["sha"],
        "summary": summary,
        "words": ch["words"],
        "budget_words": basis,
        "budget": budget,
        # The sum of the part ceilings, so a merged chapter never shows over
        # its ceiling while every part is within its own (rounding).
        "ceiling": sum(u["ceiling"] for u in units),
        "part_count": len(units),
        "status": status,
        "blocked_reason": SCRIPT_BLOCK_REASON if script_blocked else None,
        "parts": units,
    }
    # The hash of the last merged chapter summary, kept so merge_chapters.py
    # never overwrites a chapter edited after its merge.
    if prev and prev.get("merged_sha"):
        entry["merged_sha"] = prev["merged_sha"]
    chapter_entry = {"source_slug": slug, "unit_id": unit, "path": summary, "status": status}
    maxb = max(u["bytes"] for u in units)
    report = [
        f"{label} ({path.name}): {len(units)} part(s), {ch['words']} words"
        + (f" (budget basis {basis})" if basis != ch["words"] else "")
        + f", budget {budget} (ceiling {entry['ceiling']}), largest file {maxb} bytes, status {status}"
    ]
    report.extend(part_lines)
    report.extend("  -- " + n for n in info)
    report.extend("  !! " + n for n in notes)
    return entry, chapter_entry, report, files


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Split chapters into parts and build the manifests.")
    parser.add_argument("--dry-run", action="store_true", help="run everything, write nothing, print the report")
    parser.add_argument("--context", type=Path, help="extra part_context.json entries to apply (dry run only)")
    parser.add_argument("--boundaries", type=Path,
                        help="part_boundaries.json entries that replace the same chapters' entries (dry run only)")
    args = parser.parse_args(argv)
    if (args.context or args.boundaries) and not args.dry_run:
        parser.error("--context and --boundaries need --dry-run; a real run reads only "
                     "Work/part_context.json and Work/part_boundaries.json")
    for path in (args.context, args.boundaries):
        if path is not None and not path.exists():
            parser.error(f"{path} not found")
    return args


def main():
    utf8_output()
    args = parse_args(sys.argv[1:])
    budgets, errors = parse_plan_budgets()
    chapters = collect_chapters(budgets, errors)
    load_exclusions(chapters, errors)
    load_boundaries(chapters, errors, args.boundaries)
    if errors:
        print("split_parts: nothing written. Fix these first:")
        for e in errors:
            print("  " + e)
        sys.exit(1)

    contexts, context_problems = load_context()
    context_name = CONTEXT_CONFIG.name
    if args.context:
        extra, extra_problems = load_context(args.context)
        context_problems += extra_problems
        for key, entries in extra.items():
            contexts.setdefault(key, []).extend(entries)
        context_name = f"{CONTEXT_CONFIG.name} + {args.context.name}"
    old_parts = {(c["source_slug"], c["unit_id"]): c for c in load_json(PARTS_MANIFEST, [])}
    old_status = {(c["source_slug"], c["unit_id"]): c["status"] for c in load_json(CHAPTER_MANIFEST, [])}

    chapters.sort(key=lambda c: (c["meta"].get("part") or 0, str(c["path"])))
    report, parts_manifest, chapter_manifest, outputs = [], [], [], []
    for ch in chapters:
        entry, chapter_entry, lines, files = split_chapter(
            ch, budgets[ch["key"]], contexts.pop(ch["key"], []), old_parts, old_status, context_name)
        parts_manifest.append(entry)
        chapter_manifest.append(chapter_entry)
        report.extend(lines)
        outputs.append((ch["path"], files))
    for slug, unit in sorted(contexts):
        context_problems.append(f"{context_name}: context for {slug}/{unit} matches no chapter")
    report.extend("  !! " + p for p in context_problems)

    if args.dry_run:
        print("\n".join(report))
    else:
        for path, files in outputs:
            parts_dir = path.parent / "parts"
            if files:
                parts_dir.mkdir(exist_ok=True)
            for pname, data in files.items():
                (parts_dir / pname).write_bytes(data)
            # Remove part files left over from an earlier split of this chapter.
            if parts_dir.exists():
                for stale in parts_dir.glob(f"{path.stem}-part*-of-*.md"):
                    if stale.name not in files:
                        stale.unlink()
        PARTS_MANIFEST.write_text(json.dumps(parts_manifest, indent=1), encoding="utf-8", newline="\n")
        CHAPTER_MANIFEST.write_text(json.dumps(chapter_manifest, indent=1), encoding="utf-8", newline="\n")
        REPORT.write_text("\n".join(report) + "\n", encoding="utf-8", newline="\n")

    all_units = [u for c in parts_manifest for u in c["parts"]]
    print(f"chapters: {len(parts_manifest)}, processing units: {len(all_units)}")
    if all_units:
        print(f"largest file: {max(u['bytes'] for u in all_units)} bytes")
        print(f"multi-part chapters: {sum(1 for c in parts_manifest if c['part_count'] > 1)}")
        print(f"units over the {HARD_CAP}-byte cap: {sum(1 for u in all_units if u['bytes'] > HARD_CAP)}")
    flagged = sum(1 for line in report if line.startswith("  !!"))
    if flagged:
        print(f"{flagged} issue(s) flagged" + ("" if args.dry_run else f" in {rel(REPORT)}"))
    if args.dry_run:
        print("dry run: nothing written")


if __name__ == "__main__":
    main()
