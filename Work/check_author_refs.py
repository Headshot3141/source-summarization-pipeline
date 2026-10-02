"""Flag summary paragraphs that refer to a source's author more than once.

writing-rules.md ("Naming the author") allows one reference to the author
per paragraph: the paragraph's opening attribution covers its later
sentences. In an earlier run the summaries of one book named the author
about once every 80 words, mostly at the start of sentence after sentence.

A reference is a name form listed in AUTHOR_REFS for the file's source, or a
generic form ("the author", "the authors"), counted for every source. Text
inside double quotation marks, block quotations ("> ") and headings is not
counted. Pronouns are not counted, because they cannot be tied to the
author mechanically; the rule still applies to them.

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

# Fill in during Preflight: every form the summaries use for each source's
# author, keyed by source slug. Add entries keyed "<slug>/<file stem>" for a
# unit with its own main speaker, such as an interviewee; part suffixes
# ("-part1-of-2") are ignored when matching. The longest forms match first,
# so a full name and a surname in one entry are not double-counted.
AUTHOR_REFS = {
    # "surname-title": ["Ada Penhale", "Penhale"],
    # "surname-title/03-interview": ["Marlow"],
}
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


def ref_forms(slug, stem):
    forms = list(AUTHOR_REFS.get(slug, [])) + list(AUTHOR_REFS.get(f"{slug}/{stem}", []))
    return sorted(set(forms), key=len, reverse=True)


def ref_pattern(forms):
    names = [r"\b" + re.escape(f) + r"\b" for f in forms]
    generic = [r"\b(?i:" + re.escape(g) + r")\b" for g in GENERIC]
    return re.compile("|".join(names + generic))


def paragraphs(text):
    """Yield (first line number, paragraph text) for each prose paragraph."""
    line = 1
    for block in re.split(r"(\n\s*\n)", text):
        if block.strip() and not block.lstrip().startswith(("#", ">")):
            lead = len(block) - len(block.lstrip("\n"))
            yield line + lead, block
        line += block.count("\n")


def flagged_paragraphs(text, pattern):
    """[(line, references found)] for paragraphs with more than one reference."""
    found = []
    for line, para in paragraphs(text):
        refs = pattern.findall(QUOTED.sub("", para))
        if len(refs) > 1:
            found.append((line, refs))
    return found


def check_file(path):
    """Print flags for one file; return the number of flagged paragraphs."""
    slug, stem = slug_and_stem(path)
    forms = ref_forms(slug, stem)
    label = Path(path).as_posix()
    if not forms:
        print(f"NOTE {label}: no AUTHOR_REFS entry for '{slug}', checking generic forms only")
    text = Path(path).read_text(encoding="utf-8-sig")
    found = flagged_paragraphs(text, ref_pattern(forms))
    for line, refs in found:
        print(f"FLAG {label}:{line}: {len(refs)} author references ({', '.join(refs)})")
    return len(found)


def manifest_paths():
    if not MANIFEST.exists():
        sys.exit("Work/manifest.json not found; pass files instead")
    return [ROOT / e["path"] for e in json.loads(MANIFEST.read_text(encoding="utf-8"))
            if (ROOT / e["path"]).exists()]


def main(argv):
    paths = [Path(a) for a in argv] or manifest_paths()
    total = missing = 0
    for path in paths:
        if not path.exists():
            print(f"MISSING {path}")
            missing += 1
            continue
        total += check_file(path)
    print(f"check complete: {total} flagged paragraph(s)" + (f", {missing} missing file(s)" if missing else ""))
    return 1 if total or missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
