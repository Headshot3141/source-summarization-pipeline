"""Collect the open items for a pass into one item file per chapter.

A targeted pass works from items that earlier passes left behind: the new
reports in a previous pass's records, the findings of a report-only round
(the verifiers, the whole-document reviewers), or the minor findings and
coverage notes a remediation left unapplied. This script gathers them, so
each agent gets exactly its chapter's open items and no agent is dispatched
with none. In one run the round-2 fix prompts were filled for every chapter
with a fix record, and 10 of the 35 agents had no open item to work on.

Three sources, one per call:

  --new-reports <prev-pass>
      The "NR-n" bullets under "## New reports" in each record
      Work/Reviews/*/<prev-pass>/*.md, minus the IDs the coordinator listed
      on a "Settled:" line (normally under "## Coordinator gate") and minus
      "None". A bullet without an NR number is an error: number it in the
      record first, so the next pass can cite it.
  --findings <glob-or-file>
      Every finding block in the given record files: a "###" or "####"
      heading whose ID is letters-n (W-3, M-1, m-2), N.k (4.2), or a capital
      letter and a number (I.3), up to the next heading. A block is assigned
      to a chapter by its "Chapter:" line (bold and "- " allowed), else by
      any Work/Summaries/... path in the block, else (a bare "NN-name.md")
      by the matching file of the record's chunk in --chunks (default
      Work/whole_doc_chunks.txt), else by the record's own path
      (Work/Reviews/<slug>/<pass>/<file>.md). In validation-findings.md
      (Work/build_validation_report.py), I.k findings (the Introduction)
      always go to the coordinator, and D.k (disputed) and U.k (unverified)
      do unless they name a chapter summary.
  --sections "Minor findings not applied;Coverage notes" --from <pass>
      The "###" blocks under those "##" sections of each record
      Work/Reviews/*/<pass>/*.md, assigned the same way.

Blocks are copied verbatim, each with a <!-- from: <record> --> comment. An
NR bullet gets a "### NR-n (new report)" heading above it. Where two records
of one chapter (the parts of a split chapter) use the same ID, the later one
is renamed with a P<k>- prefix (part k) or R<i>- (the chapter's i-th
record), and the comment keeps the original ID. A block that names no
summary at all (a remark on the document as a whole, or on a file such as
Work/Introduction.md that is the coordinator's) goes to items/_coordinator.md.
A block that names a summary this script cannot find is UNMATCHED: it is
printed, nothing is written, and the exit status is 1; add a "Chapter:" line
to the block, or drop its category with --skip-category.

--skip-category REGEX drops blocks whose category (the parenthesis in the
heading, such as "(minor, typography)" or "(unexplained term)", or the "##"
section around the block) matches REGEX, ignoring case: the categories the
user excluded from the pass.

Record files are read in natural order (chunk2 before chunk10; LS sorted
them as text and put chunk10 first).

Writes Work/Prompts/<out>/items/<slug>--<stem>.md, one per chapter with items,
and items/index.txt:

    slug|unit|summary|count|ids

then give make_prompts.py --items Work/Prompts/<out>/items to fill one
prompt per chapter with items. --dry-run prints and writes nothing. An items
folder that already holds item files is kept unless --force, which replaces
them (an item file is part of the pass's record).

Usage:
    python Work/collect_items.py <out> --new-reports <prev-pass> [options]
    python Work/collect_items.py <out> --findings <glob-or-file> [--chunks FILE] [options]
    python Work/collect_items.py <out> --sections "A;B" --from <pass> [options]
options: [--skip-category REGEX] [--dry-run] [--force]
"""
import argparse
import glob
import json
import re
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath

from common import ROOT, utf8_output

PROMPTS = ROOT / "Work" / "Prompts"
REVIEWS = ROOT / "Work" / "Reviews"
PARTS_MANIFEST = ROOT / "Work" / "parts_manifest.json"
MANIFEST = ROOT / "Work" / "manifest.json"
CHUNKS = ROOT / "Work" / "whole_doc_chunks.txt"

INDEX_FIELDS = ("slug", "unit", "summary", "count", "ids")
COORDINATOR_FILE = "_coordinator.md"
PART_SUFFIX = re.compile(r"-part(\d+)-of-\d+$")
# An item ID, with an optional sub-point letter: letters, a hyphen, and a
# number (NR-3, W-12, M-1, m-2, FX-S-03-1a); chapter.finding (4.2, in
# validation-findings.md); or a capital letter and a number (I.3, D.1, U.2).
ITEM_ID = r"(?:[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*-\d+|\d+\.\d+|[A-Z]\.\d+)[a-z]?"
FINDING_HEAD = re.compile(r"^#{3,4}\s+\**\s*(%s)(?![\w.-])" % ITEM_ID)
# validation-findings.md: I.k findings are on the Introduction, the
# coordinator's text; D.k (disputed) and U.k (unverified) are the
# coordinator's unless they name a chapter summary.
COORDINATOR_ID = re.compile(r"^I\.\d+")
COORDINATOR_UNLESS_NAMED = re.compile(r"^[DU]\.\d+")
NR_BULLET = re.compile(r"^\s*[-*+]\s+\**\s*(NR-\d+[a-z]?)\b")
NONE_LINE = re.compile(r"^\W*(none|no new reports?|nothing)\b", re.I)
SUMMARY_PATH = re.compile(r"Work/Summaries/[^\s`'\"“”)\]|;,*]+?\.md")
BARE_NAME = re.compile(r"(?<![/\w.-])(\d{2,3}-[\w-]+\.md)\b")
OTHER_PATH = re.compile(r"Work/[^\s`'\"“”)\]|;,*]+?\.md")
SETTLED = re.compile(r"^\W*settled\W*:(.*)$", re.I | re.M)


def natural_key(text):
    """Sort key that orders the numbers inside a string by value (chunk2 < chunk10)."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(text))]


def read_chunks(path=None):
    """{chunk number: [path, ...]} from a whole_doc_chunks.txt-style file."""
    path = Path(path) if path else CHUNKS
    if not path.is_absolute():
        path = ROOT / path
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*CHUNK\s+(\d+)\s*:\s*(.*)$", line)
        if m:
            out[int(m.group(1))] = [p.strip() for p in m.group(2).split(";") if p.strip()]
    return out


def chapters():
    """[(summary path, slug, unit_id)] in manifest order."""
    if PARTS_MANIFEST.exists():
        entries = json.loads(PARTS_MANIFEST.read_text(encoding="utf-8"))
        return [(e["summary"], e["source_slug"], e["unit_id"]) for e in entries]
    if MANIFEST.exists():
        entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
        return [(e["path"], e["source_slug"], e["unit_id"]) for e in entries]
    sys.exit("Work/parts_manifest.json not found; run Work/split_parts.py first")


def item_file_name(summary):
    """Item file name for a chapter summary: <slug>--<stem>.md."""
    p = PurePosixPath(summary)
    return "%s--%s.md" % (p.parent.name, p.stem)


def item_ids(text):
    """The item IDs an item file lists, in order (the ### heading of each block)."""
    return [m.group(1) for m in (FINDING_HEAD.match(line) for line in text.splitlines()) if m]


def section_bodies(text, names):
    """[(section heading, body)] for each ## section whose heading starts with one of names."""
    out = []
    parts = re.split(r"(?m)^(?=##\s)", text)
    for part in parts:
        m = re.match(r"##\s+\**\s*(.+?)\s*\**\s*$", part.split("\n", 1)[0])
        if not m or part.startswith("###"):
            continue
        heading = m.group(1)
        if any(heading.lower().startswith(n.lower()) for n in names):
            out.append((heading, part.split("\n", 1)[1] if "\n" in part else ""))
    return out


def finding_blocks(text):
    """[(section, heading line, block text)] for each ### finding block in a record.

    A block runs from its ### heading to the next heading of any level.
    """
    out, section, cur = [], "", None
    for line in text.splitlines():
        if re.match(r"#{1,6}\s", line):
            if cur:
                out.append(cur)
                cur = None
            if line.startswith("## "):
                section = line[3:].strip(" *")
            elif FINDING_HEAD.match(line):
                cur = (section, line, [line])
            continue
        if cur:
            cur[2].append(line)
    if cur:
        out.append(cur)
    return [(s, h, "\n".join(body).rstrip()) for s, h, body in out]


def new_reports(text):
    """([(id, block text)], [unnumbered report text]) under "## New reports".

    A report is an "- NR-n: ..." bullet, with any lines that continue it, or
    a "### NR-n" block (some agents write those). A line of prose before the
    first bullet that ends with ":" introduces the list; "None" is no report.
    """
    items, unnumbered = [], []
    for _, body in section_bodies(text, ["New reports"]):
        cur = None
        for line in body.split("\n"):
            heading = re.match(r"#{1,6}\s", line)
            bullet = NR_BULLET.match(line)
            if heading or bullet:
                m = FINDING_HEAD.match(line) if heading else bullet
                cur = [m.group(1), [line], bool(heading)] if m else None
                if cur:
                    items.append(cur)
            elif cur and cur[2]:
                cur[1].append(line)  # everything up to the next heading belongs to a ### block
            elif re.match(r"\s*[-*+]\s+\S", line):
                cur = None
                if not NONE_LINE.match(line.lstrip(" \t-*+")):
                    cur = [None, [line], False]
                    unnumbered.append(cur)
            elif not line.strip():
                continue
            elif cur:
                cur[1].append(line)
            elif not NONE_LINE.match(line) and not line.rstrip().endswith(":"):
                cur = [None, [line], False]
                unnumbered.append(cur)
    return ([(i, "\n".join(lines).rstrip()) for i, lines, _ in items],
            ["\n".join(lines).strip() for _, lines, _ in unnumbered])


def settled_ids(text):
    """IDs on the record's Settled: lines."""
    ids = set()
    for m in SETTLED.finditer(text):
        ids.update(re.findall(ITEM_ID, m.group(1)))
    return ids


def category(section, heading):
    """The text a --skip-category pattern is matched against."""
    paren = re.search(r"\(([^)]*)\)", heading)
    return "%s | %s" % (paren.group(1) if paren else "", section)


class Resolver:
    """Assigns a block to chapter summaries."""

    def __init__(self, chunks):
        self.chapters = chapters()
        self.known = {s for s, _, _ in self.chapters}
        self.by_name = defaultdict(list)
        for s, _, _ in self.chapters:
            self.by_name[PurePosixPath(s).name].append(s)
        self.chunks = chunks

    def chapter_of(self, path):
        """The manifest chapter summary a summary path stands for, or None."""
        p = PurePosixPath(path)
        if p.parent.name == "parts":
            # A part summary stands for its chapter once merged.
            p = p.parent.parent / (PART_SUFFIX.sub("", p.stem) + ".md")
        p = p.as_posix()
        return p if p in self.known else None

    def bare(self, name, record):
        """Chapter summaries a bare NN-name.md can mean for this record."""
        m = re.search(r"chunk(\d+)", PurePosixPath(record).stem)
        if m and int(m.group(1)) in self.chunks:
            return [s for s in self.chunks[int(m.group(1))] if PurePosixPath(s).name == name and s in self.known]
        found = self.by_name.get(name, [])
        return found if len(found) == 1 else []

    def from_record(self, record):
        """The chapter a per-unit record belongs to (Work/Reviews/<slug>/<pass>/<file>.md)."""
        parts = PurePosixPath(record).parts
        if len(parts) >= 5 and parts[:2] == ("Work", "Reviews"):
            stem = PART_SUFFIX.sub("", PurePosixPath(record).stem)
            return self.chapter_of("Work/Summaries/%s/%s.md" % (parts[2], stem))
        return None

    def resolve(self, block, record):
        """(summaries, unmatched names). Both empty: the block names no summary."""
        chapter = re.search(r"(?im)^\W*chapter\W*:(.*)$", block)
        text = chapter.group(1) if chapter else block
        named, found, unmatched = False, set(), []
        for path in SUMMARY_PATH.findall(text):
            named = True
            c = self.chapter_of(path)
            if c:
                found.add(c)
            else:
                unmatched.append(path)
        for name in BARE_NAME.findall(SUMMARY_PATH.sub(" ", text)):
            named = True
            hits = self.bare(name, record)
            if hits:
                found.update(hits)
            else:
                unmatched.append(name)
        if named:
            return sorted(found, key=self.order), unmatched
        if chapter:
            # A Chapter: line naming another existing file (the Introduction)
            # is the coordinator's; one naming nothing usable is unmatched.
            other = OTHER_PATH.findall(text)
            if other and all((ROOT / o).exists() for o in other):
                return [], []
            return [], [text.strip() or "(empty Chapter: line)"]
        own = self.from_record(record)
        return ([own] if own else []), []

    def order(self, summary):
        return [s for s, _, _ in self.chapters].index(summary)


def rel_posix(path):
    try:
        return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def record_files(pattern):
    """Record files for a glob, file, or folder, in natural order."""
    p = Path(pattern)
    base = p if p.is_absolute() else ROOT / p
    if base.is_dir():
        files = list(base.glob("*.md"))
    elif base.is_file():
        files = [base]
    else:
        files = [Path(f) for f in glob.glob(str(base))]
    return sorted((f for f in files if f.is_file()), key=lambda f: natural_key(rel_posix(f)))


def pass_records(pass_name):
    """Every record of a pass, Work/Reviews/*/<pass>/*.md, in natural order."""
    return sorted(REVIEWS.glob("*/%s/*.md" % pass_name), key=lambda f: natural_key(rel_posix(f)))


def collect(args):
    """({summary: [(record, id, block)]}, [coordinator blocks], [problems], records read)."""
    chunks = read_chunks(args.chunks)
    resolver = Resolver(chunks)
    skip = re.compile(args.skip_category, re.I) if args.skip_category else None
    per, coord, problems = defaultdict(list), [], []

    if args.new_reports:
        files = pass_records(args.new_reports)
    elif args.findings:
        files = record_files(args.findings)
    else:
        files = pass_records(args.source_pass)
    if not files:
        problems.append("no record files found")

    for f in files:
        record = rel_posix(f)
        text = f.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        if args.new_reports:
            settled = settled_ids(text)
            found, unnumbered = new_reports(text)
            for bullet in unnumbered:
                problems.append("UNNUMBERED new report in %s (number it NR-n in the record): %s"
                                % (record, " ".join(bullet.split())[:200]))
            blocks = [("New reports", i, b) for i, b in found if i not in settled]
        elif args.findings:
            blocks = [(s, FINDING_HEAD.match(h).group(1), b) for s, h, b in finding_blocks(text)]
        else:
            names = [n.strip() for n in args.sections.split(";") if n.strip()]
            blocks = []
            for heading, body in section_bodies(text, names):
                blocks += [(heading, FINDING_HEAD.match(h).group(1), b)
                           for _, h, b in finding_blocks("## %s\n%s" % (heading, body))]
        for section, item_id, block in blocks:
            heading = block.split("\n", 1)[0]
            if skip and skip.search(category(section, heading if heading.startswith("#") else "")):
                continue
            # A new report belongs to the chapter its record covers.
            own = resolver.from_record(record) if args.new_reports else None
            targets, unmatched = ([own], []) if own else resolver.resolve(block, record)
            if COORDINATOR_ID.match(item_id):
                targets, unmatched = [], []
            elif COORDINATOR_UNLESS_NAMED.match(item_id) and not targets:
                unmatched = []
            if unmatched:
                problems.append("UNMATCHED %s %s (names %s): %s" % (
                    record, item_id, ", ".join(unmatched), " ".join(block.split())[:200]))
                continue
            if not targets:
                coord.append((record, item_id, block))
            for t in targets:
                per[t].append((record, item_id, block))
    return per, coord, problems, files


def renamed(entries):
    """Give each block a unique ID within its chapter; [(new id, record, old id, block)]."""
    seen, records, out = set(), [], []
    for record, item_id, block in entries:
        if record not in records:
            records.append(record)
        new = item_id
        if item_id in seen:
            m = PART_SUFFIX.search(PurePosixPath(record).stem)
            new = "%s-%s" % ("P%s" % m.group(1) if m else "R%d" % (records.index(record) + 1), item_id)
        seen.add(new)
        out.append((new, record, item_id, block))
    return out


def render(new_id, record, old_id, block):
    """One item block: its heading, the provenance comment, the verbatim text."""
    origin = "<!-- from: %s%s -->" % (record, "; ID there: %s" % old_id if new_id != old_id else "")
    if block.startswith("###"):
        head, _, rest = block.partition("\n")
        if new_id != old_id:
            head = head.replace(old_id, new_id, 1)
        return "%s\n%s\n%s" % (head, origin, rest.strip("\n"))
    return "### %s (new report)\n%s\n%s" % (new_id, origin, block)


def main(argv=None):
    utf8_output()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", help="the pass's prompt folder name under Work/Prompts/")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--new-reports", metavar="PREV_PASS")
    src.add_argument("--findings", metavar="GLOB_OR_FILE")
    src.add_argument("--sections", metavar='"A;B"')
    ap.add_argument("--from", dest="source_pass", metavar="PASS")
    ap.add_argument("--chunks", metavar="FILE")
    ap.add_argument("--skip-category", metavar="REGEX")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    if args.sections and not args.source_pass:
        ap.error("--sections needs --from <pass>")

    out_dir = PROMPTS / args.out / "items"
    existing = sorted(out_dir.glob("*.md")) if out_dir.exists() else []
    if existing and not args.force and not args.dry_run:
        sys.exit("%s already holds %d item file(s); item files are part of the pass's record. "
                 "Use a new <out>, or --force to replace them." % (rel_posix(out_dir), len(existing)))

    per, coord, problems, files = collect(args)
    order = {s: i for i, (s, _, _) in enumerate(chapters())}
    units = {s: (slug, unit) for s, slug, unit in chapters()}
    rows, writes = [], {}
    for summary in sorted(per, key=lambda s: order[s]):
        items = renamed(per[summary])
        slug, unit = units[summary]
        rows.append("|".join([slug, unit, summary, str(len(items)), ",".join(i[0] for i in items)]))
        writes[item_file_name(summary)] = ("# Items for %s\n\n" % summary
                                           + "\n\n".join(render(*i) for i in items) + "\n")
        print("%3d  %s  %s" % (len(items), summary, ", ".join(i[0] for i in items)))
    if coord:
        writes[COORDINATOR_FILE] = ("# Items for the coordinator (they name no chapter summary)\n\n"
                                    + "\n\n".join(render(i, r, i, b) for r, i, b in coord) + "\n")
        print("%3d  items/%s" % (len(coord), COORDINATOR_FILE))
    total = sum(len(v) for v in per.values())
    print("%d record file(s) read; %d item(s) for %d chapter(s); %d for the coordinator"
          % (len(files), total, len(per), len(coord)))
    for p in problems:
        print(p)
    if problems:
        print("nothing written: settle the lines above first")
        return 1
    if args.dry_run:
        return 0
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in existing:
        if old.name not in writes:
            old.unlink()
    for name, text in writes.items():
        (out_dir / name).write_text(text, encoding="utf-8", newline="\n")
    (out_dir / "index.txt").write_text("|".join(INDEX_FIELDS) + "\n" + "".join(r + "\n" for r in rows),
                                       encoding="utf-8", newline="\n")
    print("wrote %s" % rel_posix(out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
