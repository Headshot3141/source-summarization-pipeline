# Source Summarization Plan Template

Before the pilot, fill in the sources, scope decisions, chapter inventories, budgets, and environment details. Check the project's existing scripts first. Reuse or adapt them, and write any that are missing.

This plan is for the coordinator. Agents never read it, with one exception: extraction agents read Step 2, which holds the cleanup rules and the `repairs.tsv` kinds they apply. Every other agent gets a filled-in prompt from `prompts.md` or a pass brief from `passes/`, plus `writing-rules.md` and `settled.md`. Keep the rules agents need in those files, not here. A new session reads `status.md` first.

## Goal

Produce `Summary.md` and a PDF (and optionally an EPUB), a standalone summary of one or more source documents with one part per source and one section per chapter or logical unit. The PDF and EPUB are named from `TITLE` in `Work/build_pdf.py` ("The Grey Harbour: Essays" gives `The-Grey-Harbour-Essays.pdf`; the default is `Summary.pdf`).

The summary body as a whole is about 50% of the retained substantive source word count, and never more than 55% unless the user approves more. Two stages get there:

- **Drafting at 0.40.** Each summarizer drafts its unit to about 40% of the unit's source words (its budget), within ±15%.
- **Review room of 0.10.** Review and later passes may grow a unit by up to another 10% of its source words (its ceiling) where clarity or fidelity needs it: restoring a dropped qualification, a reasoning step, or an antecedent, or recasting a sentence compressed past easy reading. Above the ceiling, only the preservation rule, or a restored main argument, reasoning step, or piece of evidence a kept conclusion needs, justifies more words, and the record names what was restored.

Units may end up shorter or longer than 0.50, as long as the document stays around 0.50 and at or under 0.55. `Work/check_words.py` prints the running ratio per source and for the document after every batch, and a projected ratio (reviewed words plus the ceilings of units not yet reviewed). Do not pad a summary or cut essential qualifications to hit a target. The ratios are set in `Work/common.py` (`DRAFT_RATIO`, `REVIEW_ALLOWANCE`, `DOC_TARGET`, `DOC_MAX`).

A summary condenses its source in the source's own order, as "Shape of a summary" in `writing-rules.md` describes: two pages of source become about one page of summary, with minor material left out and no structure added that the source lacks.

## Priority Order

1. Fidelity to the source, including uncertainty, attribution, negation, and causal strength.
2. Coverage of the main arguments and the evidence needed to understand them.
3. Clear, standalone prose.
4. Style preferences and word targets.

Report what each source argues. Do not endorse, refute, fact-check, or add outside context. The summary speaks in the author's voice and states the author's views directly, without "the author argues"; only views that belong to someone else (quotations, allegations, objections, and views the author describes or rejects) are marked as such. Reproduce each source as printed, errors included: a summary that silently corrects its source is wrong.

## Agents

The pipeline uses **Claude Sonnet 5.5 (`claude-sonnet-5-5`) at high effort for the summarizer** and **Claude Opus 5.5 (`claude-opus-5-5`) for every other role**: preflight inspector, extraction agent, boundary inspector, reviewer, merge and transition reviewer, whole-document reviewer, verifier, and later-pass agents. The coordinator is a Claude Code session (desktop app) that dispatches each agent as a subagent with the Agent tool. Summarizers use the `summarizer` agent type (`.claude/agents/summarizer.md`, which sets `model: claude-sonnet-5-5` and `effort: high`), because the Agent tool cannot set effort per call. All other roles are dispatched with `model: "opus"`. The coordinator can therefore watch every agent directly: it receives each agent's completion report, can message a running agent, and reads the account's usage windows itself. The coordinator still checks every output file and review record before it changes a status.

Every prompt is written to a file by `Work/make_prompts.py`, and each agent is dispatched with one line naming that file ("Read Work/Prompts/batch-03/summarizer-4.txt and follow it exactly"). Reviewers never see the summarizer's reply.

Opus 5.5 in Claude Code does not silently truncate long outputs. A probe on 2026-09-26 had an Opus 5.5 subagent write 8,669 words (160 paragraphs) in a single Write call. The file was complete, with its end sentinel present, and no call was cut off or returned an error. That is several times the longest output this pipeline asks of any agent. The probe tested the harness: Claude Code imposes no cap below the model's limit. Sonnet 5.5 has the same 128K-token output limit as Opus 5.5, so the result covers the summarizer too, and no output-cap probe is needed.

Every draft is written by Sonnet 5.5 and reviewed by a fresh-context Opus 5.5 agent, so no agent reviews a file it wrote, and review is done by a stronger model than drafting. See Step 9 for the verification decision. A test in one run redrafted two pilot parts with Haiku 5.5 at its highest effort: its drafts needed about as many fidelity corrections as Sonnet's (49 against 55), but ran 19-37% over their ranges because it read the preservation rule as forbidding any cut to a hedged claim, and to resize it then cut main arguments whole; its reviewed parts ended 14-19% over their ceilings. Sonnet was kept. Do not repeat the test unless the models change.

## Lessons from earlier runs

These shaped the rest of this plan. Read them before the pilot.

- **Word budgets say nothing about fidelity.** In one full run, every chapter was accepted inside its budget, and an independent check with a stronger model then found material errors in most sampled chapters. All of them made the summary more assertive than its source: dropped contrast reversals, hardened hedges, attribution drift, pronouns resolved to the wrong actor, orphaned evidence, and computed totals. The reviewer had seen many of these and accepted them as omissions. The fix was an enumerable preservation rule with an audit, which now lives in `writing-rules.md` and the reviewer prompt from the start, and an independent verification pass (Step 9).
- **Agents fact-check from memory.** Whole-document reviewers and style-pass agents "corrected" dates and names that the summaries reproduced faithfully from their sources. Every brief forbids outside knowledge, and the coordinator checks any reported error against the chapter source before acting.
- **Every pass leaves reports behind.** Passes that may not fix what they notice log it, and the next pass resolves the log. Plan for a report-then-act sequence after the main run (Step 10), and decide with the user where to stop.
- **Usage windows, not chapter counts, set batch size.** Measure cost per task in the pilot and again at the start of each session: in one run the cost per agent varied about fivefold between sessions for similar token counts.
- **Per-chapter ranges do not bound the total.** Chapters clustered near the top of their ranges, and the overall ratio ran well above the target. Prompts now tell the summarizer to aim at its budget and treat the range as a tolerance, and `Work/check_words.py` prints the running ratio after every batch and fails above 0.55.
- **Compression by squeezing hurts clarity.** Summaries that met tight budgets by stripping articles, connectives, and antecedents were accurate but hard to read. The rule now is to leave out whole minor points before squeezing sentences, and review has room (the ceiling) to expand a sentence compressed past easy reading.
- **Attribution applied sentence by sentence buries the prose in the author's name.** In one run, a book's summary named its author 329 times in about 27,000 words, and 124 sentences opened with the name. Agents attached "X argues" to every claim, and verification added more. Then a pronoun rule (the source never gendered the author, who wrote in the first person) was applied by replacing every "he" with the name across the files. The fix is the naming rule in `writing-rules.md`: the summary speaks in the author's voice, states the author's views without attribution, and names the author only where a sentence needs it, at most once per paragraph. Only other speakers' views are marked. `Work/check_author_refs.py` enforces the cap, and every prompt carries the source's naming convention from the start. Never fix pronouns or names by mechanical find-and-replace: recast each paragraph.
- **Room gets used.** Agents given room up to a cap use nearly all of it. In one run reviewers ran to their ceilings, a full pass with 110% caps grew almost every chapter to its cap, a verification round allowed 5% grew the document 4.7%, and a fix pass told to restore every listed omission grew its pilot chapters 17-53%. A fix pass held to the budget then declined about 1,000 omissions, and two later passes, after the user raised the limit, restored about 800 of them. The standard pipeline through Step 11 added under 4% after review; only the extra passes pushed the document past 0.55. Decide the length policy with the user once, after Step 9's first round (Step 10, "Length decision"), set each cap at the growth you will accept, and pilot any pass that can add words before running the rest.
- **Material errors run out; minor ones move.** In one run, material findings per chapter fell from about 2 (the first full verification) to 1 in 74 chapters, then to none. Each further full read still found one to four minor items per chapter, and most sat in text the previous round had written: an inserted sentence that became the nearest antecedent of the next sentence's "they", a sentence moved so a group's position read as the doctrine it rejected, a restoration with a gapped verb. So every editing rule now says to reread the sentences around an edit, every gate checks paragraph structure, any pass that adds more than a few words per chapter is followed by an independent check, and once a round finds no material error the user decides whether more rounds are worth the length they add.
- **What survives is small.** After five verification rounds, a report-only validation run confirmed about 1.2 findings per 1,000 words, with a median suggested fix of three words: a dropped scope word ("modern", "main", "only"), an example marker ("for example"), a verb of degree hardened ("contributed to" made "raised"), a pronoun standing in for the source's noun. `Work/check_qualifiers.py` lists dropped hedge, scope, and example markers, and the reviewer and verifier records now settle each flag and name each pronoun's referent.
- **Finders over-report; refute before fixing.** In that validation run, 1,009 findings were reported and a refuting verifier rejected 712, most because the summary reproduced its source or the omission was ordinary compression. A fix pass would have spent an agent declining each of them. Report-only finders followed by a refuting verifier (`passes/validation-run.md`) is the right shape for a late, large check.
- **Write the tools once.** The coordinator of one run wrote about 40 one-off scripts during its passes, a prompt generator and a gate for each pass, each copied from the last; several copies carried a bug the next copy fixed. The template now ships `Work/make_prompts.py`, `Work/gate_pass.py`, `Work/collect_items.py`, and `Work/raise_exceptions.py`, and every brief names them.
- **Old sources need modern wording.** A summary that shortens a nineteenth-century text or an old translation but keeps its vocabulary and sentence shapes is as hard to read as the original. One run wrote such sources' summaries in plain modern English under a register rule, and its final validation still found old idiom left in several of them. The register is set per source in Preflight, and every prompt and brief carries it.
- **Rulings scatter.** Settled decisions (printed faults kept, misprint readings, notation, the author's first person) were copied into four briefs and the prompt generator, and agents in one pass undid rulings that sat only in an earlier brief. They now live in one file, `settled.md`, which every agent reads.

## Sources

| Part | Source file | Format | Extract from | Author(s) | Date of the English text | Register | Role | Draft ratio | Naming convention |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `Sources/<file>.md` | Markdown (docling) | docling Markdown | | | modern / source | | 0.40 | |
| 2 | `Sources/<file>` | EPUB | EPUB | | | modern / source | | 0.40 | |

The register sets the clarity rules (`writing-rules.md`, "Register"). Older prose is hard for a present-day reader, so a source whose English dates from before 1950 (a nineteenth- or early twentieth-century text, or a translation made then) is `modern`: its summary is written in plain modern English, recasting old sentence structure, archaic words, dated address, and bookish or translated-sounding phrasing, while terms of art, names, numbers, quotations, the author's images, and the author's tone stay exactly as printed, and a block quotation may be given as attributed paraphrase. A source whose English dates from 1950 or later is `source`: the normal clarity rules, which recast a hard sentence where the source makes the meaning certain and otherwise keep the source's vocabulary. Date a translation by the translation, not the original, and set a later translation that reads as antiquated to `modern`. Set it in the source's extraction config (`"register"`, with a per-chapter override for a collection that mixes old and new texts); extraction writes it into each chapter's frontmatter, and `Work/make_prompts.py` puts it in every prompt. A config without the key is extracted as `source` with a warning. Set it before extraction: changing it later rewrites the chapter files, which, like any change to a chapter source, resets the affected units' statuses when `Work/split_parts.py` runs again.

"Extract from" is the text the extraction actually reads, chosen in Preflight: the docling Markdown, the PDF's text layer (directly, or through a paged TXT dump when chapters start and end mid-page), or an EPUB of the same edition. One run used all four across 23 sources.

The naming convention is how the summaries refer to each author: the name form ("Penhale", "the authors" for a co-written book), and the pronoun the source uses for the author, or "no pronoun" when the source never genders the author. Never infer a pronoun from a name. Say whether the author's own first person ("I", "we") may stay as the author's voice (recasting it can change the meaning; see `writing-rules.md`, "First-person passages"). Name the other speakers the source quotes or discusses at length, and anyone who shares the author's surname. For an interview collection or an edited volume, say whose voice each unit is in (normally the interviewee or the essay's author) and name the interviewer or editor as another speaker, each with a pronoun or "no pronoun"; a unit in another writer's voice (an editor's introduction) gets its own convention. Settle it in Preflight, with the user if the source is unclear, and write each one into the `conventions` key of `Work/author_refs.json`, from which `Work/make_prompts.py` fills `AUTHOR` in every prompt. It always comes with the naming rule.

The usual source format is Markdown that the user converts from PDF with docling before the file goes into `Sources/`; the coordinator never runs the conversion. Ask the user to export with page-break placeholders (docling's `export_to_markdown` with `page_break_placeholder="<!-- page break -->"`): without them the chapters carry no page markers, and every record must cite a short exact quote instead (no export in one run had them). For agents, that Markdown is the source. Check the conversion in Preflight (Step 2 lists what to look for). For a PDF used directly, check whether the text layer is usable. Run OCR on scanned PDFs and on the scanned pages of mixed PDFs. Text extraction can miss figures, tables, and captions, so inspect them when they support substantive claims. When a PDF's text layer is damaged (ligatures mapped to wrong characters, missing spaces) and an EPUB of the same edition exists, extract from the EPUB. Confirm titles and authors from the title page, not PDF metadata.

## Directory Layout

```text
.claude/agents/summarizer.md        summarizer agent type: Sonnet 5.5, effort high
Sources/                            original documents, untouched
Work/
  extract.py                        extraction and cleanup (docling Markdown, PDF, EPUB, TXT); --check re-extracts and compares
  SourceConfigs/<slug>.py           one extraction config per source (README.md lists every key)
  source_helpers.py                 helpers for configs: line-numbered edits checked against the source
  md_toc.py                         Preflight: a Markdown file's heading table, running heads, and placeholder counts
  check_chapters.py                 scans chapter files for leftover characters, joins, and unfinished paragraphs
  Preflight/<file>.report.md        one inspection report per source (passes/preflight-inspection.md)
  Extraction/<slug>.md              one extraction report per source (passes/extraction.md)
  Proof/                            OCR proofreading fixes per source (passes/proofread.md)
  split_parts.py                    splits chapters into parts at or under the 32KB hard cap; --dry-run
  check_parts.py                    checks source reconstruction, boundaries, sizes, and counts
  part_boundaries.json              hand-set part boundaries, as the first words of the paragraph a part starts with
  part_context.json                 extra original-source context for parts, applied by split_parts.py
  budget_exclusions.json            chapter text left out of the budget basis (citation-only notes, in-chapter apparatus)
  Boundaries/                       boundary inspectors' records and proposals
  make_review_queue.py              builds the review queue from the parts manifest
  make_prompts.py                   fills a prompt template per unit into Prompts/<out>/; --ready lists tasks to dispatch
  Prompts/<batch or pass>/          generated prompts, index.txt, notes.json, items/, gate_log.md, and any run scripts
  check_words.py                    checks word counts against budgets and ceilings; running and projected ratios; --json
  budget_exceptions.json            settled word-count flags, so check_words.py stays usable as a gate
  raise_exceptions.py               after a gated pass, raises the exceptions of chapters the pass grew
  fill_final_words.py               fills the Final words column of the budget tables
  check_fidelity.py                 flags numbers, quotations, block quotations, and names not in the source
  check_qualifiers.py               lists dropped hedge, scope, and example markers, outside references, spelling variants
  make_verify_queue.py              lists verification tasks per part (or per whole chapter), with neighbouring parts as context
  check_author_refs.py              flags paragraphs that refer to the same author or speaker more than once
  author_refs.json                  name forms per source and unit, and each naming convention for the prompts
  count_words.py                    shared counting function and single-file word-count command
  common.py                         shared paths, frontmatter parsing, owned-text markers, and text checks
  set_status.py                     coordinator status updates, kept in sync across both manifests
  merge_chapters.py                 concatenates accepted part summaries into chapter summaries
  make_transition_queue.py          lists merged chapters for transition review
  make_doc_chunks.py                groups accepted chapters (three by default) for the whole-document review
  snapshot_summaries.py             snapshots chapter summaries before a later pass
  check_style_pass.py               gate for prose-only passes: diff against the snapshot
  gate_pass.py                      gate for editing passes: every change matched to its record, plus the checkers
  collect_items.py                  gathers reported items into one file per chapter for a fix pass
  apply_replacements.py             the coordinator's own edits, checked and applied as exact replacements
  Introduction.md                   the summary's introduction
  assemble.py                       ordered assembly and structural checks
  build_pdf.py                      reusable Markdown-to-PDF renderer; ends by running check_pdf_text.py
  check_pdf_text.py                 checks the PDF text against Summary.md word for word, plus structural checks
  build_epub.py                     optional EPUB build of Summary.md; ends by running check_epub_text.py
  check_epub_text.py                checks the EPUB text against Summary.md word for word
  fingerprint.py                    hashes every project file, to prove a report-only run changed nothing
  make_validation_tasks.py          assignment files for the validation run
  build_validation_report.py        turns the validation run's results into the findings file
  tests/                            regression tests: python -m unittest discover -s Work/tests
  manifest.json                     ordered unit paths and status
  parts_manifest.json               all processing units, with status, word counts, and budgets
  parts_report.txt                  split report: parts and sizes per chapter
  review_queue.txt                  source|draft|summary|record|budget|lower|upper|ceiling lines for review agents
  verify_queue_round{N}.txt         slug|unit|part|parts|source|prev|next|summary|record, for verification
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
passes/                             brief templates, copied to the project root and filled for each use
  preflight-inspection.md           Step 1: one inspection report per source
  extraction.md                     Step 2: one extraction config and report per source
  proofread.md                      Step 2: proofreading OCR text layers against page images
  verification-pass.md              Step 9, and re-verification after an editing pass
  style-pass.md                     Step 10
  targeted-fix-pass.md              Step 10 and Step 11
  full-pass.md                      Step 10, optional: accuracy, coverage, and clarity with room to grow
  validation-run.md                 Step 11a: report-only finders and a refuting verifier
  validation-fix-pass.md            Step 11a: applying the confirmed findings
  validation-workflow.js            Step 11a: the validation run as a Workflow script, when the user opts in
Summary.md
<OUTPUT_NAME>.pdf                   named from TITLE in Work/build_pdf.py (Summary.pdf by default)
prompts.md                          agent prompt templates for Steps 3 and 5 to 7 and 11
writing-rules.md                    shared rules for all agents, including the preservation rule
settled.md                          settled decisions every agent reads: General, then one section per source
status.md                           short handoff: where things are, what is next, open questions
requirements.txt                    Python dependencies for the pipeline scripts
plan.md
```

Give each source a unique slug, such as `author-title`. Paths are shown with forward slashes; scripts should build them portably.

Each chapter source file starts with YAML frontmatter containing `source`, `source_slug`, `unit_id`, `part`, `chapter`, `title`, `register`, `pdf_pages`, `printed_pages`, and `word_count`.

- `unit_id` is stable and unique within its `source_slug`, for example `ch-01`, `appendix-a`, or `interview-01`.
- `chapter` holds the printed chapter label, or null if there is none.
- `pdf_pages` uses one-based page numbers in the PDF file. `printed_pages` holds the printed labels, including Roman numerals and missing labels. For an EPUB source, `pdf_pages` and the page markers hold the printed page numbers from the EPUB's page anchors; record this in `Work/checks.md`.

Match files, manifest entries, and budgets on `(source_slug, unit_id)`. Filename prefixes show display order, but assembly follows the ordered chapter manifest. A config can pin a chapter's file number (`file_no`), so a pilot chapter extracted first keeps its file name when earlier chapters are added. Keep internal page markers in the text for evidence lookup: `<!-- page N -->` gives the page, on its own line above a paragraph that starts the page, or inline where a paragraph runs on from the previous page. The word counter ignores them.

`Work/manifest.json` is an ordered list. Each entry has `source_slug`, `unit_id`, a `path` relative to the project root (such as `Work/Summaries/{slug}/NN-slug.md`), and a `status` of `pending`, `drafted`, `accepted`, or `blocked`.

The budget tables in this plan are the authoritative record of chapter counts and targets. Generate the processing budgets in `Work/parts_manifest.json` from them, and do not edit the derived budgets by hand. Record section mappings only for split chapters.

If you change a chapter source, revalidate its extraction, regenerate its parts, counts, and budgets, and repeat the affected reviews. Clear any `accepted` status on the chapter and its affected processing units.

Save raw extraction automatically before cleanup; this needs no separate agent task. Checksums, extraction revisions, model and prompt versions, and revision snapshots are optional. Add them if the project needs reproducibility or several revision rounds. Commit after each batch, with the progress count in the message, so an interrupted session can resume from git.

## Scope Decisions

- Keep substantive body content. Omit covers, credits, bibliographies, acknowledgements, and similar apparatus unless they contain substantive content found nowhere else.
- Inspect notes, prefaces, introductions, conclusions, appendices, interviews, transcripts, captions, and tables before deciding. If a notes page contains relevant argument or evidence, keep that material. If the user limits scope (for example "numbered chapters only") and an omitted section carries substantive framing, record that it does.
- Apparatus inside a chapter's page range, such as a further-reading list at each chapter's end, is omitted in the summary but stays in the chapter source. List it in `Work/budget_exclusions.json` so it does not count toward the chapter's budget; a part that holds only apparatus then gets budget 0. Notes that only cite a source are listed there too (classify each note from its full text: a note with any substantive sentence counts in full). In one run citation-only notes were 2,155 words across 13 chapters, and 8.5% of one chapter.
- Treat long, independent appendices or interviews as separate units.
- Text by someone other than the author inside a unit (an editor's or translator's note, a publisher's preface) is the author's only if the scope decision says so; the extraction report lists it.
- For each source, record which sections you kept and omitted, and why. Verification and later-pass briefs quote this list so agents do not report omitted sections as coverage gaps.

| Source | Section | Keep / omit | Reason |
|---|---|---|---|
| | | | |

Total chapter units: {N per source, summed}.

## Word Budgets

Count only retained substantive text. Exclude YAML, page markers, repeated running text, omitted apparatus, and the text listed in `Work/budget_exclusions.json`. Use one deterministic counting function for both source and summary prose, and document how it counts, including its handling of hyphenated words. The shared function is `words_in_text` in `Work/count_words.py`: it removes HTML comments, drops lines starting with `#`, strips the `> ` block-quotation marker, counts only the cell words of a Markdown table (no pipes or separator row), and counts whitespace-separated tokens, so a hyphenated compound is one word. `python Work/count_words.py <file>` skips a chapter file's YAML frontmatter. If Python is unavailable to an agent, that rule can be reimplemented exactly in another shell; record the fallback. Agents report counts from this function. The counts from `Work/check_words.py` are authoritative. Exclude summary headings from budget checks, and report the introduction's length separately.

For each unit, `Target = round(budget-basis words × 0.40)`: the draft budget, where the basis is the unit's source words less its exclusions. The draft range is `0.85 × Target` to `1.15 × Target`, and the ceiling is `Target + round(0.10 × basis words)`. `Work/split_parts.py` writes both into the parts manifest, with `budget_words` for the basis, and `Work/make_review_queue.py` prints them for the prompts. Each budget row has `Source slug` and `Unit ID` values matching the source frontmatter. `Work/split_parts.py` must reject duplicate keys, missing rows, rows that match no retained unit, and a row whose part differs from the chapter's; it notes a Title or Source words cell that differs from the chapter. Fill in source counts and targets after extraction is validated and before splitting.

Proportional budgets are starting points. A Target may move for argument density or repetition; record the reason in the deviation column, or `Work/split_parts.py` notes the row in its report. When uniform compression would cut essential qualifications or supporting evidence, keep them: restoring source meaning under the preservation rule is a sufficient reason to exceed a ceiling, and the review record names the items. Read the running and projected ratios from `Work/check_words.py` after each batch. If the document runs above 0.50, lower the Targets of pending units and rerun `Work/split_parts.py`; never cut accepted chapters' faithful content to compensate. Lowering reviewers' ceilings instead held poorly in one run: reviewers told to keep to the draft's count finished 88-395 words over it, each with named preservation items. If the user approves a document above 0.55, record it with its date as a `DOCUMENT` entry in `Work/budget_exceptions.json`, so `Work/check_words.py` stays usable as a gate.

### Part 1: {Source title}

| Source slug | Unit ID | Title | Source words | Target | Ceiling | Final words | Reason for deviation |
|---|---|---|---|---|---|---|---|
| | ch-01 | | | | | | |

Source total: {n} words; draft target total: {n} words (0.40); final: {n} words (ratio {r}).

Repeat the table for each source, then give the grand total and the overall ratio:

Grand total: {n} source words; draft target total: {n} words (0.40); final: {n} words (ratio {r}; target 0.50, at most 0.55).

`python Work/fill_final_words.py` fills the Final words column, the "above ceiling" notes, and the final figures of the total lines from the summaries.

## Pipeline

### 1. Preflight

- **Inspect each source.** Run `python Work/md_toc.py "Sources/<file>.md" "Work/Preflight/<file stem>.toc.txt"` on each Markdown source (give the output path rather than redirecting, which on Windows can write another encoding): the heading table with words per section, running-head candidates, and counts of page-break, image, and formula placeholders, replacement and private-use characters, and quotation-mark styles. With several sources, dispatch one Opus inspector per one to three sources with `passes/preflight-inspection.md`; each writes `Work/Preflight/<file stem>.report.md` covering bibliographic facts from the title page, naming evidence, structure, conversion problems, quotations, text by others, blocking issues, and a recommended "Extract from". Fill the Sources table from the reports.
- **Register.** Date the English text of each source (for a translation, the translation's date) and set its register in the Sources table: `modern` before 1950, `source` from 1950 on, and `modern` for a later translation that reads as antiquated. If any source is `modern`, settle with the user how its summaries render period terms for groups of people that read today as offensive or misleading (current usage outside quotation marks, or the source's term), and record the decision in `settled.md` (General).
- **Typography policy.** Decide before any extraction agent runs, and record it in `settled.md` (General): curly or straight quotation marks (restored from the PDF where the export flattened them, or kept as exported), dashes, italics as `*x*` or none, and the form of note references. In one run some sources had curly quotes rebuilt from the PDF while others kept the export's straight ones, and later passes normalized them piecemeal until the end.
- **Confirm the scripts and their configuration.** Create one extraction config per source in `Work/SourceConfigs/` (Step 2), and fill the `PARTS` configuration in `Work/assemble.py`, `Work/Introduction.md`, and `TITLE` in `Work/build_pdf.py` (also used by `Work/build_epub.py` and for the output file names). Check that `Work/split_parts.py`, `Work/check_parts.py`, `Work/make_review_queue.py`, `Work/check_words.py`, and `Work/check_fidelity.py` work with this project's budget tables and unit keys. Run the tests: `python -m unittest discover -s Work/tests`.
- **Dependencies.** Confirm the dependencies for extraction, OCR if needed, Markdown, templating, and PDF rendering. Install `requirements.txt` and record versions, executable paths, and any installations required, including Microsoft Edge for PDF rendering, in the Preflight section of `Work/checks.md`. Record the interpreter command agents should use: PyMuPDF installed in user site-packages does not import under `python -I`, which one run's inspection brief had told agents to use.
- **Shared files.** Confirm `writing-rules.md` is present, and pass it as the shared instructions for every agent. It is the only style guide agents use. Its Style section has fixed Requirements and judgment-based Guidance: a Guidance pattern yields where applying it would make a passage harder to read. Create `settled.md` (General section, then one section per source slug) and `status.md` from their templates.
- **Agent limits.** Record each role's model, context window, and effective per-request output cap, and the file-size limits for agent inputs: a 29KB body-text target and a 32KB hard cap per assigned chapter or part source file (1KB = 1,000 bytes). Larger source files caused agent timeouts even when they fit the context window. For each task, estimate the full input and required output: instructions, source, any summary under review, and a safety margin. Whole-chapter verification and later-pass tasks are an exception that has worked up to 92KB of source (Step 9).
- **Usage.** If the account has a usage window, record how it is read and the level at which the user stops. The default stopping level is 95% of the 5-hour window; with Claude Code subagents it takes a lot of work to fill the window, so the margin can be small. Use a different level if the user sets one. In the Claude Code desktop app the coordinator can read the account's 5-hour and weekly windows itself (the session-management usage tool), so it can check before each batch without asking. Measure cost per task in the pilot. Figures from one run, in points of a 5-hour window: an Opus extraction agent 4-10 (300-500k tokens); drafting, review, and seam review about 0.65 per 1,000 source words (a Sonnet summarizer 90-135k tokens, an Opus reviewer 120-175k); the pilot of one 8,000-word chapter about 10; a round-1 verifier about 0.8 per part; a style-pass or full-pass agent 0.15-0.2 per chapter; a 276-agent validation run 64.
- **Naming convention.** Fill in the Naming convention column of the Sources table, and `Work/author_refs.json` (format in `Work/check_author_refs.py`): every name form the summaries will use for each author, `<slug>/<file stem>` entries for interviewees and for essay authors in an edited collection, `not_author` phrases for other people who share an author's surname, and under `conventions` the full AUTHOR line for each source and for each unit in another voice. The first name group of a unit entry is that unit's narrative voice (the AUTHOR line's voice); every other name, the source's author included, is another speaker. A unit whose voice is the source's author has no entry of its own, or lists the author first. Test `python Work/check_author_refs.py <file>`.
- **Commands.** Test `python Work/count_words.py <file>`, `python Work/check_author_refs.py <file>`, `python Work/check_fidelity.py <summary> <source>`, and `python Work/check_qualifiers.py <summary> <source>` from the project root. `Work/make_prompts.py` writes them into every prompt (with `--python` if `python` is not on PATH).
- Pick a pilot chapter complex enough to exercise extraction, splitting, and review: a chapter that will be split into parts is best.

### 2. Extraction and Validation

Reuse `Work/extract.py`. Each source has its own config file, `Work/SourceConfigs/<slug>.py` (slug with underscores), holding its file, slug, title, part number, chapter list, and repairs; `Work/SourceConfigs/README.md` lists every key, and `python Work/extract.py <slug> ...` extracts only the named sources. A config never reads files when it is imported (a callable value is resolved only for the selected sources), so a checkout without `Sources/` can still load every config. One file per source lets several extraction agents work at once without touching each other's settings or the shared code.

With several sources, dispatch one Opus extraction agent per one to three sources with `passes/extraction.md`, after Preflight. Each writes its sources' config files and `Work/Extraction/<slug>.md`, a report with the units table, config decisions, the `repairs.tsv` review, block quotations, footnotes moved, text by others removed, the faults kept as printed, and open issues marked blocking or not. Agents never edit `Work/*.py`: an agent that needs a code change marks the issue BLOCKING with a specification, and the coordinator makes the change, tests it, and commits it before the agent's sources are accepted. The "kept as printed" lists become the source sections of `settled.md`.

- **Docling Markdown sources** (the usual case; the user runs docling, never the coordinator): the `md` filename, and per chapter its `title` (matched against the docling heading line) or a `first_line`, with `stop_line` where a unit ends before the next chapter's heading; `occurrence` when a contents page repeats the headings. Page markers come from docling's page-break placeholder (`page_break`, default `<!-- page break -->`, numbered from `first_page`); without it the chapters carry no page markers, as for an EPUB without anchors. Running heads go in `header_patterns`, footnote paragraphs are matched by `footnote_pattern` and moved to a labelled notes block at the chapter's end, and `block_quotes`/`block_quote_fixes` work as for TXT sources. Damaged lines are repaired by line number with `line_edits` (built and checked with `Work/source_helpers.py`, which also rejects an edit whose line has changed), or by exact text with `line_fixes`; extraction warns about any `line_fixes` key that matches no line. On the first file, open the Markdown and check, recording the answers in `Work/checks.md`:
  1. The number of page-break placeholders is the PDF page count minus one; otherwise set `skip_pages` and `last_page`, and check page markers in several places.
  2. How footnotes appear (paragraphs starting with a bare number, or superscript digits) and whether they sit at the end of their page; set `footnote_pattern` to match. Note references in the body stay as plain digits; a reference printed after a space ("world. 7") still ends the sentence.
  3. Chapter titles come out as `##` headings, and whether the chapter number is a separate heading line.
  4. No running heads or page numbers leak into the text as paragraphs or headings.
  5. Line-end hyphens kept with a space ("differ- ent"); if common, set `hyphen_spaces`.
  6. Emphasis markup (`*italic*`), list layout, escaped characters, quotation-mark style against the typography policy, and whether any block quotations are already marked with `> `.
  7. Every placeholder in the file (image, formula, others): each dropped one is logged, so check the text around it for lost substance.
  Tables are kept as Markdown pipe tables, one block each; the word counter counts their cell words only. Footnotes `extract.py` moves go to a notes block at the end of the chapter, which the summarizer folds back in where each note is referenced ("Shape of a summary" in `writing-rules.md`).
- **PDF sources:** header and footer cutoffs (PDF points) and a chapter list with one-based inclusive PDF page ranges, optional printed page labels, and chapter numbers; `first_line` and `stop_line` cut a chapter that starts or ends mid-page. Per-source overrides: `hyphenates` when the hyphenation detector disagrees with the page images; `space_repair` when the text layer drops space glyphs in some fonts (calibrate the em factor against known word gaps); `char_map` for characters the font maps wrongly (such as old-style figures in the private-use area, `{chr(0xF730 + i): str(i) for i in range(10)}`); and a chapter's `title_alt` for a heading the text layer misspells, such as an OCR error.
- **EPUB sources:** the `epub` filename and, per chapter, its XHTML `file` in the archive, or `files` for a chapter spread over several. Set `epub_page_anchor` to the id prefix of the print-page anchors, `epub_heading_classes` to the class attributes of the heading elements to drop, and `epub_skip_classes` for navigation links and other furniture. Open one chapter file to find them.
- **Paged TXT sources** (a pdftotext dump with a form feed per PDF page, or a dump a config builds from the PDF with `build_txt`): the `txt` filename (a path starting `Work/` is read from the project root), `header_patterns` for running heads, and per chapter its start and end PDF pages with a `first_line` prefix (and `stop_line` if the unit ends mid-page). `"paragraphs": "blank_lines"` takes each blank-line block as one paragraph, for a dump that already marks them. Per-source repairs: `dehyphenated` and `hyphen_fixes` when the dump dropped line-end hyphens from real compounds, `kerning_spaces`, `line_fixes` for letter-spaced or two-line headings, `not_headings` for first lines shortened by a drop cap, and `notes` to attach endnotes printed at the back to their chapters. Consecutive one-row table paragraphs are joined into one table. `Work/SourceConfigs/README.md` shows each setting.
- Add recurring noise to `STAMP_PATTERNS` (page furniture that can sit mid-page, such as numbers printed as "-3-") and `JUNK_LINES` (watermarks and download stamps). Presentation-form ligatures and stray punctuation-only blocks are normalized automatically.

If the script is missing, write it with PyMuPDF or an equivalent. It saves the raw extraction before cleanup.

Cleanup rules:

- Remove verified running headers, footers, watermarks, filename stamps, and redundant page numbers. Keep internal page markers.
- Repair ligatures and line-end hyphenation only when the page image or reliable extraction evidence supports the repair. Keep legitimate compounds, names, punctuation, and the source's own typos.
- Broken `ff`, `fi`, `fl`, `ffi`, and `ffl` ligatures appear as artifacts such as `confl ict` and `fi rst`. Before applying repairs, check how the detector in `Work/extract.py` defines overlap, and calibrate its threshold for each document or font against known real spaces and known artifact spaces.
- A line-end hyphen between two known words, after a known prefix, or after an acronym is kept; an unverifiable break in a document that hyphenates is joined. Both are logged as uncertain. Never turn a hyphen into a space: that splits real compounds.
- Merge page-break continuation fragments into their parent blocks during extraction, before validation. Decide whether each join falls at a word boundary or mid-word from the page image or reliable extraction evidence. Dictionaries can help, but they cannot settle an ambiguous join alone, and an unfamiliar word stays as extracted unless other evidence supports a correction. Keep page provenance for merged text.
- Log uncertain repairs. Review every `uncertain`, `-midword`, and `page-break-unjoined` line in `Work/Raw/{slug}/repairs.tsv`, and resolve any that affect meaning against the original page before accepting the chapter. For docling Markdown sources also review every `outside-chapters` row (text in no chapter: confirm it matches the scope decisions), `chapter-start-inside`, `footnote-candidate`, `footnote-open-ended`, `footnote-moved-no-page-evidence` (a body paragraph may have been moved to the notes), `footnote-moved-from-list` (a one-item list may have been a real list), `block-unjoined` (a paragraph split by a table or a removed block on the same page), `unescaped-underscores`, `image-placeholder`, `formula-placeholder`, `comment-dropped` (another dropped placeholder), `unescaped`, `leading-markup-kept`, `chapter-start-ambiguous`, `chapter-start-not-heading`, `chapter-end-of-file`, `no-page-markers`, `page-count-mismatch`, `furniture-candidate`, `replacement-char`, `private-use`, `glyph-placeholder`, `line-edited`, `line-fix-unused` (a repair that matched nothing, often because `char_map` changed the line first), and `char-mapped` row. A chapter with no body words stops the run: fix its `title`, `occurrence`, or `first_line`.
- When extraction misses substantive figure or table content, add a faithful transcription or description through the config (a `line_edits` or `line_fixes` entry at its place, opening "[Visual transcription of Figure N (p. X): ..."), never by editing the chapter file, which the next extraction overwrites. Mark it as a visual transcription or description and give its original page. Include the labels, units, values, and qualifications a reader needs, verify the addition against the original, and do not infer values the source does not report. Count this text once in the chapter budget. If essential visual content cannot be represented reliably, block the unit until it is resolved.
- Preserve reading order, table labels, and the links between body text and substantive notes. Keep material that looks like apparatus if it carries substance.
- Mark block quotations, epigraphs included, with a Markdown `> ` prefix on each quoted paragraph (after a leading page marker), so agents can tell another speaker's words from the author's prose. Summaries reproduce a block quotation whole and exact or drop it entirely (the block-quotation rule in `writing-rules.md`). The word counter ignores the marker and the splitter never splits inside a quotation. For TXT and docling Markdown sources, `"block_quotes": True` detects quotations from colon lead-ins, citations set after the closing punctuation, and dash-attributed epigraphs; review every `blockquote-*` line in `repairs.tsv` other than plain `blockquote`, list every marked quotation with its lead-in and the paragraph after it, and record corrections in `block_quote_fixes`. For PDF sources detect them from indentation or font size, and for EPUB sources from `<blockquote>` elements; neither is implemented yet.
- List the detected headings for each source. A two-line heading split at its line break leaves its second line glued to the next paragraph; repair it in the config.
- Do not paraphrase or silently correct substantive content.

**OCR text layers.** Where a source's text layer comes from OCR, check faint print and every number on a few pages against the page images. If errors turn up, proofread every unit with `passes/proofread.md`, or at least every line containing digits: the coordinator lists the lines to check with `python Work/source_helpers.py preproof <slug> <md> <first line> <last line>`, Opus proofreaders compare them with the page images at 300 dpi and each writes `Work/Proof/<slug>.<unit_id>.fixes.json`, and the config applies them with `line_edits` built from `proof_fixes(SLUG, MD)` (which stops if a listed line has changed since it was listed). A `first_line` or `stop_line` then matches the text after the edits. In one run, one source had 8 wrong numbers in 44 lines with digits, and another needed 186 fixes in 211 proofread lines, including more than 30 words the OCR had dropped. `Work/check_fidelity.py` cannot catch these later, because the summary matches the wrong source. A redrawn text layer can make an OCR misread and a printed misprint look the same: list those for the user.

Validate every chapter boundary and page mapping. Then sample pages across each source, including difficult layouts and repaired text, and compare substantive tables and figures with the original. The offset between PDF and printed page numbers can change within a document, so check mappings in more than one place. Run `python Work/check_chapters.py`: it fails on replacement, private-use, and presentation-form characters, entities, and leftover markup, warns on run-together words ("Polish'spring", found in one run only as a fidelity flag during drafting), doubled spaces, and body paragraphs that do not end a sentence (apart from lines ending in a colon or semicolon and short heading-like lines), checks each frontmatter word count, and prints each chapter's first and last paragraph for a boundary read. Finally, `python Work/extract.py --check` re-extracts every source into a temporary folder and compares it byte for byte with `Work/Chapters/`, so no hand edit or stale config survives.

Record checks and open extraction issues in the extraction section of `Work/checks.md`, or per source in `Work/Extraction/<slug>.md` with a summary table in `Work/checks.md`. Resolve issues that affect meaning before summarizing the unit. If the content cannot be recovered, mark the unit blocked and report the limitation.

### 3. Size Limits and Chapter Splitting

Two limits govern task size.

- **Model limits.** Keep a chapter in one task only if the whole task, review inputs included, fits the model's usable context with a safety margin, and the expected output fits the effective output cap.
- **Agent runtime.** Agents given whole chapters of up to 125KB fit within the context window but spent long periods thinking and timed out. Do not assign a summarizer or reviewer a source file over the 32KB hard cap.

Splitting leaves validated source text unchanged. If text needs repair, go back to extraction and validation.

Run `Work/split_parts.py` on all chapters. It builds the processing manifest and splits chapters that exceed the limits:

- Each part targets 29KB of body text. The hard cap is 32KB, measured as the UTF-8 byte size of the complete part file, including frontmatter and overlap context. Split at paragraph boundaries where possible. A part may run past its target, up to the cap, when the next safe boundary is beyond the target. Split a block at sentence boundaries only if it cannot otherwise fit in a complete file under the cap. If a remainder cannot fit without splitting a sentence, the script flags it and it is not assigned to an agent. You must then resegment it without losing source content, or block the unit.
- Once a part passes about 20KB, prefer to split just before a detected section heading. If less than about 6KB would remain for a new part, add it to the current part instead, provided that stays under the hard cap. Otherwise keep the small final part.
- A boundary can be set by hand in `Work/part_boundaries.json`: `{"slug/unit_id": ["first words of the paragraph a part must start with", ...]}`. Each prefix must start exactly one paragraph, and the break must fall between sentences and outside a block quotation; any error writes nothing.
- Each chapter budget is divided among its parts in proportion to their budget-basis words. Each part file's frontmatter records `part_index`, `part_count`, and the part's `word_budget`.
- Parts are written to `Work/Chapters/{slug}/parts/{NN}-...-part{k}-of-{m}.md`, along with the parts manifest (`Work/parts_manifest.json`) and split report (`Work/parts_report.txt`) that drive agent runs. Each processing entry has `source_slug`, `unit_id`, `part_index`, and a `status` of `pending`, `drafted`, `accepted`, or `blocked`. Only you, the coordinator, update status, with `Work/set_status.py`, after checking the output and review record. Unsplit chapters appear as single processing units with `part_index: 1`, `part_count: 1`, the chapter budget, and their actual source, draft, summary, and review-record paths. The review queue and word-count checks cover every split part and every unsplit chapter.
- In the split report, `!!` lines are problems to act on and `--` lines are information (boundaries set, budget-basis notes). The report flags a part that starts inside a chapter's notes block and a part that holds only notes: the splitter does not keep the notes block whole, so set a boundary at the notes label where it matters.

Before summarizing, run `Work/check_parts.py`. It checks that boundaries fall between sentences, that each complete file is at or under 32,000 bytes in UTF-8, and that word counts exclude metadata and all context copies. It also rebuilds each validated chapter from its ordered owned text slices, leaving out generated frontmatter, wrappers, and context copies. The rebuilt text must match the chapter body exactly, including original whitespace and internal page markers. The check rejects missing, duplicated, reordered, or altered text. Record results in `Work/checks.md`, and rerun the check after any boundary or context change.

#### Context between parts

Each part summarizer and reviewer gets a single `SOURCE` file containing all the evidence it needs. Put any original-source context from outside the part inside that file, in delimited blocks naming the owning unit and part. Do not hand out separate context files. Context blocks count toward the 32KB file cap but are excluded from owned-text reconstruction, source word counts, and budgets.

Overlap context is added automatically, so each summarizer can follow references back into the previous part. Each part after the first opens with the end of the previous part, wrapped in comment markers and excluded from `word_count` and `word_budget`: at least `OVERLAP_BLOCKS` paragraphs (default 1; 0 turns overlap off), extended backwards until they hold `OVERLAP_MIN_WORDS` words (default 250), both in `Work/split_parts.py`. The script drops overlap that would push a part over the hard cap, oldest paragraph first, and reports it.

Overlap carries context only backward, so inspect every part boundary after splitting. With many boundaries, dispatch Boundary inspectors (`prompts.md`), one Opus agent per 10 to 15 boundaries: each reads both sides of its boundaries, proposes context entries and boundary moves, and tests them with `python Work/split_parts.py --dry-run --context <proposals>`, which prints each part's bytes and headroom and writes nothing. In one run three inspectors covered 44 boundaries; their proposals became 56 context entries and nine boundary moves. Add original-source context, from either direction, wherever a split separates a term from its definition, a claim from its evidence, a quotation from the author's comment on it, or a passage from a qualification or conclusion in the next part. Also inspect every boundary where the script dropped overlap, and add any context it needs. Record added context in `Work/part_context.json`, not in the part files, so rerunning the splitter keeps it: each entry names the receiving part by `source_slug`, `unit_id`, `part_index`, and `part_count`, or by `receiver` (a phrase from the receiving part's owned text, so the entry survives a resplit), and gives the exact chapter text. The splitter locates the owning part, inserts the block, and reports entries it cannot match. If the context won't fit, reserve room or move the boundary (`Work/part_boundaries.json`), then rerun the splitter and `Work/check_parts.py` and re-inspect the moved boundaries.

When a split chapter ends with a notes block, the block sits in the last part, away from the reference numbers in earlier parts. Add each substantive note to `Work/part_context.json` as context for the part that holds its reference number, with `"fold": true`, so its block tells that part's summarizer to fold the note in (other context blocks say "do not summarize it"); the last part folds in only the notes referenced in its own text. Expect DRAFT OVER or UNDER flags from the moved words (the note's words count in the last part's budget, its substance lands in another part): settle them in `Work/budget_exceptions.json`. A part that holds only notes is handled like an apparatus-only part.

A quotation whose speaker is named only in a note that just cites a source reads as unattributed: in one run a quotation the author took from another writer would have been summarized as the author's own. Before dispatching a split chapter, check each part's quotations against the chapter's notes block, and give such a note to the quoting part as a plain (non-fold) context entry.

Each source passage belongs to exactly one part, and only that part summarizes it. Other parts may use it to interpret or qualify their own claims. Record any change of ownership in the parts manifest. Before merging, check adjacent summaries for duplicated coverage, keeping any qualifications needed for accuracy.

If context adjustments change a part's evidence after drafting has started, reset the affected review statuses and repeat those reviews before acceptance. When a chapter is too large to compare with its summary in one context, verify coverage part by part and check the transitions separately.

### 4. Pilot

Take one representative chapter through extraction, summarizing, review, merging, and rendering. Assemble it alone by listing it in `PILOT_UNITS` in `Work/assemble.py`, and clear `PILOT_UNITS` afterwards. Evaluate fidelity (including the preservation and qualifier audits in the review record), coverage, length, readability (including `Work/check_author_refs.py`, and a read for pronoun chains it cannot count), extraction quality, and PDF layout (the pilot's PDF is for checking layout; the deliverable's PDF is rendered once, in Step 12), and adjust prompts and budgets before scaling up. Record the usage cost per task.

Get the user's approval of the finished pilot unless they have already authorized you to continue without it. Record the decision.

### 5. Summarization

Run one agent per part, or per chapter if the chapter was not split, with the Summarizer prompt in `prompts.md`. Generate the prompts with `python Work/make_prompts.py batch-NN summarizer <keys>` (keys `slug/unit_id`, or `slug/unit_id/k` for a part); the script fills paths, budgets, commands, and the AUTHOR line for each unit and applies the split-part rules. List the next pending units with `python Work/set_status.py pending`. The summarizer drafts to the unit's budget (0.40 of its source words) and condenses the source in its own order. Each agent writes a draft to `Work/Drafts/{slug}/` (part drafts go in `Work/Drafts/{slug}/parts/`).

Start with 6 agents at once. After clean batches, and within usage limits, run up to the harness's concurrency limit (20 subagents in Claude Code in one run), dispatching each reviewer as soon as its draft lands, ahead of new summarizers.

Part drafts have no `##` heading; the merge adds the chapter heading. Unsplit chapter drafts start with `## {Chapter Title}`. Either may carry `###` headings, but only where the source itself has a section heading.

Keep the original drafts. Reviewers read from `Work/Drafts/` and write directly to `Work/Summaries/`, so you don't need to copy files between them. Allow one writer per file at a time. Retry failed units individually, and check completed outputs before updating their status. A transient API failure, such as an HTTP 5xx error, usually succeeds on immediate retry; retry before reworking the unit.

Each summarizer's reply lists the source oddities it met (a misprint, a garbled passage, an apparent extraction fault). Check each against the original page before the unit's reviewer is dispatched, and give the reviewer the result in `Work/Prompts/<batch>/notes.json` ("printed so: keep", or "extraction fault: reads X"); record lasting rulings in `settled.md`. In one run summarizers "corrected" a printed phrase and replaced named people with a vague phrase; the reviewer catches these only if it knows what the source really prints.

A blocked part blocks its whole chapter. Merge a split chapter only after every part is accepted, and accept the chapter once the merge and chapter-level checks pass. A partial deliverable may leave out a blocked chapter entirely if the limitation is disclosed, but a chapter with missing parts cannot be accepted. For unsplit chapters, `set_status.py part` keeps the processing-entry status and chapter status in sync.

If a run stalls or is interrupted, archive the affected outputs before rerunning (for example, to `Work/Summaries_archive_v1/`). Re-review every part whose review status is uncertain instead of resuming from it.

### 6. Chapter Review

Assign one fresh-context agent per part or chapter with the Reviewer prompt in `prompts.md` (`python Work/make_prompts.py batch-NN reviewer <keys>`). It reads the source and the original draft, writes the reviewed summary to `Work/Summaries/`, and saves a review record in the fixed format the prompt gives, including the contrast, number, and qualifier audits required by the preservation rule. In later rounds it starts from the latest reviewed summary instead of the original draft. Fresh context helps reviewers catch errors, but they can still miss errors or introduce new ones. Sonnet 5.5 at high effort drafts and Opus 5.5 reviews (see Agents).

Build the queue with `Work/make_review_queue.py` and work through it in batches. After each batch:

1. Run `python Work/check_words.py`. It flags drafts outside their draft range, reviewed summaries above their ceiling or below the draft range, and the running and projected ratios per source and for the document. A summary above its ceiling needs preservation items named in its record; otherwise send it back to a reviewer to tighten without losing meaning. After an outlier edit, the reviewer checks the edited passages against the source, reruns the count, and updates the review record. If the document ratio passes 0.50, lower the Targets of pending units (Word Budgets). Once a flag is settled (a ceiling overage whose record names the preservation items, a short summary whose record explains it, or an apparatus-only part that is legitimately empty), record it in `Work/budget_exceptions.json` so the check stops flagging it and its exit status stays usable as a gate. Each entry is keyed `"slug/unit_id"` (an unsplit or merged chapter) or `"slug/unit_id/part k"` (a part before the merge) and names the flag it settles and the approved count: `{"flag": "ABOVE CEILING", "max_words": 520, "reason": "..."}` (flags: ABOVE CEILING, UNDER, DRAFT OVER, DRAFT UNDER). Keep `reason` to one sentence naming the record; later passes add `history` lines. It settles only that flag, an overage only up to `max_words`, and a shortfall only down to an optional `min_words`. A part's exception does not carry over to its merged chapter, which needs its own entry; once the chapter is merged, `check_words.py` lists its part keys as superseded, and `python Work/raise_exceptions.py --prune-stale` deletes them.
2. Run `python Work/check_fidelity.py <summary> <source>` on each of the batch's summaries (or with no arguments to check every reviewed summary in the manifest). Every flag on an accepted summary must be settled in the record's Script flags section, and every `Work/check_qualifiers.py` flag in its Qualifier audit.
3. Run `python Work/check_author_refs.py` on the batch's summaries. Each paragraph it still flags must appear in the review record's author-naming line, with the other speaker that justifies the second reference. Send any other flagged paragraph back to the reviewer.
4. Read each review record. Reject a record whose audits are missing, whose contrast audit says "present" without quoting the words, or whose "Omissions kept" section lists a dropped contrast, hedge, scope or example marker, attribution, frame (rule (f)), condition, negation scope, sequence, reach (rule (g)), disclaimer by the author about the text, or claim-evidence pair; those are material errors, not omissions. Reviewers tend to run to the ceiling and cut to fit, so read "Omissions kept" for hedges, disclaimers, and scope words, and for a gap whose next kept sentence no longer stands.
5. Set statuses with `python Work/set_status.py part accepted <slug> <unit_id> <part_index> ...`. While edits await verification, set previously accepted units back to `drafted`; a split chapter loses `accepted` status automatically when a part reopens.

The Reviewer prompt sets the review order (accuracy, preservation, coverage and order, clarity, a final accuracy check) and the record format; keep those in `prompts.md` only.

Reviewers write consequential corrections, supporting page or passage references, budget deviations, and unresolved issues to `Work/Reviews/` and keep them out of final prose.

When the extracted source is ambiguous or incomplete, the reviewer flags it for you to check against the original and does not reconstruct missing facts. A unit with an unresolved material issue cannot be accepted.

### 7. Merge Multi-Part Chapters

Unsplit chapters skip this step; their reviewed summaries are already at the final path.

By default, merge with `python Work/merge_chapters.py`. It concatenates each ready chapter's reviewed part summaries in order, adds one `## {Chapter Title}` heading, writes the result to `Work/Summaries/{slug}/NN-slug.md`, and reports the chapter's count against its budget. It refuses a part summary that contains frontmatter, an HTML comment, or a heading other than `###`; in one run a reviewer copied its source's frontmatter and owned-text markers into its summary. It records what it wrote (`merged_sha` in the parts manifest). A chapter summary edited since then (seam fixes, remediation, later-pass edits) is kept and reported as `kept` when its parts are unchanged; when the parts have changed, the script refuses to overwrite it and exits 1, and `--force <slug> <unit_id>` overrides that after a real rework of the parts, once the edited chapter is archived. A chapter whose part summaries cannot be merged is reported as `NOT MERGED`, and the other chapters are still processed. Then build `Work/transition_queue.txt` with `python Work/make_transition_queue.py` and run one Transition reviewer (`prompts.md`) per chapter. Each seam review uses the adjacent summary passages and the matching original passages, within the source-file cap and the model's limits, widening the passages only as far as meaning requires.

You can use a single merge agent instead when the combined reviewed part summaries are 32KB or less in UTF-8 bytes and the full task, including instructions and output, fits the model's limits with a safety margin. If a merge agent stalls, switch to the script and separate transition reviews. The merge agent reads the reviewed part summaries in order and does not read the chapter source.

Either way, the merge keeps the parts in order, smooths abrupt transitions at part boundaries, and removes duplicated framing, without adding or dropping substantive claims. The total should stay at or under the chapter ceiling. If accuracy requires more, record it and the reason. Before the merged chapter is accepted, you or a fresh-context agent must check every edited transition against the original passages. Run `python Work/check_author_refs.py` and `python Work/check_fidelity.py <chapter summary> <chapter source>` on the merged file, because seam edits can join paragraphs, leave a part re-introducing the author, or change a figure or quotation. Then check the merged file against the parts manifest: each part appears exactly once and in order, and the chapter is at or under its ceiling or has a documented, justified deviation. Accept it with `python Work/set_status.py chapter accepted <slug> <unit_id>`.

After merging, `Work/Summaries/{slug}/parts/` is stale: later edits go to the canonical chapter summary only.

### 8. Assembly

Reuse `Work/assemble.py` with updated `PARTS` configuration, and write the introduction in `Work/Introduction.md` (a file, so the whole-document review reads it and passes can edit it). The script reads `Work/manifest.json` and includes only units marked `accepted`, because `Work/Summaries/` also holds reviewed files for blocked units. It rejects missing, duplicate, or unmatched units, missing or extra headings, leftover markers, page references, footnotes, working-file references, leaked review notes, unfilled placeholders, and paragraphs, headings, or block quotations run together by a lost blank line, and follows the manifest's part and chapter order. It warns, without failing, when a chapter heading differs from its manifest title, and, when `QUOTE_STYLE` is set, on quotation marks of the other style. It prints the compression ratio per source and for the document. `python Work/assemble.py --out <path>` writes elsewhere, for a report-only comparison. `Summary.md` has this structure:

- `# Introduction`: a short note naming the sources, scope (including sections omitted by decision), and organization, with no substantive claims. Ask the user whether it should say that each source is reproduced as printed, errors included. Every count and list in it is checked against `Work/manifest.json` and the assembled document, never written from memory: in one run the introduction was the text with the highest error rate, and five of its errors were fixes made in a chapter and never carried to the introduction's description of it.
- `# Part N: {Title} by {Author}`: names the source and author(s).
- `## {Chapter Title}`, with `###` headings only where the source has its own section headings.
- No inline citations, footnotes, or page references in final prose. Mark other speakers' views in the prose where needed; the author's own views need no attribution.

Check the assembled document for missing or duplicate units, wrong order, heading errors, leftover internal markers, and leaked review notes. Run `python Work/check_author_refs.py` and `python Work/check_fidelity.py` over every accepted summary. Record the overall ratio: about 0.50, and at or under 0.55. Sentence-opening words read as names once dominated the fidelity check's output (57 of 67 flags at assembly in one run); the check now lists ordinary opening words apart, as OPENER lines that are not flags, so the NAME flags left are worth tracing.

If blocked units remain at assembly, the deliverable is partial. Record each blocked unit's reader-facing limitation in `LIMITATIONS` in `Work/assemble.py`; the script then adds a partial-deliverable notice to the introduction. Record results in the assembly section of `Work/checks.md`. Reassemble after every later step that edits a chapter summary; the PDF is rendered and inspected once, in Step 12.

### 9. Independent Verification

Once all chapters are accepted, run the verification pass in `passes/verification-pass.md`: a report-only check of a sample of chapters by Opus 5.5, a stronger model than the Sonnet 5.5 that drafted them, triage, a scope and length decision with the user, and remediation rounds under the preservation rule. Round 1 runs part by part (`python Work/make_verify_queue.py`): each verifier gets the part it checks plus the parts before and after it as context, read only where a reference crosses the boundary, and an unsplit chapter is verified as its single part. Remediation can run per whole chapter where the source fits (`--whole`), which keeps one writer per file. Copy the brief to the project root and keep its status tables there. Because Sonnet 5.5 drafts, the pass runs by default; skip it only if the user decides to, and record the decision. The verifiers are fresh-context Opus 5.5 agents that never saw the chapters they check.

The sample's material rate is a floor: in one run the full read found about 3.6 times the sampled rate. Remediation fixes minor accuracy findings as well as material ones, and files omissions that leave every kept sentence standing as Coverage notes, so the later passes start from a short list rather than every unapplied minor finding.

After remediation, run `python Work/fill_final_words.py` to update the Final words column of the budget tables, add deviation reasons, reassemble, and record the pass in `Work/checks.md`.

### 10. Later Passes

Each later pass has its own brief at the project root, copied from `passes/`, which is also its status record. Agents read that brief (only through its "Agent prompt" section), `writing-rules.md`, `settled.md`, and their assigned files. Common rules for every later pass:

- **Length decision.** Before the first dispatch of the first remediation or later pass, agree with the user how the passes' words are funded: within existing ceilings (accuracy fixes, and restorations only where an omission leaves a kept sentence misleading), or a stated room for coverage, as a per-chapter cap (for example 105% of the chapter's length at the start of the pass) or a per-change limit (for example +50 words, and no new heading or paragraph). Record it with its date in the brief and in the Decisions log, and reuse it rather than renegotiating pass by pass. Agents use nearly all the room they are given.
- **Pilot.** Pilot any pass that can add words on about six chapters from different sources, gate the pilot, and show the user its growth and cost before running the rest. If the user then changes the scope, reset the pilot chapters from the snapshot and keep their first records in a `-v1` folder.
- Snapshot the affected canonical summaries with `python Work/snapshot_summaries.py <pass>` before the first dispatch. Never refresh or reuse an earlier snapshot.
- Generate prompts with `python Work/make_prompts.py <pass> pass --brief <pass>.md ...` (and, for a list of reported items, `python Work/collect_items.py` first, so each agent gets only its chapter's open items). Never edit a generated prompt or regenerate into a used folder.
- Edit with targeted string replacements, never by regenerating a file. Never apply one replacement across many paragraphs or files (for example a pronoun or a name): that is how one run filled a summary with the author's name. Recast each paragraph under the naming rule, then run `python Work/check_author_refs.py`. After inserting or recasting a sentence, reread the sentences around it. Do not split or join paragraphs, or move a sentence across paragraphs, unless an item reports an order or structure departure.
- Agents fix only what the pass covers and log anything else under New reports. The next pass, if the user wants one, acts on that log.
- The coordinator gates every batch with `python Work/gate_pass.py <pass> <n...>`: every changed word run is matched to a record entry and unexplained hunks are reverted; record source excerpts are found in the source; fidelity flags new since the snapshot, paragraph and heading changes, and run-together paragraphs are listed; and `--pairs` lists each addition beside its closest source passage. Then check changed numbers, names, and quotations at the cited page marker or quoted passage, run `python Work/check_words.py`, and commit the batch with its progress count. After the last batch, `python Work/raise_exceptions.py <pass>` raises the exceptions of chapters the pass grew.
- Any pass that adds or rewrites more than a few words per chapter is followed by an independent check before the PDF: a re-verification of whole chapters that also reads the pass's diff (`passes/verification-pass.md`, "Re-verification after an editing pass"), or the validation run (Step 11a).
- Reassemble `Summary.md` at the end of each pass and add an entry to `Work/checks.md`.

Passes used in earlier runs, in the recommended order:

1. **Style pass** (`passes/style-pass.md`). Prose only, no source access, gated by `Work/check_style_pass.py`. Its agents report suspected factual problems instead of fixing them. In one run: about ten edits per chapter, +0.1% words, three bad edits corrected at the gate.
2. **Targeted fix passes** (`passes/targeted-fix-pass.md`). Resolve reported items against the chapter source, one pass per report list. Rank long lists into tiers and stop where the user decides. Feed it the style pass's reports, earlier passes' New reports, and the verification leftovers a length limit kept out; not every unapplied minor finding (one run's fix pass on 1,238 such items declined 992).
3. **Full pass** (`passes/full-pass.md`), optional, when the user grants room: one Opus agent per whole chapter checks accuracy, restores the most important missing content, and clears up the prose, within a per-chapter cap. In one run it was the highest-yield editing pass (149 accuracy fixes, 509 restorations, 149 clarity edits, +10%), and the next verification round found half its findings in its text, so it is always followed by a re-verification.

### 11. Whole-Document Review

Run this after the later passes, on the text that will ship, so the reader-level review is not spent on prose that later changes. Build chunks with `python Work/make_doc_chunks.py` (three chapters per chunk by default, the introduction first in chunk 1) and assign one fresh-context Whole-document reviewer (`prompts.md`) per chunk. It reads as someone unfamiliar with the sources, checking hard sentences, terminology, unexplained cross-chapter references, repetitive framing, typography, and readability. It is report-only and must not fact-check: in one run, nearly every "error" these reviewers flagged was a claim the summaries faithfully reproduced from their sources. Chunks cross source boundaries on purpose; also inspect transitions across chunk boundaries yourself. Keep substantive differences between authors and any repetition that belongs to their arguments.

Small chunks matter. In one run a first round with chunks of about eight chapters produced about 258 findings; a second round with three-chapter chunks, on text already fixed after the first, produced about 320 more, nearly all hard-to-parse or ambiguous sentences. Before dispatch, decide with the user whether unexplained terms and references are findings: they can be fixed only where the source itself explains them, and in that run the user left about 120 of them as they were. For a second round, write the chunks with `--out` so the first round's list is kept, send the records to a new folder (`make_prompts.py ... --chunks <file> --set RECORD=Work/Reviews/whole-document-2/chunk{CHUNK}.md`), and give each reviewer the earlier fix records for its chapters as a coordinator note, so it does not report what was already settled.

Act on the findings with a targeted-fix pass: `python Work/collect_items.py <pass> --findings "Work/Reviews/whole-document/*.md"` splits them into one item file per chapter (findings on the introduction go to the coordinator), and the fix agents resolve each against the chapter source. Expect about a third of them to be `faithful`. Make the coordinator's own edits (the introduction, a few items) with `python Work/apply_replacements.py`, which checks that each old text occurs exactly once and prints each change's word count before applying anything. Verify every prose edit, including changes to terminology, transitions, or framing, against the relevant original chapter passages. Verify the introduction's statements about sources and scope against source metadata, the scope inventory, and the manifest, and carry any change to how a chapter or author is described into every other place that describes them. Record verification before restoring `accepted` status. Make chapter edits in the canonical chapter summary and reassemble, so later builds keep them.

### 11a. Validation Run and Fix Pass (optional, recommended for long documents)

When the user wants a final independent check of the whole document, run `passes/validation-run.md`: report-only, after the last editing pass and before the PDF. Per chapter, an accuracy finder (summary to source, sentence by sentence) and a coverage finder (source to summary); a reader per three-chapter chunk; a check of the introduction against the manifest; then a refuting verifier per chapter that confirms or rejects every finding, and a second opinion on material confirmations and on a sample of rejections. `Work/fingerprint.py` proves the run changed no file. The confirmed findings, each with an exact quote, the source evidence, and a suggested fix with its word change, go into one findings file for the user to decide on.

Then apply the findings the user accepts with `passes/validation-fix-pass.md`, under the user's per-change limit, gated by `Work/gate_pass.py`. In one run, after five verification rounds, the validation run reported 1,009 findings, confirmed 297 (8 material, 7 of them in coordinator-written text that had been checked only once), and the fix pass applied 296 of them with a clean gate. The run used 276 agents and about 64% of a 5-hour window (about 0.9 points per chapter), and the fix pass about 8 points for 68 agents, so pilot one chunk first. It replaces "another full verification round" as the final check once a round has found no material errors; a small project can skip it or run a sample, and the decision is recorded.

Before it starts, `settled.md` is complete, `Work/author_refs.json` has every convention, and `Summary.md` is freshly assembled. `python Work/make_validation_tasks.py` writes one assignment file per chapter (the finders never see earlier records; the refuting verifier gets them in a separate file), the reader chunks, and the prompts; `python Work/build_validation_report.py` checks every confirmed finding's quotes against their files and writes `validation-findings.md`, with chapter findings for the fix pass, introduction findings for the coordinator, and a one-line appendix of every rejection and its reason. The run is dispatched as Agent-tool batches, or with the workflow script (`passes/validation-workflow.js`) only when the user opts into a multi-agent workflow. For the fix pass the user sets the per-change word limit and the structure rule (default: no new heading or paragraph); a finding a limit blocks goes to the user as a one-line question, not silently dropped.

### 12. PDF Rendering and Inspection

Render and inspect the PDF once, after the last edit to any chapter summary. Reuse `Work/build_pdf.py`. Set `TITLE` for this project and change the rest only as needed; the PDF is named from the title (`OUTPUT_NAME`). By default, the script converts Markdown to styled HTML with Python Markdown and Jinja2, then prints it to PDF with headless Microsoft Edge. Before converting, it escapes characters Markdown would otherwise reinterpret (underscores and double asterisks read as emphasis, angle brackets read as HTML, a paragraph starting "1984. " read as a numbered list), so the PDF text matches the Markdown exactly. The one markup it keeps is italics: a single-asterisk span (`*The Grey Harbour*`) prints in italics without its asterisks (in one run the first PDF printed 159 such spans with literal asterisks). After building, it runs `Work/check_pdf_text.py`, which compares the PDF's text with `Summary.md` word for word (italic asterisks removed on both sides), reports each difference with its line and page, runs the structural checks below, warns on any literal asterisk left in the PDF, and exits 1 on any failure. Run it alone with `python Work/check_pdf_text.py`. If you use a different renderer, record the change. Default layout: Letter pages, one-inch margins, 11pt serif text, and each `#` heading (the introduction and each part) on a new page, so a short last page of a part shows up as a thin-page warning to inspect. If the renderer does not add page numbers, add them with PyMuPDF, and make sure browser headers and footers don't duplicate them.

Edge prints with `--print-to-pdf`, in its new and then its old headless mode. Edge has been seen to return from it before the file was written, so each attempt waits up to `PDF_WAIT` seconds for a complete file; if neither mode produces one, the build prints through Edge's DevTools protocol (`Page.printToPDF`, which needs `aiohttp`). The build prints the route it used: record it. Headless Edge can fail inside an agent's sandbox (no PDF, nonzero exit); run the build outside the sandbox and record it.

Inspect the PDF for missing text, clipped content, broken characters, blank pages, stranded headings, bad page breaks, and misplaced page numbers. Check programmatically with PyMuPDF: page count, blank or thin pages, U+FFFD characters, every `#` and `##` heading present in the PDF text, and no leftover `Work/`, `.md`, `<!--`, or page-reference strings. Then inspect the first and last pages and the start of every part visually. Fix problems, rerender, and record results in the PDF section of `Work/checks.md`.

Optionally build the EPUB with `python Work/build_epub.py` (requires `ebooklib`): one EPUB page per chapter, grouped by part in the table of contents, named like the PDF. It ends by running `Work/check_epub_text.py`, which reads the EPUB's documents in order and compares their text with `Summary.md` word for word (ordered-list numbers aside, since e-readers generate them), and checks headings, replacement characters, and the number of italic spans.

## Operations

- **Handoff.** Keep `status.md` at the project root current after every batch: a one-line "Updated" (replaced, not appended), a table of where each stage stands, the next batch with its dispatch checklist, open questions for the user, notes for the coordinator (gotchas, usage readings), and key files. A new session reads it first, then `Work/checks.md`. The plan's Project Status keeps only the decision log; the session narrative lives in git history and `Work/checks.md`. In one run the plan's status section grew into a session diary that doubled the plan's size. Each pass brief keeps its own cold-start handoff.
- **Usage.** Where the account has a usage window, check the current reading before each batch in a costly pass (read it yourself with the session-management usage tool), never start a batch that could cross the stopping point, and log readings in the pass brief. Make a checkpoint commit, with `status.md` updated, before stopping at the limit.
- **Commits.** Commit after each batch with the pass name and progress count ("{pass}: {source} ch-03 to ch-08 (24 of 90)"), after each rebuild, and during long gates ("27 of 74 chapters gated"). Commit each user decision on its own, marked "(user)".
- **Run scripts.** Save every prompt file, notes file, workflow script, and one-off helper a batch or pass uses under `Work/Prompts/<batch or pass>/`, and commit it with the batch. In one run the scripts of a whole validation run existed only in a temporary folder.
- **Parallel agents.** Every template tells agents that others are editing other files in parallel and to ignore those changes in git status.
- **Settled decisions.** When the user or the coordinator settles a recurring question (a misprint's reading, spelling variants, `%` against "percent", quote style, notation), record it in `settled.md` (General, or the source's section) so every agent reads it and stops raising it, and log the decision below.
- **Windows.** Agents can write CRLF files; `.gitattributes` normalizes them in git. Every script writes UTF-8 to the console (`common.utf8_output()`): without it, a reason or name outside cp1252 crashed `check_words.py` in one run, or reached agents as replacement characters.

## Completion Criteria

- Every substantive unit is accounted for, and scope exclusions are documented.
- Extraction and chapter boundaries are validated for accepted units, and uncertain repairs are reviewed. `Work/check_chapters.py` passes, and `python Work/extract.py --check` reproduces every chapter file. Units with unresolved material ambiguities stay blocked.
- Every chapter or part source file given to a summarizer or reviewer, including transition-review excerpts, is at or under the 32KB hard cap, and part boundaries are sentence-aligned and validated. Drafts, summaries, and shared instructions are checked against full-task context and output limits instead of this cap. Single-agent merges meet the 32KB combined-summary limit in Step 7.
- The ordered owned source slices rebuild each validated chapter exactly. Generated metadata and context copies are excluded from reconstruction, and metadata, page markers, and context copies are excluded from source word counts.
- Part statuses are recorded, and no accepted chapter contains a blocked or unreviewed part.
- Original drafts, review records, prompt files, and pre-pass snapshots are preserved.
- Every review record includes the preservation and qualifier audits, and every final chapter was checked for accuracy after its last substantive or style edit.
- Independent verification ran, or the decision to skip it is recorded; every pass that added content was followed by an independent check.
- Each merged chapter contains every part exactly once, in order, and every transition the merge edited has been verified against the original passages.
- Budgets are measured, the overall ratio is recorded and is about 0.50 and at most 0.55 (or within a recorded user approval), and every unit above its ceiling has a recorded preservation reason. No summary was padded or stripped of essential content.
- `Work/check_fidelity.py` flags nothing that a review or remediation record has not settled.
- Whole-document consistency and completeness checks passed, and the introduction's counts and descriptions match the manifest and the chapters.
- `Work/check_author_refs.py` flags no paragraph, apart from those whose review records justify a second reference to the author.
- `Summary.md` and the PDF match, the PDF layout has been inspected, and the EPUB, if built, passes its text check.
- `Work/checks.md` has an entry for every stage and pass.
- Unresolved material limitations are disclosed, and no affected unit is marked accepted.
- No blocked units remain, or the deliverable is labeled partial and lists the omitted units and their limitations.

## Status

- [ ] Sources, scope, and dependencies recorded; preflight reports written; register, typography policy, and naming conventions recorded; `settled.md` and `status.md` created
- [ ] Agent models recorded (Sonnet 5.5 at high effort for the summarizer, Opus 5.5 in every other role); usage limits recorded
- [ ] Page mappings and chapter segmentation confirmed
- [ ] Raw extraction preserved, uncertain repairs reviewed, OCR proofread where needed, cleaned output validated, and re-extraction check passed
- [ ] Word budgets (with exclusions) and context-size checks completed
- [ ] Oversized chapters split into parts at or under the 32KB hard cap; boundaries validated and inspected
- [ ] Pilot summarized, reviewed, merged if split, rendered, and approved or authorized to proceed
- [ ] Remaining drafts completed in batches
- [ ] Reviews, preservation and qualifier audits, and final accuracy checks completed; review records saved; word-count checks passed
- [ ] Multi-part chapters merged, transitions reviewed, and verified against the parts manifest
- [ ] Accepted chapters assembled into `Summary.md`; overall ratio recorded (about 0.50, at most 0.55)
- [ ] Independent verification and remediation completed, or skip recorded; length decision recorded
- [ ] Later passes completed as agreed with the user; each gated, reassembled, and recorded; each that added content independently checked
- [ ] Whole-document review completed and changes verified
- [ ] Validation run and fix pass completed, or skip recorded
- [ ] PDF rendered once at the end and inspected; EPUB built and checked if wanted
- [ ] Completion criteria checked and deliverables supplied

## Project Status (decision log)

The current state and the next steps are in `status.md`. This section keeps only the decisions, one line each, so a later session can see why the project looks as it does.

- {Date: decision, and who made it (user or coordinator).}

Commands: `python Work/md_toc.py <md>`; `python Work/extract.py [<slug> ...] [--check]`; `python Work/check_chapters.py [<slug> ...]`; `python Work/split_parts.py [--dry-run]`; `python Work/check_parts.py`; `python Work/make_review_queue.py`; `python Work/make_prompts.py <out> <role> [<key> ...] [--all] [--brief FILE] [--section NAME] [--snapshot NAME] [--cap-ratio R] [--items DIR]`; `python Work/make_prompts.py <out> --ready`; `python Work/check_words.py [--json] [--reasons]`; `python Work/raise_exceptions.py <pass> [--prune-stale]`; `python Work/fill_final_words.py`; `python Work/check_fidelity.py [<summary> <source>]`; `python Work/check_qualifiers.py [<summary> <source>]`; `python Work/count_words.py <file>`; `python Work/check_author_refs.py [<file> ...]`; `python Work/set_status.py pending|part|chapter ...`; `python Work/merge_chapters.py [--dry-run] [--force <slug> <unit_id>]`; `python Work/make_verify_queue.py [--round N] [--whole]`; `python Work/make_transition_queue.py`; `python Work/assemble.py [--out PATH]`; `python Work/make_doc_chunks.py [--out PATH]`; `python Work/snapshot_summaries.py <pass>`; `python Work/check_style_pass.py`; `python Work/gate_pass.py <pass> [<n> ...] [--pairs] [--show]`; `python Work/collect_items.py <pass> --new-reports|--findings|--sections ...`; `python Work/apply_replacements.py <edits.json> [--apply]`; `python Work/source_helpers.py preproof <slug> <md> <first> <last>`; `python Work/make_validation_tasks.py [<out>]`; `python Work/build_validation_report.py [<out>]`; `python Work/fingerprint.py save|compare`; `python Work/build_pdf.py`; `python Work/check_pdf_text.py`; `python Work/build_epub.py`; `python Work/check_epub_text.py`; `python -m unittest discover -s Work/tests`.
