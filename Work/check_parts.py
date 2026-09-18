"""Check the processing units in Work/parts_manifest.json.

For every chapter:
- each unit file exists and its on-disk size is at or under the hard cap;
- frontmatter keys and word counts match the manifest and the text;
- the ordered owned slices rebuild the chapter body exactly, including
  whitespace and page markers, with frontmatter, headings, and overlap
  context left out;
- every part boundary falls between sentences.

Exits with status 1 if any check fails. Run from anywhere:

    python Work/check_parts.py
"""
import json
import sys

from common import HARD_CAP, ROOT, chapter_body, ends_sentence, owned_text, parse_frontmatter
from count_words import words_in_text

MANIFEST = ROOT / "Work" / "parts_manifest.json"


def first_difference(a, b):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return min(len(a), len(b))


def check_chapter(entry, fail):
    label = f"{entry['source_slug']}/{entry['unit_id']}"
    chapter_path = ROOT / entry["chapter_source"]
    if not chapter_path.exists():
        fail(f"{label}: chapter file missing: {entry['chapter_source']}")
        return
    meta, body = chapter_body(chapter_path.read_bytes().decode("utf-8"))
    words = words_in_text(body)
    if meta.get("word_count") != words:
        fail(f"{label}: chapter frontmatter word_count {meta.get('word_count')} but body has {words}")
    if entry["words"] != words:
        fail(f"{label}: manifest words {entry['words']} but body has {words}")

    parts = entry["parts"]
    m = len(parts)
    if [p["part_index"] for p in parts] != list(range(1, m + 1)):
        fail(f"{label}: part indexes are not 1..{m} in order")
    if any(p["part_count"] != m for p in parts):
        fail(f"{label}: part_count does not match the number of parts ({m})")
    if sum(p["budget"] for p in parts) != entry["budget"]:
        fail(f"{label}: part budgets sum to {sum(p['budget'] for p in parts)}, chapter budget is {entry['budget']}")

    slices = []
    for p in parts:
        path = ROOT / p["source"]
        name = p["source"]
        if not path.exists():
            fail(f"{name}: missing")
            slices.append(None)
            continue
        data = path.read_bytes()
        if len(data) > HARD_CAP:
            fail(f"{name}: {len(data)} bytes on disk, over the {HARD_CAP}-byte cap")
        if len(data) != p["bytes"]:
            fail(f"{name}: {len(data)} bytes on disk but manifest says {p['bytes']}")
        raw = data.decode("utf-8")
        if m == 1:
            if p["source"] != entry["chapter_source"]:
                fail(f"{name}: an unsplit chapter should use its own chapter file")
            slices.append(body)
            continue
        pmeta, _ = parse_frontmatter(raw)
        expected = {
            "source_slug": entry["source_slug"], "unit_id": entry["unit_id"],
            "part_index": p["part_index"], "part_count": m,
            "word_count": p["words"], "word_budget": p["budget"],
        }
        for key, value in expected.items():
            if pmeta.get(key) != value:
                fail(f"{name}: frontmatter {key} is {pmeta.get(key)!r}, expected {value!r}")
        try:
            owned = owned_text(raw)
        except ValueError as exc:
            fail(f"{name}: {exc}")
            slices.append(None)
            continue
        if words_in_text(owned) != p["words"]:
            fail(f"{name}: owned text has {words_in_text(owned)} words, manifest says {p['words']}")
        slices.append(owned)

    if None in slices:
        return
    rebuilt = "".join(slices)
    if rebuilt != body:
        i = first_difference(rebuilt, body)
        fail(
            f"{label}: owned slices do not rebuild the chapter (first difference at character {i}; "
            f"rebuilt {len(rebuilt)} chars, chapter {len(body)})\n"
            f"    chapter: {body[max(0, i - 40):i + 40]!r}\n"
            f"    rebuilt: {rebuilt[max(0, i - 40):i + 40]!r}"
        )
    for k in range(1, len(slices)):
        before, after = slices[k - 1], slices[k]
        if not ends_sentence(before):
            fail(f"{label}: part {k} ends mid-sentence: ...{before.rstrip()[-60:]!r}")
        if after.lstrip()[:1].islower():
            fail(f"{label}: part {k + 1} starts in lowercase: {after.lstrip()[:60]!r}...")


def main():
    if not MANIFEST.exists():
        sys.exit("Work/parts_manifest.json not found; run Work/split_parts.py first")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    failures = []
    for entry in manifest:
        check_chapter(entry, failures.append)
    units = sum(len(e["parts"]) for e in manifest)
    for f in failures:
        print("FAIL " + f)
    print(f"checked {len(manifest)} chapters, {units} processing units: {len(failures)} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
