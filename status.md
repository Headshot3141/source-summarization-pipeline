# Status

{Project title}. A short handoff for a new session: read this first, then `Work/checks.md`. The plan is `plan.md` (its Project Status section is the decision log); the rules agents follow are in `writing-rules.md`, `settled.md`, `prompts.md`, and the briefs.

**Updated:** {session N, date}: {one sentence on what just finished and what is next}. Replace this line each time; do not append to it.

## Where things are

| Stage | Status |
|---|---|
| Preflight (sources inspected, typography policy, naming conventions) | |
| Extraction and validation | |
| Budgets and splitting (boundaries inspected) | |
| Pilot | |
| Drafting and review | |
| Merge and transition review | |
| Assembly | |
| Independent verification (Step 9) | |
| Later passes (Step 10) | |
| Whole-document review (Step 11) | |
| Validation run and fix pass (Step 11a) | |
| PDF (and EPUB) | |
| Completion check | |

## Next

The next batch, with what a new session needs to dispatch it:

1. {Units or chapters, by key}
2. Commands: `python Work/make_prompts.py <out> <role> <keys>`; dispatch each agent with "Read Work/Prompts/<out>/<file> and follow it exactly."
3. After the batch: {the gate and checks for this stage}
4. Expected cost: {points of the usage window, from the last measured batch}

## Open questions for the user

1. {Question, with the options and what each would cost}

## Notes for the coordinator

- {Gotchas met in this project, with the date: a source fault to tell reviewers about, a script quirk, a workaround}
- Usage: {readings and cost per task measured this session; the window's reset time}

## Key files

`plan.md` (plan and decision log) · `settled.md` (rulings every agent reads) · `writing-rules.md` and `prompts.md` (what agents read) · `Work/checks.md` (every check) · `Work/Preflight/` and `Work/Extraction/` (one report per source) · `Work/Prompts/` (every prompt, by batch and pass)
