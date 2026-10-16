"""Write the validation run's findings file from the agents' results.

Reads the run's results, checks every confirmed finding's quotes against
their files, and writes validation-findings.md at the project root (the
format is in passes/validation-run.md, "Findings file format"):

- a Result section with the totals, precision by role, rejection reasons,
  the rejection audit, the projected word change, and the quote check;
- the Mechanical checks the coordinator ran (--checks FILE, Markdown);
- a table of findings per chapter, then one section per chapter with each
  confirmed finding as "#### N.k (severity, class)": Chapter, Text,
  Evidence (p. N), Problem, Suggested fix (+N words), Verification, and,
  where the verifier found an earlier round had dealt with the passage,
  Earlier rounds;
- the Introduction's findings ("#### I.k"), for the coordinator;
- disputed findings ("#### D.k": the verifier and the second opinion
  disagree, or the rejection audit reinstated a rejected finding), for the
  coordinator or the user to decide;
- findings no verifier judged ("#### U.k");
- an appendix of rejected and duplicate findings, one line each with the
  reason.

Two routes give the results (passes/validation-run.md, "Dispatch"):
- the workflow: its return value, saved as Work/Prompts/<out>/result.json,
  or one file per workflow run (result-1.json for the pilot, result-2.json
  for the rest, result-3.json for a rerun of failed chunks): every
  result*.json in the run folder is read, in natural order, and a later
  file's chapter replaces an earlier one's. --result FILE (repeatable)
  names the files instead;
- Agent-tool batches: the agents' JSON files under Work/Prompts/<out>/
  (found/, verify/, second/), read when there is no result*.json.

The quote check normalizes whitespace, quotation marks, dashes, emphasis
marks, block-quotation markers, and page markers, and accepts a quote
elided with "..." when its pieces appear in order. A quote it cannot find
gets a "Quote check" line under its finding: search a few words of it by
hand before acting on the finding.

Also writes Work/Prompts/<out>/report_stats.json (the counts, for the
brief's Status table). Reads only; writes those two files.

Usage:
    python Work/build_validation_report.py [<out>] [--result FILE ...] [--findings FILE]
                                           [--checks FILE] [--date YYYY-MM-DD]
"""
import argparse
import datetime
import json
import re
import sys
from collections import Counter
from pathlib import Path

from common import ROOT, utf8_output
from make_validation_tasks import (DEFAULT_OUT, INTRO_FILE, ROLES, load_json, merge)

FINDINGS_FILE = "validation-findings.md"
CONFIRMED = ("confirmed-material", "confirmed-minor")


# ----------------------------------------------------------------------------
# Quote check


def norm(text):
    text = re.sub(r"<!--.*?-->", " ", text or "", flags=re.S)
    for a, b in (("\u201c", '"'), ("\u201d", '"'), ("\u2018", "'"), ("\u2019", "'"), ("\u2026", "..."),
                 ("\u2014", "-"), ("\u2013", "-"), ("\u2212", "-"), ("\u00a0", " ")):
        text = text.replace(a, b)
    text = re.sub(r"[*_`>\\]", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def found_in(quote, text):
    """True or False; None when there is nothing to check ("n/a", "none", empty)."""
    q = norm(quote).strip(" .,;:\"'")
    if not q or q in ("n/a", "na", "none"):
        return None
    t = norm(text)
    if q in t:
        return True
    pieces = [p.strip(" .,;:\"'") for p in re.split(r"\.\.\.|\[\.\.\.\]", q)]
    pieces = [p for p in pieces if p]
    if len(pieces) > 1:
        pos = 0
        for p in pieces:
            i = t.find(p, pos)
            if i < 0:
                return False
            pos = i + len(p)
        return True
    return False


WORDS_RE = re.compile(r"\(\s*([+\-\u2212\u2013]?\s*\d[\d,]*)\s+words?\s*\)", re.I)


def word_change(fix):
    """The word change a fix ends with, "(+9 words)", as an int, or None."""
    found = WORDS_RE.findall(fix or "")
    if not found:
        return None
    value = re.sub(r"[\s,]", "", found[-1]).replace("\u2212", "-").replace("\u2013", "-")
    return int(value)


# ----------------------------------------------------------------------------
# Loading results


def natural_key(text):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(text))]


def merge_results(results):
    """One result from several workflow results (a pilot, then the rest, or a
    rerun of failed chunks): a later file's chapter, chunk, or Introduction
    replaces an earlier one's."""
    chapters, readers, intro, unassigned = {}, {}, None, {}
    for data in results:
        for c in data.get("chapters") or []:
            if c:
                chapters[c["n"]] = c
        for r in data.get("readers") or []:
            if r:
                readers[r.get("k")] = r
                unassigned[r.get("k")] = []
        for f in data.get("unassigned") or []:
            unassigned.setdefault(f.get("chunk"), []).append(f)
        if data.get("intro"):
            intro = data["intro"]
    return {"readers": [readers[k] for k in sorted(readers, key=natural_key)],
            "chapters": [chapters[n] for n in sorted(chapters)],
            "intro": intro,
            "unassigned": [f for k in sorted(unassigned, key=natural_key) for f in unassigned[k]]}


def read_result(path):
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict) and "result" in data and "chapters" not in data:
        data = data["result"]
    return data


def load_result(root, out, paths=None):
    """(the normalized results {readers, chapters, intro, unassigned}, a label).

    paths: workflow result files; by default every result*.json in the run
    folder, in natural order. Without any, the Agent-tool files."""
    base = root / "Work" / "Prompts" / out
    if paths:
        files = [Path(p) if Path(p).is_absolute() else root / p for p in paths]
        missing = [str(f) for f in files if not f.exists()]
        if missing:
            sys.exit("not found: " + ", ".join(missing))
    else:
        files = sorted(base.glob("result*.json"), key=lambda f: natural_key(f.name))
    if files:
        label = ", ".join(f.relative_to(root).as_posix() if f.is_relative_to(root) else str(f) for f in files)
        return merge_results([read_result(f) for f in files]), label
    if not (base / "verify" / "finders.json").exists():
        sys.exit("no results: no %s/result*.json and no %s/verify/finders.json (on the Agent-tool route, "
                 "run make_validation_tasks.py --stage verify)" % (base, base))
    return load_dir(root, out), "%s (Agent-tool files)" % base.relative_to(root).as_posix()


def load_dir(root, out):
    base = root / "Work" / "Prompts" / out
    tasks = load_json(base / "tasks.json")
    if tasks is None:
        sys.exit("Work/Prompts/%s/tasks.json not found" % out)
    finders = load_json(base / "verify" / "finders.json", {})

    def target(name):
        inp = load_json(base / "verify" / ("%s.input.json" % name))
        items = inp["findings"] if inp else []
        merged = merge(items, load_json(base / "verify" / ("%s.json" % name)))
        seconds = {}
        for r in (load_json(base / "second" / ("%s.json" % name), {}) or {}).get("results") or []:
            if isinstance(r, dict) and r.get("id"):
                seconds[r["id"]] = r
        kinds = {it["id"]: it["kind"] for it in
                 (load_json(base / "second" / ("%s.input.json" % name), {}) or {}).get("items", [])}
        for m in merged:
            s = seconds.get(m["finding"]["id"])
            if s:
                m["second"] = dict(s, kind=s.get("kind") or kinds.get(m["finding"]["id"]))
        return merged

    chapters = []
    for c in tasks["chapters"]:
        a, b = finders.get("A-ch-%d" % c["n"]), finders.get("B-ch-%d" % c["n"])
        if a is None and b is None:
            continue
        chapters.append({"n": c["n"], "finders": {"A": a, "B": b}, "merged": target("ch-%d" % c["n"])})
    readers = []
    for k in tasks["chunks"]:
        r = finders.get("W-chunk-%d" % k["k"])
        readers.append(dict(r or {}, k=k["k"], missing=r is None))
    intro = None
    if finders.get("I") is not None or (base / "verify" / "intro.input.json").exists():
        intro = {"finders": {"I": finders.get("I")}, "merged": target("intro")}
    return {"readers": readers, "chapters": chapters, "intro": intro,
            "unassigned": load_json(base / "verify" / "unassigned.json", []) or []}


# ----------------------------------------------------------------------------
# Outcomes and rendering


def outcome(m):
    """confirmed-material | confirmed-minor | disputed | rejected | duplicate | unverified"""
    v, s = m.get("verdict"), m.get("second")
    if not v or v.get("verdict") not in ("confirmed", "rejected", "duplicate"):
        return "unverified"
    if v["verdict"] == "duplicate":
        return "duplicate"
    if v["verdict"] == "rejected":
        if s and s.get("verdict") in ("material", "minor"):
            return "disputed"
        return "rejected"
    sev = v.get("severity") or m["finding"].get("severity") or "minor"
    if sev == "material" and s:
        if s.get("verdict") == "rejected":
            return "disputed"
        if s.get("verdict") == "minor":
            return "confirmed-minor"
    return "confirmed-material" if sev == "material" else "confirmed-minor"


def is_audit(m):
    s = m.get("second")
    return bool(s) and (s.get("kind") == "audit" or (m.get("verdict") or {}).get("verdict") == "rejected")


def field(m, key, default=""):
    """A finding's value: a reinstating audit's, else the verifier's, else the finder's."""
    s, v, f = m.get("second") or {}, m.get("verdict") or {}, m["finding"]
    if is_audit(m) and s.get("verdict") in ("material", "minor") and (s.get(key) or "").strip():
        return s[key]
    if key == "fix" and not is_audit(m) and (s.get("fix") or "").strip():
        return s["fix"]
    return v.get(key) or f.get(key) or default


def severity(m):
    o = outcome(m)
    if o == "confirmed-material":
        return "material"
    if o == "disputed" and is_audit(m):
        return m["second"]["verdict"]
    if o == "disputed":
        return "material"
    if o == "unverified":
        return m["finding"].get("severity") or "minor"
    return "minor"


def one_line(text):
    return " ".join((text or "").split())


def brief(text, limit=260):
    """The first sentence or two of a reason, for the appendix."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(])", one_line(text))
    out = ""
    for p in parts:
        if out and len(out) + len(p) > limit:
            break
        out = (out + " " + p).strip()
    return out


def role_of(fid):
    """The role that reported a finding, from its id prefix (A3, B1, W2-4, I1)."""
    return ROLES.get((fid or "?")[:1], ("finder", ""))[0]


class Files:
    """Cached project text, keyed by relative path."""

    def __init__(self, root):
        self.root, self.cache = root, {}

    def __call__(self, rel):
        if rel not in self.cache:
            p = self.root / rel
            self.cache[rel] = p.read_text(encoding="utf-8-sig") if rel and p.exists() else ""
        return self.cache[rel]


def target_files(m, chapter):
    """(file the summary quote is in, file the source quote is in or None)."""
    if chapter is None:
        loc = m["finding"].get("location") or ""
        return (INTRO_FILE if re.search(r"introduction", loc, re.I) else "Summary.md"), None
    return chapter["summary"], chapter["source"]


def render(m, label, chapter, heading, files, quote_issues, verifier="the refuting verifier"):
    f, v, s = m["finding"], m.get("verdict") or {}, m.get("second") or {}
    sq, srcq = field(m, "summary_quote"), field(m, "source_quote")
    page, fix = field(m, "page", "none"), field(m, "fix")
    cls = field(m, "class", "other")
    summary_file, source_file = target_files(m, chapter)
    notes = []
    if outcome(m) != "unverified":
        if found_in(sq, files(summary_file)) is False:
            notes.append("the Text was not found verbatim in %s" % summary_file)
            quote_issues.append((label, "text", one_line(sq)[:80]))
        if source_file and found_in(srcq, files(source_file)) is False:
            notes.append("the Evidence was not found verbatim in %s" % source_file)
            quote_issues.append((label, "evidence", one_line(srcq)[:80]))
    lines = ["#### %s (%s, %s)" % (label, severity(m), cls), ""]
    lines.append("- **Chapter:** %s, `%s`" % (heading, summary_file))
    lines.append('- **Text:** "%s"' % one_line(sq))
    if srcq and one_line(srcq).lower() not in ("n/a", "none"):
        pg = " (%s)" % page if page and page.lower() != "none" else ""
        lines.append('- **Evidence%s:** "%s"' % (pg, one_line(srcq)))
    lines.append("- **Problem:** %s" % one_line(f.get("problem")))
    lines.append("- **Suggested fix:** %s" % one_line(fix))
    o = outcome(m)
    finder = "found by the %s" % role_of(f.get("id"))
    if o == "unverified":
        ver = finder + "; no verifier result came back for it."
    elif o == "disputed" and is_audit(m):
        ver = "%s; rejected by %s (%s): %s Rejection audit (%s): %s" % (
            finder, verifier, v.get("reason_code") or "no code", one_line(v.get("reason")),
            s.get("verdict"), one_line(s.get("reason")))
    else:
        ver = "%s; confirmed by %s: %s" % (finder, verifier, one_line(v.get("reason")))
        if s:
            ver += " Second opinion (%s): %s" % (s.get("verdict"), one_line(s.get("reason")))
            if (s.get("fix") or "").strip():
                ver += " The suggested fix is the second opinion's."
    lines.append("- **Verification:** " + ver)
    if v.get("previously_considered"):
        lines.append("- **Earlier rounds:** %s" % one_line(v.get("prior_note") or "an earlier round dealt with "
                                                            "this passage."))
    if notes:
        lines.append("- **Quote check:** " + "; ".join(notes) + ". Search a few words of it before acting.")
    lines.append("")
    return lines


def position(m, chapter, files):
    summary_file, _ = target_files(m, chapter)
    q = norm(field(m, "summary_quote"))[:40]
    i = norm(files(summary_file)).find(q) if q else -1
    return i if i >= 0 else 10 ** 9


def part_headings():
    """{slug: part heading text} from Work/assemble.py PARTS, if it can be read."""
    try:
        import assemble
        return {slug: h.lstrip("#").strip() for slug, h in getattr(assemble, "PARTS", []) if slug}
    except Exception:  # noqa: BLE001 - assemble.py is the project's own; any failure just drops the grouping
        return {}


def appendix_line(m, where):
    f, v, s = m["finding"], m.get("verdict") or {}, m.get("second") or {}
    o = outcome(m)
    snippet = one_line(f.get("summary_quote"))[:90]
    if o == "duplicate":
        why = "duplicate of %s. %s" % (v.get("duplicate_of") or "?", brief(v.get("reason")))
        tag = "duplicate"
    else:
        why = brief(v.get("reason"))
        tag = "rejected: %s" % (v.get("reason_code") or "no code")
    line = '- %s, %s (%s, %s; %s): "%s". %s' % (where, f.get("id"), role_of(f.get("id")),
                                                f.get("class", ""), tag, snippet, why)
    if s and is_audit(m):
        line += " Audit: upheld. %s" % brief(s.get("reason"), 160)
    return line


def build(root, out, data, source_label, checks_text, date):
    tasks = load_json(root / "Work" / "Prompts" / out / "tasks.json")
    if tasks is None:
        sys.exit("Work/Prompts/%s/tasks.json not found" % out)
    chapters = {c["n"]: c for c in tasks["chapters"]}
    files = Files(root)
    parts = part_headings()
    stats, by_role, reported_role, codes, classes = Counter(), Counter(), Counter(), Counter(), Counter()
    audits = Counter()
    quote_issues, delta, unknown, largest = [], 0, 0, 0
    prev = conf_ch = 0
    table, body, appendix, disputed, unverified = [], [], [], [], []
    checked = sorted(c["n"] for c in data.get("chapters") or [] if c)
    results = {c["n"]: c for c in data.get("chapters") or [] if c}
    missing_finders = []
    cur_part = None
    none_found = []

    def tally(m):
        o = outcome(m)
        fid = m["finding"].get("id", "")
        role = fid[:1]
        reported_role[role] += 1
        if o in CONFIRMED:
            by_role[role] += 1
        v = m.get("verdict") or {}
        if o == "rejected" or (o == "disputed" and is_audit(m)):
            codes[v.get("reason_code") or "no code"] += 1
        if m.get("second") and is_audit(m):
            audits["reinstated" if o == "disputed" else "upheld"] += 1
            audits["settled" if v.get("reason_code") == "settled" else "compression"] += 1
        return o

    for n in checked:
        c = chapters.get(n)
        if c is None:
            continue
        r = results[n]
        for role, res in (r.get("finders") or {}).items():
            if res is None:
                missing_finders.append("%s chapter %d" % (ROLES.get(role, (role,))[0], n))
        ms = r.get("merged") or []
        oc = Counter(tally(m) for m in ms)
        stats.update(oc)
        table.append("| %d | %s | %d | %d | %d | %d |" % (n, c["heading"], oc["confirmed-material"],
                                                       oc["confirmed-minor"], oc["rejected"] + oc["duplicate"],
                                                       oc["disputed"]))
        part = parts.get(c["slug"], c["slug"])
        if part != cur_part:
            cur_part = part
            body += ["## %s" % part, ""]
        sw = c.get("source_words")
        body += ["### %d. %s" % (n, c["heading"]), "",
                 "Summary: `%s`; source: `%s`; %s words%s." % (
                     c["summary"], c["source"], format(c.get("words") or 0, ","),
                     " for %s source words" % format(sw, ",") if sw else ""), ""]
        conf = [m for m in ms if outcome(m) in CONFIRMED]
        conf.sort(key=lambda m: (0 if outcome(m) == "confirmed-material" else 1, position(m, c, files)))
        if not conf and (oc["disputed"] or oc["unverified"]):
            body += ["No confirmed findings yet: see the disputed or unverified findings below.", ""]
        elif not conf:
            body += ["No actionable findings.", ""]
            none_found.append("%d (%s)" % (n, c["heading"]))
        heading = "%d. %s" % (n, c["heading"])
        for i, m in enumerate(conf, 1):
            body += render(m, "%d.%d" % (n, i), c, heading, files, quote_issues)
            conf_ch += 1
            classes[field(m, "class", "other")] += 1
            if (m.get("verdict") or {}).get("previously_considered"):
                prev += 1
            w = word_change(field(m, "fix"))
            if w is None:
                unknown += 1
            else:
                delta += w
                largest = max(largest, w)
        for m in ms:
            o = outcome(m)
            if o in ("rejected", "duplicate"):
                appendix.append(appendix_line(m, heading))
            elif o == "disputed":
                disputed.append((m, c, heading))
            elif o == "unverified":
                unverified.append((m, c, heading))

    intro_body, intro_stats = [], Counter()
    intro = data.get("intro")
    if intro:
        if (intro.get("finders") or {}).get("I") is None:
            missing_finders.append("introduction checker")
        ms = intro.get("merged") or []
        intro_stats.update(tally(m) for m in ms)
        conf = [m for m in ms if outcome(m) in CONFIRMED]
        conf.sort(key=lambda m: (0 if outcome(m) == "confirmed-material" else 1, position(m, None, files)))
        if not conf:
            intro_body += ["No actionable findings.", ""]
        for i, m in enumerate(conf, 1):
            where = "Introduction" if re.search(r"introduction", m["finding"].get("location") or "", re.I) \
                else one_line(m["finding"].get("location")) or "Introduction"
            intro_body += render(m, "I.%d" % i, None, where, files, quote_issues)
        for m in ms:
            o = outcome(m)
            where = one_line(m["finding"].get("location")) or "Introduction"
            if o in ("rejected", "duplicate"):
                appendix.append(appendix_line(m, where))
            elif o == "disputed":
                disputed.append((m, None, where))
            elif o == "unverified":
                unverified.append((m, None, where))

    readers = data.get("readers") or []
    missing_finders += ["whole-document reader chunk %s" % r.get("k") for r in readers if r.get("missing")]
    unassigned = data.get("unassigned") or []

    disputed_body = []
    for i, (m, c, heading) in enumerate(disputed, 1):
        disputed_body += render(m, "D.%d" % i, c, heading, files, quote_issues)
    unverified_body = []
    for i, (m, c, heading) in enumerate(unverified, 1):
        unverified_body += render(m, "U.%d" % i, c, heading, files, quote_issues)

    total = sum(stats.values()) + sum(intro_stats.values())
    rej = stats["rejected"] + intro_stats["rejected"]
    dup = stats["duplicate"] + intro_stats["duplicate"]
    precision = []
    for role in ("A", "B", "W", "I"):
        if reported_role[role]:
            precision.append("%s %d of %d (%d%%)" % (ROLES[role][0], by_role[role], reported_role[role],
                                                    round(100 * by_role[role] / reported_role[role])))
    all_n = len(tasks["chapters"])
    out_lines = [
        "# Validation Run: Findings",
        "",
        "Validation run of %s, report-only (`passes/validation-run.md`). The text quoted under each finding "
        "is the text at the time of the run. Results read from %s." % (date, source_label),
        "",
        "## Result",
        "",
        "- **Chapters checked:** %d of %d." % (len(checked), all_n),
        "- **Chapters:** %d material and %d minor findings confirmed." % (stats["confirmed-material"],
                                                                         stats["confirmed-minor"]),
    ]
    if intro:
        out_lines.append("- **Introduction:** %d material and %d minor." % (intro_stats["confirmed-material"],
                                                                         intro_stats["confirmed-minor"]))
    out_lines += [
        "- **Reported:** %d findings; %d rejected and %d merged as duplicates (listed in the appendix with the "
        "gist of each reason); %d disputed; %d unverified." % (total, rej, dup, len(disputed), len(unverified)),
    ]
    if precision:
        out_lines.append("- **Confirmed by role:** %s." % "; ".join(precision))
    if codes:
        out_lines.append("- **Rejection reasons:** %s." % ", ".join("%s %d" % kv for kv in codes.most_common()))
    if audits["upheld"] or audits["reinstated"]:
        out_lines.append("- **Rejection audit:** %d rejection(s) audited (%d under a settled ruling, %d "
                         "compression samples): %d upheld, %d reinstated%s." % (
                             audits["upheld"] + audits["reinstated"], audits["settled"], audits["compression"],
                             audits["upheld"], audits["reinstated"],
                             " (under Disputed findings)" if audits["reinstated"] else ""))
    if classes:
        out_lines.append("- **Chapter findings by class:** %s." % ", ".join("%s %d" % kv
                                                                         for kv in classes.most_common()))
    out_lines += [
        "- **Earlier rounds:** %d of the %d confirmed chapter findings concern passages an earlier round dealt "
        "with (each has an \"Earlier rounds\" line)." % (prev, conf_ch),
        "- **Length:** applying every confirmed chapter fix would change the summaries by about %s words%s; "
        "the largest single fix adds %d." % (format(delta, "+,"), ", not counting %d fix(es) that give no count"
                                              % unknown if unknown else "", largest),
        "- **Quote check:** %s" % (
            "every quote of every listed finding was found in its file by script." if not quote_issues else
            "%d quote(s) could not be found verbatim by script; each has a \"Quote check\" line under its "
            "finding." % len(quote_issues)),
    ]
    if none_found:
        out_lines.append("- **No actionable findings:** chapters %s." % ", ".join(none_found))
    if missing_finders:
        out_lines.append("- **Did not report (rerun before the fix pass):** %s." % ", ".join(missing_finders))
    if unassigned:
        out_lines.append("- **Unassigned reader findings:** %d (listed below; no verifier saw them)."
                         % len(unassigned))
    out_lines += [
        "",
        "## How to use this list",
        "",
        "Each finding gives the chapter summary to edit, the exact text to search for, the source evidence and "
        "its page, the problem, a suggested fix with its word change, the verifier's reasoning, and, under "
        "\"Earlier rounds\", what an earlier round did with the passage. Apply them with the validation fix "
        "pass (`passes/validation-fix-pass.md`). Severity: **material** changes what a reader takes away; "
        "**minor** is real, but the takeaway stays right. Minor findings are fixed too.",
        "",
        "## Mechanical checks",
        "",
        checks_text.strip() if checks_text else
        "Not recorded. Run the checks in `validation-run.md` (\"Mechanical checks\") and rebuild this file "
        "with `--checks <file>`.",
        "",
        "## Findings by chapter",
        "",
        "| # | Chapter | Material | Minor | Rejected or duplicate | Disputed |",
        "|---|---|---|---|---|---|",
        *table,
        "",
        *body,
    ]
    if intro:
        out_lines += ["## Introduction", "",
                      "Coordinator's text (`%s` and the part headings): the coordinator applies these." % INTRO_FILE,
                      "", *intro_body]
    if disputed_body:
        out_lines += ["## Disputed findings", "",
                      "The refuting verifier and the second opinion disagree on these: confirmed as material and "
                      "then rejected, or rejected and then reinstated by the rejection audit. Decide each one "
                      "against the source before the fix pass; move an accepted one into its chapter's section "
                      "as the next N.k.", "", *disputed_body]
    if unverified_body:
        out_lines += ["## Unverified findings", "",
                      "A finder reported these, but no verifier result came back for them. Verify them (rerun "
                      "the chapter's verifier) before the fix pass.", "", *unverified_body]
    if unassigned:
        out_lines += ["## Unassigned reader findings", "",
                      "A whole-document reader gave these a location that names no chapter of its chunk; no "
                      "verifier saw them.", ""]
        for f in unassigned:
            out_lines.append('- chunk %s, %s (%s, %s): "%s". %s Suggested fix: %s' % (
                f.get("chunk", "?"), f.get("id"), f.get("location", ""), f.get("class", ""),
                one_line(f.get("summary_quote")), one_line(f.get("problem")), one_line(f.get("fix"))))
        out_lines.append("")
    out_lines += ["## Appendix: rejected findings", "",
                  "Reported by a finder, then rejected by the verifier or merged into another finding. Listed so "
                  "you can see what was weighed and why it is not actionable.", "", *appendix, ""]
    text = "\n".join(out_lines).rstrip("\n") + "\n"

    stats_out = {
        "date": date,
        "chapters_checked": len(checked),
        "chapters": dict(stats),
        "introduction": dict(intro_stats),
        "confirmed_by_role": {r: [by_role[r], reported_role[r]] for r in reported_role},
        "rejection_reasons": dict(codes),
        "audit": dict(audits),
        "classes": dict(classes),
        "earlier_rounds": [prev, conf_ch],
        "word_change": delta,
        "word_change_unknown": unknown,
        "quote_issues": quote_issues,
        "did_not_report": missing_finders,
        "disputed": len(disputed),
        "unverified": len(unverified),
        "unassigned": len(unassigned),
    }
    return text, stats_out


def main(argv=None):
    utf8_output()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", nargs="?", default=DEFAULT_OUT, help="the run's folder under Work/Prompts/")
    ap.add_argument("--result", action="append", default=[], metavar="FILE",
                    help="a workflow result JSON, repeatable (default: Work/Prompts/<out>/result*.json)")
    ap.add_argument("--findings", default=FINDINGS_FILE, help="the file to write (default %(default)s)")
    ap.add_argument("--checks", help="a Markdown file with the mechanical checks' results")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    args = ap.parse_args(argv)
    data, label = load_result(ROOT, args.out, args.result)
    checks = None
    if args.checks:
        p = Path(args.checks)
        checks = (p if p.is_absolute() else ROOT / p).read_text(encoding="utf-8-sig")
    text, stats = build(ROOT, args.out, data, label, checks, args.date)
    dest = Path(args.findings)
    dest = dest if dest.is_absolute() else ROOT / dest
    dest.write_text(text, encoding="utf-8", newline="\n")
    sp = ROOT / "Work" / "Prompts" / args.out / "report_stats.json"
    sp.write_text(json.dumps(stats, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("chapters checked: %d; chapters: %s" % (stats["chapters_checked"], stats["chapters"]))
    if stats["introduction"]:
        print("introduction: %s" % stats["introduction"])
    print("disputed %d, unverified %d, unassigned %d; word change %+d (%d unknown)" % (
        stats["disputed"], stats["unverified"], stats["unassigned"], stats["word_change"],
        stats["word_change_unknown"]))
    print("quote issues: %d" % len(stats["quote_issues"]))
    for q in stats["quote_issues"][:40]:
        print("  %s %s: %s" % q)
    if stats["did_not_report"]:
        print("did not report: " + ", ".join(stats["did_not_report"]))
    print("wrote %s" % (dest.relative_to(ROOT).as_posix() if dest.is_relative_to(ROOT) else dest))


if __name__ == "__main__":
    main()
