import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import markdown
import pymupdf
from jinja2 import Template

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD = os.path.join(ROOT, "Summary.md")
HTML = os.path.join(ROOT, "Work", "summary.html")
PDF = os.path.join(ROOT, "Summary.pdf")
TITLE = "Summary"

EDGE = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ title }}</title>
<style>
@page { size: Letter; margin: 1in; }
body {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 11pt;
  line-height: 1.5;
  color: #111;
  margin: 0;
}
h1 {
  font-size: 18pt;
  line-height: 1.3;
  margin: 1.6em 0 0.4em;
  page-break-after: avoid;
}
h1:first-child { margin-top: 0; }
h2 {
  font-size: 14pt;
  line-height: 1.35;
  margin: 1.5em 0 0.4em;
  page-break-after: avoid;
}
h3 {
  font-size: 11.5pt;
  font-style: italic;
  margin: 1.2em 0 0.3em;
  page-break-after: avoid;
}
p { margin: 0 0 0.65em; text-align: justify; }
em { font-style: italic; }
strong { font-weight: bold; }
</style>
</head>
<body>
{{ body }}
</body>
</html>
"""


def find_edge():
    on_path = shutil.which("msedge")
    if on_path:
        return on_path
    for path in EDGE:
        if os.path.exists(path):
            return path
    raise SystemExit("Microsoft Edge not found on PATH or in: " + ", ".join(EDGE))


def render_html():
    with open(MD, "r", encoding="utf-8") as fh:
        text = fh.read()
    body = markdown.markdown(text, extensions=["extra", "sane_lists"])
    html = Template(TEMPLATE).render(body=body, title=TITLE)
    with open(HTML, "w", encoding="utf-8") as fh:
        fh.write(html)


def print_pdf(edge, tmp_pdf):
    url = Path(HTML).resolve().as_uri()
    failures = []
    # A separate profile keeps an open Edge window from taking over the print job.
    with tempfile.TemporaryDirectory(prefix="edge-profile-") as profile:
        base = [edge, "--no-first-run", "--no-default-browser-check",
                "--user-data-dir=" + profile,
                "--disable-gpu", "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=10000",
                "--no-pdf-header-footer", "--print-to-pdf-no-header"]
        for mode in ("--headless=new", "--headless"):
            if os.path.exists(tmp_pdf):
                os.remove(tmp_pdf)
            cmd = base + [mode, "--print-to-pdf=" + tmp_pdf, url]
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    errors="replace", timeout=180)
            produced = os.path.exists(tmp_pdf) and os.path.getsize(tmp_pdf) > 0
            if result.returncode == 0 and produced:
                return
            failures.append("%s: exit %d%s\n%s" % (
                mode, result.returncode, "" if produced else ", no PDF",
                result.stderr.strip() or "(no stderr)"))
    raise SystemExit("Edge failed to produce a PDF\n" + "\n".join(failures))


def add_page_numbers(tmp_pdf):
    doc = pymupdf.open(tmp_pdf)
    count = doc.page_count
    for i, page in enumerate(doc):
        rect = page.rect
        label = str(i + 1)
        width = pymupdf.get_text_length(label, fontname="helv", fontsize=10)
        page.insert_text(
            (rect.width / 2 - width / 2, rect.height - 42),
            label,
            fontname="helv",
            fontsize=10,
        )
    doc.save(PDF, garbage=4, deflate=True)
    doc.close()
    return count


def main():
    render_html()
    edge = find_edge()
    fd, tmp_pdf = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        print_pdf(edge, tmp_pdf)
        pages = add_page_numbers(tmp_pdf)
    finally:
        if os.path.exists(tmp_pdf):
            os.remove(tmp_pdf)
    print("wrote %s: %d pages" % (PDF, pages))


if __name__ == "__main__":
    main()