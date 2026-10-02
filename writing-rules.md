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
- **(c) Attribution markers.** "According to X", "purportedly", "in X's view", and free-indirect framing. Claims the source attributes to others must not move into the narrative voice, and the author's own explicit judgments ("was right to", "reasonably judged") must not be deleted. Resolve a pronoun to the actor the source means, never to the nearest noun. A paragraph's opening attribution covers its later sentences (see "Naming the author"), so a sentence inside it does not need its own "the author argues".
- **(d) Aggregation ban.** No total, average, ratio, or conversion may appear that the source does not itself state. Where the source prints components separately, keep them separate. Do not round.
- **(e) Claim-evidence pairing.** If a claim is cut, its supporting evidence is cut with it; if evidence is kept, the claim it supports is kept. Evidence left without its claim reads as a non-sequitur even when every sentence is accurate.

Quotations match the source exactly. Do not add quotations the source does not have, and do not print a source quotation without quotation marks (a block quotation, below, uses `> ` instead).

## Block quotations (binding)

In a chapter source, a paragraph that starts with `> ` is a block quotation: another person's words (an interviewee, a writer, a poem or song, an epigraph at the head of a chapter), set off from the author's text. Consecutive `> ` paragraphs are one quotation; verse is often one paragraph per stanza or line. The author's lead-in before it and commentary after it are the author's own prose.

A summary handles each block quotation in exactly one of two ways:

- **Reproduce it whole and unchanged**, as a Markdown block quotation with every paragraph starting `> `, introduced by a sentence that names the speaker as the source does. Copy every word, spelling, capital, ellipsis, bracket, and punctuation mark as printed, dialect and errors included. Leave out only the parenthetical citation or dash attribution that ends it, such as "(Marlow 1986, 82)" or "—Ada Penhale 1937, 16", because the summary carries no citations.
- **Or drop it entirely.**

Never paraphrase, condense, excerpt, or partially quote a block quotation, and never restate what it says in your own words or in the author's voice. The author's own sentences about it, the lead-in and the analysis that follows, are summarized like any other prose. When you drop a quotation, keep what the author says about it only if that stands on its own without the quotation's content. Reproduce a quotation only when the author's argument turns on its words: it counts toward the word budget.

## Naming the author (binding)

In an earlier run, one book's summary named its author about once every 80 words. Sentence after sentence opened "X argues", "X notes", "X's view is". Two things caused it: agents applied the attribution rule sentence by sentence, and a later fix replaced every "he" with the name, because the source never gendered the author. Every sentence was accurate, and the summary was tiring to read.

- **Refer to the author once per paragraph.** Name the author in the sentence that opens the author's line of argument. That attribution covers every later sentence in the paragraph that reports the author's view. Write those sentences as the claims themselves, without a fresh "the author argues", "X notes", or "X adds".
- **Every form counts.** The name, "the author", "the authors", a possessive ("X's view"), and a pronoun are all references. Don't swap the name for one of them to get around the limit. Rewrite instead: make the claim, the event, or the group the subject of the sentence, or join short sentences that share the author as subject. A reference to the work ("the essay", "the chapter") is one more reference, so use it sparingly.
- **One exception: another speaker in the same paragraph.** When a paragraph also reports someone else's view (an opponent, an interviewer, a writer the author cites), the return to the author's view needs a marker. Start a new paragraph for the author's reply where you can. Where the two views have to stay together, one more brief reference to the author is allowed. Attribution clarity outranks the limit: never let a claim drift between speakers to save a name.
- **Pronouns follow the convention set for each source** (the coordinator puts it in your prompt). Never infer gender from a name. When the source never genders its author, as is common in a book written in the first person, use no pronoun for the author and let the paragraph's opening attribution carry the sentences that follow. Never substitute the name for every pronoun.
- **First-person passages** (memoir, an interview answer, an author's preface): frame the passage once ("In the preface, X recalls ...") and then report its content. Do not turn every "I" into the name.
- **This does not weaken rule (c).** A sentence inside a paragraph that opens with the author's attribution is attributed. Attribution drift means moving someone else's claim into the author's voice or the narrative voice. It also means stating the author's claim as fact where no attribution covers it, such as in a paragraph that never names the author, or after another speaker's view without a marker for the return. When you restore an attribution, add it at the paragraph level, not to each sentence.

The check script `Work/check_author_refs.py` flags paragraphs with more than one reference. It counts names and "the author", not pronouns, so read for pronoun chains too.

## Style

- Write concrete, direct prose. Cut filler, throat-clearing, rhetorical setups, and formulaic transitions ("It is important to note that", "When it comes to", "serves as", "plays a key role in").
- Prefer active voice. Use passive voice when the actor is unknown, unspecified, or irrelevant, and do not invent an actor to avoid it.
- Cut unnecessary adverbs and intensifiers. Keep words that express uncertainty, frequency, degree, attribution, or scope.
- Do not use em dashes in summary prose. Text inside quotation marks and block quotations keeps its original punctuation, and extracted source text is never edited.
- Avoid formulaic "not X but Y" framing. When the source draws a real contrast, state it plainly.
- Vary sentence length naturally, without forcing it or writing awkward circumlocutions.
- Write in the third person. Never address the reader.
- Attribute arguments, disputed claims, interpretations, and allegations clearly, once per paragraph for the author (see "Naming the author"). Do not present a quoted opponent's view as the author's.
- Keep qualifications and distinctions. Do not turn association into causation, possibility into certainty, or a single example into a general claim.
- Explain source-defined terms for a reader who has not read the original, using only the source.
- Keep every sentence parseable on first reading. Compression produces garden-path sentences, dangling modifiers, gapped verbs, and pronouns whose antecedent was cut. Name the actor when a pronoun could point two ways.
- Write in paragraphs. Use a list only where the source passage is itself a list. The only other Markdown in a summary is a reproduced block quotation (`> `).
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
| Cut quotable lines | Does not apply to quoted source material. A block quotation is kept whole or dropped whole. |
| Score the draft | Ignore the scoring table. |

The goal is prose that is concise and understandable. Where applying a rule would make a passage harder to read, do not apply it. A sentence that is plain but clear is finished.
