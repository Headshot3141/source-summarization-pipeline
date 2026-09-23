# Writing Rules for All Agents

These are the shared writing instructions for every summarizer, reviewer, merger, and later-pass agent. Follow the `stop-slop` skill at `stop-slop-main/SKILL.md` when it is available, within the priority order and overrides below. These rules also work on their own as a fallback.

Priority order: fidelity to the source first, then coverage of the main arguments, then clear standalone prose, then style preferences and word targets. Where a style instruction conflicts with fidelity, follow fidelity.

Report what each source argues. Do not endorse, refute, fact-check, or add outside context, and attribute claims to the author instead of stating them as fact. Keep the author's own position separate from quotations, allegations, objections, and views the author describes or rejects.

## The source as printed

The summary reproduces what the source says, including its errors. If the source prints a wrong date, a misspelled name, a misprint, or figures that do not add up, the summary keeps the source's version. Do not correct the author from your own knowledge, and do not use your knowledge to judge whether a claim is true. Silently correcting the source is itself an error. If something in the source looks like an extraction artifact, such as a broken word or stray character, rather than the author's text, report it and do not guess.

## Preservation rule (binding)

In earlier runs, the most common errors made a summary more confident or more assertive than its source, and every such summary was inside its word budget. These source features must survive into the summary with their force intact. Losing any of them is a material error, not a style trim, and preservation outranks the word budget.

- **(a) Contrast reversals.** Where the source qualifies or reverses a claim ("But", "Yet", "However", "Even so", "Nevertheless", "In truth", "Although", "On the other hand"), the reversal appears in the summary wherever the first half appears, attached to the same scope. Dropping the second half leaves the concession standing as the author's whole view.
- **(b) Epistemic modality.** Hedges ("perhaps", "probably", "seemingly", "apparently", "tended to", "often", "not necessarily", "may have"), counterfactual mood ("would have been"), estimate markers ("it is reckoned", "it is estimated"), and scope words ("some", "most", "only") keep the source's strength. They are meaning, never "unnecessary adverbs".
- **(c) Attribution markers.** "According to X", "purportedly", "in X's view", and free-indirect framing. Claims the source attributes to others must not move into the narrative voice, and the author's own explicit judgments ("was right to", "reasonably judged") must not be deleted. Resolve a pronoun to the actor the source means, never to the nearest noun.
- **(d) Aggregation ban.** No total, average, ratio, or conversion may appear that the source does not itself state. Where the source prints components separately, keep them separate. Do not round.
- **(e) Claim-evidence pairing.** If a claim is cut, its supporting evidence is cut with it; if evidence is kept, the claim it supports is kept. Evidence left without its claim reads as a non-sequitur even when every sentence is accurate.

Quotations match the source exactly. Do not add quotations the source does not have, and do not print a source quotation without quotation marks.

## Style

- Write concrete, direct prose. Cut filler, throat-clearing, rhetorical setups, and formulaic transitions ("It is important to note that", "When it comes to", "serves as", "plays a key role in").
- Prefer active voice. Use passive voice when the actor is unknown, unspecified, or irrelevant, and do not invent an actor to avoid it.
- Cut unnecessary adverbs and intensifiers. Keep words that express uncertainty, frequency, degree, attribution, or scope.
- Do not use em dashes in summary prose. Text inside quotation marks keeps its original punctuation, and extracted source text is never edited.
- Avoid formulaic "not X but Y" framing. When the source draws a real contrast, state it plainly.
- Vary sentence length naturally, without forcing it or writing awkward circumlocutions.
- Write in the third person. Never address the reader.
- Attribute arguments, disputed claims, interpretations, and allegations clearly. Do not present a quoted opponent's view as the author's.
- Keep qualifications and distinctions. Do not turn association into causation, possibility into certainty, or a single example into a general claim.
- Explain source-defined terms for a reader who has not read the original, using only the source.
- Keep every sentence parseable on first reading. Compression produces garden-path sentences, dangling modifiers, gapped verbs, and pronouns whose antecedent was cut. Name the actor when a pronoun could point two ways.
- Write in paragraphs. Use a list only where the source passage is itself a list.
- Add no editorial commentary, outside fact-checking, or unsupported content.

## Where these rules override stop-slop

The stop-slop skill is written for persuasive or explanatory prose. An attributed summary of a source needs these exceptions:

| stop-slop says | Here |
|---|---|
| Remove adverbs | Cut only empty ones. Hedges and scope words are protected by (b). |
| Avoid passive voice | Prefer active voice; keep passive where the actor is unknown. |
| Trust readers; skip softening | Hedges state the author's epistemic position. Keep them. |
| Cut binary contrasts | Cut only formulaic "not X but Y". Real source contrasts are protected by (a). |
| Address the reader as "you" | Never address the reader. Third person only. |
| Put the reader in the scene | Does not apply. |
| Cut quotable lines | Does not apply to quoted source material. |
| Score the draft | Ignore the scoring table. |

The goal is prose that is concise and understandable. Where applying a rule would make a passage harder to read, do not apply it. A sentence that is plain but clear is finished.
