# Writing Rules for All Agents

These are the shared writing instructions for every agent that writes, edits, reviews, or verifies a summary. They are complete on their own: no other style guide applies.

Priority order: fidelity to the source first, then coverage of the main arguments, then clear standalone prose, then style preferences and word targets. Where a style instruction conflicts with fidelity, follow fidelity.

Report what each source argues. Do not endorse, refute, fact-check, or add outside context. The summary speaks in the author's voice: a reader of a summary knows its claims and opinions are the author's, so state them directly, without "the author argues" or the author's name. Mark only views that belong to someone else (quotations, allegations, objections, and views the author describes or rejects), so that none of them reads as the author's own.

## The source as printed

The summary reproduces what the source says, including its errors. If the source prints a wrong date, a misspelled name, a misprint, or figures that do not add up, the summary keeps the source's version. Do not correct the author from your own knowledge, and do not use your knowledge to judge whether a claim is true. Silently correcting the source is itself an error. If something in the source looks like an extraction artifact, such as a broken word or stray character, rather than the author's text, report it and do not guess.

## Preservation rule (binding)

In earlier runs, the most common errors made a summary more confident or more assertive than its source, and every such summary was inside its word budget. These source features must survive into the summary with their force intact. Losing any of them is a material error, not a style trim, and preservation outranks the word budget.

- **(a) Contrast reversals.** Where the source qualifies or reverses a claim ("But", "Yet", "However", "Even so", "Nevertheless", "In truth", "Although", "On the other hand"), the reversal appears in the summary wherever the first half appears, attached to the same scope. Dropping the second half leaves the concession standing as the author's whole view.
- **(b) Epistemic modality.** Hedges ("perhaps", "probably", "seemingly", "apparently", "tended to", "often", "not necessarily", "may have"), counterfactual mood ("would have been"), estimate markers ("it is reckoned", "it is estimated"), and scope words ("some", "most", "only") keep the source's strength. They are meaning, never "unnecessary adverbs".
- **(c) Attribution markers.** "According to X", "purportedly", "in X's view", and free-indirect framing. The narrative voice belongs to the author, so a claim the source attributes to someone else keeps its marker and never moves into it, and a view the author describes in order to reject stays marked as someone else's. The author's own explicit judgments ("was right to", "reasonably judged") must not be deleted. Resolve a pronoun to the actor the source means, never to the nearest noun. The author's own claims need no attribution (see "Naming the author").
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

In an earlier run, one book's summary named its author about once every 80 words. Sentence after sentence opened "X argues", "X notes", "X's view is". Two things caused it: agents attributed every claim to the author, and a later fix replaced every "he" with the name, because the source never gendered the author. Every sentence was accurate, and the summary was tiring to read.

- **State the author's views directly.** The summary's narrative voice is the author's. Write the author's claims, opinions, and judgments as plain statements, with no "the author argues", "X notes", "X believes", or "in the author's view". Do not add the author's name to show that a statement is an opinion: the source's own hedges and evaluative words carry that, and rule (b) keeps them.
- **Name the author only where a sentence needs it,** at most once per paragraph. A sentence needs it when the author is an actor in the events ("Penhale moved to Leeds in 1930"), or to mark the return to the author's view after another speaker's view in the same paragraph. Start a new paragraph for the author's reply where you can instead.
- **Every form counts.** The name, "the author", "the authors", a possessive ("X's view"), and a pronoun are all references. Don't swap the name for one of them to get around the limit. Rewrite instead: make the claim, the event, or the group the subject of the sentence. A reference to the work ("the essay", "the chapter") is one more reference, so use it sparingly.
- **Attribution clarity outranks the limit.** When a paragraph reports several speakers and the author's view has to be told apart from theirs more than once, a further brief reference is allowed. Never let a claim drift between speakers to save a name.
- **Other voices get the marker.** In an interview collection or an edited volume, the narrative voice belongs to the person the AUTHOR line in your prompt names for the unit, such as the interviewee or the essay's author. Mark everyone else, interviewer included.
- **Pronouns follow the convention set for each source** (the coordinator puts it in your prompt). Never infer gender from a name. When the source never genders its author, as is common in a book written in the first person, use no pronoun for the author. Never substitute the name for every pronoun.
- **First-person passages** (memoir, an author's preface): where the author is the subject of the events, name the author once and carry on. Do not turn every "I" into the name.
- **This does not weaken rule (c).** Attribution drift means moving someone else's claim into the narrative voice, where it reads as the author's, or deleting the marker that separates another speaker's view from the author's. A plain statement of the author's own view is not drift. When you restore a missing marker, attach it to the other speaker's view, not to the author's.

The check script `Work/check_author_refs.py` flags paragraphs with more than one reference. It counts names and "the author", not pronouns, so read for pronoun chains too. A paragraph it passes can still carry a reference it does not need: remove an "X argues" that only prefaces the author's own view.

## Style

The goal is prose that is clear and concise for a reader who has not read the source. Everything in this section serves that goal. The Requirements below always apply. The Guidance patterns are judgment: a sentence that is plain but clear is finished, so do not rework it to satisfy a Guidance item, and never make a passage awkward or roundabout to avoid one of those patterns.

### Requirements

- Write in the third person. Never address the reader.
- Do not use em dashes in summary prose. Text inside quotation marks and block quotations keeps its original punctuation, and extracted source text is never edited.
- Write in paragraphs. Use a list only where the source passage is itself a list. Apart from the headings your prompt asks for, the only other Markdown in a summary is a reproduced block quotation (`> `).
- State the author's views directly (see "Naming the author"). Clearly mark views that belong to others: quoted speakers, opponents, cited writers, and allegations. Do not present a quoted opponent's view as the author's.
- Keep qualifications and distinctions. Do not turn association into causation, possibility into certainty, or a single example into a general claim.
- Explain source-defined terms for a reader who has not read the original, using only the source.
- Keep every sentence parseable on first reading. Compression produces garden-path sentences, dangling modifiers, gapped verbs, and pronouns whose antecedent was cut. Name the actor when a pronoun could point two ways.
- Add no editorial commentary, outside fact-checking, or unsupported content.

### Guidance

These patterns usually make a summary less clear. Use judgment: where the plain way to say something matches one of them, say it plainly.

- **Filler and throat-clearing.** Phrases that announce a point instead of making it: "It is important to note that", "It is worth noting", "When it comes to", "At its core", "The reality is", "Here's why". Make the point.
- **Meta commentary.** "This chapter explores", "The author then turns to", "As we will see". Report what the chapter says, not that it says something. A brief signpost is fine where the source's structure itself matters to the argument.
- **Empty emphasis.** Intensifiers that add no meaning: "really", "truly", "deeply", "fundamentally", "crucially", "importantly". Keep any word that expresses uncertainty, frequency, degree, or scope, as rule (b) requires, and keep the source's own evaluative words.
- **Vague declaratives.** "The implications are significant", "The reasons are structural". Name the implication or the reason the source gives, or cut the sentence.
- **Stock phrases and jargon.** "Plays a key role in", "serves as", "navigate challenges", "unpack", "landscape", "deep dive". Use the plain word, unless it is the source's own term.
- **Formulaic contrasts and reveals.** "Not X, but Y", "The question isn't X. It's Y.", "It wasn't X. It wasn't Y. It was Z." State the point directly. When the source draws a real contrast, keep it (rule (a)) and state it plainly.
- **Rhetorical setups and fragments.** Rhetorical questions, "Think about it:", staccato fragments for drama ("And Y. And Z."). Write complete declarative sentences.
- **Passive voice and vague actors.** Prefer active voice when the source names the actor. Use passive voice when the actor is unknown, unspecified, or irrelevant, and never invent an actor to avoid it. The same goes for abstractions doing human verbs ("the decision emerged"): name the person if the source does, otherwise keep the source's framing.
- **Repeated conclusions.** A sentence that restates what the paragraph or chapter has just said ("In short", "Ultimately", "Taken together"). End on the last substantive point. Keep a conclusion the source itself draws.
- **Slogans and pull-quote endings.** A punchy closing line such as "It was a system built on fear." Besides reading as filler, it often adds emphasis or a judgment the source does not make, which is a fidelity error. Close with the source's own point, at the source's strength.
- **Forced groups of three.** Lists of three adjectives, examples, or clauses added for cadence. Give as many items as the source supports; when the source lists three, keep all three.
- **Monotonous rhythm.** Several sentences of the same shape in a row, or paragraphs that all open or close the same way. Vary sentence length naturally, never at the cost of clarity.
