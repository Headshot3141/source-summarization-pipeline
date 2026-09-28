# Checks

Record every check, its result, the problems found, and how each was resolved. Every stage adds an entry, including independent verification and every later pass, even when the pass keeps its own brief and status file. Record dependency versions, executable paths, and installations in the Preflight section, keyed to `requirements.txt`.

## Preflight

### Sources

| Part | File | Format | Title and author (confirmed from) | Pages | Size | Text layer / OCR notes |
|---|---|---|---|---|---|---|

Do not trust PDF title metadata; it can be junk. Confirm title and author from the title page.

### Environment

- Python executable and version:
- Package versions checked against `requirements.txt`:
- Microsoft Edge path (PDF rendering):
- `writing-rules.md` and `stop-slop-main/SKILL.md` present:
- Word-count command tested: `{WORD_COUNT_COMMAND}` on `{file}` returned `{n}`
- Fallbacks in use (interpreter path, PDF build outside the sandbox, manual count rule):

### Agent harness and limits

| Role | Model | Context | Effective output cap | Reasoning setting | Concurrency |
|---|---|---|---|---|---|
| Summarizer | Claude Sonnet 5.5 (Claude Code subagent, `summarizer` agent type, `model: claude-sonnet-5-5`) | | Probe before dispatch (see below) | `effort: high` | |
| Reviewer | Claude Opus 5.5 (Claude Code subagent, `model: "opus"`) | | No truncation (see below) | | |
| Verifier / later passes | Claude Opus 5.5 (Claude Code subagent, `model: "opus"`) | | No truncation (see below) | | |

Default setup (plan.md, Agents). Change these rows only if the project uses another model or harness.

- How the output cap is set, and the probe that proved it (finish reasons, largest total seen, no truncated `length` finishes): Opus 5.5 roles, probe not needed. On 2026-09-26 an Opus 5.5 subagent in Claude Code wrote 8,669 words (160 paragraphs, end sentinel present) in one Write call, with no cut-off and no error. Sonnet 5.5 summarizer: not yet probed; record the probe result here before dispatching drafts. Re-probe for another harness or model.
- Provider exclusions or retry rules:
- Usage-window cost per task, measured in the pilot:

## Extraction and Validation

| Source | Units | Retained words | Method (PDF text / OCR / EPUB) | Config overrides | Notes |
|---|---|---|---|---|---|

- Chapter boundaries and page mappings checked (where):
- No presentation-form ligatures or U+FFFD left in chapter files:
- `repairs.tsv` reviewed: every `uncertain`, `-midword`, and `page-break-unjoined` line checked against the page image, and the result:
- Pages sampled against the originals, including difficult layouts and repaired text:
- Figures and tables inspected; visual transcriptions added:
- Block quotations marked (`> `): detection method, count, weaker-evidence log lines and a full listing reviewed, hand fixes:
- Detected headings listed and checked for split or letter-spaced headings:
- Open extraction issues (blocking? y/n):

## Size Limits and Chapter Splitting

- Chapters, parts, and split chapters:
- Largest part file in bytes, against the 32,000-byte cap:
- `Work/check_parts.py` result:
- Boundaries inspected, context added in `Work/part_context.json`, and overlap dropped:

## Pilot

- Unit(s), per-part counts against their ranges:
- Merge seam edits and their verification:
- Pilot assembly and PDF result:
- Usage cost measured:
- User decision and date:

## Summarization and Review

| Batch | Units | Accepted | Blocked | Word-count outliers and disposition | Failures and retries |
|---|---|---|---|---|---|

## Scope Exceptions

| Unit | Exception | Reason | Check that will keep flagging it |
|---|---|---|---|

## Merge and Transition Review

- Chapters merged, seams edited, and edits verified against the source:
- Structural artifacts found in part summaries (frontmatter, markers, headings):

## Assembly

- Units assembled; missing, duplicate, or blocked units:
- Introduction words; chapter-summary words; overall ratio against the aggregate target:
- Structural checks from `Work/assemble.py`:

## Whole-Document Review

- Chunks and reviewers:
- Findings triage, including rejected outside-knowledge fact-checks:
- Edits made and their verification against the source:

## Independent Verification

| Round | Chapters | Model | CLEAN | MINOR | MATERIAL | Material findings |
|---|---|---|---|---|---|---|

- Defect classes found, and the decision on remediation scope:
- Remediation rounds and records:

## PDF Rendering and Inspection

- Pages; blank or thin pages; U+FFFD count:
- Every heading found in the PDF text:
- No leftover `Work/`, `.md`, `<!--`, or page-reference strings:
- Pages inspected visually (first, last, each part start, changed passages):

## Later Passes

One entry per pass: brief file, scope, snapshot directory, records path, edits applied, checker results, rebuild and PDF result.

## Open Issues
