"""Flag summary text that the source does not support word for word.

Summaries reproduce numbers, names, and quotations exactly as the source
prints them (errors included), never compute totals, averages, or rounded
figures, and reproduce a block quotation whole or not at all. This script
compares a summary with its source and flags four kinds of text (and lists
a fifth, OPENER, that is not a flag):

  NUMBER      a digit token (thousands separators removed, a trailing % or
              ordinal suffix ignored) that does not occur as a number in the
              source, or a run of number words (zero to twenty, the tens,
              hundred, thousand, million, billion, and the ordinals fourth to
              twentieth, the tens' ordinals, hundredth ... billionth, and
              "-first/-second/-third" after a tens or scale word) whose value
              does not occur there; also half, third, quarter, dozen, twice,
              percent when neither the word nor its digit form occurs there.
              A source number word counts as its digit form and the reverse
              ("twelve" supports 12, "nineteenth" supports 19th), as does
              "3 million" for 3,000,000. A single number word is also
              supported by the same word in the source; a run of several
              ("three hundred", "twenty-five") needs its value, not just its
              words. Words join across a space or hyphen, and across "and"
              only after hundred/thousand/million/billion when the value
              after "and" is smaller ("two hundred and five" is 205; "two and
              three" is 2 and 3, never a total of 5). A vulgar fraction
              character (½ ⅓ ⅔ ¼ ¾ ⅕ ... ⅞ ⅒) needs the same character, its
              slash form (1/3), or its words ("a third", "one-third", "two
              thirds", "half") in the source; the other way round, a
              fraction in words or slash form ("two-thirds", "three
              quarters", "one fifth", "2/3") is supported by its character
              (⅔ ¾ ⅕) or any other of its forms in the source.
  QUOTE       a quoted span of 3+ words ("...", curly double quotes, single
              curly quotes, or straight single quotes) that is not in the
              source. A single quotation opens after the start, a space, or
              an opening bracket, quote, or dash and closes before a space,
              punctuation, or the end, so apostrophes (mill's, 'tis, don't)
              are not read as quotes; a straight single quotation also pairs
              only with the first closing quote after it. The first letter
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
  NAME        a capitalized word absent from the source. Mid-sentence the
              match is case-sensitive. At a sentence start (the start of a
              line, after . ! ? or an opening quote) and after ":", where a
              capital carries no signal, the word is flagged only if the
              source lacks it in every case, it is not a common opener
              (SENTENCE_OPENERS: The, However, In, Nobody, One ...) or an
              "-ly" adverb followed by a comma, and it is a name by one of
              these signs: the dictionary (pyspellchecker) does not know it
              in lower case ("Josias" for "Josiah"); the summary capitalizes
              it mid-sentence elsewhere; or it is a near spelling (same first
              letter, similarity at least NEAR_NAME) of a word the source
              always capitalizes ("Hodge" for "Hodges", "Thompson" for
              "Thomson"). Otherwise it is an OPENER. A straight quote (" or
              ') opens a quotation only after the start, a space, an opening
              bracket, or a dash, so the word after a closing quote ('"the
              end" Smyth') or a trailing
              possessive apostrophe ("workers' Onion", "Jones' Mull") is
              mid-sentence. A period after an abbreviation (Mr. Mrs. Dr. St.
              Prof. Gen. Rev. e.g. ..., the list in split_parts.ABBREVIATIONS)
              or a single initial (J.) does not end a sentence, so the name
              after it is checked. This catches silently corrected spellings
              and invented actors. Text inside quotations is skipped (QUOTE
              covers it). Allowed: the author and speaker name forms in
              Work/author_refs.json for the file's source or unit, and
              ALLOWED_NAMES below. A word run together with the next across
              an apostrophe ("Polish'spring" for "Polish 'spring'") is one
              word the source lacks, so it is flagged as it stands.
  OPENER      a capitalized dictionary word at a sentence start that the
              source lacks in every case and that shows no sign of being a
              name: almost always a paraphrase word ("Fixing the rate, ...",
              "Converting the debt, ..."). In one run such words were 57 of
              67 NAME flags at assembly and 74 of 83 at completion; on that
              run's final summaries this check gives 15 NAME flags and 62
              OPENER lines where it gave 84 NAME flags before. Listed
              after the flags so a reader can glance for a name the
              dictionary happens to know ("Thompson" invented outright, only
              ever at a sentence start); not counted as a flag, and no
              record needs to settle it.

Both texts are normalized first: frontmatter and HTML comments removed, curly
and straight quotes and apostrophes unified (single and double alike, so a
quotation nested in a quotation still matches), dashes unified with the
spaces around them removed, ". . ." and the ellipsis character read as "...",
"*" emphasis removed, and whitespace collapsed. Summary heading lines are
ignored; text in the same block after a heading line is checked. Numbers and
names inside a summary block quotation are checked only when that block
quotation fails the BLOCKQUOTE check. A quotation hard-wrapped across lines
of one summary paragraph is found as if the lines were joined.

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
chapter. Once a split chapter's merged summary exists, its part summaries are
stale and are not checked (as in Work/check_words.py). Drafts are checked by passing their paths. The source slug for
author_refs.json comes from the summary path (Work/Drafts/<slug>/...,
Work/Summaries/<slug>/...).

Output: one line per flag, then one per OPENER,
    KIND para N, line L: "offending text" | context snippet
(paragraphs are blank-line-separated blocks of the summary, headings
included; BLOCKQUOTE lines name PARTIAL or ALTERED after the kind), then a
count per kind, and the OPENER count when there are any ("; OPENER n, not
flags"). In manifest mode a summary whose source file is missing is
printed as "MISSING source <source> for <summary>" and counted as a flag
("MISSING n" joins the counts). Exit status is 1 when anything is flagged,
else 0; OPENER lines never change it.

Known false positives (and gaps):
  - NAME: a capitalized word after a sentence that ends with an abbreviation
    or a single letter ("... in the U.S. Then"), or after "no." / "ed.", is
    checked as if mid-sentence. A word capitalized in the summary but not in
    the source (a term used as a title) is flagged. A sentence-start word
    that the dictionary does not know and the source lacks is flagged even
    when it is no name (a rare or technical word). A respelled name that
    matches a source word in another case ("Mill" for "mill") is not
    flagged at a sentence start, and one the dictionary knows that is not
    near any word the source capitalizes is only an OPENER.
  - NUMBER: "one" used as a pronoun ("one of them", "no one") is checked as
    a number. "first", "second", "third"
    alone are not checked; "one fifth" is read as 1 and 5, not a fraction;
    "two hundred and five thousand" is read as 200 and 5,000. Number words
    joined by a bare space are read as one value ("five twenty" is 25).
  - QUOTE: a straight single quotation whose first closing quote is a plural
    possessive ('the workers' houses were cold') pairs too early and, if that
    gives fewer than 3 words, is not checked. A leading elision outside the
    built-in list ('bus, 'phone) can open a quotation.
"""
import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher, get_close_matches
from functools import cache
from pathlib import Path

import check_author_refs
from common import ROOT, parse_frontmatter, strip_comments, utf8_output
# Importing split_parts has no side effects (its main() runs only as a
# script) and needs no PDF libraries: only common and count_words.
from split_parts import ABBREVIATIONS

PARTS_MANIFEST = ROOT / "Work" / "parts_manifest.json"
KINDS = ("NUMBER", "QUOTE", "BLOCKQUOTE", "NAME")
# Listed after the flags, never counted as one (see the docstring).
OPENER = "OPENER"
# How alike a sentence-start dictionary word and a word the source always
# capitalizes must be (difflib ratio, same first letter) for the word to be
# read as a respelled name: "Hodge"/"Hodges" 0.91, "Smyth"/"Smith" 0.8,
# "Fixing"/"Fishing" 0.77.
NEAR_NAME = 0.8

# Capitalized words that never need source support. "I" is the pronoun;
# "Chapter" and "Part" let a summary refer to the book's own divisions.
ALLOWED_NAMES = {"I", "Chapter", "Part"}

# Common sentence openers. A capitalized word at a sentence start (or after
# ":") is flagged only if the source lacks it in every case and it is not one
# of these, so an invented or respelled name there is still caught.
SENTENCE_OPENERS = set("""
The A An In On At To Of But And Or Nor So Yet However This That These Those
It Its He She They We You His Her Their Our My Your Him Them Us Me There Here
When While After Before As By For From With Without Although Though If Since
During Under Over Most Some Many Few All Both Each Every No Not None Nobody
Nothing Neither Either Such Other Others Another Several Any Anyone Someone
Something Everyone Everything Then Now Later Earlier Soon Once Until Because
Despite Unlike Like Through Throughout Within Among Between Against Across
Along Around Into Upon Toward Towards Above Below Beyond Except Instead
Indeed Thus Hence Therefore Meanwhile Afterwards Afterward Also Still Even
Only Again Next Finally Last First Second Third Rather Perhaps What Which Who
Whom Whose Why How Where Whether Whatever Whoever Wherever Given Having Being
Following According
Unless Whereas Moreover Furthermore Nevertheless Nonetheless Elsewhere
Together Similarly Likewise Overall Otherwise Ultimately Initially
""".split())

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
# Straight single quotations, with the same guards: an opening ' follows the
# start, a space, or an opening bracket, quote, or dash and precedes a letter
# or digit, and is not a leading elision ('tis, 'twas, 'em, 'n', '90s); a
# closing ' follows a non-space and precedes a space, punctuation, or the end.
# An apostrophe inside a word (mill's, don't) is neither; a trailing one
# (workers') can close, so a span is kept only when the first closing quote
# after the opening one gives 3 or more words (see straight_single_spans).
STRAIGHT_OPEN = re.compile(
    r"(?<![^\s(\[“\"—–-])'(?=[^\W_])(?!(?:tis|twas|twere|twill|em|n|cause|til|bout)\b|\d+s\b)", re.I)
STRAIGHT_CLOSE = re.compile(r"(?<=[^\s'])'(?![^\W_])")
STRAIGHT_MIN_WORDS = 3

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
SENTENCE_OPENERS |= {w.capitalize() for w in list(UNITS) + list(SCALES)}
# Other number words: the digit value or source strings that support them.
OTHER_NUMBER_WORDS = {
    "dozen": 12, "dozens": 12, "twice": 2,
    "half": ["½", "1/2"], "halves": ["½", "1/2"],
    "third": ["⅓", "1/3", "3rd"], "thirds": ["⅓", "1/3"],
    "quarter": ["¼", "1/4"], "quarters": ["¼", "1/4"],
    "percent": ["%", "per cent"],
}
PLURAL_SCALES = {w + "s": w for w in SCALES}
TENS = {"twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"}
# Ordinal words and the cardinal word each stands for: "nineteenth" counts as
# 19, so it supports and is supported by 19 or 19th. "first", "second" and
# "third" are number words only after a tens or scale word ("twenty-first",
# "a hundred and second"); alone they are too often not numbers, and "third"
# alone is the fraction in OTHER_NUMBER_WORDS.
ORDINALS = {
    "first": "one", "second": "two", "third": "three", "fourth": "four",
    "fifth": "five", "sixth": "six", "seventh": "seven", "eighth": "eight",
    "ninth": "nine", "tenth": "ten", "eleventh": "eleven", "twelfth": "twelve",
    "thirteenth": "thirteen", "fourteenth": "fourteen", "fifteenth": "fifteen",
    "sixteenth": "sixteen", "seventeenth": "seventeen", "eighteenth": "eighteen",
    "nineteenth": "nineteen", "twentieth": "twenty", "thirtieth": "thirty",
    "fortieth": "forty", "fiftieth": "fifty", "sixtieth": "sixty",
    "seventieth": "seventy", "eightieth": "eighty", "ninetieth": "ninety",
    "hundredth": "hundred", "thousandth": "thousand", "millionth": "million",
    "billionth": "billion",
}
WEAK_ORDINALS = {"first", "second", "third"}
NUMBER_WORD = re.compile(r"\b(?:%s)\b" % "|".join(
    sorted(list(UNITS) + list(SCALES) + list(ORDINALS), key=len, reverse=True)), re.I)
WORD_GAP = re.compile(r"\s*-\s*|\s+")
AND_GAP = re.compile(r"\s+and\s+", re.I)
OTHER_WORD = re.compile(
    r"\b(?:%s)\b" % "|".join(sorted(list(OTHER_NUMBER_WORDS) + list(PLURAL_SCALES), key=len, reverse=True)),
    re.I)
DIGIT_SCALE = re.compile(r"(\d+(?:[.,]\d+)*)\s+(hundred|thousand|million|billion)\b", re.I)

# Unicode vulgar fractions (½ ⅓ ⅔ ¼ ¾ ⅕ ... ⅒), each with its slash form and
# the source phrases that also support it ("a third", "one-third", "two
# thirds", "half"). Words join across a space or hyphen.
_DENOMINATORS = {2: ["half", "halves"], 3: ["third", "thirds"], 4: ["quarter", "quarters", "fourth", "fourths"],
                 5: ["fifth", "fifths"], 6: ["sixth", "sixths"], 7: ["seventh", "sevenths"],
                 8: ["eighth", "eighths"], 9: ["ninth", "ninths"], 10: ["tenth", "tenths"]}
_NUMERATORS = {1: ["a", "an", "one"], 2: ["two"], 3: ["three"], 4: ["four"], 5: ["five"], 7: ["seven"]}


def _fraction_forms():
    """{fraction character: pattern for the source text that supports it}."""
    table = {}
    for code in [0xBC, 0xBD, 0xBE] + list(range(0x2150, 0x215F)):
        char = chr(code)
        # "<fraction> 0031 2044 0033" is 1⁄3.
        decomposed = unicodedata.decomposition(char).split()
        num, den = (int(x) for x in "".join(chr(int(h, 16)) for h in decomposed[1:]).split("⁄"))
        words = [n + " " + d for n in _NUMERATORS.get(num, []) for d in _DENOMINATORS[den]]
        if den == 2 and num == 1:
            words.append("half")
        pattern = re.compile(r"(?<![\d/])%d/%d(?![\d/])|%s|\b(?:%s)\b" % (
            num, den, re.escape(char), "|".join(w.replace(" ", "[ -]") for w in words)), re.I)
        table[char] = pattern
    return table


FRACTION_FORMS = _fraction_forms()
FRACTION_CHAR = re.compile("[%s]" % "".join(FRACTION_FORMS))

HEADING_LINE = re.compile(r"\s*#{1,6}(?:\s|$)")
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
        self.names_lower = {w.lower() for w in self.names}
        # Words the source always capitalizes, by first letter, for reading a
        # dictionary word at a summary sentence start as a respelled name.
        # Openers and "-ly" adverbs ("Fifthly", "Fourthly") are no names.
        self.capitalized = {}
        for w in self.names:
            if (w[:1].isupper() and w.lower() not in self.names and w not in SENTENCE_OPENERS
                    and not w.endswith("ly")):
                self.capitalized.setdefault(w[0].lower(), []).append(w)


# ------------------------------------------------------------------- numbers

def number_value(token):
    """A digit token as a comparable string: "1,250" -> "1250"."""
    return token.replace(",", "") if THOUSANDS.match(token) else token


def words_value(run):
    """The value of a run of number words (a string or a list of words):
    "two hundred and five" -> 205, "twenty-first" -> 21."""
    words = re.findall(r"[a-z]+", run.lower()) if isinstance(run, str) else run
    total = current = 0
    for w in words:
        w = ORDINALS.get(w, w)
        if w in UNITS:
            current += UNITS[w]
        elif w == "hundred":
            current = max(current, 1) * 100
        elif w in SCALES:
            total += max(current, 1) * SCALES[w]
            current = 0
    return total + current


def _joins(last, word):
    """True if number word `word` continues a run that ends with `last`
    across a space or hyphen."""
    if last in ORDINALS:
        return False  # an ordinal ends a run
    if word in ORDINALS and ORDINALS[word] not in SCALES:
        # "twenty-fifth", "hundred fifth"; not "one fifth" (a fraction)
        return last in TENS or last in SCALES
    return True


def number_word_runs(text):
    """[(start, end, [words])] for runs of number words in text.

    Words join across a space or hyphen. "and" joins only after hundred,
    thousand, million or billion, and only when the value after it is smaller
    than that scale ("two hundred and five"); otherwise each side is its own
    run, so "between two and three" is 2 and 3, never 5. An ordinal ends a
    run, and a lone first/second/third is not a number word.
    """
    segs = []
    for m in NUMBER_WORD.finditer(text):
        w = m.group().lower()
        if segs and WORD_GAP.fullmatch(text[segs[-1][1]:m.start()]) and _joins(segs[-1][2][-1], w):
            segs[-1][1] = m.end()
            segs[-1][2].append(w)
        else:
            segs.append([m.start(), m.end(), [w]])
    runs = []
    for seg in segs:
        if runs:
            prev = runs[-1]
            last = prev[2][-1]
            if (last in SCALES and AND_GAP.fullmatch(text[prev[1]:seg[0]])
                    and words_value(seg[2]) < SCALES[last]):
                prev[1] = seg[1]
                prev[2] = prev[2] + seg[2]
                continue
        runs.append(seg)
    return [(s, e, words) for s, e, words in runs
            if not (len(words) == 1 and words[0] in WEAK_ORDINALS)]


def scaled(token, scale):
    try:
        value = float(number_value(token).replace(",", "")) * SCALES[scale.lower()]
    except ValueError:
        return None
    return str(int(value)) if value == int(value) else str(value)


def number_set(text):
    """Every number in normalized text, as comparable strings."""
    found = {number_value(t) for t in NUMBER_TOKEN.findall(text)}
    found |= {str(words_value(words)) for _, _, words in number_word_runs(text)}
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
    # A fraction in words or slash form ("two-thirds", "three quarters",
    # "2/3") whose character (or another form of it) the source prints is
    # supported as a whole, so its words are not checked one by one.
    supported = [(m.start(), m.end()) for char, pattern in FRACTION_FORMS.items() if pattern.search(src.text)
                 for m in pattern.finditer(text)]

    def in_fraction(pos):
        return any(s <= pos < e for s, e in supported)

    scale_after = {m.start(1): m for m in DIGIT_SCALE.finditer(text)}
    for m in NUMBER_TOKEN.finditer(text):
        token = m.group()
        if in_fraction(m.start()):
            continue
        if number_value(token) in src.numbers:
            continue
        sm = scale_after.get(m.start())
        if sm and scaled(sm.group(1), sm.group(2)) in src.numbers:
            continue
        flags.append((token, m.start()))
    runs = number_word_runs(text)
    for start, end, words in runs:
        if str(words_value(words)) in src.numbers or in_fraction(start):
            continue
        # A single word may also be supported by the same word in the source.
        # A multi-word run must match a value: its words found separately
        # ("three thousand", "a hundred") do not support "three hundred".
        if len(words) == 1 and words[0] in src.words_lower:
            continue
        # "3 million": the scale is supported when the scaled value is.
        before = re.search(r"(\d+(?:[.,]\d+)*)\s+$", text[:start])
        if before and len(words) == 1 and words[0] in SCALES and scaled(before.group(1), words[0]) in src.numbers:
            continue
        flags.append((text[start:end], start))
    for m in OTHER_WORD.finditer(text):
        if any(s <= m.start() < e for s, e, _ in runs) or in_fraction(m.start()):
            continue  # the "third" of "twenty-third"; the "thirds" of a supported "two-thirds"
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
    for m in FRACTION_CHAR.finditer(text):
        # ½ is supported by ½, 1/2, or "half"; ⅔ by ⅔, 2/3, or "two thirds".
        if not FRACTION_FORMS[m.group()].search(src.text):
            flags.append((m.group(), m.start()))
    return flags


# ---------------------------------------------------------------- quotations

def straight_single_spans(text):
    """[(start, end, inner text)] for straight single quotations (see
    STRAIGHT_OPEN). Each opening quote pairs with the first closing quote on
    its line; the pair is dropped unless it encloses 3 or more words."""
    spans, pos = [], 0
    for m in STRAIGHT_OPEN.finditer(text):
        if m.start() < pos:
            continue
        line_end = text.find("\n", m.end())
        close = STRAIGHT_CLOSE.search(text, m.end(), len(text) if line_end < 0 else line_end)
        if not close:
            continue
        inner = text[m.end():close.start()]
        if len(inner.split()) >= STRAIGHT_MIN_WORDS:
            spans.append((m.start(), close.end(), inner))
            pos = close.end()
    return spans


def quote_spans(text, straight_single=True):
    """[(start, end, inner text)] for quotations in raw text, outermost only.

    straight_single=False leaves out straight single quotations ('...'), as
    check_style_pass.py does."""
    spans = [(m.start(), m.end(), m.group(1) or m.group(2)) for m in DOUBLE_QUOTE.finditer(text)]
    singles = [(m.start(), m.end(), m.group(1)) for m in SINGLE_QUOTE.finditer(text)]
    if straight_single:
        singles += straight_single_spans(text)
    for start, end, inner in sorted(singles):
        if not any(a <= start < b for a, b, _ in spans):
            spans = [s for s in spans if not (start <= s[0] < end)]
            spans.append((start, end, inner))
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
    for start, _, inner in block_quote_spans(text):
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

def block_quote_spans(text):
    """quote_spans for one block, finding quotations hard-wrapped across lines
    (newlines read as spaces; positions are unchanged)."""
    return quote_spans(text.replace("\n", " "))


def mask_quotes(text):
    """Replace each quotation's content with "x", keeping a final . ! ? or :
    so a sentence that ends inside a quotation still ends."""
    out, pos = [], 0
    for start, end, inner in block_quote_spans(text):
        tail = inner.rstrip()[-1:] if inner.rstrip()[-1:] in ".!?:" else ""
        out.append(text[pos:start] + text[start] + "x" + tail + text[end - 1])
        pos = end
    out.append(text[pos:])
    return "".join(out)


def sentence_start(before):
    """True if a word after this text starts a sentence: at the start of a
    line (after any list marker), or after . ! ? : (and closing quotes or
    brackets), or after an opening quote. A straight quote (" or ') is an
    opening quote only after the start, a space, an opening bracket, or a
    dash, so the word after a closing quote ('"the end" Smyth') or a trailing
    possessive apostrophe ("workers' Onion") is mid-sentence. A period that
    ends an abbreviation (Mr. Dr. St. e.g. ..., split_parts.ABBREVIATIONS) or
    a single initial (J.) is not a sentence end, so the name after it is
    checked. The pronoun "I." is not read as an initial, nor is a quotation
    closed before its period ('"x".', as mask_quotes leaves '"the end".')."""
    line = before.split("\n")[-1].rstrip()
    if re.fullmatch(r"\s*(?:[-*]|\d+[.)])?", line):
        return True
    if re.search(r"(?:^|[\s(\[—–-])[\"']$|“$", line):
        return True
    if not re.search(r"[.!?:][\"')\]”]*$", line):
        return False
    last = line.split()[-1]
    if last.endswith("."):
        core = re.sub(r"[^A-Za-z]", "", last)
        if core.lower() in ABBREVIATIONS or (len(core) == 1 and core != "I" and last[-2:-1].isalpha()):
            return False
    return True


@cache
def _dictionary():
    """The pyspellchecker English dictionary, loaded on first use (as in
    Work/extract.py), so importing this module stays cheap."""
    from spellchecker import SpellChecker
    return SpellChecker()


def in_dictionary(word):
    """True if the dictionary knows the word in lower case. A word run
    together across an apostrophe ("polish'spring") is not known."""
    return bool(_dictionary().known([word.lower()]))


def mid_sentence_capitals(text):
    """Words (possessive removed) that text capitalizes mid-sentence, outside
    quotations: names, by the summary's own usage."""
    norm = re.sub(r"[’‘]", "'", mask_quotes(text))
    return {POSSESSIVE.sub("", m.group()) for m in WORD.finditer(norm)
            if m.group()[0].isupper() and not sentence_start(norm[:m.start()])}


def near_name(word, src):
    """True if word is a near spelling of a word the source always
    capitalizes: same first letter, similarity at least NEAR_NAME."""
    return bool(get_close_matches(word, src.capitalized.get(word[0].lower(), []), n=1, cutoff=NEAR_NAME))


def name_flags(text, src, allowed, named=frozenset()):
    """[(kind, offending text, context)] for capitalized words absent from
    the source: NAME, or OPENER for a sentence-start dictionary word with no
    sign of being a name (see the docstring). named: words the summary
    capitalizes mid-sentence anywhere (mid_sentence_capitals). Adjacent
    words of one kind are reported as one run."""
    flags = []
    norm = re.sub(r"[’‘]", "'", mask_quotes(text))
    for m in WORD.finditer(norm):
        word = POSSESSIVE.sub("", m.group())
        if not word[0].isupper() or word in allowed or word in src.names:
            continue
        kind = "NAME"
        # At a sentence start (or after ":") capitals carry no signal, so the
        # word is flagged only if the source lacks it in any case and it is
        # not a common opener or a "-ly," adverb ("Unfortunately, ..."); a
        # dictionary word is a NAME only with a sign that it is one.
        if sentence_start(norm[:m.start()]):
            if (word.lower() in src.names_lower or word in SENTENCE_OPENERS
                    or (word.endswith("ly") and norm[m.end():m.end() + 1] == ",")):
                continue
            if in_dictionary(word) and word not in named and not near_name(word, src):
                kind = OPENER
        flags.append((kind, word, m.start(), m.end()))
    runs = []
    for kind, word, start, end in flags:
        if runs and runs[-1][0] == kind and re.fullmatch(r"\s+", norm[runs[-1][3]:start]):
            runs[-1] = (kind, runs[-1][1] + norm[runs[-1][3]:start] + word, runs[-1][2], end)
        else:
            runs.append((kind, word, start, end))
    return [(k, w, snippet(norm, s, len(w))) for k, w, s, _ in runs]


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
    named = set()
    for _, block in paras:
        if not is_quote_block(block):
            named |= mid_sentence_capitals("\n".join(ln for ln in block.split("\n") if not HEADING_LINE.match(ln)))

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
        # Heading lines are skipped; text in the same block after one is not.
        lines = block.split("\n")
        kept = [k for k, ln in enumerate(lines) if not HEADING_LINE.match(ln)]
        if not kept:
            continue
        line += kept[0]
        quoted = is_quote_block(block)
        block = "\n".join(lines[k] for k in kept)
        if quoted:
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
        if not quoted:
            for kind, word, context in name_flags(body, src, allowed, named):
                add(kind, word, i + 1, line, context)
    order = {k: n for n, k in enumerate(KINDS + (OPENER,))}
    found.sort(key=lambda f: (f[0] == OPENER, f[2], order[f[0]]))
    return found


def report(summary, source):
    """Print the flags for one summary; return {kind: count}."""
    summary, source = Path(summary), Path(source)
    flags = check(summary.read_text(encoding="utf-8-sig"), source.read_text(encoding="utf-8-sig"),
                  author_forms(summary))
    print("== %s vs %s" % (summary.as_posix(), source.as_posix()))
    for kind, offending, n, line, context in flags:
        print('%s para %d, line %d: "%s" | %s' % (kind, n, line, offending, context))
    counts = {k: 0 for k in KINDS + (OPENER,)}
    for f in flags:
        counts[f[0]] += 1
    return counts


def manifest_pairs():
    """([(summary, source)], missing) for every existing summary in the parts
    manifest; missing counts summaries whose source file does not exist (each
    is printed as a MISSING line)."""
    if not PARTS_MANIFEST.exists():
        sys.exit("Work/parts_manifest.json not found; pass <summary> <source> instead")
    pairs = []
    for ch in json.loads(PARTS_MANIFEST.read_text(encoding="utf-8")):
        parts = ch.get("parts", [])
        # Once a split chapter is merged, its part summaries are stale: the
        # merged chapter summary is checked against the chapter instead.
        if len(parts) > 1 and not (ROOT / ch["summary"]).exists():
            pairs += [(p["summary"], p["source"]) for p in parts]
        chapter = ch.get("chapter_source") or (parts[0]["source"] if len(parts) == 1 else
                                               "Work/Chapters/%s/%s" % (ch["source_slug"], Path(ch["summary"]).name))
        pairs.append((ch["summary"], chapter))
    out, missing = [], 0
    for summary, source in pairs:
        summary, source = ROOT / summary, ROOT / source
        if summary.exists():
            if not source.exists():
                print("MISSING source %s for %s" % (source, summary))
                missing += 1
                continue
            out.append((summary, source))
    return out, missing


def main(argv):
    utf8_output()
    missing = 0
    if len(argv) == 2:
        pairs = [(Path(argv[0]), Path(argv[1]))]
        for p in pairs[0]:
            if not p.exists():
                sys.exit("not found: %s" % p)
    elif not argv:
        pairs, missing = manifest_pairs()
    else:
        sys.exit("usage: python Work/check_fidelity.py [<summary> <source>]")
    totals = {k: 0 for k in KINDS + (OPENER,)}
    for summary, source in pairs:
        for kind, n in report(summary, source).items():
            totals[kind] += n
    total = sum(totals[k] for k in KINDS) + missing
    counts = ["%s %d" % (k, totals[k]) for k in KINDS] + (["MISSING %d" % missing] if missing else [])
    openers = "; %s %d, not flags" % (OPENER, totals[OPENER]) if totals[OPENER] else ""
    print("checked %d summary file(s): %s; %d flag(s)%s" % (len(pairs), ", ".join(counts), total, openers))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
