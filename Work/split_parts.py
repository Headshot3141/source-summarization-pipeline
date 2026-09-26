"""Split validated chapters into processing parts and build both manifests.

Reads chapter budgets from the Word Budgets tables in plan.md, keyed on
(source slug, unit ID). Rejects duplicate rows, retained units with no
row, and rows that match no retained unit, and writes nothing if any of
these are found.

Chapters whose complete file is at or under the hard cap stay whole and
are listed with their own path. Larger chapters are cut into parts. Each
part owns an exact slice of the chapter body, stored between owned-text
markers, so the ordered slices rebuild the chapter byte for byte. Text is
never rewritten here; repairs belong in extraction. A page marker stays
with the text that follows it. Extra context for weak boundaries comes
from Work/part_context.json (see CONTEXT_CONFIG), so reruns keep it.

Writes Work/parts_manifest.json, Work/manifest.json, and
Work/parts_report.txt. Statuses from a previous run are kept for units
whose files are unchanged, and reset to pending otherwise.
"""
import hashlib
import json
import re
import sys

from common import (
    HARD_CAP,
    OWNED_END,
    OWNED_START,
    PAGE_MARKER_RE,
    ROOT,
    chapter_body,
    ends_sentence,
    is_heading,
    rel,
    strip_comments,
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

OVERLAP_BLOCKS = 1
OVERLAP_START = "<!-- overlap context from the end of the previous part: use for reference only, do not re-summarize it, excluded from word_count and word_budget -->"
OVERLAP_END = "<!-- end overlap context -->"

# Extra original-source context for a part, added by the coordinator where a
# boundary separates a term from its definition, a claim from its evidence,
# and so on. Kept out of the part files so a rerun never loses it. Each entry:
#   {"source_slug": ..., "unit_id": ..., "part_index": 2, "part_count": 3,
#    "text": "exact chapter text", "reason": "optional note"}
# The text must appear verbatim in the chapter body. The splitter finds the
# part that owns it and places it before the owned text (earlier parts) or
# after it (later parts). Entries whose part_index/part_count no longer exist
# after a resplit are reported, not applied.
CONTEXT_CONFIG = ROOT / "Work" / "part_context.json"
CONTEXT_START = "<!-- context from {owner}, owned there: use for reference only, do not summarize it, excluded from word_count and word_budget -->"
CONTEXT_END = "<!-- end context -->"

SCRIPT_BLOCK_REASON = "part over hard cap"
ABBREVIATIONS = {
    "dr", "mr", "mrs", "ms", "st", "jr", "sr", "prof", "vs", "cf", "eg", "ie",
    "no", "vol", "pp", "p", "ch", "fig", "ed", "eds", "al", "gen", "col", "rev",
}
SENTENCE_GAP = re.compile(r"(?<=[.!?…”\")])\s+")


def size(text):
    return len(text.encode("utf-8"))


def sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- budgets

def parse_plan_budgets():
    """Return ({(slug, unit_id): row}, [errors]) from the Word Budgets section."""
    budgets, errors = {}, []
    if not PLAN.exists():
        return budgets, ["plan.md not found"]
    in_section = False
    current_part = None
    for n, line in enumerate(PLAN.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("## "):
            in_section = line.strip() == "## Word Budgets"
            continue
        if not in_section:
            continue
        m = re.match(r"^###\s+Part\s+(\d+):", line)
        if m:
            current_part = int(m.group(1))
            continue
        if current_part is None or not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        slug, unit, title, _source_words, target = cells[:5]
        if slug.lower() == "source slug" or re.fullmatch(r"[-: ]*", slug + unit):
            continue  # header or separator row
        if not slug and not target:
            continue  # unfilled template row
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
        budgets[key] = {"target": int(target.replace(",", "")), "title": title, "plan_part": current_part}
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


def make_parts(body, limit):
    """Return (part spans, oversized unit count)."""
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
    total = sum(sizes)
    parts = []
    cur_start, cur_size, consumed = units[0][0], 0, 0
    for i, (a, b) in enumerate(units):
        s = sizes[i]
        text = strip_comments(body[a:b]).strip()
        remaining = total - consumed
        prev = body[units[i - 1][0]:units[i - 1][1]] if i else ""
        can_break = (
            cur_size > 0
            and ends_sentence(prev)
            and not text[:1].islower()
            # Keep a multi-paragraph block quotation (verse) in one part.
            and not (is_block_quote(text) and is_block_quote(prev))
        )
        if can_break and (
            cur_size + s > limit
            or (cur_size + s > TARGET and remaining >= MIN_REMAINING)
            or (is_heading(text) and cur_size >= PREFER_HEADING_AT and remaining >= MIN_REMAINING)
        ):
            parts.append((cur_start, a))
            cur_start, cur_size = a, 0
        cur_size += s
        consumed += s
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


def overlap_blocks(body, prev_span, count):
    if count <= 0:
        return []
    spans = [(a, b) for a, b in paragraph_units(body) if a >= prev_span[0] and b <= prev_span[1]]
    return [body[a:b].strip() for a, b in spans[-count:]]


def context_block(owner, text):
    return CONTEXT_START.format(owner=owner) + "\n\n" + text + "\n\n" + CONTEXT_END


def render_part(fields, heading, overlap, owned, before=(), after=()):
    """before/after: [(owner label, text)] extra context from other parts."""
    head = "---\n" + "".join(f"{k}: {yaml_value(v)}\n" for k, v in fields) + "---\n\n" + heading + "\n\n"
    context = ""
    if overlap:
        context = OVERLAP_START + "\n\n" + "\n\n".join(overlap) + "\n\n" + OVERLAP_END + "\n\n"
    context += "".join(context_block(o, t) + "\n\n" for o, t in before)
    tail = "".join("\n\n" + context_block(o, t) for o, t in after)
    return head + context + OWNED_START + owned + OWNED_END + tail + "\n"


def load_context():
    """Return ({(slug, unit, part_index, part_count): [entry]}, [problems])."""
    if not CONTEXT_CONFIG.exists():
        return {}, []
    try:
        entries = json.loads(CONTEXT_CONFIG.read_text(encoding="utf-8"))
    except ValueError as exc:
        return {}, [f"{CONTEXT_CONFIG.name}: not valid JSON: {exc}"]
    grouped, problems = {}, []
    for n, e in enumerate(entries if isinstance(entries, list) else [], 1):
        keys = ("source_slug", "unit_id", "part_index", "part_count", "text")
        if not isinstance(e, dict) or any(not e.get(k) for k in keys):
            problems.append(f"{CONTEXT_CONFIG.name} entry {n}: needs {', '.join(keys)}")
            continue
        key = (e["source_slug"], e["unit_id"], e["part_index"], e["part_count"])
        grouped.setdefault(key, []).append(e)
    if not isinstance(entries, list):
        problems.append(f"{CONTEXT_CONFIG.name}: must be a JSON list")
    return grouped, problems


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
        (before if owners[-1] < k else after).append((label, text.strip()))
    return before, after


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


def main():
    budgets, errors = parse_plan_budgets()
    chapters = collect_chapters(budgets, errors)
    if errors:
        print("split_parts: nothing written. Fix these first:")
        for e in errors:
            print("  " + e)
        sys.exit(1)

    contexts, context_problems = load_context()
    used_contexts = set()
    old_parts = {(c["source_slug"], c["unit_id"]): c for c in load_json(PARTS_MANIFEST, [])}
    old_status = {(c["source_slug"], c["unit_id"]): c["status"] for c in load_json(CHAPTER_MANIFEST, [])}

    chapters.sort(key=lambda c: (c["meta"].get("part") or 0, str(c["path"])))
    report, parts_manifest, chapter_manifest = [], [], []
    for ch in chapters:
        path, meta, body = ch["path"], ch["meta"], ch["body"]
        slug, unit = ch["key"]
        budget = budgets[ch["key"]]["target"]
        stem = path.stem
        parts_dir = path.parent / "parts"
        summary = f"Work/Summaries/{slug}/{stem}.md"
        notes = []
        if meta.get("word_count") != ch["words"]:
            notes.append(f"frontmatter word_count {meta.get('word_count')} differs from measured {ch['words']}")

        written = set()
        units = []
        if ch["bytes"] <= HARD_CAP:
            units.append({
                "part_index": 1, "part_count": 1,
                "source": rel(path),
                "draft": f"Work/Drafts/{slug}/{stem}.md",
                "summary": summary,
                "record": f"Work/Reviews/{slug}/{stem}.md",
                "words": ch["words"], "budget": budget, "bytes": ch["bytes"],
                "sha": ch["sha"], "status": "pending", "context_from": [],
            })
        else:
            spans, oversized = make_parts(body, HARD_CAP - FILE_OVERHEAD)
            if oversized:
                notes.append(f"{oversized} sentence(s) too long to fit any part: resegment in extraction or block the unit")
            m = len(spans)
            words = [words_in_text(body[a:b]) for a, b in spans]
            shares = [int(round(budget * w / ch["words"])) for w in words]
            shares[words.index(max(words))] += budget - sum(shares)
            parts_dir.mkdir(exist_ok=True)
            for k, ((a, b), w, share) in enumerate(zip(spans, words, shares), 1):
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
                want = OVERLAP_BLOCKS if k > 1 else 0
                overlap = overlap_blocks(body, spans[k - 2], want) if k > 1 else []
                ckey = (slug, unit, k, m)
                before, after = place_context(contexts.get(ckey, []), body, spans, k, unit, notes)
                if ckey in contexts:
                    used_contexts.add(ckey)
                content = render_part(fields, heading, overlap, owned, before, after)
                while overlap and size(content) > HARD_CAP:
                    overlap = overlap[1:]
                    content = render_part(fields, heading, overlap, owned, before, after)
                if k > 1 and len(overlap) < want:
                    notes.append(f"part {k}: overlap dropped to {len(overlap)} block(s) to stay under the cap; inspect this boundary")
                data = content.encode("utf-8")
                (parts_dir / pname).write_bytes(data)
                written.add(pname)
                status = "pending"
                if len(data) > HARD_CAP:
                    status = "blocked"
                    fix = "; shorten the added context or move the boundary" if before or after else ""
                    notes.append(f"part {k}: {len(data)} bytes is over the {HARD_CAP}-byte cap; not assignable{fix}")
                units.append({
                    "part_index": k, "part_count": m,
                    "source": f"Work/Chapters/{slug}/parts/{pname}",
                    "draft": f"Work/Drafts/{slug}/parts/{pname}",
                    "summary": f"Work/Summaries/{slug}/parts/{pname}",
                    "record": f"Work/Reviews/{slug}/parts/{pname}",
                    "words": w, "budget": share, "bytes": len(data),
                    "sha": sha(data), "status": status,
                    "context_from": [o for o, _ in before + after],
                })

        # Remove part files left over from an earlier split of this chapter.
        if parts_dir.exists():
            for stale in parts_dir.glob(f"{stem}-part*-of-*.md"):
                if stale.name not in written:
                    stale.unlink()

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

        parts_manifest.append({
            "source_slug": slug,
            "unit_id": unit,
            "part": meta.get("part"),
            "chapter": meta.get("chapter"),
            "title": meta.get("title", ""),
            "chapter_source": rel(path),
            "chapter_sha": ch["sha"],
            "summary": summary,
            "words": ch["words"],
            "budget": budget,
            "part_count": len(units),
            "status": status,
            "blocked_reason": SCRIPT_BLOCK_REASON if script_blocked else None,
            "parts": units,
        })
        chapter_manifest.append({"source_slug": slug, "unit_id": unit, "path": summary, "status": status})
        maxb = max(u["bytes"] for u in units)
        report.append(
            f"{slug}/{unit} ({path.name}): {len(units)} part(s), {ch['words']} words, "
            f"budget {budget}, largest file {maxb} bytes, status {status}"
        )
        report.extend("  !! " + n for n in notes)

    for slug, unit, k, m in sorted(set(contexts) - used_contexts):
        context_problems.append(
            f"{CONTEXT_CONFIG.name}: context for {slug}/{unit} part {k} of {m} matches no part "
            f"(the chapter was resplit or is unsplit); re-inspect its boundaries and update the entry"
        )
    report.extend("  !! " + p for p in context_problems)

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
        print(f"{flagged} issue(s) flagged in {rel(REPORT)}")


if __name__ == "__main__":
    main()
