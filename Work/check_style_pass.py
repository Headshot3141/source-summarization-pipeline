"""Verify prose-only edits to chapter summaries against a pre-pass snapshot.

Used as the gate for a style pass (see passes/style-pass.md). A style pass may
change wording but never meaning, so this checks only what it must not change:

  quotes   every quoted span ("...", curly double quotes, and single curly
           quotes, with apostrophes such as mill’s or workers’ not read as
           quotes; straight single quotes are not read as quotations here),
           in order, identical (trailing .,;: ignored). Within a paragraph a
           line break reads as a space, so a quotation hard-wrapped across
           lines is found, and rewrapping it is no change.
  numbers  every numeric token (digits, and vulgar fractions such as ½ ⅓ ¾)
           identical; a reorder of the same numbers is reported separately
           as a softer "NUMBER ORDER" flag. Number words (twelve, hundred,
           half, dozen, percent, ...) and ordinal words (fourth, nineteenth,
           hundredth, ...; first/second/third only after a tens or scale
           word, as in "twenty-first") must also survive; the "one" of "no
           one" is not a number word.
  headings ## / ### heading text identical
  blocks   block-quotation lines ("> ") identical
  paras    paragraph count unchanged
  breaks   no two adjacent lines of the edited file that Markdown would run
           together (common.paragraph_break_problems): a lost blank line
           merges two paragraphs or pulls a heading into the text, and a
           word diff cannot see it. Every such line of the edited file is
           reported, as PARAGRAPH BREAK line N: <what>, since assembly
           refuses them too.
  markers  protected markers, counted by class (whole words, ignoring case;
           within a class, overlapping matches count once, longest first):
             hedges        perhaps, probably, possibly, seemingly, apparently,
                           tended to, seem to and appear to (any tense:
                           "seems to", "appeared to"), often, usually,
                           sometimes, not necessarily, may/might/would/could
                           have, it is reckoned, it is estimated,
                           purportedly, reportedly, allegedly, arguably
             contrast      but, yet, however, although, though, whereas,
                           nevertheless, even so, on the other hand, in
                           truth, while
             reporting     every form of argue, claim, say, believe, insist,
                           contend, maintain, write, think, suggest, hold,
                           note, observe, state, conclude, warn, remark, add,
                           acknowledge, admit, concede, assert, explain,
                           point out, recall, suspect, doubt, guess (state,
                           note, hold, remark, recall, warn, suspect, doubt
                           and guess not after "the", "a", "his", ...,
                           where they are nouns, nor in "beyond doubt", "is
                           suspect", "an educated guess" and the like,
                           EXTRA_GUARDS); according to; in his/her/their
                           view; in X's view
             negation      not (also cannot and n't), no, never, none, nor,
                           without, nobody, no one, nothing
             scope         some, most, only, merely, solely, just, all, few
             conditionals  if, unless, provided
             reach         one of the, among the, for example, for instance,
                           such as
             frames        suppose, imagine, one might, granted, on this
                           view, whether, and each "?"
             sequence      before, after, until, at first, eventually,
                           later, earlier, then, afterwards, afterward,
                           subsequently, previously, beforehand, formerly
           A class is flagged only when its count falls, so a swap within a
           class ("but" -> "however", "says" -> "notes", "only" -> "merely")
           passes. The style pass never merges or splits paragraphs, so
           counts are compared paragraph by paragraph (blank-line-separated
           blocks, headings included); when the paragraph count changed, they
           are compared over the whole file instead, alongside the PARAGRAPH
           COUNT flag.

A non-reporting class whose count fell gives
    PROTECTED MARKER <class> "<lost markers>" <old> -> <new>[ in paragraph N]
where the counts are the class's and the lost markers are those whose own
count fell; "while", "yet", "most" and "all" add a "(check sense: ...)" note.

Reporting markers are also compared by subject, whether or not their count
fell. The subject of each marker is found in the old and the new text: the
name or noun phrase just before the verb, joined across "and" (stepping back
over ", ...," asides: "Marlow, for his part, believes" and "Penhale, the
historian, says" give Marlow and Penhale; such a name wins over a short
phrase after the verb, as in "Penhale, however, argues the owners, not the
union, ..."); the one after it in inverted order ('"...," says Marlow',
"..., says the author.", but never "that ..."); after "according to"; or
inside "in X's view". A comma or period between digits ("4,000") is not a
clause break. A relative pronoun stands for its antecedent ("Ketteridge, who
argues" and "the critics who argue" give Ketteridge and the critics), and an
elided subject after "and"/"but" for the speaker of the reporting marker
before it in the sentence ("Thompson thinks X, and claims Y").

Old and new subjects are then aligned in order, paragraph by paragraph
(difflib over speakers). Two subjects are the same speaker when they match
ignoring case, a leading article and the order of "and"-joined names, or
when one is a longer form of the other ("Ada Penhale" for "Penhale") of the
same kind (below), the same name group in author_refs.json, and the same
not_author phrase: "Tom Penhale" never pairs with the author "Penhale", nor
"Thomas Marlow" (a group of his own) with the voice "Ida Marlow"/"Marlow".
A pronoun pairs with the subject it is read as (below), and a pronoun with
no name to read it as pairs with a lowercase noun phrase named earlier in
its sentence ("ordinary opinion, which suggests" -> "ordinary opinions, and
they suggest"). Then:

  SPEAKER ORDER       the same speakers report in a different order ("Marlow
                      says A; Quint says B" -> "Quint says A; Marlow says B").
                      Fails.
  VIEW MOVED          the first content words a paired marker introduces
                      (up to the next marker, a sentence break, or ", but")
                      now include another speaker's words that were not its
                      own, and either its own words are gone or the other
                      speaker took its words in turn ("Quint says the union
                      was weak; Marlow says it was strong" -> "... strong;
                      ... weak"). Fails.

and each old subject left unpaired gives one line, the same line once with
a count ("(2 times)"):

  ADVISORY            the subject is the unit's narrative voice (below), "the
                      author(s)", or "I" (or every "and"-joined subject is),
                      or a pronoun read as the voice: the author preface was
                      removed, which is correct if it only introduced the
                      author's own view. When the count did not fall, only if
                      no new subject is another speaker; never when another
                      speaker's marker changed order or moved onto other
                      words, or now introduces the author's lost view
                      ("Penhale argues A. Thompson thinks B." -> "Thompson
                      argues A; B."): that is an ATTRIBUTION DROP. Advisory
                      lines are printed but do not flag the file. Only a
                      neutral reporting verb (argues, writes, notes, says,
                      points out, ...) or phrase ("in Penhale's view") is
                      advisory; a hedging verb is an AUTHOR HEDGE.
  AUTHOR HEDGE        as ADVISORY, but the lost marker is a verb that hedges
                      (think, believe, suspect, doubt, guess): "Penhale
                      thinks the mill failed" may render the source's own
                      "we think", and "The mill failed" then states flatly
                      what the source offered as an opinion. Fails, unless
                      the paragraph (the file, when the paragraph count
                      changed) gained a hedges-class marker for each such
                      loss ("The mill probably failed"), which keeps
                      it ADVISORY. "suppose" (frames) and "seem to"/"appear
                      to" (hedges) fail through their own classes, whatever
                      their subject.
  ATTRIBUTION CHECK   a pronoun subject (he, she, they, it, one, we, you, and
                      his/her/their/him/them/its/us/our) that cannot be read
                      as a speaker: the coordinator confirms who; a defect if
                      it was another speaker. Fails. He/she/his/her/him (and
                      "in his/her view") are read as the nearest earlier
                      capitalized name in the same paragraph that is a name
                      form in author_refs.json (not_author included) or a
                      reporting subject; they/their/them as the nearest
                      earlier plural reporting subject ("the critics",
                      "Marlow and Quint"). Gender and number are not checked.
  ATTRIBUTION DROP    any other subject, including several subjects of which
                      any is not the voice ("Marlow and Penhale argue"), a
                      "not_author" phrase from author_refs.json ("Tom
                      Penhale"), a pronoun read as another speaker, and the
                      voice when its view now goes to another speaker:
                      another speaker's marker was removed, or the view was
                      handed to someone else ("Marlow argues" -> "Quint
                      argues"); a defect unless the source supports it.
                      Fails.

The narrative voice comes from Work/author_refs.json: the first name group of
a unit entry ("<slug>/<file stem>") is that unit's voice, the person the
prompt's AUTHOR line names (an interviewee, or an essay's author in an edited
volume); a unit with no entry of its own takes the source's (first) group.
Every other name group, interviewer included, is another speaker. A name
matches a form exactly or ends with it ("Professor Penhale" for "Penhale");
another group's form that ends with a voice form ("Thomas Marlow") counts as
a not_author phrase.

Lines read
    SPEAKER ORDER "<markers>" <old> -> <new>[ in paragraph N]: "<old subject>", ... -> "<new subject>", ...: the same speakers report in a different order; ...
    VIEW MOVED "<markers>" <old> -> <new>[ in paragraph N]: "<speaker>" now reports "<word>", ... (from "<other speaker>")[; ...]: defect unless the source gives each view to its new speaker
    ADVISORY "<markers>" <old> -> <new>[ in paragraph N] by "<subject>"[ (N times)][ (now "<new subject>", ...)]: ...
    AUTHOR HEDGE "<markers>" <old> -> <new>[ in paragraph N] by "<subject>"[ (N times)]: ...
    ATTRIBUTION CHECK "<markers>" <old> -> <new>[ in paragraph N] by pronoun '<subject>'[ (now ...)]: confirm who; defect if it was another speaker
    ATTRIBUTION DROP "<markers>" <old> -> <new>[ in paragraph N] by "<subject>"[ (now ...)]: ...
where a pronoun read as a speaker is given as by pronoun '<subject>' (read
as "<name>"), <markers> are the lost markers, or, when none was lost, the
markers of the subjects concerned, and "(now ...)" lists the unpaired new
subjects. If the count fell but every old subject is still found, a
PROTECTED MARKER reporting line is printed instead.

Files are read as UTF-8 with an optional byte-order mark. Word count is
deliberately NOT checked; a style pass may grow the text.

Usage (from the project root):
    python Work/check_style_pass.py                       # every edited summary
    python Work/check_style_pass.py Work/Summaries/<slug>/<file>.md ...
    python Work/check_style_pass.py --archive Work/Summaries_prestyle ...

A named file outside Work/Summaries, or missing, is reported as "[error] ..."
and counts as flagged. Exit status is 1 when any file is flagged (any line
other than ADVISORY).
"""
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

import check_author_refs
from check_fidelity import (FRACTION_FORMS, ORDINALS, OTHER_NUMBER_WORDS, PLURAL_SCALES, SCALES, UNITS,
                            WEAK_ORDINALS, quote_spans)
from common import ROOT, paragraph_break_problems, utf8_output

DEFAULT_ARCHIVE = ROOT / "Work" / "Summaries_prestyle"
CURRENT = ROOT / "Work" / "Summaries"

# A number ends in a digit, so a comma or period after it is not absorbed. A
# vulgar fraction character (½ ⅓ ¾ ...) is a number of its own.
NUMBER = re.compile(r"\d(?:[\d,.]*\d)?|[%s]" % "".join(FRACTION_FORMS))
# The "one" of "no one" is not a number, so "no one" -> "nobody" is no loss.
# Ordinals count ("nineteenth", "fifth"), but "first", "second" and "third"
# only after a tens or scale word ("twenty-first", "hundred and first" is not
# caught): alone they are too often not numbers, and "third" is the fraction.
_STRONG_ORDINALS = [w for w in ORDINALS if w not in WEAK_ORDINALS]
_WEAK_AFTER = "|".join(r"(?<=%s%s)" % (w, gap) for w in ("ty", "hundred", "thousand", "million", "billion")
                       for gap in ("-", " "))
NUMBER_WORD = re.compile(r"(?<!\bno[ -])\b(?:%s)\b|(?:%s)(?:%s)\b" % (
    "|".join(sorted(list(UNITS) + list(SCALES) + list(PLURAL_SCALES) + list(OTHER_NUMBER_WORDS)
                    + _STRONG_ORDINALS, key=len, reverse=True)),
    _WEAK_AFTER, "|".join(sorted(WEAK_ORDINALS))))
HEADING = re.compile(r"^#{2,3} .*$", re.M)
# A block quotation reproduces the source exactly, so a style pass never touches it.
BLOCK_QUOTE = re.compile(r"^>.*$", re.M)

# Markers whose loss usually changes meaning (preservation rules in
# writing-rules.md), in classes. Each class is counted per paragraph, and a
# drop in a class's count is flagged; a swap within a class ("but" for
# "however", "says" for "argues", "no one" for "nobody") is not. Matches are
# whole words, case-insensitive, and do not overlap within a class (the
# longest wins: "no one" is one negation, not two). Extend per project with
# source-specific hedges or attribution phrases.
POSSESSIVE_VIEW = "in <name>'s view"


def _forms(verb, doubled=False):
    """Every form of a regular reporting verb: argue -> argue, argues, argued,
    arguing; admit (doubled) -> admits, admitted, admitting."""
    stem = verb[:-1] if verb.endswith("e") else verb + (verb[-1] if doubled else "")
    return [verb, verb + "s", verb + "d" if verb.endswith("e") else stem + "ed", stem + "ing"]


REPORTING_VERBS = {v: _forms(v) for v in (
    "argue", "claim", "believe", "insist", "contend", "maintain", "suggest", "note", "observe",
    "state", "conclude", "warn", "remark", "add", "acknowledge", "concede", "assert", "explain",
    "recall")}
REPORTING_VERBS.update({
    "say": ["say", "says", "said", "saying"],
    "write": ["write", "writes", "wrote", "written", "writing"],
    "think": ["think", "thinks", "thought", "thinking"],
    "hold": ["hold", "holds", "held", "holding"],
    "admit": _forms("admit", doubled=True),
    "point out": ["point out", "points out", "pointed out", "pointing out"],
    "suspect": _forms("suspect"),
    "doubt": _forms("doubt"),
    "guess": ["guess", "guesses", "guessed", "guessing"],
})
# Reporting verbs that are also common nouns ("the state", "a note", "his
# notes", "a warning", "no doubt", "a suspect"): a form after one of these
# words is not counted.
NOUN_LIKE_VERBS = {"state", "note", "hold", "remark", "recall", "warn", "suspect", "doubt", "guess"}
# Reporting verbs that hedge. With the author as subject they often render
# the source's own hedge ("we think", "I suspect"), so removing one is an
# AUTHOR HEDGE, not an ADVISORY author preface.
AUTHOR_HEDGES = {"think", "believe", "suspect", "doubt", "guess"}
# Hedges that are a verb and "to", in any tense ("seems to", "appeared to").
VERB_HEDGES = {"seem to": "seem", "appear to": "appear"}
NOUN_GUARD = "".join(r"(?<!\b%s\s)" % w for w in (
    "the", "a", "an", "this", "that", "these", "those", "his", "her", "their", "its", "our", "my",
    "your", "each", "every", "no", "any", "one", "whole", "same", "new", "own", "such", "another",
    "united", "member", "nation", "welfare", "written", "final", "early", "first", "last"))
# More words before the nouns (and the adjective "suspect") that the hedging
# verbs also are: "beyond doubt", "casts doubt", "the prime suspect", "the
# figures are suspect", "an educated guess".
EXTRA_GUARDS = {
    "doubt": ("beyond", "without", "in", "of", "cast", "casts", "casting", "raise", "raises", "raised",
              "raising", "serious", "grave", "real", "reasonable", "some", "little", "much"),
    "suspect": ("prime", "chief", "main", "usual", "is", "are", "was", "were", "be", "been", "seem",
                "seems", "seemed", "remain", "remains", "remained", "look", "looks", "looked"),
    "guess": ("educated", "best", "wild", "rough", "good", "fair"),
}
MARKER_CLASSES = {
    "hedges": [
        "perhaps", "probably", "possibly", "seemingly", "apparently", "tended to",
        "seem to", "appear to", "often", "usually", "sometimes", "not necessarily",
        "may have", "might have", "would have", "could have", "it is reckoned", "it is estimated",
        "purportedly", "reportedly", "allegedly", "arguably",
    ],
    "contrast": [
        "but", "yet", "however", "although", "though", "whereas", "nevertheless",
        "even so", "on the other hand", "in truth", "while",
    ],
    # Attribution: reporting verbs (any form) and attribution phrases. A drop
    # is classified by its subject (see compare_markers).
    "reporting": list(REPORTING_VERBS) + [
        "according to", "in his view", "in her view", "in their view", POSSESSIVE_VIEW,
    ],
    # "not" also counts "cannot" and n't.
    "negation": ["not", "no", "never", "none", "nor", "without", "nobody", "no one", "nothing"],
    # "merely", "solely" and "just" count as "only".
    "scope": ["some", "most", "only", "merely", "solely", "just", "all", "few"],
    "conditionals": ["if", "unless", "provided"],
    "reach": ["one of the", "among the", "for example", "for instance", "such as"],
    # "?" counts question marks: a question frames a view rather than asserts it.
    "frames": ["suppose", "imagine", "one might", "granted", "on this view", "whether", "?"],
    "sequence": ["before", "after", "until", "at first", "eventually", "later", "earlier", "then",
                 "afterwards", "afterward", "subsequently", "previously", "beforehand", "formerly"],
}


def _marker_pattern(marker):
    if marker == "?":
        return re.compile(r"\?")
    if marker == "not":
        return re.compile(r"\b(?:can)?not\b|n['’]t\b", re.I)
    if marker in REPORTING_VERBS:
        guard = NOUN_GUARD if marker in NOUN_LIKE_VERBS else ""
        guard += "".join(r"(?<!\b%s\s)" % w for w in EXTRA_GUARDS.get(marker, ()))
        forms = sorted(REPORTING_VERBS[marker], key=len, reverse=True)
        return re.compile(guard + r"\b(?:%s)\b" % "|".join(f.replace(" ", r"\s+") for f in forms), re.I)
    if marker == POSSESSIVE_VIEW:
        return re.compile(r"\bin\s+((?:the\s+)?(?:[\w.-]+\s+){0,2}?[\w.-]+?)['’]s?\s+view\b", re.I)
    if marker in VERB_HEDGES:
        return re.compile(r"\b%s(?:s|ed|ing)?\s+to\b" % VERB_HEDGES[marker], re.I)
    return re.compile(r"\b" + re.escape(marker).replace(r"\ ", r"\s+") + r"\b", re.I)


CLASS_PATTERNS = {cls: [(m, _marker_pattern(m)) for m in markers]
                  for cls, markers in MARKER_CLASSES.items()}
# The class whose drops are checked for a dropped attribution.
ATTRIBUTION_CLASS = "reporting"
# Markers whose sense varies; a drop is reported with a reminder to check it.
ADVISORY = {
    "while": "'while' may be temporal rather than concessive",
    "yet": "'yet' may mean 'so far' rather than a contrast",
    "most": "'the most' may be a superlative rather than scope",
    "all": "'at all' is emphasis rather than scope",
}
AUTHOR_NOTE = "author preface removed; correct if it only introduced the author's own view"
HEDGE_NOTE = ("author's hedge removed; the verb may render the source's own hedge (\"we think\"): "
              "restore a hedge (perhaps, probably) unless the source states the view flatly")
HEDGE_KEPT_NOTE = "author's hedging verb removed and a hedge added; confirm the hedge matches the source's"
OTHER_NOTE = "another speaker's marker removed; defect unless the view is still marked"
PRONOUN_NOTE = "confirm who; defect if it was another speaker"
SWAP_NOTE = "speaker changed; defect unless the source gives the view to the new speaker"
VOICE_SWAP_NOTE = "author's marker now names another form or a pronoun; confirm it is still the author"

# A dropped attribution by a pronoun subject is read as the nearest earlier
# known name or speaker (see resolve_pronoun); one that cannot be read is a
# failing ATTRIBUTION CHECK for the coordinator to settle. "it" and "one" are
# here too: "it is said" and "one might argue" attribute a view to others.
# Only the first person ("I") is the author.
PRONOUNS = {"he", "she", "they", "it", "one", "we", "you", "his", "her", "their",
            "him", "them", "its", "us", "our"}
FIRST_PERSON = {"i", "me", "my"}
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
# A comma or period between digits ("4,000", "1.5") is part of a number, not a
# clause break.
CLAUSE_BREAK = r"(?:[;:!?\"“”()—–]|(?<!\d)[.,]|[.,](?!\d))"
# Sentence (and semicolon) breaks, for the words a reporting marker introduces.
SENTENCE_BREAK = re.compile(r"[;!?]|(?<!\d)\.|\.(?!\d)")
FULL_STOP = re.compile(r"[!?]|(?<!\d)\.|\.(?!\d)")
# Relative pronouns: "Ketteridge, who argues" is Ketteridge's view, "the evidence,
# which suggests" the evidence's.
RELATIVES = {"who", "which", "that"}
CONJUNCTIONS = {"and", "but", "or", "yet"}
# A closing quote, with or without a comma, just before a reporting verb:
# '"The mill failed," says Marlow' or '"The mill failed", says Marlow'.
QUOTE_BEFORE_VERB = re.compile(r"[\"”’'],?\s*$")


def quotes(text):
    # Trailing sentence punctuation may sit inside the quote in American style
    # but belongs to the sentence, so recasting may legitimately move it out.
    # Straight single quotes ('...') are not read as quotations here. Within a
    # paragraph a newline reads as a space, so a quotation hard-wrapped across
    # lines is found, and rewrapping it is no change.
    pieces = re.split(r"(\n\s*\n)", text)
    flat = "".join(p if i % 2 else p.replace("\n", " ") for i, p in enumerate(pieces))
    return [re.sub(r"\s+", " ", inner).rstrip(".,;:")
            for _, _, inner in quote_spans(flat, straight_single=False)]


def blocks(text):
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


def paragraphs(text):
    return len(blocks(text))


def bare(word):
    return re.sub(r"['’]s?$", "", re.sub(r"[.,;:!?]+$", "", word))


def capitalized_run(words, i):
    """(names, start) for the capitalized words ending just before words[i],
    joined across "and" ("Marlow and Penhale"); names is [] if there are none."""
    run, j = [], i
    while j > 0:
        w = words[j - 1]
        if w.lower() == "and" and run and j > 1 and words[j - 2][:1].isupper() \
                and words[j - 2].lower() not in FUNCTION_WORDS:
            run.insert(0, "and")
        elif w[:1].isupper() and w.lower() not in FUNCTION_WORDS:
            run.insert(0, bare(w))
        else:
            break
        j -= 1
    return run, j


def phrase_before(clause, i, first):
    """(subject phrase, start) for the noun phrase ending just before
    clause[i]: a pronoun, a run of capitalized words, or a determiner phrase
    within the last four words. For the first phrase found (first=True) the
    last two words are the fallback; otherwise (None, i)."""
    if clause[i - 1].lower() in PRONOUNS | FIRST_PERSON:
        return clause[i - 1], i - 1
    run, j = capitalized_run(clause, i)
    if run:
        return " ".join(run), j
    for k in range(max(0, i - 4), i):
        if clause[k].lower() in DETERMINERS:
            return " ".join(clause[k:i]), k
    if first:
        return " ".join(clause[max(0, i - 2):i]), max(0, i - 2)
    return None, i


def marker_subject(marker, match, text):
    """The speaker (or speakers, joined by "and") an attribution marker
    attaches to, read from text."""
    if marker == POSSESSIVE_VIEW:
        return match.group(1)
    if marker in ("in his view", "in her view", "in their view"):
        return marker.split()[1]
    if marker == "according to":
        words = re.split(CLAUSE_BREAK, text[match.end():])[0].split()[:6]
        if words and words[0].lower() in PRONOUNS | FIRST_PERSON:
            return words[0]
        run = []
        for k, w in enumerate(words):
            if w.lower() == "and" and run and k + 1 < len(words) and words[k + 1][:1].isupper():
                run.append("and")
            elif w[:1].isupper() and w.lower() not in FUNCTION_WORDS:
                run.append(bare(w))
            else:
                break
        return " ".join(run or words[:4]) or "?"
    # A reporting verb. Inverted order when a closing quote (and comma) sits
    # just before it: '"...," says Penhale'.
    before = text[:match.start()]
    if QUOTE_BEFORE_VERB.search(before):
        return inverted_subject(text, match)
    # Otherwise the subject just before it in the same clause.
    pieces = re.split("(%s)" % CLAUSE_BREAK, before)
    segs, breaks = pieces[0::2], pieces[1::2]
    # A relative pronoun stands for its antecedent: "the critics who argue"
    # in the same clause, "Ketteridge, who argues" before the comma.
    # An elided subject after "and"/"but" ("Thompson thinks X, and claims Y",
    # "the critics argue X and say Y") is that of the reporting marker
    # before it in the sentence.
    tail = segs[-1].split()
    while tail and tail[-1].lower() in SKIP_BEFORE_VERB - CONJUNCTIONS:
        tail.pop()
    if tail and tail[-1].lower() in CONJUNCTIONS:
        starts = [m.end() for m in FULL_STOP.finditer(text, 0, match.start())]
        start = starts[-1] if starts else 0
        earlier = [(mk, m) for mk, m in class_matches(ATTRIBUTION_CLASS, text)
                   if start <= m.start() and m.end() <= match.start()]
        if earlier:
            return marker_subject(earlier[-1][0], earlier[-1][1], text)
    rest = relative_rest(segs[-1])
    if rest is not None:
        antecedent = clause_subject(rest, fallback=False) if rest.strip() else ""
        if not antecedent and breaks and breaks[-1] == ",":
            antecedent = clause_subject(segs[-2])
        if antecedent:
            return antecedent
    subject = clause_subject(segs[-1])
    if subject:
        return subject
    # Nothing between the verb and the last break. "It failed, says Marlow."
    # is inverted; "Marlow, for his part, believes ..." and "Penhale, the
    # historian, says ..." step back over the ", ...," aside to the clause
    # before it. An appositive aside after a name ("Penhale, the historian,
    # however, says") gives the name. A name that is the whole clause before
    # the aside wins over a short phrase after the verb ("Penhale, however,
    # argues the owners, not the union, ..."); a closing quote before the
    # verb was handled above.
    if breaks and breaks[-1] == ",":
        stepped, whole = step_back(segs, breaks)
        if stepped and (not short_inversion(text, match)
                        or (whole and stepped[:1].isupper()
                            and stepped.split()[0].lower() not in DETERMINERS | PRONOUNS)):
            return stepped
    return inverted_subject(text, match)


def relative_rest(seg):
    """The clause text before a relative pronoun that ends seg (after
    auxiliaries and adverbs: "who also argues"), or None if seg does not end
    in one."""
    words = seg.split()
    while words and (words[-1].lower() in SKIP_BEFORE_VERB
                     or (words[-1].endswith("ly") and not words[-1][:1].isupper())):
        words.pop()
    if words and words[-1].lower() in RELATIVES:
        # "That suggests ..." opening a clause is a demonstrative, not a relative.
        return " ".join(words[:-1])
    return None


def step_back(segs, breaks):
    """(subject, whole) from the clauses before a ", ...," aside that ends
    just before a verb; whole is True if the subject is that whole clause.
    ("", False) if there is none."""
    j = len(segs) - 3
    while j >= 0 and breaks[j] == ",":
        subject = clause_subject(segs[j], fallback=False)
        if subject:
            if subject.split()[0].lower() in DETERMINERS and j > 0 and breaks[j - 1] == ",":
                name = clause_subject(segs[j - 1], fallback=False)
                if name and name.split()[0].lower() not in DETERMINERS:
                    return name, name.split() == segs[j - 1].split()
            return subject, subject.split() == segs[j].split()
        j -= 1
    return "", False


def clause_subject(text, fallback=True):
    """The subject phrase (or phrases joined by "and") at the end of a clause,
    after skipping auxiliaries and adverbs; "" if there is none. Without
    fallback, a clause with no pronoun, name, or determiner phrase gives ""."""
    clause = text.split()
    # Skip auxiliaries and lowercase -ly adverbs; a capitalized word ending in
    # -ly (Kelly, Italy) is a name, not an adverb.
    while clause and (clause[-1].lower() in SKIP_BEFORE_VERB
                      or (clause[-1].endswith("ly") and not clause[-1][:1].isupper())):
        clause.pop()
    parts, i = [], len(clause)
    while i > 0:
        phrase, i = phrase_before(clause, i, fallback and not parts)
        if not phrase:
            break
        parts.insert(0, phrase)
        # "Marlow and the critics argue": take the phrase before "and" too.
        if i > 1 and clause[i - 1].lower() == "and":
            i -= 1
            continue
        break
    return " and ".join(parts)


def short_inversion(text, match):
    """True if only a subject follows the verb before the clause ends: ", says
    Marlow.", ", says the author.", ", said he"."""
    words = re.split(CLAUSE_BREAK, text[match.end():])[0].split()
    # "claims that 4,000 marched": "that" opens a clause, never a subject.
    if not words or len(words) > 3 or words[0].lower() == "that":
        return False
    if len(words) == 1:
        return words[0].lower() in PRONOUNS | FIRST_PERSON or words[0][:1].isupper()
    if words[0].lower() in DETERMINERS:
        return len(words) == 2
    return all(w[:1].isupper() for w in words)


def inverted_subject(text, match):
    """The subject after a reporting verb: '"...," says Penhale', '"...,"
    writes the author', 'said he'."""
    after = text[match.end():].split()[:4]
    if after and after[0].lower() in PRONOUNS | FIRST_PERSON:
        return bare(after[0])
    if after and after[0].lower() in DETERMINERS - {"that"} and len(after) > 1:
        return after[0] + " " + bare(after[1])
    run = []
    for w in after:
        if not w[:1].isupper():
            break
        run.append(bare(w))
        if bare(w) != w:
            break
    return " ".join(run) or "?"


def _matches_form(s, forms):
    """True if s is one of forms or ends with one ("Professor Penhale",
    "Ada Penhale" for "Penhale"), ignoring case."""
    return any(s == f or s.endswith(" " + f) for f in (f.lower() for f in forms))


def subject_kind(subject, author_forms, not_author=()):
    """"author", "pronoun", or "other" for an attribution subject.

    author:  every speaker is an explicit author name form (or ends with
             one), "the author(s)", or the first person.
    pronoun: no speaker is "other" and at least one is a pronoun (he, she,
             they, it, one, we, ...), which cannot be tied to the author.
    other:   any speaker is anyone else ("Marlow and Penhale" when only
             Penhale is the author), or a not_author phrase ("Tom Penhale").
    """
    kinds = set()
    for part in re.split(r"\s+(?:and|&)\s+", subject.strip()):
        s = re.sub(r"\s+", " ", bare(part.strip())).lower()
        if s in FIRST_PERSON or s in ("the author", "the authors"):
            kinds.add("author")
        elif s in PRONOUNS:
            kinds.add("pronoun")
        elif not _matches_form(s, not_author) and _matches_form(s, author_forms):
            kinds.add("author")
        else:
            kinds.add("other")
    for kind in ("other", "pronoun"):
        if kind in kinds:
            return kind
    return "author"


def class_matches(cls, text):
    """[(marker, match)] for a class's markers in text, in order, without
    overlaps (the longest match at a position wins)."""
    found = []
    for marker, pat in CLASS_PATTERNS[cls]:
        found += [(m.start(), -m.end(), marker, m) for m in pat.finditer(text)]
    found.sort(key=lambda f: f[:2])
    out, end = [], -1
    for start, _, marker, m in found:
        if start >= end:
            out.append((marker, m))
            end = m.end()
    return out


def subject_key(subject):
    """A subject for comparison: each speaker lowercased, without a leading
    article, in sorted order ("The critics and Marlow" -> ("critics", "marlow"))."""
    parts = []
    for part in re.split(r"\s+(?:and|&)\s+", subject.strip()):
        part = re.sub(r"\s+", " ", bare(part.strip())).lower()
        parts.append(re.sub(r"^(?:the|a|an) ", "", part))
    return tuple(sorted(parts))


def same_speaker(a, b):
    """True if subject keys a and b name the same speakers, a longer form
    matching its ending ("ada penhale" and "penhale")."""
    def match(x, y):
        return x == y or x.endswith(" " + y) or y.endswith(" " + x)
    return len(a) == len(b) and all(any(match(x, y) for y in b) for x in a)


class Speakers:
    """Who is who in one unit: the voice's name forms (the author), the
    not_author phrases, and every name group from author_refs.json (the
    voice's included)."""

    def __init__(self, voice=(), not_author=(), groups=()):
        self.voice = list(voice)
        voice_lower = {f.lower() for f in self.voice}
        self.groups = [list(g) for g in groups if g]
        others = [f for g in self.groups if {x.lower() for x in g} != voice_lower for f in g]
        # Another person's form that ends with one of the voice's forms
        # ("Thomas Marlow" when the voice is "Ida Marlow", "Marlow") names
        # someone else, as a not_author phrase does.
        clash = [f for f in others if f.lower() not in voice_lower and _matches_form(f.lower(), self.voice)]
        self.not_author = list(not_author) + clash
        self.forms = self.voice + others + list(not_author)

    def kind(self, subject):
        return subject_kind(subject, self.voice, self.not_author)

    def signature(self, subject):
        """Per speaker: the name group and the not_author phrase it matches
        (the longest matching form wins), or None."""
        sig = []
        for part in re.split(r"\s+(?:and|&)\s+", subject.strip()):
            s = re.sub(r"\s+", " ", bare(part.strip())).lower()
            group = max(((len(f), i) for i, g in enumerate(self.groups) for f in g if _matches_form(s, [f])),
                        default=(0, None))[1]
            phrase = max(((len(f), f.lower()) for f in self.not_author if _matches_form(s, [f])),
                         default=(0, None))[1]
            sig.append(repr((group, phrase)))
        return sorted(sig)

    def same(self, a, b):
        """True if subjects a and b name the same speakers: equal keys, or a
        longer form of the same name ("Ada Penhale", "Penhale") of the same
        kind, name group, and not_author phrase, so "Tom Penhale" never pairs
        with the author "Penhale"."""
        ka, kb = subject_key(a), subject_key(b)
        if ka == kb:
            return True
        return (same_speaker(ka, kb) and self.kind(a) == self.kind(b)
                and self.signature(a) == self.signature(b))


class Item:
    """A reporting marker in a text, with its subject."""

    def __init__(self, marker, match, subject):
        self.marker, self.match, self.subject = marker, match, subject
        self.pos = match.start()


# Pronouns tied to an earlier speaker: he/she/his/her/him to the nearest
# earlier known name, they/their/them to the nearest earlier plural speaker.
SINGULAR_PRONOUNS = {"he", "she", "his", "her", "him"}
PLURAL_PRONOUNS = {"they", "their", "them"}
# The words a reporting marker introduces (up to the next marker or sentence
# break), at most this many, compared to see whether a view moved.
OBJECT_WORDS = 5
OBJECT_END = re.compile(SENTENCE_BREAK.pattern + r"|\n\s*\n|,\s+(?:but|while|whereas|although|though|yet)\b")
STOPWORDS = set("""
the and was were that this these those with from have has had not but for its his her their they
them she him who whom which what are been being into onto than then there here also would could
should will can may might did does our out all any some more most very such only just about over
upon when while where whether because since after before yet nor one each other own same both
either neither how why its it's itself""".split())
VERB_FORMS = {f for forms in REPORTING_VERBS.values() for form in forms for f in form.split()}
ORDER_NOTE = "the same speakers report in a different order; defect unless each view still goes to its own speaker"
VIEW_NOTE = "defect unless the source gives each view to its new speaker"
MOVED_NOTE = ("author preface removed while the marker of %s moved onto other words; "
              "defect if the author's view now goes to that speaker")


def paragraph_start(text, pos):
    """The offset where the paragraph holding pos starts."""
    ends = [m.end() for m in re.finditer(r"\n\s*\n", text[:pos])]
    return ends[-1] if ends else 0


def capitalized_names(text, start, end):
    """Runs of capitalized words in text[start:end], in order, each without
    leading function words or pronouns ("In Penhale's" -> "Penhale")."""
    out, run = [], []

    def flush():
        words = [bare(m.group()) for m in run]
        while words and words[0].lower() in FUNCTION_WORDS | PRONOUNS | FIRST_PERSON | {"according", "to"}:
            words.pop(0)
        if words:
            out.append(" ".join(words))

    for m in re.finditer(r"[^\W\d_][\w'’-]*", text[start:end]):
        if not m.group()[:1].isupper():
            flush()
            run = []
        elif run and text[start + run[-1].end():start + m.start()].strip():
            flush()
            run = [m]
        else:
            run.append(m)
    flush()
    return out


def is_plural(subject):
    key = subject_key(subject)
    last = subject.split()[-1] if subject.split() else ""
    return len(key) > 1 or key == ("authors",) or (last.lower().endswith("s") and not last[:1].isupper())


def resolve_pronoun(text, item, items, sp, subjects=()):
    """The speaker a pronoun subject refers to, or None: for he/she/his/
    her/him the nearest earlier capitalized name in the same paragraph that is
    a known name form (author_refs) or a reporting subject; for they/their/
    them the nearest earlier plural reporting subject there."""
    key = subject_key(item.subject)
    if len(key) != 1:
        return None
    start = paragraph_start(text, item.pos)
    if key[0] in SINGULAR_PRONOUNS:
        speakers = [s for s in [it.subject for it in items] + list(subjects) if sp.kind(s) != "pronoun"]
        found = None
        for name in capitalized_names(text, start, item.pos):
            if _matches_form(name.lower(), sp.forms) or any(sp.same(name, s) for s in speakers):
                found = name
        return found
    if key[0] in PLURAL_PRONOUNS:
        found = [it for it in items if start <= it.pos < item.pos and sp.kind(it.subject) != "pronoun"
                 and is_plural(it.subject)]
        return found[-1].subject if found else None
    return None


def named_earlier(text, pos, subject):
    """True if the head noun of a lowercase noun-phrase subject ("ordinary
    opinion") occurs earlier in the sentence holding pos ("ordinary opinions,
    and they suggest")."""
    words = subject.split()
    if not words or words[-1][:1].isupper() or subject_key(subject)[0] in PRONOUNS:
        return False
    head = bare(words[-1]).lower()[:5]
    breaks = [m.end() for m in OBJECT_END.finditer(text, 0, pos)]
    sentence = text[breaks[-1] if breaks else 0:pos].lower()
    return any(w[:5] == head for w in re.findall(r"[^\W\d_]+", sentence))


def anaphor_pairs(pronoun_items, pronoun_idx, other_items, other_idx, text, sp):
    """[(pronoun index, other index)] pairing each pronoun subject (in text)
    with the other side's subject it refers to."""
    pairs, taken = [], set()
    for i in pronoun_idx:
        it = pronoun_items[i]
        if sp.kind(it.subject) != "pronoun":
            continue
        name = resolve_pronoun(text, it, pronoun_items, sp, [o.subject for o in other_items])
        for j in other_idx:
            other = other_items[j].subject
            if j in taken or sp.kind(other) == "pronoun":
                continue
            if (name and sp.same(name, other)) or (not name and named_earlier(text, it.pos, other)):
                pairs.append((i, j))
                taken.add(j)
                break
    return pairs


def object_words(items, k, text):
    """{stem: word} for the first content words a reporting marker
    introduces, up to the next marker or sentence break."""
    it = items[k]
    end = min([o.pos for o in items if o.pos > it.pos] + [len(text)])
    m = OBJECT_END.search(text, it.match.end(), end)
    if m:
        end = m.start()
    exclude = {w for part in subject_key(it.subject) for w in part.split()}
    words = [w for w in re.findall(r"[^\W\d_]+", text[it.match.end():end].lower())
             if len(w) >= 3 and w not in STOPWORDS and w not in exclude and w not in VERB_FORMS]
    out = {}
    for w in words[:OBJECT_WORDS]:
        out.setdefault(w[:5], w)
    return out


class Alignment:
    """Old and new reporting subjects aligned in order (see align)."""

    def __init__(self):
        self.pairs, self.lost, self.gained = [], [], []
        self.reordered = []     # old indices of speakers found at another place
        self.resolved = {}      # old index of a lost pronoun -> the name it refers to
        self.taken = {}         # old index of a lost subject -> speaker now on its view
        self.moves = []         # (old index A, old index B, words): A now reports B's words
        self.moved_other = []   # non-voice speakers whose marker moved


def align(olds, news, old, new, sp):
    """Align old and new reporting subjects in order (difflib on speakers,
    "Ada Penhale" and "Penhale" being one), then pair a speaker found at
    another place (a reorder), and a pronoun with the subject it refers to.
    Then compare the words each paired marker introduces: a marker that now
    introduces another speaker's words moved."""
    al = Alignment()
    reps = []

    def ident(subject):
        key = subject_key(subject)
        for i, r in enumerate(reps):
            if subject_key(r) == key:
                return i
        for i, r in enumerate(reps):
            if sp.same(r, subject):
                return i
        reps.append(subject)
        return len(reps) - 1

    oid = [ident(it.subject) for it in olds]
    nid = [ident(it.subject) for it in news]
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, oid, nid, autojunk=False).get_opcodes():
        if tag == "equal":
            al.pairs += list(zip(range(i1, i2), range(j1, j2)))
        else:
            al.lost += range(i1, i2)
            al.gained += range(j1, j2)
    for i in al.lost:
        if sp.kind(olds[i].subject) == "pronoun":
            name = resolve_pronoun(old, olds[i], olds, sp, [it.subject for it in news])
            if name:
                al.resolved[i] = name
    for i, j in anaphor_pairs(olds, al.lost, news, al.gained, old, sp):
        al.lost.remove(i)
        al.gained.remove(j)
        al.pairs.append((i, j))
    for j, i in anaphor_pairs(news, al.gained, olds, al.lost, new, sp):
        al.lost.remove(i)
        al.gained.remove(j)
        al.pairs.append((i, j))
    for i in list(al.lost):
        j = next((j for j in al.gained if nid[j] == oid[i]), None)
        if j is not None:
            al.lost.remove(i)
            al.gained.remove(j)
            al.pairs.append((i, j))
            al.reordered.append(i)

    before = [object_words(olds, i, old) for i in range(len(olds))]
    after = {i: object_words(news, j, new) for i, j in al.pairs}
    took = {}
    for i, j in al.pairs:
        for b in range(len(olds)):
            if b != i and oid[b] != oid[i]:
                words = [w for s, w in after[i].items() if s in before[b] and s not in before[i]]
                if words:
                    took[(i, b)] = words
    for (i, b), words in took.items():
        own_gone = not set(before[i]) & set(after[i])
        if b in al.lost and own_gone:
            if sp.kind(olds[i].subject) != "author":
                al.taken.setdefault(b, olds[i].subject)
        elif b in after and (own_gone or (b, i) in took):
            al.moves.append((i, b, words))
        else:
            continue
        if sp.kind(olds[i].subject) != "author":
            al.moved_other.append(olds[i].subject)
    al.moved_other += [olds[i].subject for i in al.reordered if sp.kind(olds[i].subject) != "author"]
    return al


def compare_markers(old, new, where, speakers):
    """Problems for protected-marker classes whose count fell from old to new,
    and for reporting subjects that changed, moved, or changed order (see the
    module docstring)."""
    problems = []
    for cls in CLASS_PATTERNS:
        om, nm = class_matches(cls, old), class_matches(cls, new)
        fell = len(nm) < len(om)
        al, olds, news = Alignment(), [], []
        if cls == ATTRIBUTION_CLASS:
            olds = [Item(mk, m, marker_subject(mk, m, old)) for mk, m in om]
            news = [Item(mk, m, marker_subject(mk, m, new)) for mk, m in nm]
            al = align(olds, news, old, new, speakers)
        if not fell and not al.lost and not al.reordered and not al.moves:
            continue
        lost = Counter(mk for mk, _ in om) - Counter(mk for mk, _ in nm)
        names = list(dict.fromkeys(mk for mk, _ in om if mk in lost))

        def counts(idx=None):
            marks = names or list(dict.fromkeys(olds[i].marker for i in sorted(idx or [])))
            return '"%s" %d -> %d%s' % (", ".join(marks), len(om), len(nm), where)

        if al.reordered:
            problems.append('SPEAKER ORDER %s: %s -> %s: %s' % (
                counts(al.reordered), ", ".join('"%s"' % it.subject for it in olds),
                ", ".join('"%s"' % it.subject for it in news), ORDER_NOTE))
        if al.moves:
            done = []
            for i, b, words in al.moves:
                if {i, b} not in done:
                    done.append({i, b})
            for pair in done:
                parts = ['"%s" now reports %s (from "%s")' % (olds[i].subject, ", ".join('"%s"' % w for w in words),
                                                              olds[b].subject)
                         for i, b, words in al.moves if {i, b} == pair]
                problems.append("VIEW MOVED %s: %s: %s" % (counts(pair), "; ".join(parts), VIEW_NOTE))
        if al.lost:
            hedged = [i for i in al.lost if olds[i].marker in AUTHOR_HEDGES and olds[i].marker in lost]
            added = len(class_matches("hedges", new)) - len(class_matches("hedges", old))
            problems += attribution_problems(
                [(i, olds[i].subject) for i in al.lost], [news[j].subject for j in sorted(al.gained)], fell,
                counts(al.lost), speakers, al, hedged, added)
            continue
        if fell:
            notes = "".join("  (check sense: %s)" % ADVISORY[mk] for mk in names if mk in ADVISORY)
            problems.append("PROTECTED MARKER %s %s%s" % (cls, counts(), notes))
    return problems


def attribution_problems(lost, gained, fell, counts, sp, al=None, hedged=(), added_hedges=0):
    """One line per lost reporting subject ((old index, subject) pairs), the
    same line given once with a count. When the reporting count did not
    fall, a lost subject means the view now goes to someone else. hedged:
    the old indices whose marker is a hedging verb (AUTHOR_HEDGES) whose
    count fell; added_hedges: how many hedges-class markers the text gained,
    each of which makes up for one lost hedging verb."""
    al = al or Alignment()
    now = ' (now %s)' % ", ".join('"%s"' % g for g in gained) if gained else ""
    # The voice's view moved to another speaker is a defect, not a removed preface.
    gained_other = any(sp.kind(g) == "other" for g in gained)
    lines = []
    for i, subject in sorted(lost, key=lambda x: (x[1], x[0])):
        kind, by = sp.kind(subject), '"%s"' % subject
        if kind == "pronoun" and i in al.resolved:
            by = "pronoun '%s' (read as \"%s\")" % (subject, al.resolved[i])
            kind = sp.kind(al.resolved[i])
        moved = [al.taken[i]] if i in al.taken else list(dict.fromkeys(al.moved_other))
        if kind == "author" and moved:
            lines.append(("ATTRIBUTION DROP", by, MOVED_NOTE % ", ".join('"%s"' % m for m in moved)))
        elif kind == "author" and fell and i in hedged:
            if added_hedges > 0:
                added_hedges -= 1
                lines.append(("ADVISORY", by, HEDGE_KEPT_NOTE))
            else:
                lines.append(("AUTHOR HEDGE", by, HEDGE_NOTE))
        elif kind == "author" and (fell or not gained_other):
            lines.append(("ADVISORY", by, AUTHOR_NOTE if fell else VOICE_SWAP_NOTE))
        elif kind == "pronoun":
            lines.append(("ATTRIBUTION CHECK", "pronoun '%s'" % subject, PRONOUN_NOTE))
        else:
            lines.append(("ATTRIBUTION DROP", by, OTHER_NOTE if fell else SWAP_NOTE))
    problems = []
    for (label, by, note), n in Counter(lines).items():
        times = " (%d times)" % n if n > 1 else ""
        problems.append("%s %s by %s%s%s: %s" % (label, counts, by, times, now, note))
    return problems


def check(old, new, author_forms=(), not_author=(), name_groups=()):
    """Problems between the snapshot (old) and the edited text (new).

    Lines starting "ADVISORY" are notes, not defects. author_forms: the name
    forms of the unit's narrative voice only (see voice_forms); every other
    speaker, interviewer included, is left out so their markers stay guarded;
    not_author: phrases naming someone else who shares a form ("Tom Penhale");
    name_groups: every name group for the unit (see name_groups), so another
    person sharing the voice's surname ("Thomas Marlow") is told apart.
    """
    speakers = Speakers(author_forms, not_author, name_groups)
    old, new = old.lstrip("\ufeff"), new.lstrip("\ufeff")
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

    for n, message in paragraph_break_problems(new):
        problems.append("PARAGRAPH BREAK line %d: %s" % (n, message))

    op, np_ = blocks(old), blocks(new)
    if len(op) != len(np_):
        problems.append("PARAGRAPH COUNT %d -> %d" % (len(op), len(np_)))
        problems += compare_markers(old, new, "", speakers)
    else:
        for i, (a, b) in enumerate(zip(op, np_), 1):
            problems += compare_markers(a, b, " in paragraph %d" % i, speakers)
    return problems


def voice_forms(slug, stem, refs):
    """The name forms of the unit's narrative voice in author_refs.json refs.

    The first name group of a unit entry ("<slug>/<file stem>") is that
    unit's voice: the interviewee, or the essay's author in an edited volume
    (the person the prompt's AUTHOR line names). Without a unit entry the
    voice is the source's own group (its first, if it lists several). Every
    other group, the source's author or interviewer included, is another
    speaker."""
    for key in (f"{slug}/{stem}", slug):
        entry = refs.get(key) or []
        if entry:
            return list(entry) if all(isinstance(e, str) for e in entry) else list(entry[0])
    return []


def name_groups(slug, stem, refs):
    """Every name group for a unit in author_refs.json refs: the unit
    entry's, then the source's. A list of names is one group."""
    groups = []
    for key in (f"{slug}/{stem}", slug):
        entry = refs.get(key) or []
        if entry and all(isinstance(e, str) for e in entry):
            entry = [entry]
        groups += [list(g) for g in entry]
    return groups


def author_forms_for(path):
    """(the voice's name forms, not_author phrases) from Work/author_refs.json
    for the file's unit or source (see voice_forms)."""
    slug, stem = check_author_refs.slug_and_stem(path)
    refs, not_author = check_author_refs.load_config()
    return voice_forms(slug, stem, refs), not_author.get(slug, [])


def name_groups_for(path):
    """Every name group from Work/author_refs.json for the file's unit."""
    slug, stem = check_author_refs.slug_and_stem(path)
    refs, _ = check_author_refs.load_config()
    return name_groups(slug, stem, refs)


def main():
    utf8_output()
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
        try:
            rel = cur.resolve().relative_to(CURRENT.resolve())
        except ValueError:
            flagged += 1
            print("[error] %s is not under %s; pass a summary there" % (cur.as_posix(), CURRENT.as_posix()))
            continue
        if not cur.is_file():
            flagged += 1
            print("[error] %s not found" % rel.as_posix())
            continue
        old = archive / rel
        if not old.exists():
            print("[skip] no archive for %s" % rel.as_posix())
            continue
        o, n = old.read_text(encoding="utf-8-sig"), cur.read_text(encoding="utf-8-sig")
        if o == n:
            print("[unchanged] %s" % rel.as_posix())
            continue
        problems = check(o, n, *author_forms_for(cur), name_groups_for(cur))
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
