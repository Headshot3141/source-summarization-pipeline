# Source Summarization Plan Template

Before the pilot, fill in the sources, scope decisions, chapter inventories, budgets, and environment details. Check the project's existing scripts first. Reuse or adapt them, and write any that are missing.

This plan is for the coordinator. Agents never read it: each agent gets a filled-in prompt from `prompts.md` or a pass brief from `passes/`, plus `writing-rules.md`. Keep the rules agents need in those files, not here.

## Goal

Produce `Summary.md` and `Summary.pdf` (and optionally `Summary.epub`), a standalone summary of one or more source documents with one part per source and one section per chapter or logical unit.

Set the summary body at about 40% of the retained substantive source word count. Very long sources can go down toward 30%, and short sources may need more than 40%. Record the ratio you choose for each source. Chapter targets allow ±15%. If a chapter needs more words to stay accurate and complete, exceed the range and record why. Do not pad a summary or cut essential qualifications to hit a target.

## Priority Order

1. Fidelity to the source, including uncertainty, attribution, negation, and causal strength.
2. Coverage of the main arguments and the evidence needed to understand them.
3. Clear, standalone prose.
4. Style preferences and word targets.

Report what each source argues. Do not endorse, refute, fact-check, or add outside context. The summary speaks in the author's voice and states the author's views directly, without "the author argues"; only views that belong to someone else (quotations, allegations, objections, and views the author describes or rejects) are marked as such. Reproduce each source as printed, errors included: a summary that silently corrects its source is wrong.

## Agents

The default setup uses **Claude Sonnet 5.5 (`claude-sonnet-5-5`) at high effort for the summarizer** and **Claude Opus 5.5 (`claude-opus-5-5`) for every other role**: reviewer, merge and transition reviewer, whole-document reviewer, verifier, and later-pass agents. The coordinator is a Claude Code session (desktop app) that dispatches each agent as a subagent with the Agent tool. Summarizers use the `summarizer` agent type (`.claude/agents/summarizer.md`, which sets `model: claude-sonnet-5-5` and `effort: high`), because the Agent tool cannot set effort per call. All other roles are dispatched with `model: "opus"`. The coordinator can therefore watch every agent directly: it receives each agent's completion report, can message a running agent, and reads the plan's usage windows itself. The coordinator still checks every output file and review record before it changes a status.

Opus 5.5 in Claude Code does not silently truncate long outputs. A probe on 2026-09-26 had an Opus 5.5 subagent write 8,669 words (160 paragraphs) in a single Write call. The file was complete, with its end sentinel present, and no call was cut off or returned an error. That is several times the longest output this pipeline asks of any agent. The probe tested the harness: Claude Code imposes no cap below the model's limit. Sonnet 5.5 has the same 128K-token output limit as Opus 5.5, so the result covers the summarizer too, and no output-cap probe is needed.

Every draft is written by Sonnet 5.5 and reviewed by a fresh-context Opus 5.5 agent, so no agent reviews a file it wrote, and review is done by a stronger model than drafting. See Step 10 for the verification decision.

## Lessons from earlier runs

These shaped the rest of this plan. Read them before the pilot.

- **Word budgets say nothing about fidelity.** In one full run, every chapter was accepted inside its budget, and an independent check with a stronger model then found material errors in most sampled chapters. All of them made the summary more assertive than its source: dropped contrast reversals, hardened hedges, attribution drift, pronouns resolved to the wrong actor, orphaned evidence, and computed totals. The reviewer had seen many of these and accepted them as omissions. The fix was an enumerable preservation rule with an audit, which now lives in `writing-rules.md` and the reviewer prompt from the start, and an independent verification pass (Step 10).
- **Agents fact-check from memory.** Whole-document reviewers and style-pass agents "corrected" dates and names that the summaries reproduced faithfully from their sources. Every brief forbids outside knowledge, and the coordinator checks any reported error against the chapter source before acting.
- **Every pass leaves reports behind.** Passes that may not fix what they notice log it, and the next pass resolves the log. Plan for a report-then-act sequence after the main run (Step 11), and decide with the user where to stop.
- **Usage windows, not chapter counts, set batch size.** Measure cost per task in the pilot and size rounds to fit.
- **Per-chapter ranges do not bound the total.** Chapters clustered near the top of their ranges, and the overall ratio ran well above the target. Track the aggregate.
- **Attribution applied sentence by sentence buries the prose in the author's name.** In one run, a book's summary named its author 329 times in about 27,000 words, and 124 sentences opened with the name. Agents attached "X argues" to every claim, and verification added more. Then a pronoun rule (the source never gendered the author, who wrote in the first person) was applied by replacing every "he" with the name across the files. The fix is the naming rule in `writing-rules.md`: the summary speaks in the author's voice, states the author's views without attribution, and names the author only where a sentence needs it, at most once per paragraph. Only other speakers' views are marked. `Work/check_author_refs.py` enforces the cap, and every prompt carries the source's naming convention from the start. Never fix pronouns or names by mechanical find-and-replace: recast each paragraph.

## Sources

| Part | Source file | Format | Author(s) | Role | Target ratio | Naming convention |
|---|---|---|---|---|---|---|
| 1 | `Sources/<file>` | PDF | | | 0.40 | |
| 2 | `Sources/<file>` | EPUB | | | 0.40 | |

The naming convention is how the summaries refer to each author: the name form ("Penhale", "the authors" for a co-written book), and the pronoun the source uses for the author, or "no pronoun" when the source never genders the author. Never infer a pronoun from a name. For an interview collection, give the interviewer and each interviewee. Settle it in Preflight, with the user if the source is unclear. Every prompt carries it as `AUTHOR`, and it always comes with the naming rule.

For each PDF, check whether the text layer is usable. Run OCR on scanned PDFs and on the scanned pages of mixed PDFs. Text extraction can miss figures, tables, and captions, so inspect them when they support substantive claims. When a PDF's text layer is damaged (ligatures mapped to wrong characters, missing spaces) and an EPUB of the same edition exists, extract from the EPUB. Confirm titles and authors from the title page, not PDF metadata.

## Directory Layout

```text
.claude/agents/summarizer.md        summarizer agent type: Sonnet 5.5, effort high
Sources/                            original documents, untouched
Work/
  extract.py                        project-specific extraction and cleanup (PDF and EPUB)
  split_parts.py                    splits chapters into parts at or under the 32KB hard cap
  check_parts.py                    checks source reconstruction, boundaries, sizes, and counts
  make_review_queue.py              builds the review queue from the parts manifest
  check_words.py                    checks summary word counts against budgets
  check_author_refs.py              flags paragraphs that refer to the author more than once
  author_refs.json                  name forms per source and unit for check_author_refs.py
  count_words.py                    shared counting function and single-file word-count command
  common.py                         shared paths, frontmatter parsing, and owned-text markers
  set_status.py                     coordinator status updates, kept in sync across both manifests
  merge_chapters.py                 concatenates accepted part summaries into chapter summaries
  make_transition_queue.py          lists merged chapters for transition review
  make_doc_chunks.py                groups accepted chapters for the whole-document review
  snapshot_summaries.py             snapshots chapter summaries before a later pass
  check_style_pass.py               gate for prose-only passes: diff against the snapshot
  assemble.py                       ordered assembly and structural checks
  build_pdf.py                      reusable Markdown-to-PDF renderer
  build_epub.py                     optional EPUB build of Summary.md
  tests/                            regression tests: python -m unittest discover -s Work/tests
  manifest.json                     ordered unit paths and status
  parts_manifest.json               all processing units, with status, word counts, and budgets
  parts_report.txt                  split report: parts and sizes per chapter
  part_context.json                 extra original-source context for parts, applied by split_parts.py
  review_queue.txt                  source|draft|summary|record|budget lines for review agents
  transition_queue.txt              slug|unit|parts|summary|title|part sources, for seam review
  whole_doc_chunks.txt              CHUNK k: chapter paths, for the whole-document review
  Raw/{slug}/raw.txt                raw text of every page, before cleanup, with page markers
  Raw/{slug}/repairs.tsv            extraction repairs and uncertain decisions to check
  Chapters/{slug}/NN-slug.md        validated chapter source text
  Chapters/{slug}/parts/*.md        chapter parts assigned to agents
  Drafts/{slug}/NN-slug.md          original summarizer output, preserved
  Drafts/{slug}/parts/*.md          per-part drafts
  Summaries/{slug}/NN-slug.md       canonical chapter summaries; later passes edit these
  Summaries/{slug}/parts/*.md       per-part summaries; stale once merged, never edited later
  Summaries_pre{pass}/              snapshot taken before each later pass; never refreshed
  Summaries_archive_vN/             optional: superseded output from stalled or rerun batches
  Reviews/{slug}/NN-slug.md         chapter review records (unsplit chapters)
  Reviews/{slug}/parts/*.md         part review records
  Reviews/{slug}/transitions/       transition review records
  Reviews/{slug}/{pass}/            records from verification rounds and later passes
  Reviews/whole-document/           whole-document review findings, one file per chunk
  checks.md                         every check and its result, stage by stage and pass by pass
passes/                             brief templates for Steps 10 and 11
  verification-pass.md
  style-pass.md
  targeted-fix-pass.md
Summary.md
Summary.pdf
prompts.md                          agent prompt templates for Steps 5 to 8
writing-rules.md                    shared rules for all agents, including the preservation rule
requirements.txt                    Python dependencies for the pipeline scripts
plan.md
```

Give each source a unique slug, such as `author-title`. Paths are shown with forward slashes; scripts should build them portably.

Each chapter source file starts with YAML frontmatter containing `source`, `source_slug`, `unit_id`, `part`, `chapter`, `title`, `pdf_pages`, `printed_pages`, and `word_count`.

- `unit_id` is stable and unique within its `source_slug`, for example `ch-01`, `appendix-a`, or `interview-01`.
- `chapter` holds the printed chapter label, or null if there is none.
- `pdf_pages` uses one-based page numbers in the PDF file. `printed_pages` holds the printed labels, including Roman numerals and missing labels. For an EPUB source, `pdf_pages` and the page markers hold the printed page numbers from the EPUB's page anchors; record this in `Work/checks.md`.

Match files, manifest entries, and budgets on `(source_slug, unit_id)`. Filename prefixes show display order, but assembly follows the ordered chapter manifest. Keep internal page markers in the text for evidence lookup: `<!-- page N -->` gives the page, on its own line above a paragraph that starts the page, or inline where a paragraph runs on from the previous page. The word counter ignores them.

`Work/manifest.json` is an ordered list. Each entry has `source_slug`, `unit_id`, a `path` relative to the project root (such as `Work/Summaries/{slug}/NN-slug.md`), and a `status` of `pending`, `drafted`, `accepted`, or `blocked`.

The budget tables in this plan are the authoritative record of chapter counts and targets. Generate the processing budgets in `Work/parts_manifest.json` from them, and do not edit the derived budgets by hand. Record section mappings only for split chapters.

If you change a chapter source, revalidate its extraction, regenerate its parts, counts, and budgets, and repeat the affected reviews. Clear any `accepted` status on the chapter and its affected processing units.

Save raw extraction automatically before cleanup; this needs no separate agent task. Checksums, extraction revisions, model and prompt versions, and revision snapshots are optional. Add them if the project needs reproducibility or several revision rounds. Commit after each batch, with the progress count in the message, so an interrupted session can resume from git.

## Scope Decisions

- Keep substantive body content. Omit covers, credits, bibliographies, acknowledgements, and similar apparatus unless they contain substantive content found nowhere else.
- Inspect notes, prefaces, introductions, conclusions, appendices, interviews, transcripts, captions, and tables before deciding. If a notes page contains relevant argument or evidence, keep that material. If the user limits scope (for example "numbered chapters only") and an omitted section carries substantive framing, record that it does.
- Apparatus inside a chapter's page range, such as a further-reading list at each chapter's end, is omitted in the summary but stays in the chapter source. A part that holds only apparatus gets an empty summary and a scope exception in `Work/checks.md`.
- Treat long, independent appendices or interviews as separate units.
- For each source, record which sections you kept and omitted, and why. Verification and later-pass briefs quote this list so agents do not report omitted sections as coverage gaps.

| Source | Section | Keep / omit | Reason |
|---|---|---|---|
| | | | |

Total chapter units: {N per source, summed}.

## Word Budgets

Count only retained substantive text. Exclude YAML, page markers, repeated running text, and omitted apparatus. Use one deterministic counting function for both source and summary prose, and document how it counts, including its handling of hyphenated words. The shared function is `words_in_text` in `Work/count_words.py`: it removes HTML comments, drops lines starting with `#`, and counts whitespace-separated tokens, so a hyphenated compound is one word. If Python is unavailable to an agent, that rule can be reimplemented exactly in another shell; record the fallback. Agents report counts from this function. The counts from `Work/check_words.py` are authoritative. Exclude summary headings from budget checks, and report the introduction's length separately.

For each unit, `target = retained source words × selected ratio`, and the default range is `0.85 × target` to `1.15 × target`. Each budget row has `Source slug` and `Unit ID` values matching the source frontmatter. `Work/split_parts.py` must reject duplicate keys, missing rows, and rows that match no retained unit. Fill in source counts and targets after extraction is validated and before splitting.

Treat proportional budgets as starting points and adjust them for argument density and repetition. Record substantial deviations and the resulting overall ratio. When uniform compression would cut essential qualifications or supporting evidence, keep them. Restoring source meaning under the preservation rule is a sufficient reason to exceed a range; record it as such in the deviation column. Summaries tend to land near the top of their ranges, so check the aggregate ratio after each source and before assembly, and tighten targets for the remaining sources if it is running high.

### Part 1: {Source title}

| Source slug | Unit ID | Title | Source words | Target | Range | Final words | Reason for deviation |
|---|---|---|---|---|---|---|---|
| | ch-01 | | | | | | |

Source total: {n} words; target total: {n} words (ratio {r}).

Repeat the table for each source, then give the grand total and overall ratio.

## Pipeline

### 1. Preflight

- Inspect each source's quality, layout, chapter structure, notes, figures, and tables.
- Confirm that the project scripts and their configuration entries exist. Fill in the per-source configuration in `Work/extract.py`, the `PARTS` and `INTRO` configuration in `Work/assemble.py`, and `TITLE` in `Work/build_pdf.py` (also used by `Work/build_epub.py`). Check that `Work/split_parts.py`, `Work/check_parts.py`, `Work/make_review_queue.py`, and `Work/check_words.py` work with this project's budget tables and unit keys. Run the tests: `python -m unittest discover -s Work/tests`.
- Confirm the dependencies for extraction, OCR if needed, Markdown, templating, and PDF rendering. Install `requirements.txt` and record versions, executable paths, and any installations required, including Microsoft Edge for PDF rendering, in the Preflight section of `Work/checks.md`.
- Confirm the shared writing rules at `writing-rules.md` are present, and pass them as the shared instructions for every agent. They are the only style guide agents use: their style section is guidance toward clear prose, not a checklist.
- **Agent limits.** Record each role's model, context window, and effective per-request output cap, and the file-size limits for agent inputs: a 29KB body-text target and a 32KB hard cap per assigned chapter or part source file (1KB = 1,000 bytes). Larger source files caused agent timeouts even when they fit the context window. For each task, estimate the full input and required output: instructions, source, any summary under review, and a safety margin.
- **Usage.** If the account has a usage window, record how it is read and the level at which the user stops. The default stopping level is 95% of the 5-hour window; with the default setup's subagents it takes a lot of work to fill the window, so the margin can be small. Use a different level if the user sets one. In the Claude Code desktop app the coordinator can read the plan's 5-hour and weekly windows itself (the session-management usage tool), so it can check before each batch without asking. Measure cost per task in the pilot.
- **Naming convention.** Fill in the Naming convention column of the Sources table, and `Work/author_refs.json` (format in `Work/check_author_refs.py`): every name form the summaries will use for each author, `<slug>/<file stem>` entries for interviewees and for essay authors in an edited collection, and `not_author` phrases for other people who share an author's surname. Test `python Work/check_author_refs.py <file>` and use it as `{AUTHOR_CHECK_COMMAND}` in prompts.
- **Word count command.** Test `python Work/count_words.py <file>` from the project root, then use that tested invocation as `{WORD_COUNT_COMMAND}` in prompts, including the executable path if `python` is not on PATH.
- Pick a pilot chapter complex enough to exercise extraction, splitting, and review: a chapter that will be split into parts is best.

### 2. Extraction and Validation

Reuse `Work/extract.py`. In `SOURCES_CONFIG`, give each source its file, slug, title, and part number.

- **PDF sources:** header and footer cutoffs (PDF points) and a chapter list with one-based inclusive PDF page ranges, optional printed page labels, and chapter numbers. Per-source overrides: `hyphenates` when the hyphenation detector disagrees with the page images; `space_repair` when the text layer drops space glyphs in some fonts (calibrate the em factor against known word gaps); and a chapter's `title_alt` for a heading the text layer misspells, such as an OCR error.
- **EPUB sources:** the `epub` filename and, per chapter, its XHTML `file` in the archive. Set `epub_page_anchor` to the id prefix of the print-page anchors and `epub_heading_classes` to the class attributes of the heading elements to drop. Open one chapter file to find both.
- **Paged TXT sources** (a pdftotext dump with a form feed per PDF page, when no usable PDF or EPUB exists): the `txt` filename, `header_patterns` for running heads, and per chapter its start and end PDF pages with a `first_line` prefix (and `stop_line` if the unit ends mid-page). Per-source repairs: `dehyphenated` and `hyphen_fixes` when the dump dropped line-end hyphens from real compounds, `kerning_spaces`, `line_fixes` for letter-spaced or two-line headings, `not_headings` for first lines shortened by a drop cap, and `notes` to attach endnotes printed at the back to their chapters. The commented example in `SOURCES_CONFIG` shows each setting.
- Add recurring noise to `STAMP_PATTERNS` (page furniture that can sit mid-page, such as numbers printed as "-3-") and `JUNK_LINES` (watermarks and download stamps). Presentation-form ligatures and stray punctuation-only blocks are normalized automatically.

If the script is missing, write it with PyMuPDF or an equivalent. It saves the raw extraction before cleanup.

Cleanup rules:

- Remove verified running headers, footers, watermarks, filename stamps, and redundant page numbers. Keep internal page markers.
- Repair ligatures and line-end hyphenation only when the page image or reliable extraction evidence supports the repair. Keep legitimate compounds, names, punctuation, and the source's own typos.
- Broken `ff`, `fi`, `fl`, `ffi`, and `ffl` ligatures appear as artifacts such as `confl ict` and `fi rst`. Before applying repairs, check how the detector in `Work/extract.py` defines overlap, and calibrate its threshold for each document or font against known real spaces and known artifact spaces.
- A line-end hyphen between two known words, after a known prefix, or after an acronym is kept; an unverifiable break in a document that hyphenates is joined. Both are logged as uncertain. Never turn a hyphen into a space: that splits real compounds.
- Merge page-break continuation fragments into their parent blocks during extraction, before validation. Decide whether each join falls at a word boundary or mid-word from the page image or reliable extraction evidence. Dictionaries can help, but they cannot settle an ambiguous join alone, and an unfamiliar word stays as extracted unless other evidence supports a correction. Keep page provenance for merged text.
- Log uncertain repairs. Review every `uncertain`, `-midword`, and `page-break-unjoined` line in `Work/Raw/{slug}/repairs.tsv`, and resolve any that affect meaning against the original page before accepting the chapter.
- When extraction misses substantive figure or table content, add a faithful transcription or description to the chapter file. Mark it as a visual transcription or description and give its original page. Include the labels, units, values, and qualifications a reader needs, verify the addition against the original, and do not infer values the source does not report. Count this text once in the chapter budget. If essential visual content cannot be represented reliably, block the unit until it is resolved.
- Preserve reading order, table labels, and the links between body text and substantive notes. Keep material that looks like apparatus if it carries substance.
- Mark block quotations, epigraphs included, with a Markdown `> ` prefix on each quoted paragraph (after a leading page marker), so agents can tell another speaker's words from the author's prose. Summaries reproduce a block quotation whole and exact or drop it entirely (the block-quotation rule in `writing-rules.md`). The word counter ignores the marker and the splitter never splits inside a quotation. For TXT sources, `"block_quotes": True` detects quotations from colon lead-ins, citations set after the closing punctuation, and dash-attributed epigraphs; review every `blockquote-*` line in `repairs.tsv` other than plain `blockquote`, list every marked quotation with its lead-in and the paragraph after it, and record corrections in `block_quote_fixes`. For PDF sources detect them from indentation or font size, and for EPUB sources from `<blockquote>` elements; neither is implemented yet.
- List the detected headings for each source. A two-line heading split at its line break leaves its second line glued to the next paragraph; repair it in the config.
- Do not paraphrase or silently correct substantive content.

Validate every chapter boundary and page mapping. Then sample pages across each source, including difficult layouts and repaired text, and compare substantive tables and figures with the original. The offset between PDF and printed page numbers can change within a document, so check mappings in more than one place. Check that no presentation-form ligature or U+FFFD replacement character remains in any chapter file.

Record checks and open extraction issues in the extraction section of `Work/checks.md`. Resolve issues that affect meaning before summarizing the unit. If the content cannot be recovered, mark the unit blocked and report the limitation.

### 3. Size Limits and Chapter Splitting

Two limits govern task size.

- **Model limits.** Keep a chapter in one task only if the whole task, review inputs included, fits the model's usable context with a safety margin, and the expected output fits the effective output cap.
- **Agent runtime.** Agents given whole chapters of up to 125KB fit within the context window but spent long periods thinking and timed out. Do not assign a summarizer or reviewer a source file over the 32KB hard cap.

Splitting leaves validated source text unchanged. If text needs repair, go back to extraction and validation.

Run `Work/split_parts.py` on all chapters. It builds the processing manifest and splits chapters that exceed the limits:

- Each part targets 29KB of body text. The hard cap is 32KB, measured as the UTF-8 byte size of the complete part file, including frontmatter and overlap context. Split at paragraph boundaries where possible. A part may run past its target, up to the cap, when the next safe boundary is beyond the target. Split a block at sentence boundaries only if it cannot otherwise fit in a complete file under the cap. If a remainder cannot fit without splitting a sentence, the script flags it and it is not assigned to an agent. You must then resegment it without losing source content, or block the unit.
- Once a part passes about 20KB, prefer to split just before a detected section heading. If less than about 6KB would remain for a new part, add it to the current part instead, provided that stays under the hard cap. Otherwise keep the small final part.
- Each chapter budget is divided among its parts in proportion to their word counts. Each part file's frontmatter records `part_index`, `part_count`, and the part's `word_budget`.
- Parts are written to `Work/Chapters/{slug}/parts/{NN}-...-part{k}-of-{m}.md`, along with the parts manifest (`Work/parts_manifest.json`) and split report (`Work/parts_report.txt`) that drive agent runs. Each processing entry has `source_slug`, `unit_id`, `part_index`, and a `status` of `pending`, `drafted`, `accepted`, or `blocked`. Only you, the coordinator, update status, with `Work/set_status.py`, after checking the output and review record. Unsplit chapters appear as single processing units with `part_index: 1`, `part_count: 1`, the chapter budget, and their actual source, draft, summary, and review-record paths. The review queue and word-count checks cover every split part and every unsplit chapter.

Before summarizing, run `Work/check_parts.py`. It checks that boundaries fall between sentences, that each complete file is at or under 32,000 bytes in UTF-8, and that word counts exclude metadata and all context copies. It also rebuilds each validated chapter from its ordered owned text slices, leaving out generated frontmatter, wrappers, and context copies. The rebuilt text must match the chapter body exactly, including original whitespace and internal page markers. The check rejects missing, duplicated, reordered, or altered text. Record results in `Work/checks.md`, and rerun the check after any boundary or context change.

#### Context between parts

Each part summarizer and reviewer gets a single `SOURCE` file containing all the evidence it needs. Put any original-source context from outside the part inside that file, in delimited blocks naming the owning unit and part. Do not hand out separate context files. Context blocks count toward the 32KB file cap but are excluded from owned-text reconstruction, source word counts, and budgets.

Overlap context is added automatically. Each part after the first opens with the final block or blocks of the previous part, wrapped in comment markers and excluded from `word_count` and `word_budget`. Set the number of blocks with `OVERLAP_BLOCKS` in `Work/split_parts.py` (default 1; 0 turns overlap off). The script drops overlap that would push a part over the hard cap.

Overlap carries context only backward, so inspect every part boundary after splitting, using the split report and the `Work/check_parts.py` output. Add original-source context, from either direction, wherever a split separates a term from its definition, a claim from its evidence, or a passage from a qualification or conclusion in the next part. Also inspect every boundary where the script dropped overlap, and add any context it needs. Record added context in `Work/part_context.json`, not in the part files, so rerunning the splitter keeps it: each entry names the receiving part by `source_slug`, `unit_id`, `part_index`, and `part_count`, and gives the exact chapter text. The splitter locates the owning part, inserts the block, and reports entries it cannot match. If the context won't fit, reserve room or move the boundary, then recheck size and ownership.

Each source passage belongs to exactly one part, and only that part summarizes it. Other parts may use it to interpret or qualify their own claims. Record any change of ownership in the parts manifest. Before merging, check adjacent summaries for duplicated coverage, keeping any qualifications needed for accuracy.

If context adjustments change a part's evidence after drafting has started, reset the affected review statuses and repeat those reviews before acceptance. When a chapter is too large to compare with its summary in one context, verify coverage part by part and check the transitions separately.

### 4. Pilot

Take one representative chapter through extraction, summarizing, review, merging, and rendering. Assemble it alone by listing it in `PILOT_UNITS` in `Work/assemble.py`, and clear `PILOT_UNITS` afterwards. Evaluate fidelity (including the preservation audit in the review record), coverage, length, readability (including `Work/check_author_refs.py`, and a read for pronoun chains it cannot count), extraction quality, and PDF layout, and adjust prompts and budgets before scaling up. Record the usage cost per task.

Get the user's approval of the finished pilot unless they have already authorized you to continue without it. Record the decision.

### 5. Summarization

Run one agent per part, or per chapter if the chapter was not split, with the Summarizer prompt in `prompts.md`. Each agent writes a draft to `Work/Drafts/{slug}/` (part drafts go in `Work/Drafts/{slug}/parts/`). Run at most 6 agents at once. Raise that number only after clean batches and within provider and usage limits. List the next pending units with `python Work/set_status.py pending`.

Part drafts are prose with no headings; the merge adds the chapter heading. Unsplit chapter drafts start with `## {Chapter Title}`.

Keep the original drafts. Reviewers read from `Work/Drafts/` and write directly to `Work/Summaries/`, so you don't need to copy files between them. Allow one writer per file at a time. Retry failed units individually, and check completed outputs before updating their status. A transient API failure, such as an HTTP 5xx error, usually succeeds on immediate retry; retry before reworking the unit.

A blocked part blocks its whole chapter. Merge a split chapter only after every part is accepted, and accept the chapter once the merge and chapter-level checks pass. A partial deliverable may leave out a blocked chapter entirely if the limitation is disclosed, but a chapter with missing parts cannot be accepted. For unsplit chapters, `set_status.py part` keeps the processing-entry status and chapter status in sync.

If a run stalls or is interrupted, archive the affected outputs before rerunning (for example, to `Work/Summaries_archive_v1/`). Re-review every part whose review status is uncertain instead of resuming from it.

### 6. Chapter Review

Assign one fresh-context agent per part or chapter with the Reviewer prompt in `prompts.md`. It reads the source and the original draft, writes the reviewed summary to `Work/Summaries/`, and saves a review record in the fixed format the prompt gives, including the contrast audit and number audit required by the preservation rule. In later rounds it starts from the latest reviewed summary instead of the original draft. Fresh context helps reviewers catch errors, but they can still miss errors or introduce new ones. Sonnet 5.5 at high effort drafts and Opus 5.5 reviews (see Agents).

Build the queue with `Work/make_review_queue.py` and work through it in batches. After each batch:

1. Run `Work/check_words.py` to flag summaries outside their budget range. Send each outlier to a reviewer, who either trims it without losing meaning or records a justified exception, such as restored source meaning. After an outlier edit, the reviewer checks the edited passages against the source, reruns the count, and updates the review record.
2. Run `python Work/check_author_refs.py` on the batch's summaries. Each paragraph it still flags must appear in the review record's author-naming line, with the other speaker that justifies the second reference. Send any other flagged paragraph back to the reviewer.
3. Read each review record. Reject a record whose audits are missing or whose "Omissions kept" section lists a dropped contrast, hedge, attribution, or claim-evidence pair; those are material errors, not omissions.
4. Set statuses with `python Work/set_status.py part accepted <slug> <unit_id> <part_index> ...`. While edits await verification, set previously accepted units back to `drafted`; a split chapter loses `accepted` status automatically when a part reopens.

Review in this order:

1. Accuracy and attribution: check claims against the source, including names, numbers, dates, uncertainty, negation, chronology, causal strength, and whose position is reported.
2. Preservation: the binding rule in `writing-rules.md`.
3. Coverage: work from the source to the summary to find missing main arguments, consequential qualifications, and supporting evidence.
4. Style and length: improve readability without changing meaning. Make local corrections where they are enough, instead of broad rewrites.
5. Final accuracy check: after all additions, cuts, and style edits, recheck the summary against the source, with particular care for every changed substantive claim.

Reviewers write consequential corrections, supporting page or passage references, budget deviations, and unresolved issues to `Work/Reviews/` and keep them out of final prose.

When the extracted source is ambiguous or incomplete, the reviewer flags it for you to check against the original and does not reconstruct missing facts. A unit with an unresolved material issue cannot be accepted.

### 7. Merge Multi-Part Chapters

Unsplit chapters skip this step; their reviewed summaries are already at the final path.

By default, merge with `python Work/merge_chapters.py`. It concatenates each ready chapter's reviewed part summaries in order, adds one `## {Chapter Title}` heading, writes the result to `Work/Summaries/{slug}/NN-slug.md`, and reports the chapter's count against its budget. It refuses a part summary that contains frontmatter, an HTML comment, or a heading; in one run a reviewer copied its source's frontmatter and owned-text markers into its summary. Then build `Work/transition_queue.txt` with `python Work/make_transition_queue.py` and run one Transition reviewer (`prompts.md`) per chapter. Each seam review uses the adjacent summary passages and the matching original passages, within the source-file cap and the model's limits, widening the passages only as far as meaning requires.

You can use a single merge agent instead when the combined reviewed part summaries are 32KB or less in UTF-8 bytes and the full task, including instructions and output, fits the model's limits with a safety margin. If a merge agent stalls, switch to the script and separate transition reviews. The merge agent reads the reviewed part summaries in order and does not read the chapter source.

Either way, the merge keeps the parts in order, smooths abrupt transitions at part boundaries, and removes duplicated framing, without adding or dropping substantive claims. The total should stay within the chapter budget and tolerance. If accuracy requires a deviation, record it and the reason. Before the merged chapter is accepted, you or a fresh-context agent must check every edited transition against the original passages. Run `python Work/check_author_refs.py` on the merged file, because two parts that each open with the author's name can put two references in one paragraph at the seam. Then check the merged file against the parts manifest: each part appears exactly once and in order, and the chapter is within budget or has a documented, justified deviation. Accept it with `python Work/set_status.py chapter accepted <slug> <unit_id>`.

After merging, `Work/Summaries/{slug}/parts/` is stale: later edits go to the canonical chapter summary only.

### 8. Assembly and Whole-Document Review

Reuse `Work/assemble.py` with updated `PARTS` and `INTRO` configuration. The script reads `Work/manifest.json` and includes only units marked `accepted`, because `Work/Summaries/` also holds reviewed files for blocked units. It rejects missing, duplicate, or unmatched units, missing or extra headings, leftover markers, page references, footnotes, working-file references, leaked review notes, and unfilled placeholders, and follows the manifest's part and chapter order. `Summary.md` has this structure:

- `# Introduction`: a short note naming the sources, scope (including sections omitted by decision), and organization, with no substantive claims. Ask the user whether it should say that each source is reproduced as printed, errors included.
- `# Part N: {Title} by {Author}`: names the source and author(s).
- `## {Chapter Title}`, with optional `###` topic headings. Decide whether `###` headings are used for every source or none, so parts look consistent.
- No inline citations, footnotes, or page references in final prose. Mark other speakers' views in the prose where needed; the author's own views need no attribution.

Check the assembled document for missing or duplicate units, wrong order, heading errors, leftover internal markers, and leaked review notes. Run `python Work/check_author_refs.py` over every accepted summary. Compare the body word count with the aggregate target and record the overall ratio.

Then run the whole-document review. Build chunks with `python Work/make_doc_chunks.py` and assign one fresh-context Whole-document reviewer (`prompts.md`) per chunk. It reads as someone unfamiliar with the sources, checking terminology, unexplained cross-chapter references, repetitive framing, and readability. It is report-only and must not fact-check: in one run, nearly every "error" these reviewers flagged was a claim the summaries faithfully reproduced from their sources. Chunks cross source boundaries on purpose; also inspect transitions across chunk boundaries yourself. Keep substantive differences between authors and any repetition that belongs to their arguments.

After any prose edit, including changes to terminology, transitions, or framing, verify it against the relevant original chapter passages. Verify the introduction's statements about sources and scope against source metadata and the scope inventory. Record verification before restoring `accepted` status. Make chapter edits in the canonical chapter summary and reassemble, so later builds keep them.

If blocked units remain at assembly, the deliverable is partial. Record each blocked unit's reader-facing limitation in `LIMITATIONS` in `Work/assemble.py`; the script then adds a partial-deliverable notice to the introduction. Record results in the assembly section of `Work/checks.md`.

### 9. PDF Rendering and Inspection

Reuse `Work/build_pdf.py`. Set `TITLE` for this project and change the rest only as needed. By default, the script converts Markdown to styled HTML with Python Markdown and Jinja2, then prints it to PDF with headless Microsoft Edge (`--print-to-pdf`). If you use a different renderer, record the change. Default layout: Letter pages, one-inch margins, 11pt serif text. If the renderer does not add page numbers, add them with PyMuPDF, and make sure browser headers and footers don't duplicate them. Headless Edge can fail inside an agent's sandbox (no PDF, nonzero exit); run the build outside the sandbox and record it.

Inspect the PDF for missing text, clipped content, broken characters, blank pages, stranded headings, bad page breaks, and misplaced page numbers. Check programmatically with PyMuPDF: page count, blank or thin pages, U+FFFD characters, every `#` and `##` heading present in the PDF text, and no leftover `Work/`, `.md`, `<!--`, or page-reference strings. Then inspect the first and last pages and the start of every part visually. Confirm that the PDF text matches the final Markdown. Fix problems, rerender, and record results in the PDF section of `Work/checks.md`.

Optionally build `Summary.epub` with `python Work/build_epub.py` (requires `ebooklib`): one EPUB page per chapter, grouped by part in the table of contents.

### 10. Independent Verification

Once all chapters are accepted, run the verification pass in `passes/verification-pass.md`: a report-only check of a sample of chapters by a stronger model than the one that drafted them, triage, a scope decision with the user, and remediation rounds under the preservation rule. Copy the brief to the project root and keep its status tables there. Skip it only if the strongest available model drafted and reviewed every chapter under the current prompts and the user agrees; record the decision. Under the default setup Sonnet 5.5 drafts, so that condition is not met and the pass runs by default; skipping it is the user's call, and the decision is recorded. The verifiers are fresh-context Opus 5.5 agents that never saw the chapters they check.

After remediation, update the Final words and deviation columns in the budget tables, reassemble, rebuild the PDF, and record the pass in `Work/checks.md`.

### 11. Later Passes

Each later pass has its own brief at the project root, copied from `passes/`, which is also its item list and status record. Agents read that brief (only through its "Agent prompt" section), `writing-rules.md`, and their assigned files. Common rules for every later pass:

- Snapshot the affected canonical summaries with `python Work/snapshot_summaries.py <pass>` before the first dispatch. Never refresh or reuse an earlier snapshot.
- Edit with targeted string replacements, never by regenerating a file. Never apply one replacement across many paragraphs or files (for example a pronoun or a name): that is how one run filled a summary with the author's name. Recast each paragraph under the naming rule, then run `python Work/check_author_refs.py`.
- Agents fix only what the pass covers and log anything else under New reports. The next pass, if the user wants one, acts on that log.
- The coordinator gates every batch: diff against the snapshot and revert unexplained hunks, check changed numbers, names, and quotations at the cited page, and commit the batch with its progress count.
- Rebuild `Summary.md` and the PDF once at the end of each pass, inspect the changed pages, and add an entry to `Work/checks.md`.

Passes used in earlier runs, in order:

1. **Style pass** (`passes/style-pass.md`). Prose only, no source access, gated by `Work/check_style_pass.py`. Its agents report suspected factual problems instead of fixing them.
2. **Targeted fix passes** (`passes/targeted-fix-pass.md`). Resolve reported items against the chapter source, one pass per report list. Rank long lists into tiers and stop where the user decides.

## Operations

- **Handoff.** Keep a Project Status section at the end of this plan current: what is complete, the next pending units, decisions and gotchas, and the commands in use. A new session should be able to resume from it and `Work/checks.md` alone. Each pass brief keeps its own cold-start handoff.
- **Usage.** Where the account has a usage window, check the current reading before each batch in a costly pass (read it yourself in Claude Code, or ask the user), never start a batch that could cross their stopping point, and log readings in the pass brief.
- **Commits.** Commit after each batch with the pass name and progress count ("{pass}: {source} ch-03 to ch-08 (24 of 90)"), and after each rebuild.
- **Parallel agents.** Tell agents that others are editing other files in parallel and to ignore those changes in git status.
- **Settled decisions.** When the user settles a recurring question (spelling variants, `%` against "percent", quote style), record it in the relevant brief so agents stop raising it.

## Completion Criteria

- Every substantive unit is accounted for, and scope exclusions are documented.
- Extraction and chapter boundaries are validated for accepted units, and uncertain repairs are reviewed. Units with unresolved material ambiguities stay blocked.
- Every chapter or part source file given to a summarizer or reviewer, including transition-review excerpts, is at or under the 32KB hard cap, and part boundaries are sentence-aligned and validated. Drafts, summaries, and shared instructions are checked against full-task context and output limits instead of this cap. Single-agent merges meet the 32KB combined-summary limit in Section 7.
- The ordered owned source slices rebuild each validated chapter exactly. Generated metadata and context copies are excluded from reconstruction, and metadata, page markers, and context copies are excluded from source word counts.
- Part statuses are recorded, and no accepted chapter contains a blocked or unreviewed part.
- Original drafts, review records, and pre-pass snapshots are preserved.
- Every review record includes the preservation audit, and every final chapter was checked for accuracy after its last substantive or style edit.
- Independent verification ran, or the decision to skip it is recorded.
- Each merged chapter contains every part exactly once, in order, and every transition the merge edited has been verified against the original passages.
- Budgets are measured, the overall ratio is recorded, and meaningful deviations are explained. No summary was padded or stripped of essential content.
- Whole-document consistency and completeness checks passed.
- `Work/check_author_refs.py` flags no paragraph, apart from those whose review records justify a second reference to the author.
- `Summary.md` and `Summary.pdf` match, and the PDF layout has been inspected.
- `Work/checks.md` has an entry for every stage and pass.
- Unresolved material limitations are disclosed, and no affected unit is marked accepted.
- No blocked units remain, or the deliverable is labeled partial and lists the omitted units and their limitations.

## Status

- [ ] Sources, scope, dependencies, style instructions, and each author's naming convention recorded
- [ ] Agent models recorded (default: Sonnet 5.5 at high effort for the summarizer, Opus 5.5 in every other role); usage limits recorded
- [ ] Page mappings and chapter segmentation confirmed
- [ ] Raw extraction preserved, uncertain repairs reviewed, and cleaned output validated
- [ ] Word budgets and context-size checks completed
- [ ] Oversized chapters split into parts at or under the 32KB hard cap; boundaries validated and inspected
- [ ] Pilot summarized, reviewed, merged if split, rendered, and approved or authorized to proceed
- [ ] Remaining drafts completed in batches of up to 6
- [ ] Reviews, preservation audits, and final accuracy checks completed; review records saved; word-count checks passed
- [ ] Multi-part chapters merged, transitions reviewed, and verified against the parts manifest
- [ ] Accepted chapters assembled into `Summary.md`; overall ratio recorded
- [ ] Whole-document review completed and changes verified
- [ ] `Summary.pdf` rendered and inspected
- [ ] Independent verification and remediation completed, or skip recorded
- [ ] Later passes completed as agreed with the user; each rebuilt and recorded
- [ ] Completion criteria checked and deliverables supplied

## Project Status (handoff)

{Date: what is complete, what is in progress, and the next pending units, in manifest order.}

Decisions and gotchas:

- {Decision, with date and whether the user made it.}

Commands: `python Work/extract.py`; `python Work/split_parts.py`; `python Work/check_parts.py`; `python Work/make_review_queue.py`; `python Work/check_words.py`; `python Work/count_words.py <file>`; `python Work/check_author_refs.py [<file> ...]`; `python Work/set_status.py pending|part|chapter ...`; `python Work/merge_chapters.py [--dry-run]`; `python Work/make_transition_queue.py`; `python Work/assemble.py`; `python Work/make_doc_chunks.py`; `python Work/build_pdf.py`; `python Work/build_epub.py`; `python Work/snapshot_summaries.py <pass>`; `python Work/check_style_pass.py`; `python -m unittest discover -s Work/tests`.
