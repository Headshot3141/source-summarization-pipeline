"""Verify prose-only edits to chapter summaries against a pre-pass snapshot.

Used as the gate for a style pass (see passes/style-pass.md). A style pass may
change wording but never meaning, so this checks only what it must not change:

  quotes   every quoted span ("...", curly double quotes, and single curly
           quotes, with apostrophes such as mill’s or workers’ not read as
           quotes), in order, identical (trailing .,;: ignored)
  numbers  every numeric token identical; a reorder of the same numbers is
           reported separately as a softer "NUMBER ORDER" flag. Number words
           (twelve, hundred, half, dozen, percent, ...) must also survive.
  headings ## / ### heading text identical
  blocks   block-quotation lines ("> ") identical
  paras    paragraph count unchanged
  markers  counts of protected markers (hedges, contrasts, attribution
           phrases and reporting verbs, negations, scope words, conditionals,
           and reach phrases) not reduced, whole-word matches. The style pass
           never merges or splits paragraphs, so counts are compared paragraph
           by paragraph (blank-line-separated blocks, headings included);
           when the paragraph count changed, they are compared over the whole
           file instead, alongside the PARAGRAPH COUNT flag.

When a reporting verb or attribution phrase ("according to", "in his view",
"in Penhale's view", argues, says, ...) disappears, its subject in the old
text is found (the name or noun phrase just before the verb, or after
"according to", or inside "in X's view"):

  ADVISORY          the subject is "the author(s)", a personal pronoun, or a
                    name form from Work/author_refs.json for the file's source
                    or unit: the author preface was removed, which is correct
                    if it only introduced the author's own view. Advisory lines
                    are printed but do not flag the file.
  ATTRIBUTION DROP  any other subject: another speaker's marker was removed,
                    a defect unless the view is still marked as theirs.

Word count is deliberately NOT checked; a style pass may grow the text.

Usage (from the project root):
    python Work/check_style_pass.py                       # every edited summary
    python Work/check_style_pass.py Work/Summaries/<slug>/<file>.md ...
    python Work/check_style_pass.py --archive Work/Summaries_prestyle ...

Exit status is 1 when any file is flagged (any line other than ADVISORY).
"""
import re
import sys
from collections import Counter
from pathlib import Path

import check_author_refs
from check_fidelity import OTHER_NUMBER_WORDS, PLURAL_SCALES, SCALES, UNITS, quote_spans
from common import ROOT

DEFAULT_ARCHIVE = ROOT / "Work" / "Summaries_prestyle"
CURRENT = ROOT / "Work" / "Summaries"

# A number ends in a digit, so a comma or period after it is not absorbed.
NUMBER = re.compile(r"\d(?:[\d,.]*\d)?")
NUMBER_WORD = re.compile(r"\b(?:%s)\b" % "|".join(
    sorted(list(UNITS) + list(SCALES) + list(PLURAL_SCALES) + list(OTHER_NUMBER_WORDS), key=len, reverse=True)))
HEADING = re.compile(r"^#{2,3} .*$", re.M)
# A block quotation reproduces the source exactly, so a style pass never touches it.
BLOCK_QUOTE = re.compile(r"^>.*$", re.M)

# Markers whose loss usually changes meaning (preservation rules in
# writing-rules.md): hedges, contrasts, attribution, negation, scope,
# conditions, and reach. Attribution markers (ATTRIBUTION below) are protected
# on other speakers' views; dropping one that only prefaced the author's own
# view is correct and is reported as ADVISORY. Extend per project with
# source-specific hedges or attribution phrases.
PROTECTED = [
    # hedges
    "perhaps", "probably", "possibly", "seemingly", "apparently", "tended to",
    "often", "usually", "sometimes", "not necessarily", "may have", "might have",
    "would have", "could have", "it is reckoned", "it is estimated",
    "purportedly", "reportedly", "allegedly", "arguably",
    # attribution phrases
    "according to", "in his view", "in her view", "in their view",
    # contrast and concession
    "but", "yet", "however", "even so", "nevertheless", "in truth", "although",
    "on the other hand", "though", "while", "whereas",
    # negation ("not" also counts "cannot" and n't)
    "not", "no", "never", "nor", "without", "none",
    # scope
    "some", "most", "only", "all", "few",
    # conditions
    "if", "unless",
    # reach
    "one of the", "among the", "for example",
]
# Reporting verbs, counted per verb so a change of tense is not a loss.
REPORTING_VERBS = [
    ["argue", "argues", "argued"],
    ["claim", "claims", "claimed"],
    ["say", "says", "said"],
    ["believe", "believes", "believed"],
    ["insist", "insists", "insisted"],
    ["contend", "contends", "contended"],
    ["maintain", "maintains", "maintained"],
    ["write", "writes", "wrote", "written"],
    ["think", "thinks", "thought"],
    ["suggest", "suggests", "suggested"],
]
POSSESSIVE_VIEW = "in <name>'s view"
MARKER_PATTERNS = {m: re.compile(r"\b" + re.escape(m) + r"\b", re.I) for m in PROTECTED}
MARKER_PATTERNS["not"] = re.compile(r"\b(?:can)?not\b|n['’]t\b", re.I)
for _forms in REPORTING_VERBS:
    MARKER_PATTERNS["/".join(_forms)] = re.compile(r"\b(?:%s)\b" % "|".join(_forms), re.I)
MARKER_PATTERNS[POSSESSIVE_VIEW] = re.compile(
    r"\bin\s+((?:the\s+)?(?:[\w.-]+\s+){0,2}?[\w.-]+?)['’]s?\s+view\b", re.I)
# Markers whose subject is looked up when they disappear.
ATTRIBUTION = {"according to", "in his view", "in her view", "in their view", POSSESSIVE_VIEW}
ATTRIBUTION |= {"/".join(f) for f in REPORTING_VERBS}
# Markers whose sense varies; a drop is reported with a reminder to check it.
ADVISORY = {
    "while": "'while' may be temporal rather than concessive",
    "yet": "'yet' may mean 'so far' rather than a contrast",
    "most": "'the most' may be a superlative rather than scope",
    "all": "'at all' is emphasis rather than scope",
}
AUTHOR_NOTE = "author preface removed; correct if it only introduced the author's own view"
OTHER_NOTE = "another speaker's marker removed; defect unless the view is still marked"

# Personal pronouns are read as the author (or the unit's speaker). "it" and
# "one" are not: "it is said" and "one might argue" attribute a view to others.
PRONOUNS = {"he", "she", "they", "i", "we", "you", "his", "her", "their", "him", "them", "us", "me"}
SKIP_BEFORE_VERB = {
    "has", "have", "had", "is", "was", "were", "are", "be", "been", "also", "once",
    "later", "often", "will", "would", "may", "might", "can", "could", "does", "did",
    "do", "then", "still", "further", "even", "already", "elsewhere", "now", "always",
    "never", "not", "himself", "herself", "themselves", "itself", "to",
}
DETERMINERS = {"the", "a", "an", "this", "that", "these", "those", "his", "her", "their",
               "its", "many", "some", "most", "other", "several", "both", "few"}
FUNCTION_WORDS = DETERMINERS | {"as", "but", "and", "yet", "so", "in", "for", "when", "while",
                                "although", "though", "if", "then", "here", "there", "what"}
CLAUSE_BREAK = r"[.;:!?,\"“”()—–]"


def quotes(text):
    # Trailing sentence punctuation may sit inside the quote in American style
    # but belongs to the sentence, so recasting may legitimately move it out.
    return [inner.rstrip(".,;:") for _, _, inner in quote_spans(text)]


def blocks(text):
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


def paragraphs(text):
    return len(blocks(text))


def bare(word):
    return re.sub(r"['’]s?$", "", re.sub(r"[.,;:!?]+$", "", word))


def marker_subject(marker, match, text):
    """The speaker an attribution marker attaches to, read from text."""
    if marker == POSSESSIVE_VIEW:
        return match.group(1)
    if marker in ("in his view", "in her view", "in their view"):
        return marker.split()[1]
    if marker == "according to":
        words = re.split(CLAUSE_BREAK, text[match.end():])[0].split()[:4]
        run = []
        for w in words:
            if not w[:1].isupper():
                break
            run.append(bare(w))
        return " ".join(run or words) or "?"
    # A reporting verb: the subject just before it in the same clause.
    clause = re.split(CLAUSE_BREAK, text[:match.start()])[-1].split()
    while clause and (clause[-1].lower() in SKIP_BEFORE_VERB or clause[-1].lower().endswith("ly")):
        clause.pop()
    if clause:
        if clause[-1].lower() in PRONOUNS | {"it", "one"}:
            return clause[-1]
        run = []
        for w in reversed(clause):
            if not w[:1].isupper() or w.lower() in FUNCTION_WORDS:
                break
            run.insert(0, bare(w))
        if run:
            return " ".join(run)
        tail = clause[-4:]
        for k, w in enumerate(tail):
            if w.lower() in DETERMINERS:
                return " ".join(tail[k:])
        return " ".join(tail[-2:])
    # Inverted order: '"...," says Penhale' or '"...," writes the author'.
    after = text[match.end():].split()[:4]
    if after and after[0].lower() in DETERMINERS and len(after) > 1:
        return after[0] + " " + bare(after[1])
    run = []
    for w in after:
        if not w[:1].isupper():
            break
        run.append(bare(w))
        if bare(w) != w:
            break
    return " ".join(run) or "?"


def is_author(subject, author_forms):
    s = bare(subject.strip()).lower()
    return s in PRONOUNS or s in ("the author", "the authors") or s in {f.lower() for f in author_forms}


def compare_markers(old, new, where, author_forms):
    """Problems for protected markers lost between old and new text."""
    problems = []
    for marker, pat in MARKER_PATTERNS.items():
        om, nm = list(pat.finditer(old)), list(pat.finditer(new))
        if len(nm) >= len(om):
            continue
        counts = '"%s" %d -> %d%s' % (marker, len(om), len(nm), where)
        if marker in ATTRIBUTION:
            dropped = (Counter(marker_subject(marker, m, old) for m in om)
                       - Counter(marker_subject(marker, m, new) for m in nm))
            for subject in sorted(dropped.elements()):
                if is_author(subject, author_forms):
                    problems.append('ADVISORY %s by "%s": %s' % (counts, subject, AUTHOR_NOTE))
                else:
                    problems.append('ATTRIBUTION DROP %s by "%s": %s' % (counts, subject, OTHER_NOTE))
            if dropped:
                continue
        note = "  (check sense: %s)" % ADVISORY[marker] if marker in ADVISORY else ""
        problems.append("PROTECTED MARKER %s%s" % (counts, note))
    return problems


def check(old, new, author_forms=()):
    """Problems between the snapshot (old) and the edited text (new).

    Lines starting "ADVISORY" are notes, not defects. author_forms: the name
    forms of the author (and the unit's speakers) for the attribution check.
    """
    problems = []

    oq, nq = quotes(old), quotes(new)
    if oq != nq:
        for a, b in zip(oq, nq):
            if a != b:
                problems.append('QUOTE CHANGED: "%s" -> "%s"' % (a, b))
        if len(oq) != len(nq):
            problems.append("QUOTE COUNT %d -> %d" % (len(oq), len(nq)))

    on, nn = NUMBER.findall(old), NUMBER.findall(new)
    if on != nn:
        if Counter(on) == Counter(nn):
            problems.append("NUMBER ORDER changed (same numbers); confirm each still attaches to the right claim")
        else:
            lost = Counter(on) - Counter(nn)
            added = Counter(nn) - Counter(on)
            if lost:
                problems.append("NUMBER REMOVED: %s" % ", ".join(sorted(lost.elements())))
            if added:
                problems.append("NUMBER ADDED: %s" % ", ".join(sorted(added.elements())))

    ow, nw = Counter(NUMBER_WORD.findall(old.lower())), Counter(NUMBER_WORD.findall(new.lower()))
    if ow - nw:
        problems.append("NUMBER WORD REMOVED: %s" % ", ".join(sorted((ow - nw).elements())))
    if nw - ow:
        problems.append("NUMBER WORD ADDED: %s" % ", ".join(sorted((nw - ow).elements())))

    ob, nb = BLOCK_QUOTE.findall(old), BLOCK_QUOTE.findall(new)
    if ob != nb:
        problems.append("BLOCK QUOTE CHANGED: %d block-quote lines before, %d after; they must match exactly" % (len(ob), len(nb)))

    oh, nh = HEADING.findall(old), HEADING.findall(new)
    if oh != nh:
        problems.append("HEADINGS CHANGED: %s -> %s" % (oh, nh))

    op, np_ = blocks(old), blocks(new)
    if len(op) != len(np_):
        problems.append("PARAGRAPH COUNT %d -> %d" % (len(op), len(np_)))
        problems += compare_markers(old, new, "", author_forms)
    else:
        for i, (a, b) in enumerate(zip(op, np_), 1):
            problems += compare_markers(a, b, " in paragraph %d" % i, author_forms)
    return problems


def author_forms_for(path):
    """Every name form in Work/author_refs.json for the file's source or unit."""
    slug, stem = check_author_refs.slug_and_stem(path)
    refs, _ = check_author_refs.load_config()
    return [f for group in check_author_refs.ref_groups(slug, stem, refs) for f in group]


def main():
    args = sys.argv[1:]
    archive = DEFAULT_ARCHIVE
    if "--archive" in args:
        i = args.index("--archive")
        if i + 1 >= len(args):
            raise SystemExit(__doc__)
        archive = Path(args[i + 1])
        if not archive.is_absolute():
            archive = ROOT / archive
        del args[i:i + 2]
    if not archive.is_dir():
        raise SystemExit("archive not found: %s (snapshot the summaries before the pass)" % archive)

    if args:
        targets = [Path(t) if Path(t).is_absolute() else ROOT / t for t in args]
    else:
        # Canonical chapter summaries only; parts/ files do not feed Summary.md.
        targets = sorted(CURRENT.glob("*/*.md"))

    clean = flagged = 0
    for cur in targets:
        rel = cur.resolve().relative_to(CURRENT.resolve())
        old = archive / rel
        if not old.exists():
            print("[skip] no archive for %s" % rel.as_posix())
            continue
        o, n = old.read_text(encoding="utf-8"), cur.read_text(encoding="utf-8")
        if o == n:
            print("[unchanged] %s" % rel.as_posix())
            continue
        problems = check(o, n, author_forms_for(cur))
        if any(not p.startswith("ADVISORY") for p in problems):
            flagged += 1
            print("[FLAG] %s" % rel.as_posix())
        else:
            clean += 1
            print("[ok] %s" % rel.as_posix())
        for p in problems:
            print("    %s" % p)
    print("\n%d edited file(s) passed all checks; %d flagged." % (clean, flagged))
    sys.exit(1 if flagged else 0)


if __name__ == "__main__":
    main()
