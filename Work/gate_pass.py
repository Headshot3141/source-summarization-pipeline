"""Gate a batch of an editing pass: check each chapter's edits against its record.

After an editing pass, every change to a chapter summary must be one the
record explains, every source excerpt in the record must be the source's
own words, and nothing the pass did not mean to touch (paragraph breaks,
headings, quotations, names, the author's naming) may change. In one run
the coordinator rewrote this check for every pass, each copy slightly
different; one pass dropped three blank lines and its gate passed, so the
next round had to scan every file by hand.

Usage (from the project root):
    python Work/gate_pass.py <out> [n | slug | slug/unit_id ...] [options]

Reads Work/Prompts/<out>/index.txt (Work/make_prompts.py) and gates each
chapter whose records all exist (a split chapter's part tasks are gated
together; a cell may list several records joined with ";"). Without a
selection, every chapter that is ready; a selected chapter that is not ready
is a problem. For each chapter it prints one summary line and one line per
problem, appends one line to Work/Prompts/<out>/gate_log.md, and exits 1 if
any chapter has a problem.

Checks, against the snapshot copy Work/Summaries_pre<snapshot>/... (default
<snapshot>: <out>) and the chapter source:

  WORDS      before -> after; OVER CAP with --cap (the index's cap column).
  DIFF       the word diff (difflib over whitespace-split words). Each
             changed run (its new words; a deletion's old words), normalized
             (lower case, dashes and ellipses spaced, markup, brackets and
             quotation marks dropped, trailing punctuation stripped), must
             occur in the record; a run under 4 words needs 3 words of its
             context too. Typography-only changes are skipped. Others are
             UNMATCHED, shown with 6 words around them. --no-match makes them
             notes, for a pass whose records hold no Before/After entries
             (the style pass).
  STRUCTURE  paragraph count and heading list against the snapshot
             (PARAGRAPHS a -> b, HEADINGS CHANGED; notes only with
             --keep-structure, for a pass allowed to move structure), and
             lines Markdown will run together (common.paragraph_break_problems)
             that the snapshot did not have.
  ENTRIES    each record entry with Before/After ("### <ID> (...): label",
             any heading from ## to ####, IDs such as E-3, 4.2, or I.3;
             fields "Before:", "After:", "Words:", bold and "- " bullets
             allowed, fields may wrap): AFTER NOT IN SUMMARY, BEFORE NOT IN
             SNAPSHOT; its word change recounted with the shared counter
             (After minus Before) against its Words: line, and against
             --max-delta N. Entries without Before/After (findings not
             applied, coverage notes) are not edits. NO RECORD ENTRY for an
             item ID in the index's items column (or the item file it names)
             that no record heading carries (X-1a counts for X-1).
             --sections "A;B": each record must have those ## sections.
  SOURCE     on "Source" lines, each quoted span of 20+ characters is split
             at "...", "…", and "[…]"; every piece of 5+ words must occur in
             the normalized chapter source, else SOURCE NOT FOUND.
  FIDELITY   check_fidelity on the summary and on the snapshot copy; only
             flags the snapshot did not have are problems.
  AUTHOR     check_author_refs flagged paragraphs: more than the snapshot had
             is a problem.

Reading aids (printed, never problems):

  --pairs [--min 6]  each inserted or replaced run of at least --min words,
             beside the three-sentence source window with the most content
             words in common (and that share), and the content words the
             source never uses (NOT IN SOURCE; a plural "s" is tolerated):
             where an agent may have added words.
  --show     each changed sentence, old and new, with the sentence before
             and after it; pronouns and demonstratives (he she it they this
             these that which) in the next sentence are marked [[like
             this]]. In one run about a quarter of the defects a late
             validation found sat in wording a later pass wrote, often a
             pronoun in the next sentence that now pointed at the inserted
             one.

--records DIR reads each record from Work/Reviews/<slug>/DIR/<file> instead
of the index's path (the same file name, another pass folder).

Known false positives: a source excerpt that spans a page marker or a note
number joined to a word is found, but one that spans a paragraph the
extraction split, or adds an ellipsis without marking it, is not; a
paraphrase put in quotation marks on a Source line is SOURCE NOT FOUND (it
belongs outside them); a fidelity NAME flag on a sentence-opening word that
moved to the start of a sentence; a short changed run whose context words
the record quotes with different punctuation or line breaks inside a
quotation.
"""
import argparse
import datetime
import difflib
import json
import re
import sys
from collections import Counter
from pathlib import PurePosixPath

import check_author_refs
import check_fidelity
import collect_items
import make_prompts
from common import ROOT, chapter_body, paragraph_break_problems, utf8_output
from count_words import words_in_text

PROMPTS = ROOT / "Work" / "Prompts"
PARTS_MANIFEST = ROOT / "Work" / "parts_manifest.json"
GATE_LOG = "gate_log.md"
# Problem kinds, longest first where one starts another, for the log's tally.
KINDS = ("NOT A CANONICAL SUMMARY", "NO SNAPSHOT", "NO SOURCE", "OVER CAP", "UNMATCHED", "PARAGRAPHS",
         "HEADINGS CHANGED", "BREAK", "AFTER NOT IN SUMMARY", "BEFORE NOT IN SNAPSHOT", "WORDS",
         "OVER MAX DELTA", "NO RECORD ENTRY", "MISSING SECTION", "SOURCE NOT FOUND", "NEW FIDELITY FLAG",
         "AUTHOR")

QUOTES = "\"'‘’“”«»"
CONTEXT = 3       # words of context a short changed run needs in the record
SHORT_RUN = 4     # runs shorter than this need context
SHOW_WORDS = 6    # words shown around an unmatched run
MIN_PIECE = 5     # words a source excerpt piece needs to be checked
EDIT_FIELDS = ("Before", "After")
FIELD = re.compile(r"^\s*(?:[-*+]\s+)?\**\s*([A-Z][A-Za-z]*(?: [a-z]+){0,2})\s*\**\s*:\s*\**\s*(.*)$")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
EMPTY_VALUE = re.compile(r"^\(?\s*(none|n/a|unchanged|omitted|omit|no change|-|—)\b", re.I)
QUOTED_SPAN = re.compile(r"[\"“]([^\"“”]{20,}?)[\"”]")
ELLIPSIS = re.compile(r"\.\s?\.\s?\.|…|\[[^\]]*\]")
PRONOUNS = re.compile(r"\b(he|she|it|they|this|these|that|which)\b", re.I)
STOP = set("""a an the and or but if of to in on at by for with from as is are was were be been being it its this that
these those he she they them his her their we our you i not no so than then there which who whom whose what when where
while had has have do does did would could should may might must can will shall also only even such more most other
into over under after before about because since all any each one two some very upon out up""".split())


# ------------------------------------------------------------------ text helpers

def norm_words(text):
    """Words for matching a diff run against a record: case, markup, quotes, and punctuation ignored."""
    text = text.lower().replace("—", " - ").replace("–", " - ").replace("…", " ... ")
    text = re.sub(r"[*_`#>\[\]()" + QUOTES + "]", " ", text)
    return [w for w in (re.sub(r"[.,;:!?]+$", "", t) for t in text.split()) if w]


def norm_src(text):
    """Source text for finding an excerpt: comments, punctuation, dashes, and bare numbers removed."""
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = text.lower().replace("—", " ").replace("–", " ").replace("-", " ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\b\d+\b", " ", text)
    return " ".join(text.split())


def joined(words):
    return " " + " ".join(words) + " "


def contains(hay, needle):
    return bool(needle) and joined(needle) in hay


def read(path):
    return (ROOT / path).read_text(encoding="utf-8-sig").replace("\r\n", "\n")


def clip(text, n=300):
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n - 3] + "..."


# ------------------------------------------------------------------ records

def unquote(value):
    """A Before/After value without its outer quotation marks; "" for none or unchanged."""
    v = (value or "").strip()
    if not v or EMPTY_VALUE.match(v):
        return ""
    if len(v) >= 2 and v[0] in "\"“" and v[-1] in "\"”":
        v = v[1:-1]
    return v.strip()


def heading_ids(heading):
    """The IDs a record heading names: "### E-3 (minor, x): label" -> ["E-3"]; "## 1.5+1.6" -> both."""
    text = heading.replace("*", "").strip()
    head = re.split(r"\s\(|:", text, maxsplit=1)[0]
    return [i.strip() for i in re.split(r"[,+&]|\s+and\s+", head) if i.strip()]


def entries(text):
    """[{id, ids, heading, fields}] for each heading block of a record; field values unwrapped."""
    out, cur, key = [], None, None
    for line in text.split("\n"):
        h = HEADING.match(line)
        if h:
            cur, key = None, None
            if len(h.group(1)) >= 2:
                cur = {"heading": h.group(2).strip(), "ids": heading_ids(h.group(2)), "fields": {}}
                out.append(cur)
            continue
        if cur is None:
            continue
        m = FIELD.match(line)
        if m:
            key = m.group(1)
            cur["fields"].setdefault(key, m.group(2).strip())
        elif key in EDIT_FIELDS + ("Source",) and line.strip():
            cur["fields"][key] += "\n" + line.strip()
        elif key in EDIT_FIELDS and not line.strip():
            cur["fields"][key] += "\n"
    for e in out:
        e["id"] = ", ".join(e["ids"]) or e["heading"]
        for k in EDIT_FIELDS:
            if k in e["fields"]:
                e["fields"][k] = e["fields"][k].strip()
    return out


def edit_entries(ents):
    return [e for e in ents if any(k in e["fields"] for k in EDIT_FIELDS)]


def claimed_words(value):
    m = re.search(r"([+\-−]?\s*\d+)", value or "")
    return int(m.group(1).replace("−", "-").replace(" ", "")) if m else None


def source_quotes(text):
    """[(line number, quoted span)] from the record's Source lines, wrapped lines joined."""
    out, lines = [], text.split("\n")
    for i, line in enumerate(lines):
        m = FIELD.match(line)
        if not m or m.group(1) != "Source":
            continue
        body = line
        for nxt in lines[i + 1:]:
            if not nxt.strip() or FIELD.match(nxt) or HEADING.match(nxt):
                break
            body += " " + nxt.strip()
        out += [(i + 1, q) for q in QUOTED_SPAN.findall(body)]
    return out


# ------------------------------------------------------------------ checks

def shape(text):
    """(paragraph count, [heading lines])."""
    blocks = [b for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]
    heads = [line.strip() for line in text.split("\n") if re.match(r"#{1,6}\s", line)]
    return len(blocks), heads


def break_keys(text):
    lines = text.split("\n")
    return {n: (msg, lines[n - 2].strip(), lines[n - 1].strip()) for n, msg in paragraph_break_problems(text)}


def changed_runs(old_text, new_text):
    """[(tag, i1, i2, j1, j2)] of the word diff, typography-only runs left out."""
    old, new = old_text.split(), new_text.split()
    runs = []
    for op in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        tag, i1, i2, j1, j2 = op
        if tag == "equal":
            continue
        if norm_words(" ".join(old[i1:i2])) == norm_words(" ".join(new[j1:j2])):
            continue
        runs.append(op)
    return old, new, runs


def run_matched(words, a, b, hay):
    seg = norm_words(" ".join(words[a:b]))
    if not seg:
        return True
    if len(seg) >= SHORT_RUN:
        return contains(hay, seg)
    left = norm_words(" ".join(words[max(0, a - CONTEXT):a]))
    right = norm_words(" ".join(words[b:b + CONTEXT]))
    return contains(hay, left + seg) or contains(hay, seg + right)


def fidelity_flags(summary_text, source_text, forms):
    return check_fidelity.check(summary_text, source_text, forms)


def author_flags(summary_path, text):
    slug, stem = check_author_refs.slug_and_stem(summary_path)
    refs, not_author = check_author_refs.load_config()
    patterns = [check_author_refs.ref_pattern(g) for g in check_author_refs.ref_groups(slug, stem, refs)]
    return len(check_author_refs.flagged_paragraphs(text, patterns, not_author.get(slug, [])))


def toks(text):
    return re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)*|\d+", text.lower().replace("’", "'"))


def content(words):
    return {w.strip("'") for w in words if w.strip("'") not in STOP and len(w.strip("'")) > 2}


def pairs(old, new, runs, source_text, minimum):
    """Lines pairing each long addition with its closest source window."""
    body = chapter_body(source_text)[1]  # frontmatter and title are not source prose
    src = " ".join(re.sub(r"<!--.*?-->", " ", body, flags=re.S).split())
    sents = re.split(r"(?<=[.!?:;])\s+", src)
    windows = [" ".join(sents[i:i + 3]) for i in range(len(sents))]
    wsets = [content(toks(w)) for w in windows]
    vocab = set(toks(src)) | {w.strip("'") for w in toks(src)}
    out = []
    for tag, i1, i2, j1, j2 in runs:
        if tag == "delete" or j2 - j1 < minimum:
            continue
        added = " ".join(new[j1:j2])
        cw = content(toks(added))
        if not cw or not windows:
            continue
        best = max(range(len(windows)), key=lambda k: len(cw & wsets[k]))
        share = len(cw & wsets[best]) / len(cw)
        missing = sorted(w for w in cw if w not in vocab and w.rstrip("s") not in vocab and w + "s" not in vocab)
        out.append("   pair (%s, %d words, overlap %d%%)" % (tag, j2 - j1, round(100 * share)))
        if tag == "replace":
            out.append("      old: " + clip(" ".join(old[i1:i2]), 600))
        out.append("      new: " + clip(added, 1500))
        out.append("      src: " + clip(windows[best], 1500))
        if missing:
            out.append("      NOT IN SOURCE: " + ", ".join(missing))
    return out


SENTENCE_END = re.compile(r"(?<=[.?!…\"”’)])\s+(?=[\"“‘(]?[A-Z0-9])")
PARA = "¶"


def sentences(text):
    """Sentences in order, with a paragraph mark between paragraphs."""
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        if block.strip():
            out += [s for s in SENTENCE_END.split(" ".join(block.split())) if s] + [PARA]
    return out


def show(old_text, new_text):
    """Each changed sentence in context, old and new; pronouns in the next sentence marked."""
    old, new = sentences(old_text), sentences(new_text)
    out = []

    def near(seq, i, step):
        while 0 <= i < len(seq) and seq[i] == PARA:
            i += step
        return seq[i] if 0 <= i < len(seq) else ""

    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        gone = [s for s in old[i1:i2] if s != PARA]
        added = [s for s in new[j1:j2] if s != PARA]
        para = new[:j1].count(PARA) + 1
        if not gone and not added:
            out.append("   [show] paragraph %d: paragraph break %s" % (para, "removed" if i2 > i1 else "added"))
            continue
        out.append("   [show] paragraph %d" % para)
        before = near(new, j1 - 1, -1)
        if before:
            out.append("      before: " + before)
        out += ["      - " + s for s in gone]
        out += ["      + " + s for s in added]
        after = near(new, j2, 1)
        if after:
            out.append("      after:  " + PRONOUNS.sub(lambda m: "[[%s]]" % m.group(0), after))
    return out


# ------------------------------------------------------------------ one chapter

def items_for(rows):
    """Item IDs from the rows' items cells: a list of IDs, or an item file to read them from."""
    ids = []
    for row in rows:
        cell = (row.get("items") or "-").strip()
        if cell in ("", "-"):
            continue
        if cell.endswith(".md") and (ROOT / cell).exists():
            ids += collect_items.item_ids(read(cell))
        else:
            ids += [i for i in re.split(r"[,\s]+", cell) if i]
    return list(dict.fromkeys(ids))


def has_entry(item, ids):
    return any(i == item or re.fullmatch(re.escape(item) + r"[a-z]", i) for i in ids)


def gate_chapter(summary, rows, records, args, manifest):
    """(summary line, problems, notes, reading aids)."""
    problems, notes, aids = [], [], []
    entry = manifest.get(summary)
    source = make_prompts.chapter_source(entry) if entry else None
    new_text = read(summary)
    try:
        snap = make_prompts.snapshot_copy(summary, args.snapshot)
    except SystemExit:
        snap = None
        problems.append("NOT A CANONICAL SUMMARY %s: it has no snapshot copy; the diff checks were skipped" % summary)
    old_text = read(snap) if snap and (ROOT / snap).exists() else None
    if snap and old_text is None:
        problems.append("NO SNAPSHOT %s: the diff checks were skipped" % snap)
    src_text = read(source) if source and (ROOT / source).exists() else None
    if src_text is None:
        problems.append("NO SOURCE %s: the source checks were skipped" % (source or "for this summary"))
    recs = [(r, read(r)) for r in records]
    rec_hay = " \x00 ".join(joined(norm_words(t)) for _, t in recs)

    # WORDS
    w_new = words_in_text(new_text)
    w_old = words_in_text(old_text) if old_text is not None else None
    caps = [int(r["cap"]) for r in rows if (r.get("cap") or "").isdigit()]
    cap = max(caps) if caps else None
    if args.cap and cap is not None and w_new > cap:
        problems.append("OVER CAP by %d (%d words, cap %d)" % (w_new - cap, w_new, cap))

    # DIFF
    runs, unmatched = [], 0
    if old_text is not None:
        old, new, runs = changed_runs(old_text, new_text)
        for tag, i1, i2, j1, j2 in runs:
            words, a, b = (old, i1, i2) if tag == "delete" else (new, j1, j2)
            if run_matched(words, a, b, rec_hay):
                continue
            unmatched += 1
            line = 'UNMATCHED %s: old "%s" | new "%s"' % (
                tag, clip(" ".join(old[max(0, i1 - SHOW_WORDS):i2 + SHOW_WORDS])),
                clip(" ".join(new[max(0, j1 - SHOW_WORDS):j2 + SHOW_WORDS])))
            (notes if args.no_match else problems).append(line)

    # STRUCTURE
    if old_text is not None:
        (pa, ha), (pb, hb) = shape(old_text), shape(new_text)
        target = notes if args.keep_structure else problems
        if pa != pb:
            target.append("PARAGRAPHS %d -> %d" % (pa, pb))
        if ha != hb:
            gone = [h for h in ha if h not in hb]
            added = [h for h in hb if h not in ha]
            what = "; ".join(x for x in ("removed %s" % gone if gone else "", "added %s" % added if added else "") if x)
            target.append("HEADINGS CHANGED: %s" % (what or "order changed"))
    before_breaks = set(break_keys(old_text).values()) if old_text is not None else set()
    for n, key in sorted(break_keys(new_text).items()):
        line = "BREAK line %d: %s" % (n, key[0])
        (notes if key in before_breaks else problems).append(line + (" (also in the snapshot)" if key in before_breaks else ""))

    # ENTRIES
    all_ents = [e for _, t in recs for e in entries(t)]
    edits = edit_entries(all_ents)
    new_hay = joined(norm_words(new_text))
    old_hay = joined(norm_words(old_text)) if old_text is not None else None
    total = 0
    for e in edits:
        b, a = unquote(e["fields"].get("Before")), unquote(e["fields"].get("After"))
        delta = words_in_text(a) - words_in_text(b)
        total += delta
        if a and not found_in(a, new_hay):
            problems.append('AFTER NOT IN SUMMARY %s: "%s"' % (e["id"], clip(a, 200)))
        if b and old_hay is not None and not found_in(b, old_hay):
            problems.append('BEFORE NOT IN SNAPSHOT %s: "%s"' % (e["id"], clip(b, 200)))
        claimed = claimed_words(e["fields"].get("Words"))
        if claimed is not None and claimed != delta:
            problems.append("WORDS %s: the record says %+d, counted %+d" % (e["id"], claimed, delta))
        if args.max_delta is not None and delta > args.max_delta:
            problems.append("OVER MAX DELTA %s: %+d (limit +%d)" % (e["id"], delta, args.max_delta))
    ids = [i for e in all_ents for i in e["ids"]]
    for item in items_for(rows):
        if not has_entry(item, ids):
            problems.append("NO RECORD ENTRY for item %s" % item)
    for name in [s.strip() for s in (args.sections or "").split(";") if s.strip()]:
        for r, t in recs:
            if not re.search(r"(?im)^##\s+\**\s*" + re.escape(name), t):
                problems.append('MISSING SECTION "%s" in %s' % (name, r))

    # SOURCE
    checked = 0
    if src_text is not None:
        hay = " " + norm_src(src_text) + " "
        for r, t in recs:
            for line, quote in source_quotes(t):
                for piece in ELLIPSIS.split(quote):
                    p = norm_src(piece)
                    if len(p.split()) < MIN_PIECE:
                        continue
                    checked += 1
                    if " " + p + " " not in hay:
                        problems.append('SOURCE NOT FOUND (%s:%d): "%s"' % (PurePosixPath(r).name, line, clip(piece, 160)))

    # FIDELITY
    new_flags = []
    if src_text is not None:
        forms = check_fidelity.author_forms(summary)
        now = fidelity_flags(new_text, src_text, forms)
        before = Counter((k, o[:40]) for k, o, *_ in fidelity_flags(old_text, src_text, forms)) \
            if old_text is not None else Counter()
        for kind, offending, n, line, context in now:
            key = (kind, offending[:40])
            if before[key] > 0:
                before[key] -= 1
                continue
            new_flags.append(1)
            problems.append('NEW FIDELITY FLAG %s para %d, line %d: "%s" | %s' % (kind, n, line, offending, clip(context, 160)))

    # AUTHOR
    a_new = author_flags(summary, new_text)
    a_old = author_flags(summary, old_text) if old_text is not None else 0
    if a_new > a_old:
        problems.append("AUTHOR: %d -> %d flagged paragraph(s) (python Work/check_author_refs.py %s)" % (a_old, a_new, summary))

    if old_text is not None and src_text is not None and args.pairs:
        aids += pairs(old, new, runs, src_text, args.min)
    if old_text is not None and args.show:
        aids += show(old_text, new_text)

    ns = ",".join(r["n"] for r in rows)
    keys = ",".join(dict.fromkeys(r["key"] for r in rows))
    words = ("%d -> %d words (%+d" % (w_old, w_new, w_new - w_old) if w_old is not None else "%d words (" % w_new)
    words += (", cap %d)" % cap if cap is not None else ")")
    head = ("== %s %s %s: %s; %d record(s), %d edit entr%s (sum %+d); %d changed run(s), %d unmatched; "
            "%d source piece(s) checked; %d new fidelity flag(s); author %d -> %d; %s" % (
                ns, keys, summary, words, len(recs), len(edits), "y" if len(edits) == 1 else "ies", total,
                len(runs), unmatched, checked, len(new_flags), a_old, a_new,
                "%d problem(s)" % len(problems) if problems else "OK"))
    return head, problems, notes, aids


def found_in(text, hay):
    """True if text (normalized) occurs in hay, or each piece of it between ellipses does."""
    if contains(hay, norm_words(text)):
        return True
    pieces = [norm_words(p) for p in ELLIPSIS.split(text)]
    pieces = [p for p in pieces if p]
    return len(pieces) > 1 and all(contains(hay, p) for p in pieces)


# ------------------------------------------------------------------ main

def chapters_to_gate(rows, selection, records_dir):
    """{summary: {"rows": [...], "records": [...]}} in index order, and unknown selectors."""
    chosen, unknown = [], []
    for sel in selection:
        hits = [r for r in rows if (sel.isdigit() and r["n"] == sel)
                or (not sel.isdigit() and (r["key"] == sel or r["key"].startswith(sel + "/")))]
        if not hits:
            unknown.append(sel)
        chosen += [r for r in hits if r not in chosen]
    out = {}
    for row in (chosen if selection else rows):
        recs = make_prompts.split_paths(row["record"])
        if records_dir:
            recs = [(PurePosixPath(r).parent.parent / records_dir / PurePosixPath(r).name).as_posix() for r in recs]
        for summary in make_prompts.split_paths(row["summary"]):
            ch = out.setdefault(summary, {"rows": [], "records": []})
            ch["rows"].append(row)
            ch["records"] += [r for r in recs if r not in ch["records"]]
    return out, unknown


def main(argv=None):
    utf8_output()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("select", nargs="*", help="task numbers, slugs, or slug/unit_id keys")
    ap.add_argument("--snapshot")
    ap.add_argument("--records", metavar="DIR")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--pairs", action="store_true")
    ap.add_argument("--min", type=int, default=6)
    ap.add_argument("--max-delta", type=int)
    ap.add_argument("--keep-structure", action="store_true")
    ap.add_argument("--no-match", action="store_true")
    ap.add_argument("--sections", metavar='"A;B"')
    ap.add_argument("--cap", action="store_true")
    args = ap.parse_args(argv)
    args.snapshot = args.snapshot or args.out

    out_dir = PROMPTS / args.out
    rows = make_prompts.read_index(out_dir)
    if not rows:
        sys.exit("no index.txt rows in %s; generate the prompts with Work/make_prompts.py" % make_prompts.rel(out_dir))
    chapters, unknown = chapters_to_gate(rows, args.select, args.records)
    manifest = {e["summary"]: e for e in make_prompts.load_json(PARTS_MANIFEST, [])}

    failed, gated, waiting, log = bool(unknown), 0, [], []
    for sel in unknown:
        print("== %s: no such task in %s" % (sel, make_prompts.rel(out_dir / make_prompts.INDEX)))
    for summary, ch in chapters.items():
        keys = ",".join(dict.fromkeys(r["key"] for r in ch["rows"]))
        missing = [r for r in ch["records"] if not (ROOT / r).exists()]
        if not ch["records"] or missing or not (ROOT / summary).exists():
            why = ("records missing (%d of %d)" % (len(missing), len(ch["records"])) if ch["records"]
                   else "the task has no record")
            if not (ROOT / summary).exists():
                why = "summary not found"
            if args.select:
                print("== %s %s: %s, not gated" % (keys, summary, why))
                failed = True
            else:
                waiting.append(keys)
            continue
        head, problems, notes, aids = gate_chapter(summary, ch["rows"], ch["records"], args, manifest)
        gated += 1
        print(head)
        for p in problems:
            print("   " + p)
        for n in notes:
            print("   note: " + n)
        for a in aids:
            print(a)
        failed = failed or bool(problems)
        kinds = Counter(next((k for k in KINDS if p.startswith(k)), p.split(" ", 1)[0]) for p in problems)
        log.append("- %s | %s | %s | %s" % (
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), keys, summary,
            ("%d problem(s): " % len(problems) + ", ".join("%s x%d" % kv for kv in sorted(kinds.items())))
            if problems else "OK"))
    if waiting:
        print("%d chapter(s) not gated, records not all written: %s" % (len(waiting), " ".join(waiting)))
    print("%d chapter(s) gated; %s" % (gated, "problems found" if failed else "no problems"))
    if log:
        path = out_dir / GATE_LOG
        head = "" if path.exists() else "# Gate log: %s\n\n" % args.out
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(head + "\n".join(log) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
