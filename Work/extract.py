import os
import re
import pymupdf
from spellchecker import SpellChecker

from common import ends_sentence, is_heading, yaml_value
from count_words import words_in_text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = os.path.join(ROOT, "Sources")
OUT = os.path.join(ROOT, "Work", "Chapters")
RAW = os.path.join(ROOT, "Work", "Raw")

sp = SpellChecker()

STAMP_PATTERNS = []
JUNK_LINES = set()
DATE = re.compile(r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}$")
BARE_NUM = re.compile(r"^\d{1,4}$")
OVERLAP_THRESHOLD = 1.6
# Bare numbers and date stamps are page furniture only when they are the first
# or last block on the page and sit within this fraction of the page height
# from the top or bottom edge. Elsewhere they are content (table cells, years).
PAGE_NUM_ZONE = 0.12
# A chapter heading is looked for only in the first few blocks of its first page.
MAX_HEADING_BLOCKS = 4
WORD = re.compile(r"[A-Za-z][A-Za-z\u2019'-]*[A-Za-z]")
# A document "hyphenates" (breaks words at line ends) when at least this many
# line-end hyphens, and this share of those the document itself settles, are
# line-break hyphens. Otherwise every line-end hyphen is kept as real text.
# Set "hyphenates": True or False in a source's config to override detection.
HYPHENATION_MIN_BREAKS = 3
HYPHENATION_MIN_SHARE = 0.5
# A block starting with a list or note marker never continues the previous page.
LIST_MARKER = re.compile(r"^(\(?(\d{1,3}|[A-Za-z]|[ivxlcdm]{1,5})[.)]|[\u2022\u25aa\u25e6\u25cf\u25a0*]|\d{1,3}(?= +[A-Z\u201c\u2018\"']))\s")

SOURCES_CONFIG = [
    {
        "slug": "",
        "pdf": "",
        "title": "",
        "part": 1,
        "header_ymax": 0,
        "footer_ymin": 10000,
        # Optional "hyphenates": True/False overrides line-end hyphenation detection.
        "chapters": [
            # unit_id: stable and unique within this source (ch-01, appendix-a, ...).
            # slug: used in the filename. num: printed chapter label, or None if none.
            {"unit_id": "", "slug": "", "title": "", "start": 1, "end": 1, "num": None, "printed_pages": ""},
        ],
    },
]


def norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def headnorm(s):
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    s = re.sub(r"[^A-Za-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


class RepairLog:
    """Extraction decisions to check against the page image.

    Written to Work/Raw/{slug}/repairs.tsv. Kinds:
      heading-stripped, heading-not-found
      hyphen-removed, hyphen-kept         line-end hyphen before a lowercase letter
      page-join, page-join-midword        paragraph continued across a page break
      page-join-uncertain                 continued across a page break; check the page
      block-join, block-join-midword,     block continued by a lowercase block on the same page
      block-join-uncertain
      page-break-unjoined                 page ends without closing punctuation but was not joined
      furniture-dropped                   bare page number or date stamp in a margin zone
    """

    COLUMNS = ("unit_id", "pdf_page", "kind", "detail")

    def __init__(self):
        self.rows = []
        self.unit = ""

    def add(self, page, kind, detail):
        self.rows.append((self.unit, page, kind, detail))

    def kinds(self):
        return [row[2] for row in self.rows]

    def write(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\t".join(self.COLUMNS) + "\n")
            for row in self.rows:
                f.write("\t".join(re.sub(r"[\t\n]", " ", str(v)) for v in row) + "\n")


def _log(log, page, kind, detail):
    if log is not None:
        log.add(page, kind, detail)


def heading_forms(title, num=None):
    """Normalized strings that count as a complete chapter heading."""
    t = headnorm(title or "")
    n = headnorm(str(num)) if num not in (None, "") else ""
    forms = set()
    if n:
        forms |= {n, "chapter " + n}
    if t:
        forms.add(t)
    if n and t:
        forms |= {n + " " + t, "chapter " + n + " " + t}
    return forms


def strip_chapter_heading(paras, title, num=None, log=None, page=None):
    """Remove the chapter heading from the first blocks of a chapter's first page.

    Strips leading blocks that, alone or together, spell the chapter number or
    title (a title can be broken over several blocks). Stops at the first block
    that does not, so body text is never removed.
    """
    forms = heading_forms(title, num)
    if not forms:
        return list(paras)
    done, acc = 0, ""
    for i, para in enumerate(paras[:MAX_HEADING_BLOCKS]):
        pn = headnorm(para)
        if not pn:
            break
        # A note number can be set right after the heading text: "Title1".
        cands = [(acc + " " + x).strip() for x in {pn, re.sub(r"(?<=[a-z])\d{1,3}$", "", pn)}]
        if any(c in forms for c in cands):
            done, acc = i + 1, ""
        elif any(f.startswith(c + " ") for c in cands for f in forms):
            acc = next(c for c in cands if any(f.startswith(c + " ") for f in forms))
        else:
            break
    for para in paras[:done]:
        _log(log, page, "heading-stripped", para)
    if not done:
        _log(log, page, "heading-not-found", "first block: %s" % (paras[0][:80] if paras else ""))
    return list(paras[done:])


def is_known(word):
    for part in re.split(r"[-\u2019']", word):
        p = re.sub(r"[^A-Za-z]", "", part)
        if not p:
            continue
        if not sp.known([p.lower()]):
            return False
    return True


def ov(a, b):
    return min(a[2], b[2]) - max(a[0], b[0])


def line_text(chars):
    out = []
    n = len(chars)
    for i, c in enumerate(chars):
        ch = c["c"]
        if ch == " ":
            artifact = False
            for j in range(n):
                if j == i or chars[j]["c"] == " ":
                    continue
                if ov(c["bbox"], chars[j]["bbox"]) > OVERLAP_THRESHOLD:
                    artifact = True
                    break
            if artifact:
                continue
        out.append(ch)
    return "".join(out)


def is_url(token):
    return "://" in token or token.startswith("www.") or "/" in token


class DocEvidence:
    """What the source document itself shows about spelling and hyphenation.

    forms: lowercased word forms that appear whole inside a line. A line-end
    break leaves only fragments, so these show how the source spells a word,
    e.g. "co-operate" versus "cooperate".
    hyphenates: whether the document breaks words at line ends at all. A
    reflowed ebook usually does not, so its line-end hyphens are real text.
    """

    def __init__(self, forms=(), hyphenates=True):
        self.forms = set(forms)
        self.hyphenates = hyphenates

    @classmethod
    def from_doc(cls, doc, hyphenates=None):
        lines = [ln for page in doc for ln in page.get_text("text").splitlines()]
        ev = cls(w.lower() for ln in lines for w in WORD.findall(ln))
        ev.breaks, ev.settled = 0, 0
        for a, b in zip(lines, lines[1:]):
            m = re.search(r"(\S*?)([A-Za-z]+)-\s*$", a)
            n = re.match(r"\s*([a-z]+)", b)
            if not (m and n) or is_url(m.group(1)):
                continue
            joined = (m.group(2) + n.group(1)).lower() in ev.forms
            hyphened = (m.group(2) + "-" + n.group(1)).lower() in ev.forms
            if joined != hyphened:
                ev.settled += 1
                ev.breaks += joined
        if hyphenates is None:
            hyphenates = ev.breaks >= HYPHENATION_MIN_BREAKS and ev.breaks >= HYPHENATION_MIN_SHARE * ev.settled
        ev.hyphenates = hyphenates
        return ev


NO_EVIDENCE = DocEvidence()


def hyphen_decision(stem, first, ev):
    """Return (keep_hyphen, basis) for a word broken as stem- / first."""
    if not ev.hyphenates:
        return True, "document does not break words at line ends"
    joined, hyphened = (stem + first).lower(), (stem + "-" + first).lower()
    in_joined, in_hyphened = joined in ev.forms, hyphened in ev.forms
    if in_hyphened and not in_joined:
        return True, "document"
    if in_joined and not in_hyphened:
        return False, "document"
    if in_joined and in_hyphened:
        return True, "uncertain: document has both forms"
    if is_known(joined):
        if is_known(stem) and is_known(first):
            return False, "uncertain: dictionary, but both parts are words"
        return False, "dictionary"
    return True, "unverified"


def join_hyphenated(left, right, ev=NO_EVIDENCE, log=None, page=None):
    """Join text ending in a letter and hyphen to its continuation, with no space.

    Before a capital or digit, or after a digit, the hyphen belongs to the
    word (Anglo-Saxon, pre-1990, 55-member) and is kept, as it is inside a URL. Before a lowercase letter it
    may be a line-break hyphen; the decision and its basis are logged.
    """
    m = re.match(r"[a-z]+", right)
    token = left.rsplit(None, 1)[-1]
    stem = re.search(r"([A-Za-z]*)-$", left).group(1)
    if not m or not stem or is_url(token):
        return left + right
    first = m.group(0)
    keep, basis = hyphen_decision(stem, first, ev)
    word = stem + ("-" if keep else "") + first
    _log(log, page, "hyphen-kept" if keep else "hyphen-removed", "%s- / %s -> %s (%s)" % (stem, first, word, basis))
    return left + right if keep else left[:-1] + right


def join_lines(lines, ev=NO_EVIDENCE, log=None, page=None):
    text = ""
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if not text:
            text = ln
        elif re.search(r"[A-Za-z0-9]-$", text):
            text = join_hyphenated(text, ln, ev, log, page)
        else:
            text = text + " " + ln
    return re.sub(r"\s+", " ", text).strip()


def in_margin_zone(bbox, page):
    r = page.rect
    zone = r.height * PAGE_NUM_ZONE
    return bbox[3] <= r.y0 + zone or bbox[1] >= r.y1 - zone


def block_paragraphs(page, header_ymax, footer_ymin, ev=NO_EVIDENCE, log=None):
    page_no = page.number + 1
    blocks = []
    for b in page.get_text("rawdict")["blocks"]:
        if b.get("type", 0) != 0:
            continue
        y0, y1 = b["bbox"][1], b["bbox"][3]
        if header_ymax and y1 <= header_ymax:
            continue
        if footer_ymin and y0 >= footer_ymin:
            continue
        lines = []
        for l in b.get("lines", []):
            chars = [c for s in l["spans"] for c in s["chars"]]
            lines.append(line_text(chars))
        text = join_lines(lines, ev, log, page_no)
        if text:
            blocks.append((text, b["bbox"]))
    paras = []
    for i, (text, bbox) in enumerate(blocks):
        if norm(text) in JUNK_LINES or any(p.match(text) for p in STAMP_PATTERNS):
            continue
        edge = i == 0 or i == len(blocks) - 1
        if (BARE_NUM.match(text) or DATE.match(text)) and edge and in_margin_zone(bbox, page):
            _log(log, page_no, "furniture-dropped", text)
            continue
        paras.append(text)
    return paras


def last_alpha(text):
    m = re.search(r"([A-Za-z]+)[^A-Za-z]*$", text)
    return m.group(1) if m else ""


def first_alpha(text):
    m = re.match(r"[^A-Za-z]*([A-Za-z]+)", text)
    return m.group(1) if m else ""


def is_open_ended(block):
    """True if block stops without closing punctuation, so it may continue."""
    t = block.rstrip()
    return bool(t) and not ends_sentence(t) and t[-1] not in ":—-–"


def continues_across(a, b):
    """True if block a, ending one page, may run on into block b on the next.

    A short page-end fragment looks like a heading, so the heading test is
    applied only when b starts with a capital. A heading is never followed by
    a lowercase continuation or ends in a hyphen. A block that starts with a
    list or note marker is a new item.
    """
    if LIST_MARKER.match(b):
        return False
    if re.search(r"[A-Za-z0-9]-$", a):
        return True
    if not is_open_ended(a):
        return False
    if b[:1].islower():
        return True
    return not is_heading(a) and not is_heading(b)


def continues_within(a, b):
    """True if block a runs on into the next block b on the same page.

    Only a lowercase start counts: a new paragraph or heading never starts in
    lowercase, while "...as follows" / "First, ..." stays two paragraphs.
    """
    if LIST_MARKER.match(b) or not b[:1].islower():
        return False
    return bool(re.search(r"[A-Za-z0-9]-$", a)) or is_open_ended(a)


def join_across(a, b, ev, log, where, kind="page-join"):
    if re.search(r"[A-Za-z0-9]-$", a):
        return join_hyphenated(a, b, ev, log, where)
    lw, fw = last_alpha(a), first_alpha(b)
    seam = "...%s | %s..." % (a[-30:], b[:30])
    lower = b[:1].islower()
    lw_known = is_known(lw)
    joined_known = bool(fw) and ((lw + fw).lower() in ev.forms or is_known(lw + fw))
    if lower and not lw_known and joined_known:
        _log(log, where, kind + "-midword", "%s -> %s" % (seam, lw + fw))
        return a + b
    # A word break needs a known last word and a lowercase continuation;
    # anything else (a possible new paragraph, an unknown word) needs a look.
    certain = lower and lw_known and not joined_known
    _log(log, where, kind if certain else kind + "-uncertain", seam)
    return a + " " + b


def join_pages(pages, ev=NO_EVIDENCE, log=None):
    """Flatten [(pdf_page, paragraphs)] into one paragraph list.

    The last block of a page merges with the first block of the next page when
    the first does not end a sentence. On the same page, a block merges with
    the previous one only when it starts in lowercase. Each join is logged
    with its page numbers.
    """
    out = []
    prev_page = None
    for page_no, paras in pages:
        for i, b in enumerate(paras):
            if i == 0 and out and continues_across(out[-1], b):
                out[-1] = join_across(out[-1], b, ev, log, "%s-%s" % (prev_page, page_no))
                continue
            if i > 0 and continues_within(out[-1], b):
                out[-1] = join_across(out[-1], b, ev, log, page_no, "block-join")
                continue
            if i == 0 and out and is_open_ended(out[-1]):
                _log(log, "%s-%s" % (prev_page, page_no), "page-break-unjoined",
                     "...%s | %s..." % (out[-1][-30:], b[:30]))
            out.append(b)
        if paras:
            prev_page = page_no
    return out


def make_extractor(cfg, log=None):
    path = os.path.join(SOURCES, cfg["pdf"])
    with pymupdf.open(path) as doc:
        ev = DocEvidence.from_doc(doc, cfg.get("hyphenates"))
    print("%s: %d of %d settled line-end hyphens are word breaks; hyphenates=%s"
          % (cfg["pdf"], ev.breaks, ev.settled, ev.hyphenates))

    def extractor(ch):
        if log is not None:
            log.unit = ch["unit_id"]
        pages = []
        with pymupdf.open(path) as doc:
            for p in range(ch["start"] - 1, ch["end"]):
                paras = block_paragraphs(doc[p], cfg["header_ymax"], cfg["footer_ymin"], ev, log)
                pages.append((p + 1, paras))
        first = next((i for i, (_, paras) in enumerate(pages) if paras), None)
        if first is not None:
            no, paras = pages[first]
            pages[first] = (no, strip_chapter_heading(paras, ch["title"], ch.get("num"), log, no))
        return join_pages(pages, ev, log)

    return extractor


def validate_config(cfg):
    errors = []
    src = cfg.get("slug") or cfg.get("pdf")
    if not cfg.get("slug"):
        errors.append("source %r has no slug" % cfg.get("pdf"))
    seen = set()
    for ch in cfg["chapters"]:
        uid = ch.get("unit_id")
        if not uid:
            errors.append("%s: chapter %r has no unit_id" % (src, ch.get("title")))
        elif uid in seen:
            errors.append("%s: duplicate unit_id %r" % (src, uid))
        seen.add(uid)
        if not ch.get("slug"):
            errors.append("%s: chapter %r has no filename slug" % (src, uid))
        if ch["end"] < ch["start"]:
            errors.append("%s: chapter %r ends before it starts" % (src, uid))
    return errors


def build_markdown(src_title, part, chapters, extractor, slug, pdf=""):
    folder = os.path.join(OUT, slug)
    os.makedirs(folder, exist_ok=True)
    total_out = 0
    for idx, ch in enumerate(chapters, 1):
        paras = extractor(ch)
        body = "\n\n".join(paras) + "\n"
        wc = words_in_text(body)
        total_out += wc
        pages = "%d-%d" % (ch["start"], ch["end"])
        fname = "%02d-%s.md" % (idx, ch["slug"])
        label = ch.get("num")
        fields = [
            ("source", src_title or pdf),
            ("source_slug", slug),
            ("unit_id", ch["unit_id"]),
            ("part", part),
            ("chapter", None if label is None else str(label)),
            ("title", ch["title"]),
            ("pdf_pages", pages),
            ("printed_pages", ch.get("printed_pages", "")),
            ("word_count", wc),
        ]
        front = "---\n" + "".join("%s: %s\n" % (k, yaml_value(v)) for k, v in fields) + "---\n\n"
        front += "# %s\n\n" % ch["title"]
        # newline="\n" keeps byte sizes identical on Windows and elsewhere.
        with open(os.path.join(folder, fname), "w", encoding="utf-8", newline="\n") as f:
            f.write(front + body)
        print("%-4s %-6d %s" % (part, wc, fname))
    print("TOTAL part %d: %d words" % (part, total_out))


if __name__ == "__main__":
    ran = False
    for cfg in SOURCES_CONFIG:
        if not cfg["pdf"] or not cfg["chapters"]:
            continue
        problems = validate_config(cfg)
        if problems:
            raise SystemExit("SOURCES_CONFIG errors:\n  " + "\n  ".join(problems))
        ran = True
        log = RepairLog()
        build_markdown(cfg["title"], cfg["part"], cfg["chapters"], make_extractor(cfg, log), cfg["slug"], cfg["pdf"])
        log_path = os.path.join(RAW, cfg["slug"], "repairs.tsv")
        log.write(log_path)
        print("repair log: %d entries -> %s" % (len(log.rows), log_path))
    if not ran:
        print("no sources configured in SOURCES_CONFIG")
