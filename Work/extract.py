import os
import re
import pymupdf
from spellchecker import SpellChecker

from common import ends_sentence, is_heading, yaml_value
from count_words import words_in_text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = os.path.join(ROOT, "Sources")
OUT = os.path.join(ROOT, "Work", "Chapters")

sp = SpellChecker()
FREQ = sp.word_frequency.dictionary

STAMP_PATTERNS = []
JUNK_LINES = set()
DATE = re.compile(r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}$")
BARE_NUM = re.compile(r"^\d{1,4}$")
OVERLAP_THRESHOLD = 1.6

SOURCES_CONFIG = [
    {
        "slug": "",
        "pdf": "",
        "title": "",
        "part": 1,
        "header_ymax": 0,
        "footer_ymin": 10000,
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


def strip_chapter_heading(paras, title, num=None):
    title_norm = headnorm(title)
    out = []
    for i, para in enumerate(paras):
        if i < 4:
            pn = headnorm(para)
            head = re.sub(r"^\d+\s*", "", pn)
            if not head:
                continue
            if (num and pn == str(num)) or head == title_norm or (head and head in title_norm) or title_norm in head:
                continue
        out.append(para)
    return out


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


def join_lines(lines):
    text = ""
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if not text:
            text = ln
            continue
        if re.search(r"[A-Za-z]-$", text) and ln[:1].islower():
            left = text[:-1]
            m = re.match(r"[A-Za-z\u2019']+", ln)
            first = m.group(0) if m else ""
            cand = re.sub(r"[^A-Za-z]", "", left.split()[-1] + first) if first else ""
            if cand and is_known(cand):
                text = left + ln
            else:
                text = text + ln
        else:
            text = text + " " + ln
    return re.sub(r"\s+", " ", text).strip()


def block_paragraphs(page, header_ymax, footer_ymin):
    paras = []
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
        text = join_lines(lines)
        if not text:
            continue
        low = norm(text)
        if low in JUNK_LINES or any(p.match(text) for p in STAMP_PATTERNS) or DATE.match(text):
            continue
        if BARE_NUM.match(text):
            continue
        paras.append(text)
    return paras


def last_alpha(text):
    m = re.search(r"([A-Za-z]+)[^A-Za-z]*$", text)
    return m.group(1) if m else ""


def first_alpha(text):
    m = re.match(r"[^A-Za-z]*([A-Za-z]+)", text)
    return m.group(1) if m else ""


def is_continuable(block):
    t = block.rstrip()
    return bool(t) and not ends_sentence(t) and t[-1] not in ":—-–" and not is_heading(t)


def join_fragments(blocks):
    """Merge page-break continuation fragments into their parent paragraph.

    Runs during extraction so the chapter file is validated in its final
    form. Splitting never changes the text afterwards.
    """
    out = []
    for b in blocks:
        if out and is_continuable(out[-1]) and not is_heading(b):
            a = out[-1]
            lw, fw = last_alpha(a), first_alpha(b)
            if lw.lower() in FREQ:
                out[-1] = a + " " + b
            elif fw and (lw + fw).lower() in FREQ:
                out[-1] = a + b
            elif lw.lower() not in FREQ and b[0].islower():
                out[-1] = a + b
            else:
                out[-1] = a + " " + b
        else:
            out.append(b)
    return out


def make_extractor(cfg):
    path = os.path.join(SOURCES, cfg["pdf"])

    def extractor(ch):
        paras = []
        with pymupdf.open(path) as doc:
            for p in range(ch["start"] - 1, ch["end"]):
                paras.extend(block_paragraphs(doc[p], header_ymax=cfg["header_ymax"], footer_ymin=cfg["footer_ymin"]))
        return join_fragments(strip_chapter_heading(paras, ch["title"], ch.get("num")))

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
        build_markdown(cfg["title"], cfg["part"], cfg["chapters"], make_extractor(cfg), cfg["slug"], cfg["pdf"])
    if not ran:
        print("no sources configured in SOURCES_CONFIG")
