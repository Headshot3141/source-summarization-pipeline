"""Flag summary text that the source does not support word for word.

Summaries reproduce numbers, names, and quotations exactly as the source
prints them (errors included), never compute totals, averages, or rounded
figures, and reproduce a block quotation whole or not at all. This script
compares a summary with its source and flags four kinds of text:

  NUMBER      a digit token (thousands separators removed, a trailing % or
              ordinal suffix ignored) that does not occur as a number in the
              source, or a number word (zero to twenty, the tens, hundred,
              thousand, million, billion, half, third, quarter, dozen, twice,
              percent) when neither the word nor its digit form occurs there.
              A source number word counts as its digit form and the reverse
              ("twelve" supports 12), as does "3 million" for 3,000,000.
  QUOTE       a quoted span of 3+ words ("...", curly double quotes, or
              single curly quotes) that is not in the source. The first letter
              of each piece may differ in case, trailing sentence punctuation
              inside the quote may be missing from the source, and an ellipsis
              (... or the single character) is a gap: the pieces must occur in
              order. A span found only inside a source block quotation is also
              flagged, because a block quotation is never partially quoted.
  BLOCKQUOTE  each run of consecutive "> " paragraphs must equal one whole
              run in the source, minus the parenthetical citation or dash
              attribution that ends it. PARTIAL: an excerpt of a source block
              quotation. ALTERED: no source run matches (the closest source
              run is shown).
  NAME        a capitalized word that is not at the start of a sentence (after
              . ! ? : an opening quote, or the start of a line) and is absent
              from the source, case-sensitively. This catches silently
              corrected spellings and invented actors. Text inside quotations
              is skipped (QUOTE covers it). Allowed: the author and speaker
              name forms in Work/author_refs.json for the file's source or
              unit, and ALLOWED_NAMES below.

Both texts are normalized first: frontmatter and HTML comments removed, curly
and straight quotes and apostrophes unified (single and double alike, so a
quotation nested in a quotation still matches), dashes unified with the
spaces around them removed, ". . ." and the ellipsis character read as "...",
"*" emphasis removed, and whitespace collapsed. Summary headings are ignored.
Numbers and names inside a summary block quotation are checked only when that
block quotation fails the BLOCKQUOTE check.

Flags are prompts to check, not automatic defects. A number may legitimately
appear as a word form the source also uses, a capitalized word may be a
heading-style term the source capitalizes differently, and a quotation may
differ from the source only in a way the writing rules allow. The reviewer
dispositions every flag in the unit's review record: corrected, or kept with
the reason.

For a part file, the whole part file is the evidence, overlap and context
blocks included, because the summary may draw on them.

Usage (from the project root):
    python Work/check_fidelity.py <summary> <source>
    python Work/check_fidelity.py          # every summary in Work/parts_manifest.json

<source> is the chapter file (Work/Chapters/<slug>/NN-name.md) or a part file
(Work/Chapters/<slug>/parts/...). With no arguments, each existing summary in
the parts manifest is checked: an unsplit unit against its chapter, each part
summary against its part file, and a merged chapter summary against the
chapter. Drafts are checked by passing their paths. The source slug for
author_refs.json comes from the summary path (Work/Drafts/<slug>/...,
Work/Summaries/<slug>/...).

Output: one line per flag,
    KIND para N, line L: "offending text" | context snippet
(paragraphs are blank-line-separated blocks of the summary, headings
included; BLOCKQUOTE lines name PARTIAL or ALTERED after the kind), then a
count per kind. Exit status is 1 when anything is flagged, else 0.
"""
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

import check_author_refs
from common import ROOT, parse_frontmatter, strip_comments

PARTS_MANIFEST = ROOT / "Work" / "parts_manifest.json"
KINDS = ("NUMBER", "QUOTE", "BLOCKQUOTE", "NAME")

# Capitalized words that never need source support. "I" is the pronoun;
# "Chapter" and "Part" let a summary refer to the book's own divisions.
ALLOWED_NAMES = {"I", "Chapter", "Part"}

# Block-quotation endings, mirrored from Work/extract.py (BLOCK_CITATION,
# EPIGRAPH, CITATION_ONLY), which cannot be imported without its PDF
# dependencies. Keep them in step.
BLOCK_CITATION = re.compile(r"[.?!…”’\]]\s*\([^()]*\d[^()]*\)$")
EPIGRAPH = re.compile(r"[.?!…”’]\s+—\s?[A-Z][^—?!]{1,80}$")
CITATION_ONLY = re.compile(r"^\([^()]*\d[^()]*\)$")

# Quotations. A single curly quotation opens after the start, a space, or an
# opening bracket, quote, or dash, and closes before a space, punctuation, or
# the end, so apostrophes (the mill’s, ’tis, workers’) are not read as quotes.
DOUBLE_QUOTE = re.compile(r'"([^"\n]+)"|“([^”\n]+)”')
SINGLE_QUOTE = re.compile(r"(?<![^\s(\[“\"—–-])‘((?:[^‘’\n]|’(?=\w))+)’(?![\w])")

NUMBER_TOKEN = re.compile(r"\d+(?:[.,]\d+)*")
THOUSANDS = re.compile(r"^\d{1,3}(?:,\d{3})+(?:\.\d+)?$")

UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
}
SCALES = {"hundred": 100, "thousand": 1000, "million": 10 ** 6, "billion": 10 ** 9}
# Other number words: the digit value or source strings that support them.
OTHER_NUMBER_WORDS = {
    "dozen": 12, "dozens": 12, "twice": 2,
    "half": ["½", "1/2"], "halves": ["½", "1/2"],
    "third": ["⅓", "1/3", "3rd"], "thirds": ["⅓", "1/3"],
    "quarter": ["¼", "1/4"], "quarters": ["¼", "1/4"],
    "percent": ["%", "per cent"],
}
PLURAL_SCALES = {w + "s": w for w in SCALES}
_NUM_WORD = "|".join(sorted(list(UNITS) + list(SCALES), key=len, reverse=True))
NUMBER_WORD_RUN = re.compile(
    r"\b(?:%s)(?:(?:\s*-\s*|\s+and\s+|\s+)(?:%s))*\b" % (_NUM_WORD, _NUM_WORD), re.I)
OTHER_WORD = re.compile(
    r"\b(?:%s)\b" % "|".join(sorted(list(OTHER_NUMBER_WORDS) + list(PLURAL_SCALES), key=len, reverse=True)),
    re.I)
DIGIT_SCALE = re.compile(r"(\d+(?:[.,]\d+)*)\s+(hundred|thousand|million|billion)\b", re.I)

WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)*")
POSSESSIVE = re.compile(r"'s$")


# ---------------------------------------------------------------- normalizing

def normalize(text):
    """Text with quotes, dashes, ellipses, emphasis, and whitespace unified."""
    text = re.sub(r"[“”„‟″\"‘’‚‛′`]", "'", text)
    text = re.sub(r"\s*(?:--|[-‐‑‒–—―−])\s*", "-", text)
    text = re.sub(r"\.\s\.\s\.", "...", text).replace("…", "...")
    text = text.replace("*", "")
    return re.sub(r"\s+", " ", text).strip()


def blocks(text):
    """[(first line number, block text)] for blank-line-separated blocks.

    A line holding only ">" separates block-quotation paragraphs, as a blank
    line does.
    """
    out, cur, start = [], [], 0
    for n, line in enumerate(text.split("\n"), 1):
        if not line.strip() or re.fullmatch(r"\s*>\s*", line):
            if cur:
                out.append((start, "\n".join(cur)))
                cur = []
            continue
        if not cur:
            start = n
        cur.append(line)
    if cur:
        out.append((start, "\n".join(cur)))
    return out


def is_quote_block(block):
    return block.lstrip().startswith(">")


def unquote_block(block):
    """A "> " paragraph's text without the markers."""
    return "\n".join(re.sub(r"^\s*>\s?", "", ln) for ln in block.split("\n"))


def quote_groups(paras):
    """Group consecutive block-quote paragraphs: [[index, ...], ...]."""
    groups, cur = [], []
    for i, (_, block) in enumerate(paras):
        if is_quote_block(block):
            cur.append(i)
        elif cur:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def strip_citation(paras):
    """A source block quotation's paragraphs without the citation that ends it."""
    paras = list(paras)
    if paras and CITATION_ONLY.match(paras[-1].strip()):
        paras.pop()
    if paras:
        last = paras[-1].rstrip()
        m = BLOCK_CITATION.search(last)
        if m:
            last = last[:m.start() + 1]
        else:
            m = EPIGRAPH.search(last)
            if m:
                last = last[:m.start() + 1]
        paras[-1] = last
    return paras


class Source:
    """The normalized evidence for one summary."""

    def __init__(self, raw):
        _, rest = parse_frontmatter(raw.replace("\r\n", "\n").lstrip("﻿"))
        paras = [b for _, b in blocks(strip_comments(rest))]
        prose, quoted = [], []
        for block in paras:
            if is_quote_block(block):
                quoted.append(normalize(unquote_block(block)))
            else:
                prose.append(normalize(re.sub(r"^#+\s*", "", block)))
        self.prose = "\n".join(prose)
        self.text = "\n".join(prose + quoted)
        # Each source block quotation as normalized paragraphs, citation
        # removed; also kept whole so a summary that kept the citation can be told.
        self.quotes = []
        for group in quote_groups([(0, b) for b in paras]):
            raw_paras = [unquote_block(paras[i]) for i in group]
            self.quotes.append(([normalize(p) for p in strip_citation(raw_paras)],
                                [normalize(p) for p in raw_paras]))
        self.numbers = number_set(self.text)
        self.words_lower = {w.lower() for w in WORD.findall(self.text)}
        self.names = {POSSESSIVE.sub("", w) for w in WORD.findall(self.text)}


# ------------------------------------------------------------------- numbers

def number_value(token):
    """A digit token as a comparable string: "1,250" -> "1250"."""
    return token.replace(",", "") if THOUSANDS.match(token) else token


def words_value(run):
    """The value of a run of number words: "two hundred and five" -> 205."""
    total = current = 0
    for w in re.findall(r"[a-z]+", run.lower()):
        if w in UNITS:
            current += UNITS[w]
        elif w == "hundred":
            current = max(current, 1) * 100
        elif w in SCALES:
            total += max(current, 1) * SCALES[w]
            current = 0
    return total + current


def scaled(token, scale):
    try:
        value = float(number_value(token).replace(",", "")) * SCALES[scale.lower()]
    except ValueError:
        return None
    return str(int(value)) if value == int(value) else str(value)


def number_set(text):
    """Every number in normalized text, as comparable strings."""
    found = {number_value(t) for t in NUMBER_TOKEN.findall(text)}
    found |= {str(words_value(m.group())) for m in NUMBER_WORD_RUN.finditer(text)}
    for m in DIGIT_SCALE.finditer(text):
        value = scaled(m.group(1), m.group(2))
        if value:
            found.add(value)
    for word, value in OTHER_NUMBER_WORDS.items():
        if isinstance(value, int) and re.search(r"\b%s\b" % word, text, re.I):
            found.add(str(value))
    return found


def number_flags(text, src):
    """[(offending text, position)] for numbers the source does not support."""
    flags = []
    scale_after = {m.start(1): m for m in DIGIT_SCALE.finditer(text)}
    for m in NUMBER_TOKEN.finditer(text):
        token = m.group()
        if number_value(token) in src.numbers:
            continue
        sm = scale_after.get(m.start())
        if sm and scaled(sm.group(1), sm.group(2)) in src.numbers:
            continue
        flags.append((token, m.start()))
    for m in NUMBER_WORD_RUN.finditer(text):
        words = re.findall(r"[a-z]+", m.group().lower())
        words = [w for w in words if w != "and"]
        if all(w in src.words_lower for w in words) or str(words_value(m.group())) in src.numbers:
            continue
        # "3 million": the scale is supported when the scaled value is.
        before = re.search(r"(\d+(?:[.,]\d+)*)\s+$", text[:m.start()])
        if before and len(words) == 1 and words[0] in SCALES and scaled(before.group(1), words[0]) in src.numbers:
            continue
        flags.append((m.group(), m.start()))
    for m in OTHER_WORD.finditer(text):
        w = m.group().lower()
        if w in PLURAL_SCALES:
            if w in src.words_lower or PLURAL_SCALES[w] in src.words_lower:
                continue
        elif w in src.words_lower:
            continue
        else:
            value = OTHER_NUMBER_WORDS[w]
            if isinstance(value, int) and str(value) in src.numbers:
                continue
            if isinstance(value, list) and any(v in src.text.lower() for v in value):
                continue
        flags.append((m.group(), m.start()))
    return flags


# ---------------------------------------------------------------- quotations

def quote_spans(text):
    """[(start, end, inner text)] for quotations in raw text, outermost only."""
    spans = [(m.start(), m.end(), m.group(1) or m.group(2)) for m in DOUBLE_QUOTE.finditer(text)]
    for m in SINGLE_QUOTE.finditer(text):
        if not any(a <= m.start() < b for a, b, _ in spans):
            spans = [s for s in spans if not (m.start() <= s[0] < m.end())]
            spans.append((m.start(), m.end(), m.group(1)))
    return sorted(spans)


def find_in(quote, haystack):
    """True if the normalized quotation occurs in haystack (see the docstring)."""
    pieces = [p.strip() for p in quote.split("...")]
    last = max((i for i, p in enumerate(pieces) if p.strip(" .,;:!?")), default=-1)
    pos = 0
    for i, piece in enumerate(pieces):
        if i == last:
            piece_variants = [piece, piece.rstrip(".,;:!?").rstrip()]
        else:
            piece_variants = [piece]
        piece_variants = [v for v in piece_variants if v.strip(" .,;:!?'")]
        if not piece_variants:
            continue
        best = None
        for v in piece_variants:
            for cand in {v, v[0].swapcase() + v[1:]}:
                k = haystack.find(cand, pos)
                if k >= 0 and (best is None or k + len(cand) < best):
                    best = k + len(cand)
        if best is None:
            return False
        pos = best
    return True


def quote_flags(text, src):
    """[(offending text, position, note)] for unsupported quotations."""
    flags = []
    for start, _, inner in quote_spans(text):
        if len(inner.split()) < 3:
            continue
        q = normalize(inner)
        if not find_in(q, src.text):
            flags.append((inner, start, ""))
        elif not find_in(q, src.prose):
            flags.append((inner, start, "excerpt of a source block quotation"))
    return flags


def blockquote_flag(paras, src):
    """None if a summary block quotation matches a whole source one, else
    (PARTIAL or ALTERED, note)."""
    joined = "\n".join(paras)
    for bare, whole in src.quotes:
        if paras == bare:
            return None
    for bare, whole in src.quotes:
        if paras == whole:
            return "ALTERED", "keeps the source citation; drop it"
    for bare, whole in src.quotes:
        if find_in(joined, "\n".join(whole)):
            return "PARTIAL", "excerpt of a source block quotation; reproduce it whole or drop it"
    best, near = 0.0, ""
    for bare, _ in src.quotes:
        other = "\n".join(bare)
        ratio = SequenceMatcher(None, joined, other, autojunk=False).ratio()
        if ratio > best:
            best, near = ratio, other
    note = "closest source quotation: %s" % snippet(near, 0, 0) if near else "no block quotation in the source"
    return "ALTERED", note


# --------------------------------------------------------------------- names

def mask_quotes(text):
    """Replace each quotation's content with "x", keeping a final . ! ? or :
    so a sentence that ends inside a quotation still ends."""
    out, pos = [], 0
    for start, end, inner in quote_spans(text):
        tail = inner.rstrip()[-1:] if inner.rstrip()[-1:] in ".!?:" else ""
        out.append(text[pos:start] + text[start] + "x" + tail + text[end - 1])
        pos = end
    out.append(text[pos:])
    return "".join(out)


def sentence_start(before):
    """True if a word after this text starts a sentence: at the start of a
    line (after any list marker), or after . ! ? : (and closing quotes or
    brackets), or after an opening quote."""
    line = before.split("\n")[-1].rstrip()
    if re.fullmatch(r"\s*(?:[-*]|\d+[.)])?", line):
        return True
    return bool(re.search(r"[.!?:][\"')\]”]*$", line) or re.search(r"[\"'“]$", line))


def name_flags(text, src, allowed):
    """[(offending text, context)] for capitalized words absent from the
    source; adjacent flagged words are reported as one run."""
    flags = []
    norm = re.sub(r"[’‘]", "'", mask_quotes(text))
    for m in WORD.finditer(norm):
        word = POSSESSIVE.sub("", m.group())
        if not word[0].isupper() or sentence_start(norm[:m.start()]):
            continue
        if word in allowed or word in src.names:
            continue
        flags.append((word, m.start(), m.end()))
    runs = []
    for word, start, end in flags:
        if runs and re.fullmatch(r"\s+", norm[runs[-1][2]:start]):
            runs[-1] = (runs[-1][0] + norm[runs[-1][2]:start] + word, runs[-1][1], end)
        else:
            runs.append((word, start, end))
    return [(w, snippet(norm, s, len(w))) for w, s, _ in runs]


def author_forms(summary_path):
    """Words of every author and speaker name form for the summary's source/unit."""
    slug, stem = check_author_refs.slug_and_stem(summary_path)
    refs, _ = check_author_refs.load_config()
    words = set()
    for group in check_author_refs.ref_groups(slug, stem, refs):
        for form in group:
            words.update(POSSESSIVE.sub("", w) for w in WORD.findall(form.replace("’", "'")))
    return words


# ---------------------------------------------------------------------- check

def snippet(text, start, length, width=40):
    a, b = max(0, start - width), min(len(text), start + length + width)
    s = re.sub(r"\s+", " ", text[a:b]).strip()
    return ("..." if a else "") + s + ("..." if b < len(text) else "")


def check(summary_raw, source_raw, allowed=frozenset()):
    """[(kind, offending text, paragraph number, line, context)] for a summary."""
    src = Source(source_raw)
    summary_raw = summary_raw.replace("\r\n", "\n").lstrip("﻿")
    _, rest = parse_frontmatter(summary_raw)
    text = strip_comments(rest)
    paras = blocks(text)
    allowed = set(allowed) | ALLOWED_NAMES
    found, seen = [], set()

    def add(kind, offending, n, line, context):
        key = (kind, offending, n)
        if key not in seen:
            seen.add(key)
            found.append((kind, offending, n, line, context))

    failed_quotes = set()
    for group in quote_groups(paras):
        qparas = [normalize(unquote_block(paras[i][1])) for i in group]
        flag = blockquote_flag(qparas, src)
        if flag:
            failed_quotes.update(group)
            n = group[0]
            first = unquote_block(paras[n][1])
            add("BLOCKQUOTE", "%s: %s" % (flag[0], snippet(first, 0, 0, 30)), n + 1, paras[n][0], flag[1])

    for i, (line, block) in enumerate(paras):
        if block.lstrip().startswith("#"):
            continue
        if is_quote_block(block):
            if i not in failed_quotes:
                continue
            body = unquote_block(block)
        else:
            body = block
            for inner, pos, note in quote_flags(body, src):
                add("QUOTE", inner, i + 1, line, note or snippet(body, pos, len(inner) + 2))
        ntext = normalize(body)
        for token, pos in number_flags(ntext, src):
            add("NUMBER", token, i + 1, line, snippet(ntext, pos, len(token)))
        if not is_quote_block(block):
            for word, context in name_flags(body, src, allowed):
                add("NAME", word, i + 1, line, context)
    order = {k: n for n, k in enumerate(KINDS)}
    found.sort(key=lambda f: (f[2], order[f[0]]))
    return found


def report(summary, source):
    """Print the flags for one summary; return {kind: count}."""
    summary, source = Path(summary), Path(source)
    flags = check(summary.read_text(encoding="utf-8-sig"), source.read_text(encoding="utf-8-sig"),
                  author_forms(summary))
    print("== %s vs %s" % (summary.as_posix(), source.as_posix()))
    for kind, offending, n, line, context in flags:
        print('%s para %d, line %d: "%s" | %s' % (kind, n, line, offending, context))
    counts = {k: 0 for k in KINDS}
    for f in flags:
        counts[f[0]] += 1
    return counts


def manifest_pairs():
    """[(summary, source)] for every existing summary in the parts manifest."""
    if not PARTS_MANIFEST.exists():
        sys.exit("Work/parts_manifest.json not found; pass <summary> <source> instead")
    pairs = []
    for ch in json.loads(PARTS_MANIFEST.read_text(encoding="utf-8")):
        parts = ch.get("parts", [])
        if len(parts) > 1:
            pairs += [(p["summary"], p["source"]) for p in parts]
        chapter = ch.get("chapter_source") or (parts[0]["source"] if len(parts) == 1 else
                                               "Work/Chapters/%s/%s" % (ch["source_slug"], Path(ch["summary"]).name))
        pairs.append((ch["summary"], chapter))
    out = []
    for summary, source in pairs:
        summary, source = ROOT / summary, ROOT / source
        if summary.exists():
            if not source.exists():
                print("MISSING source %s for %s" % (source, summary))
                continue
            out.append((summary, source))
    return out


def main(argv):
    if len(argv) == 2:
        pairs = [(Path(argv[0]), Path(argv[1]))]
        for p in pairs[0]:
            if not p.exists():
                sys.exit("not found: %s" % p)
    elif not argv:
        pairs = manifest_pairs()
    else:
        sys.exit("usage: python Work/check_fidelity.py [<summary> <source>]")
    totals = {k: 0 for k in KINDS}
    for summary, source in pairs:
        for kind, n in report(summary, source).items():
            totals[kind] += n
    total = sum(totals.values())
    print("checked %d summary file(s): %s; %d flag(s)" % (
        len(pairs), ", ".join("%s %d" % (k, totals[k]) for k in KINDS), total))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
