# Bug-Fix To-Do

These are the problems from the code review that are still open. The four blocking problems are fixed: budget parsing, the missing chapter manifest, frontmatter fields, and the part checker. Items are grouped by priority. Line numbers were current as of this file's first commit.

## High: text is lost or corrupted during extraction

Fixed. Regression tests are in `Work/tests/test_extract.py` (`python -m unittest discover -s Work/tests`). Extraction decisions are now logged to `Work/Raw/{slug}/repairs.tsv`; the kinds are listed in `RepairLog` in `Work/extract.py`. Tune `PAGE_NUM_ZONE` and the ligature threshold against the first real source.

- [x] **Heading stripping deletes real paragraphs.** `strip_chapter_heading` (`Work/extract.py:49`) drops any of a chapter's first four paragraphs whose text contains the title, or is contained in it. With the title "War", it deleted "The war began in the spring." With an empty title, it deletes all four. Only strip leading lines that closely match the title or chapter number, and stop at the first body paragraph.
- [x] **Paragraphs without end punctuation are merged into the next one.** `join_fragments` (`Work/extract.py:161`) joins any paragraph that doesn't end a sentence to the paragraph after it. It merged "...as follows" into the next paragraph. Apply joining only across page breaks, where the last block of one page continues on the next, and keep the page number for merged text.
- [x] **A space is inserted after a line-end hyphen before a capital.** In `join_lines` (`Work/extract.py:116`), "Anglo-" at a line end followed by "Saxon" becomes "Anglo- Saxon". When a line ends in a hyphen, join without a space whatever the next letter's case.
- [x] **Hyphen repairs happen silently.** `join_lines` (`Work/extract.py:111`) removes a line-end hyphen whenever the dictionary knows the joined word, so "co-" and "operate" become "cooperate". Log every repair, and every join the dictionary couldn't settle, to a review file, as the plan requires.
- [x] **Standalone numbers are dropped.** `block_paragraphs` (`Work/extract.py:140`) discards every block that is just a number, and line 138 discards date-time stamps. This also removes table cells and figures such as "1990". Remove numbers only where they sit in the header or footer zone, or match a page-number position.

## Medium: plan requirements not implemented

- [ ] **Page markers are not written.** The plan keeps internal page markers for evidence lookup, but extraction discards page boundaries. Write a marker such as `<!-- page 12 -->` at each page break in the chapter text. The word counter already ignores lines that are only an HTML comment. The splitter must keep a marker attached to the text that follows it.
- [ ] **The raw extraction is not saved.** Nothing writes to `Work/Raw/{slug}/`. Save each page's raw text before cleanup, with page boundaries, so repairs can be checked later.
- [ ] **Rerunning the splitter overwrites hand-added context.** The plan lets the coordinator add context blocks to part files at weak boundaries. `split_parts.py` (`Work/split_parts.py:321`) rewrites every part file on each run, so those additions are lost. Store extra context in a separate config keyed by unit and part, and have the splitter insert it.
- [ ] **Assembly skips its structural checks.** `assemble.py` doesn't check for missing `##` chapter headings, leftover page or pipeline markers, or leaked review notes. It also doesn't add the partial-deliverable notice when blocked units remain. Add these checks and fail on any hit.
- [ ] **The introduction's length isn't reported separately.** The plan asks for it. `assemble.py` (`Work/assemble.py:59`) counts total words with a plain split, which includes headings. Use `words_in_text` and report the introduction and body separately.

## Low: robustness

- [ ] **The path check in `assemble.py` uses a plain prefix test.** At `Work/assemble.py:31`, a sibling folder such as `summarise2` would pass. Compare resolved paths with `Path.is_relative_to` instead.
- [ ] **`build_pdf.py` only finds Edge in two fixed locations.** At `Work/build_pdf.py:67`, the script ignores PATH, although `requirements.txt` says Edge on PATH works. Try `shutil.which("msedge")` first.
- [ ] **`build_pdf.py` builds the file URL by hand.** At `Work/build_pdf.py:82`, a path containing `#`, `%` or spaces breaks the URL. Use `pathlib.Path(HTML).as_uri()`.
- [ ] **`build_pdf.py` ignores Edge's exit code and uses the default profile.** At `Work/build_pdf.py:91`, errors are hidden, and an open Edge window can interfere with printing. Check the return code, report stderr on failure, and pass a temporary `--user-data-dir`.
- [ ] **Sentence splitting relies on a fixed abbreviation list.** `ABBREVIATIONS` (`Work/split_parts.py:52`) covers common cases only. It also treats any one-letter word followed by a period as an initial, so a sentence ending in "I." won't split there. This only matters for paragraphs too large for one part. Review any such splits in the split report.

- [ ] **URLs broken across lines get a space.** When a URL wraps at a `/` or `.` rather than a hyphen, `join_lines` joins the two lines with a space, splitting the URL. This mostly affects notes sections, which are usually omitted as apparatus. If notes are kept, join without a space when the left token is URL-like and doesn't end a sentence.

## Verification after fixes

- [ ] Rerun the scratchpad-style end-to-end test with a generated PDF: extract, split, then run the part checker, the review queue and the word-count check.
- [ ] Add test cases for each fixed bug above (done for the High items), using the inputs from the review: the "War" title, the "as follows" paragraph, "Anglo-" and "Saxon", and a table cell reading "1990".
