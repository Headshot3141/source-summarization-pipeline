"""Flag summary paragraphs that refer to a source's author more than once.

writing-rules.md ("Naming the author") has the summary speak in the
author's voice and allows at most one reference to the author per
paragraph, where a sentence needs it. In an earlier run the summaries of one book named the author
about once every 80 words, mostly at the start of sentence after sentence.

A reference is a name form listed in Work/author_refs.json for the file's
source or unit, or a generic form ("the author", "the authors"). Each person
is counted separately, so an interview paragraph that names the interviewer
once and the interviewee once passes. Text inside double quotation marks,
block quotations ("> ") and headings is not counted, nor are phrases listed
under "not_author" (another person who shares the author's surname).
Pronouns are not counted, because they cannot be tied to a person
mechanically; the rule still applies to them.

A flagged paragraph is either rewritten or, where a second reference keeps
another speaker's view apart from the author's, kept and justified in the
review record.

Usage (from the project root):
    python Work/check_author_refs.py                  # every summary in Work/manifest.json
    python Work/check_author_refs.py <file> ...        # drafts or summaries, part files too

The source slug comes from the path (Work/Drafts/<slug>/..., Work/Summaries/<slug>/...).
Exit status is 1 when any paragraph is flagged.
"""
import json
import re
import sys
from pathlib import Path

from common import ROOT

CONFIG = ROOT / "Work" / "author_refs.json"
# Fill in Work/author_refs.json during Preflight, for example:
# {
#   "refs": {
#     "penhale-mills": ["Ada Penhale", "Penhale"],
#     "penhale-mills/03-interview": ["Marlow"],
#     "penhale-mills/04-interview": [["Ida Marlow", "Marlow"], ["Quint"]]
#   },
#   "not_author": {"penhale-mills": ["Tom Penhale"]}
# }
# "refs" maps a source slug to every form the summaries use for its author,
# and "<slug>/<file stem>" to a unit's other main speakers (interviewees, or
# an essay's author in an edited collection). A list of names is one person;
# a list of lists is several people, each counted on their own. Part
# suffixes ("-part1-of-2") are ignored when matching file stems. The longest
# form matches first, so a full name and a surname are not double-counted.
# The generic forms belong to the source's entry, or to the unit's entry when
# the source has none.
GENERIC = ["the authors", "the author"]

MANIFEST = ROOT / "Work" / "manifest.json"
QUOTED = re.compile(r'"[^"\n]*"|“[^”]*”')
PART_SUFFIX = re.compile(r"-part\d+-of-\d+$")


def slug_and_stem(path):
    """(slug, stem) from a Drafts or Summaries path, or (None, stem)."""
    parts = Path(path).parts
    for i, name in enumerate(parts[:-1]):
        if name.startswith(("Drafts", "Summaries")) and i + 1 < len(parts) - 1:
            return parts[i + 1], PART_SUFFIX.sub("", Path(path).stem)
    return None, Path(path).stem


def load_config():
    if not CONFIG.exists():
        return {}, {}
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    return data.get("refs", {}), data.get("not_author", {})


def ref_groups(slug, stem, refs):
    """[[forms of one person], ...] for a file; generic forms join the first group."""
    groups = []
    for key in (slug, f"{slug}/{stem}"):
        entry = refs.get(key) or []
        if entry and all(isinstance(e, str) for e in entry):
            entry = [entry]
        groups += [list(person) for person in entry]
    if not groups:
        return [list(GENERIC)]
    groups[0] += GENERIC
    return groups


def ref_pattern(forms):
    """One pattern for a person's forms; the generic forms ignore case."""
    alts = []
    for form in sorted(set(forms), key=len, reverse=True):
        body = re.escape(form)
        alts.append(r"\b(?i:" + body + r")\b" if form in GENERIC else r"\b" + body + r"\b")
    return re.compile("|".join(alts))


def paragraphs(text):
    """Yield (first line number, paragraph text) for each prose paragraph."""
    line = 1
    for block in re.split(r"(\n\s*\n)", text):
        if block.strip() and not block.lstrip().startswith(("#", ">")):
            lead = len(block) - len(block.lstrip("\n"))
            yield line + lead, block
        line += block.count("\n")


def flagged_paragraphs(text, patterns, exclude=()):
    """[(line, references)] for paragraphs that refer to one person more than once."""
    found = []
    for line, para in paragraphs(text):
        para = QUOTED.sub("", para)
        for phrase in exclude:
            para = para.replace(phrase, "")
        over = [r for p in patterns for r in [p.findall(para)] if len(r) > 1]
        if over:
            found.append((line, [x for r in over for x in r]))
    return found


def check_file(path, refs, not_author):
    """Print flags for one file; return the number of flagged paragraphs."""
    slug, stem = slug_and_stem(path)
    label = Path(path).as_posix()
    if slug not in refs and f"{slug}/{stem}" not in refs:
        print(f"NOTE {label}: no author_refs.json entry for '{slug}', checking generic forms only")
    patterns = [ref_pattern(g) for g in ref_groups(slug, stem, refs)]
    text = Path(path).read_text(encoding="utf-8-sig")
    found = flagged_paragraphs(text, patterns, not_author.get(slug, []))
    for line, found_refs in found:
        print(f"FLAG {label}:{line}: {len(found_refs)} references ({', '.join(found_refs)})")
    return len(found)


def manifest_paths():
    if not MANIFEST.exists():
        sys.exit("Work/manifest.json not found; pass files instead")
    return [ROOT / e["path"] for e in json.loads(MANIFEST.read_text(encoding="utf-8"))
            if (ROOT / e["path"]).exists()]


def main(argv):
    refs, not_author = load_config()
    paths = [Path(a) for a in argv] or manifest_paths()
    total = missing = 0
    for path in paths:
        if not path.exists():
            print(f"MISSING {path}")
            missing += 1
            continue
        total += check_file(path, refs, not_author)
    print(f"check complete: {total} flagged paragraph(s)" + (f", {missing} missing file(s)" if missing else ""))
    return 1 if total or missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
