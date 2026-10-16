# Checks

Record every check, its result, the problems found, and how each was resolved. Every stage adds an entry, including independent verification and every later pass, even when the pass keeps its own brief and status file. Record dependency versions, executable paths, and installations in the Preflight section, keyed to `requirements.txt`.

## Preflight

### Sources

| Part | File | Format | Extract from | Title and author (confirmed from) | Pages | Size | Text layer / OCR notes | Preflight report |
|---|---|---|---|---|---|---|---|---|

Do not trust PDF title metadata; it can be junk. Confirm title and author from the title page.

### Environment

- Python executable and version:
- Interpreter command given to agents (PyMuPDF from user site-packages does not import under `python -I`):
- Package versions checked against `requirements.txt`:
- Microsoft Edge path and version (PDF rendering); `aiohttp` version for the DevTools fallback:
- Typography policy recorded in `settled.md` (quotation marks, dashes, italics, note references):
- Register per source (date of the English text; `modern` before 1950, `source` from 1950 on) set in each config, and the period-terms decision in `settled.md`:
- `settled.md` and `status.md` created:
- `writing-rules.md` present:
- Word-count command tested: `{WORD_COUNT_COMMAND}` on `{file}` returned `{n}`
- Author-check, fidelity-check, and qualifier-check commands tested (`python Work/check_author_refs.py`, `python Work/check_fidelity.py`, `python Work/check_qualifiers.py`):
- Naming conventions written to `Work/author_refs.json` (`conventions`), one per source and per unit in another voice:
- Fallbacks in use (interpreter path, PDF build outside the sandbox, manual count rule):

### Agent harness and limits

| Role | Model | Context | Effective output cap | Reasoning setting | Concurrency |
|---|---|---|---|---|---|
| Summarizer | Claude Sonnet 5.5 (Claude Code subagent, `summarizer` agent type, `model: claude-sonnet-5-5`) | | No truncation (see below) | `effort: high` | 6, then up to the harness limit (20 in one run) |
| Reviewer | Claude Opus 5.5 (Claude Code subagent, `model: "opus"`) | | No truncation (see below) | | as above |
| Preflight, extraction, boundary inspection | Claude Opus 5.5 (Claude Code subagent, `model: "opus"`) | | No truncation (see below) | | one agent per 1-3 sources |
| Verifier / later passes | Claude Opus 5.5 (Claude Code subagent, `model: "opus"`) | | No truncation (see below) | | |

Models and dispatch as set in plan.md, Agents.

- Output cap: no probe needed. On 2026-09-26 an Opus 5.5 subagent in Claude Code wrote 8,669 words (160 paragraphs, end sentinel present) in one Write call, with no cut-off and no error. Claude Code imposes no cap below the model limit, and Sonnet 5.5 shares Opus 5.5's 128K-token output limit, so the result covers the summarizer.
- Retry rules:
- Usage stop point agreed with the user (default 95% of the 5-hour window):
- Usage-window cost per task, measured in the pilot and again at the start of each session:

## Extraction and Validation

| Source | Units | Retained words | Method (docling Markdown / PDF text / OCR / EPUB / TXT) | Config overrides | Notes |
|---|---|---|---|---|---|

- Chapter boundaries and page mappings checked (where):
- No presentation-form ligatures or U+FFFD left in chapter files:
- `repairs.tsv` reviewed: every `uncertain`, `-midword`, and `page-break-unjoined` line checked against the page image, and the result:
- Pages sampled against the originals, including difficult layouts and repaired text:
- Figures and tables inspected; visual transcriptions added:
- Block quotations marked (`> `): detection method, count, weaker-evidence log lines and a full listing reviewed, hand fixes:
- Detected headings listed and checked for split or letter-spaced headings:
- Docling Markdown, first file (plan.md Step 2, checks 1-7): page-break count against the PDF page count; footnote form and `footnote_pattern`; chapter title headings and number lines; leaked running heads; line-end hyphens; emphasis, lists, escapes, and existing `> ` quotations; every placeholder and the text around it:
- `repairs.tsv` rows for text outside every chapter (`outside-chapters`) checked against the scope decisions:
- Per-source extraction reports (`Work/Extraction/<slug>.md`), each with its open issues marked blocking or not; faults kept as printed copied to `settled.md`:
- OCR text layers: numbers and faint print checked against page images; proofreading (`passes/proofread.md`) and its fixes:
- `python Work/check_chapters.py` result, and each warning settled:
- `python Work/extract.py --check` result (every chapter file reproduced byte for byte):
- Open extraction issues (blocking? y/n):

## Size Limits and Chapter Splitting

- Chapters, parts, and split chapters:
- Largest part file in bytes, against the 32,000-byte cap:
- `Work/check_parts.py` result:
- Boundaries inspected (records in `Work/Boundaries/`), context added in `Work/part_context.json`, and overlap dropped:
- Hand-set boundaries in `Work/part_boundaries.json`, and why each was moved:
- Text left out of the budget basis (`Work/budget_exclusions.json`), with words per chapter:
- Parts starting inside a notes block, or holding only notes, and how each was settled:
- Quotations whose speaker is named only in a citation-only note, and the context entries that carry the attribution:

## Pilot

- Unit(s), per-part counts against their ranges:
- Merge seam edits and their verification:
- Pilot assembly and PDF result:
- Usage cost measured:
- User decision and date:

## Summarization and Review

| Batch | Units | Accepted | Blocked | Word-count outliers and disposition | Fidelity and qualifier flags settled | Source oddities checked before review | Running and projected ratio (document) | Usage cost | Failures and retries |
|---|---|---|---|---|---|---|---|---|---|

## Scope Exceptions

| Unit | Exception | Reason | Entry in `Work/budget_exceptions.json` (or other check it settles) |
|---|---|---|---|

## Merge and Transition Review

- Chapters merged, seams edited, and edits verified against the source:
- Structural artifacts found in part summaries (frontmatter, markers, headings):

## Assembly

- Units assembled; missing, duplicate, or blocked units:
- Introduction words; chapter-summary words; ratio per source and overall (target 0.50, maximum 0.55):
- Structural checks from `Work/assemble.py`:

## Independent Verification

| Round | Chapters | Model | CLEAN | MINOR | MATERIAL | Material findings |
|---|---|---|---|---|---|---|

- Defect classes found, and the decisions on remediation scope and length (room for restorations):
- Remediation rounds and records:

## Later Passes

One entry per pass: brief file, scope, length decision, snapshot directory, prompts folder, records path, edits applied, `gate_pass.py` results and coordinator corrections, exceptions raised (`raise_exceptions.py`), checker results (including the `check_words.py` ratio), reassembly result, and usage cost. A pass that added content names the independent check that followed it.

## Whole-Document Review

- Chunks and reviewers (chapters per chunk):
- Decision on unexplained terms and references:
- Findings triage, including rejected outside-knowledge fact-checks, and the fix pass's dispositions:
- Edits made and their verification against the source:

## Validation Run

- Brief, agents, and usage cost; `Work/fingerprint.py compare` result (no file changed):
- Findings reported, confirmed (material, minor), and rejected, by finder and by reason:
- Mechanical checks (reassembly matches `Summary.md`, checkers, quotes of every confirmed finding found):
- Fix pass: limits, findings applied, applied with changes, not applied, gate result:

## PDF Rendering and Inspection

- Output name (from `TITLE`) and print route (`--print-to-pdf` or DevTools):
- Pages; blank or thin pages (part ends expected); U+FFFD count; literal-asterisk warnings settled:
- `python Work/check_pdf_text.py` result (word-for-word match with Summary.md, structural checks):
- Every heading found in the PDF text:
- No leftover `Work/`, `.md`, `<!--`, or page-reference strings:
- Pages inspected visually (first, last, each part start, changed passages):
- EPUB, if built: `Work/check_epub_text.py` result, documents, words, italic spans:

## Completion

- Each completion criterion in `plan.md`, met or superseded by a recorded user decision:
- Remaining fidelity flags traced to the record that settles each:

## Open Issues
