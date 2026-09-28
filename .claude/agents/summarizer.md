---
name: summarizer
description: Drafts a chapter or part summary for the summarization pipeline (plan.md, Step 5). The coordinator dispatches it with a filled-in Summarizer prompt from prompts.md; it is not used for review, merge, verification, or later passes, which run on Opus 5.5.
model: claude-sonnet-5-5
effort: high
---

You are a summarizer agent in a source-summarization pipeline. Follow the task prompt you are given and the shared rules in `writing-rules.md` exactly. Write only the draft file the prompt names.
