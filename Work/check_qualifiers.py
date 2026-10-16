"""List small slips for the reviewer to settle: dropped qualifiers, pointers
outside the summary, and mixed spellings. A review list, not a gate.

After several verification rounds, what survives in a summary is a one- to
five-word slip that a reader of the summary alone cannot see. In one run the
only material finding left in a chapter was a dropped scope word ("modern"
dropped, so a claim about the modern state became one about the state as
such); others were "main" dropped from "two main lines", "only", "always",
"regularly", "certain" and "in effect" dropped, "for example", "to mention
only" and "particularly" dropped so that an example reads as the whole,
"designed to regulate" become "regulate", and "similar" become "the same".
Writing rules (b) and (g) were self-certified in one line each, and nothing
listed these. This script lists them:

  QUALIFIER  Each summary sentence (outside block quotations, with at least
             MIN_CONTENT distinct content words) is aligned with the one
             source sentence that holds the largest share of its content
             words (stems of five letters), if that share is at least
             MIN_SHARE. A qualifier the source sentence has and the summary
             sentence lacks is listed when the word it qualifies is kept:
             the first content word in the three words after it (or, when
             there is none, the content word just before it) appears in the
             summary sentence. A qualifier counts as kept when any word of
             its group appears (QUALIFIERS: "for instance" keeps "for
             example", "ever" keeps "never"). The list: hedges (perhaps,
             probably, seemingly, seem to, tend to, not necessarily,
             allegedly, ...), scope (only, merely, solely, some, most, few,
             main, mainly, chiefly, largely, partly, certain, at least,
             almost, nearly, essentially, in effect), frequency (always,
             never, generally, usually, often, regularly, sometimes),
             examples and emphasis (for example, for instance, such as, to
             mention only, particularly, especially), aims (designed to,
             try, seeks to), and others (similar, modern, in this respect,
             for the moment, at first). Left out as too noisy: "all",
             "every", "many", "several", "whole", may, might, could, would,
             and the "only" of "not only".
  REFERENCE  A pointer to material outside the summary, in prose outside
             quotations: "the preceding/following pages/chapter(s)", "this
             book", "the same work", "as we have seen", "(see) above/below",
             "Chapter IV", "Part 2" (headings are not read).
  VARIANT    One word spelled two ways in the summary outside quotations
             (organise/organize, labour/labor, instil/instill,
             centre/center, analyse/analyze, defence/defense, co-operate/
             cooperate, "business men"/businessmen), unless the source uses
             every one of the forms itself.
  PRONOUN    Only with --pronouns: in an aligned sentence pair, a noun
             phrase of the source (up to five words) became a pronoun (it,
             they, this, these, which, he, she, ...) in the summary. Low
             precision; for a reader checking pronoun reference by hand.

Measured on one run's summaries before its last fixes (69 chapter files,
196,000 summary words): QUALIFIER listed 210 items, about 3 per chapter,
among them the dropped word of 13 findings that independent verifiers had
confirmed; in a sample from a prototype, about a third deserved a look.
REFERENCE listed 8 (in the prototype, 2 of 7 were real); VARIANT 3 (1
real); PRONOUN about 2.6 per 1,000 words.

Known false positives: "not only ... but" recast without "only" (the "only"
of the plain phrase is still read); a rewording that keeps the sense with
other words ("never" -> "no ... ever", "similar" -> "alike"); a sentence
aligned with the wrong source sentence (a summary sentence that merges two
source sentences, or repeats words found elsewhere); a qualifier the
summary carries in another sentence of the paragraph; a qualifier dropped
on purpose because the summary's sentence no longer makes the claim it
qualified.

Every item is settled in the review or remediation record's "Qualifier
audit" section: restored (with the source page), or kept with the reason
("not only" recast, carried in the next sentence, misaligned).

Output, per summary:
    == <summary> vs <source>
    QUALIFIER line L: missing "<qualifier>" (qualifies "<word>")
        summary: <the summary sentence, shortened>
        source[, page N]: <the source sentence, shortened>
    REFERENCE line L: "<pointer>" | <context>
    VARIANT: "<form>" (line L), "<form>" (line L)
    PRONOUN line L: "<source words>" -> "<pronoun>"   (then the two sentences)
and a total per kind. Exit status is 0 (1 only for a usage error or a
missing file named on the command line): the list never fails a run.

Usage (from the project root):
    python Work/check_qualifiers.py [--pronouns] <summary> <source>
    python Work/check_qualifiers.py [--pronouns]   # every summary in Work/parts_manifest.json

The no-argument mode reads the same pairs as Work/check_fidelity.py: each
existing summary against its part file or chapter (a split chapter's part
summaries until its merged summary exists). For a part file, the whole part
file is the evidence, overlap and context blocks included.
"""
import re
import sys
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import check_fidelity
from common import PAGE_MARKER_RE, parse_frontmatter, strip_comments, utf8_output
from split_parts import sentence_units

KINDS = ("QUALIFIER", "REFERENCE", "VARIANT")
# A summary sentence needs this many distinct content-word stems to be
# aligned, and its best source sentence must hold this share of them.
MIN_CONTENT = 4
MIN_SHARE = 0.6
STEM = 5
SHOWN = 160

STOP = set("""
the a an and or but of to in on at for by with from as is are was were be been being that this these
those it its they them their he his she her which who whom what when where while than then so not no
nor if into out over under up down only also more most such can could would should may might must
will shall has have had do does did any all each every some one two other own same very just
""".split())

# Qualifier groups: (markers, also accepted). A marker the source sentence
# has is kept when the summary sentence has any word of its group, markers
# or the words also accepted (which are too common to list as markers).
QUALIFIERS = [
    # Hedges.
    (["perhaps", "possibly", "maybe"], []),
    (["probably", "likely"], []),
    (["seemingly", "apparently", "seem to", "seems to", "seemed to", "appear to", "appears to",
      "appeared to"], []),
    (["tend to", "tends to", "tended to"], ["tendency"]),
    (["not necessarily"], []),
    (["it is reckoned", "it is estimated"], ["estimate", "estimated"]),
    (["purportedly", "reportedly", "allegedly"], []),
    (["arguably"], []),
    (["so to speak", "it may be said"], []),
    # Scope.
    (["only", "merely", "solely", "exclusively", "sole"], ["just", "alone"]),
    (["some"], []),
    (["most"], ["mostly"]),
    (["few"], []),
    (["main"], ["chief", "principal", "primary"]),
    (["mainly", "chiefly", "largely", "in the main"], ["mostly", "principally", "primarily", "predominantly"]),
    (["partly", "in part"], ["partially"]),
    (["certain"], []),
    (["at least"], []),
    (["almost", "nearly", "virtually"], ["practically"]),
    (["essentially", "in effect"], ["in essence"]),
    (["in principle"], []),
    # Frequency.
    (["always"], ["invariably"]),
    (["never"], ["ever", "at no time"]),
    # "generally speaking" is a marker of its own, so the word it qualifies
    # is the one after "speaking".
    (["generally", "generally speaking", "usually"], ["typically", "normally", "as a rule", "ordinarily",
                                                      "in general", "on the whole"]),
    (["often"], ["frequently", "commonly"]),
    (["regularly"], []),
    (["sometimes"], ["occasionally", "at times"]),
    # Examples and emphasis.
    (["for example", "for instance", "such as", "to mention only"], ["e.g.", "including", "among them",
                                                                    "among others", "like"]),
    (["particularly", "especially"], ["in particular", "notably", "above all"]),
    # Aims and attempts.
    (["designed to"], ["intended to", "meant to", "aimed", "aim"]),
    (["try", "tries", "tried", "seek to", "seeks to", "sought to"], ["attempt", "attempts", "attempted",
                                                                   "trying", "seeking"]),
    # Others.
    (["similar"], ["similarly", "like", "alike", "comparable", "akin"]),
    (["modern", "present-day"], ["contemporary", "today"]),
    (["in this respect"], ["in this regard", "in that respect", "in this sense"]),
    (["for the moment"], ["for now", "for the time being", "temporarily"]),
    (["at first"], ["initially", "at the outset"]),
]


def _phrase(word):
    return re.compile(r"(?<!\w)%s(?!\w)" % re.escape(word).replace(r"\ ", r"\s+"), re.I)


# "only" in "not only" is left out: "not only ... but" is often recast.
NOT_ONLY = re.compile(r"\bnot\s+$", re.I)
MARKERS = [(m, _phrase(m), [_phrase(w) for w in markers + accepted])
           for markers, accepted in QUALIFIERS for m in markers]

# Pointers outside the summary. Only "Chapter"/"Part" and a numeral is case
# sensitive, so "for my part I" is no pointer.
REFERENCES = re.compile("|".join([r"(?i:%s)" % p for p in [
    r"\b(?:the\s+)?(?:preceding|previous|foregoing|following|next|earlier|later|subsequent)\s+"
    r"(?:pages?|chapters?|sections?|essays?|volumes?)\b",
    r"\b(?:this|the\s+present)\s+(?:book|volume)\b",
    r"\bthe\s+same\s+(?:work|book|volume)\b",
    r"\bas\s+(?:we|I)\s+(?:have\s+seen|saw|shall\s+see|will\s+see)\b",
    r"\b(?:see|as|noted|mentioned|discussed|described|quoted|cited|shown|given|listed|stated|outlined)"
    r"\s+(?:above|below)\b",
    r"\((?:see\s+)?(?:above|below)\)",
]] + [r"\b(?:Chapters?|chapters?|Parts?)\s+(?:[IVXLC]+|\d+)\b"]))

PRONOUNS = set("it its they them their theirs he him his she her this these those which who".split())


# --------------------------------------------------------------- sentences

def toks(text):
    return re.findall(r"[a-z][a-z'\-]*", text.lower())


def content(text):
    return [w for w in toks(text) if w not in STOP and len(w) > 2]


def stem(word):
    return word[:STEM]


def shorten(text, at=0, width=SHOWN):
    """text on one line, cut to about width characters around offset at."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= width:
        return text
    a = max(0, min(at - width // 3, len(text) - width))
    return ("..." if a else "") + text[a:a + width].strip() + ("..." if a + width < len(text) else "")


def page_label(markers, x, y, text):
    """"page N" (or "pages N-M") for text[x:y] from the page markers
    [(offset, page)]: the last marker before the sentence's first words, and
    any marker inside it; "" when the text has none."""
    first, later = None, []
    for pos, page in markers:
        if pos >= y:
            break
        if pos < x or not strip_comments(text[x:pos]).strip():
            first = page
        else:
            later.append(page)
    if first is None and not later:
        return ""
    first = later[0] if first is None else first
    last = later[-1] if later else first
    return "page %d" % first if first == last else "pages %d-%d" % (first, last)


def unquote(text):
    """A block quotation's text without its "> " markers."""
    return re.sub(r"(?m)^\s*>\s?", "", text)


def source_sentences(raw):
    """[(text, page label)] for the source's sentences, block quotations
    included and headings left out."""
    _, rest = parse_frontmatter(raw.replace("\r\n", "\n").lstrip("\ufeff"))
    # Heading lines become spaces, so offsets (and page markers) stay put.
    rest = re.sub(r"(?m)^#{1,6}(?:\s.*)?$", lambda m: " " * len(m.group()), rest)
    markers = [(m.start(), int(m.group(1))) for m in PAGE_MARKER_RE.finditer(rest)]
    out = []
    for block in re.finditer(r"[^\n]*\S[^\n]*(?:\n[^\n]*\S[^\n]*)*", rest):
        for x, y in sentence_units(rest, block.start(), block.end()):
            text = re.sub(r"\s+", " ", unquote(strip_comments(rest[x:y]))).strip()
            if text:
                out.append((text, page_label(markers, x, y, rest)))
    return out


def summary_paragraphs(raw):
    """[(first line number, paragraph text)] for the summary's paragraphs,
    with frontmatter and comments removed. Heading lines are dropped (the
    text after one in the same block is kept)."""
    raw = raw.replace("\r\n", "\n").lstrip("\ufeff")
    _, rest = parse_frontmatter(raw)
    offset = raw[:len(raw) - len(rest)].count("\n")
    # Comments go, but their line breaks stay, so line numbers match the file.
    text = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group().count("\n"), rest, flags=re.S)
    out = []
    for start, block in check_fidelity.blocks(text):
        lines = block.split("\n")
        kept = [k for k, ln in enumerate(lines) if not check_fidelity.HEADING_LINE.match(ln)]
        if kept:
            out.append((start + offset + kept[0], "\n".join(lines[k] for k in kept)))
    return out


def summary_sentences(raw):
    """[(line number, sentence)] for the summary's prose sentences, block
    quotations left out."""
    out = []
    for line, para in summary_paragraphs(raw):
        if check_fidelity.is_quote_block(para):
            continue
        for x, y in sentence_units(para, 0, len(para)):
            sentence = re.sub(r"\s+", " ", para[x:y]).strip()
            if sentence:
                out.append((line + para.count("\n", 0, x), sentence))
    return out


# ---------------------------------------------------------------- checks

class Aligner:
    """Finds, for a summary sentence, the source sentence holding the
    largest share of its content-word stems."""

    def __init__(self, sentences):
        self.sentences = sentences
        self.index = defaultdict(set)
        for k, (text, _) in enumerate(sentences):
            for s in {stem(w) for w in content(text)}:
                self.index[s].add(k)

    def best(self, sentence):
        """(source index, share), or None if the sentence is too short or
        no source sentence holds MIN_SHARE of its stems."""
        stems = {stem(w) for w in content(sentence)}
        if len(stems) < MIN_CONTENT:
            return None
        counts = defaultdict(int)
        for s in stems:
            for k in self.index.get(s, ()):
                counts[k] += 1
        if not counts:
            return None
        k = max(counts, key=lambda i: (counts[i], -i))
        share = counts[k] / len(stems)
        return (k, share) if share >= MIN_SHARE else None


def qualifier_flags(sentence, source):
    """[(qualifier, the word it qualifies)] for qualifiers in the source
    sentence that the summary sentence lacks while keeping that word."""
    kept_stems = {stem(t) for t in toks(sentence)}
    found = []
    for marker, pattern, group in MARKERS:
        if any(p.search(sentence) for p in group):
            continue
        for m in pattern.finditer(source):
            if marker == "only" and NOT_ONLY.search(source[:m.start()]):
                continue
            after = [w for w in toks(source[m.end():])[:3] if w not in STOP and len(w) > 2]
            before = [w for w in toks(source[:m.start()])[-2:] if w not in STOP and len(w) > 2]
            head = after[:1] or before[-1:]
            if head and stem(head[0]) in kept_stems:
                found.append((marker, head[0]))
                break
    return found


def pronoun_flags(sentence, source):
    """[(source words, pronoun)] where a short source noun phrase became a
    pronoun in the summary sentence."""
    a, b = toks(source), toks(sentence)
    found = []
    for op, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if (op == "replace" and j2 - j1 <= 2 and i2 - i1 <= 5 and any(w in PRONOUNS for w in b[j1:j2])
                and any(w not in STOP and len(w) > 3 for w in a[i1:i2])):
            found.append((" ".join(a[i1:i2]), " ".join(b[j1:j2])))
    return found


def reference_flags(raw):
    """[(line number, pointer, context)] for pointers outside the summary,
    in prose outside quotations."""
    found = []
    for line, para in summary_paragraphs(raw):
        if check_fidelity.is_quote_block(para):
            continue
        masked = check_fidelity.mask_quotes(para)
        for m in REFERENCES.finditer(masked):
            found.append((line + masked.count("\n", 0, m.start()), m.group(),
                          check_fidelity.snippet(masked, m.start(), len(m.group()))))
    return found


def spelling_key(word):
    """One key for the spellings of a word: without hyphens or accents, and
    with British endings made American (-ise -> -ize, -our -> -or, -yse ->
    -yze, -ence -> -ense, -tre -> -ter, a final -ll after a vowel -> -l)."""
    k = unicodedata.normalize("NFKD", word.lower().replace("-", ""))
    k = "".join(c for c in k if not unicodedata.combining(c))
    k = re.sub(r"is(e|es|ed|ing|ation|ations)$", r"iz\1", k)
    k = re.sub(r"ys(e|es|ed|ing)$", r"yz\1", k)
    k = re.sub(r"our(s|ed|ing|able|ite|ites)?$", r"or\1", k)
    k = re.sub(r"([aeiou])ll(s|ment|ments)?$", r"\1l\2", k)
    k = re.sub(r"tre(s)?$", r"ter\1", k)
    k = re.sub(r"ence$", "ense", k)
    return k


WORD = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*")
# Closed words whose open form is another word: "every one of them",
# "may be", "some time ago".
OPEN_AND_CLOSED = {"anyone", "everyone", "someone", "everyday", "everything", "anything", "something",
                   "nothing", "maybe", "sometime", "sometimes", "anyway", "anyways", "altogether",
                   "already", "alright", "awhile", "into", "onto", "cannot", "nobody", "anybody",
                   "everybody", "somebody", "whatever", "however", "wherever", "whoever", "apart",
                   "indeed", "therefore", "forever", "overall", "underway", "without", "within"}


def variant_flags(raw, source_raw):
    """[[(form, first line number), ...]] for words the summary spells more
    than one way outside quotations, unless the source uses every form."""
    forms = defaultdict(dict)   # key -> {form: first line}
    pairs = []                  # (key, two-word form, line)
    for line, para in summary_paragraphs(raw):
        if check_fidelity.is_quote_block(para):
            continue
        masked = check_fidelity.mask_quotes(para)
        words = list(WORD.finditer(masked))
        for i, m in enumerate(words):
            n = line + masked.count("\n", 0, m.start())
            w = m.group().lower()
            if len(w) >= 5:
                forms[spelling_key(w)].setdefault(w, n)
            if i + 1 < len(words) and masked[m.end():words[i + 1].start()] == " ":
                nxt = words[i + 1].group().lower()
                if len(w) >= 3 and len(nxt) >= 3 and "-" not in w + nxt:
                    pairs.append((spelling_key(w + nxt), w + " " + nxt, n))
    # A two-word form joins only a closed one ("business men", "businessmen"):
    # an open noun beside a hyphenated adjective ("civil war", "civil-war
    # refugees") is the usual style, as are "every day" and "everyday".
    for key, form, n in pairs:
        if any("-" not in f and f not in OPEN_AND_CLOSED for f in forms.get(key, ())):
            forms[key].setdefault(form, n)
    source_text = re.sub(r"\s+", " ", strip_comments(source_raw)).lower()
    source_words = {w.lower() for w in WORD.findall(source_text)}
    found = []
    for key, seen in forms.items():
        if len(seen) < 2:
            continue
        if all((f in source_words) if " " not in f else re.search(r"\b%s\b" % re.escape(f), source_text)
               for f in seen):
            continue
        found.append(sorted(seen.items(), key=lambda x: (x[1], x[0])))
    return sorted(found, key=lambda f: f[0][1])


def check(summary_raw, source_raw, pronouns=False):
    """[(kind, line number, detail lines)] for one summary, in line order
    (VARIANT last)."""
    src = source_sentences(source_raw)
    aligner = Aligner(src)
    found = []
    for line, sentence in summary_sentences(summary_raw):
        best = aligner.best(sentence)
        if best is None:
            continue
        text, page = src[best[0]]
        where = "source, %s" % page if page else "source"
        for marker, head in qualifier_flags(sentence, text):
            at = re.search(r"\b%s" % re.escape(head[:STEM]), sentence, re.I)
            m = re.search(r"(?<!\w)%s(?!\w)" % re.escape(marker).replace(r"\ ", r"\s+"), text, re.I)
            found.append(("QUALIFIER", line, ['missing "%s" (qualifies "%s")' % (marker, head),
                                              "summary: " + shorten(sentence, at.start() if at else 0),
                                              "%s: %s" % (where, shorten(text, m.start() if m else 0))]))
        if pronouns:
            for words, pronoun in pronoun_flags(sentence, text):
                found.append(("PRONOUN", line, ['"%s" -> "%s"' % (words, pronoun), "summary: " + shorten(sentence),
                                                "%s: %s" % (where, shorten(text))]))
    for line, pointer, context in reference_flags(summary_raw):
        found.append(("REFERENCE", line, ['"%s" | %s' % (pointer, context)]))
    found.sort(key=lambda f: f[1])
    for group in variant_flags(summary_raw, source_raw):
        found.append(("VARIANT", group[0][1], [", ".join('"%s" (line %d)' % (f, n) for f, n in group)]))
    return found


def report(summary, source, pronouns=False):
    """Print the list for one summary; return {kind: count}."""
    summary, source = Path(summary), Path(source)
    found = check(summary.read_text(encoding="utf-8-sig"), source.read_text(encoding="utf-8-sig"), pronouns)
    print("== %s vs %s" % (summary.as_posix(), source.as_posix()))
    counts = defaultdict(int)
    for kind, line, details in found:
        counts[kind] += 1
        if kind == "VARIANT":
            print("VARIANT: %s" % details[0])
        else:
            print("%s line %d: %s" % (kind, line, details[0]))
            for d in details[1:]:
                print("    " + d)
    return counts


def main(argv):
    utf8_output()
    argv = list(argv)
    pronouns = "--pronouns" in argv
    if pronouns:
        argv.remove("--pronouns")
    missing = 0
    if len(argv) == 2:
        pairs = [(Path(argv[0]), Path(argv[1]))]
        for p in pairs[0]:
            if not p.exists():
                print("not found: %s" % p)
                return 1
    elif not argv:
        pairs, missing = check_fidelity.manifest_pairs()
    else:
        print("usage: python Work/check_qualifiers.py [--pronouns] [<summary> <source>]")
        return 1
    totals = defaultdict(int)
    for summary, source in pairs:
        for kind, n in report(summary, source, pronouns).items():
            totals[kind] += n
    kinds = KINDS + (("PRONOUN",) if pronouns else ())
    counts = ", ".join("%s %d" % (k, totals[k]) for k in kinds)
    print("listed %d item(s) in %d summary file(s): %s%s; settle each in the record's Qualifier audit"
          % (sum(totals.values()), len(pairs), counts, "; MISSING %d" % missing if missing else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
