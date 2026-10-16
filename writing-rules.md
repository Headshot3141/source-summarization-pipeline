# Writing Rules for All Agents

These are the shared writing instructions for every agent that writes, edits, reviews, or verifies a summary. They are complete on their own: no other style guide applies.

Priority order: fidelity to the source first, then coverage of the main arguments, then clear standalone prose, then style preferences and word targets. Where a style instruction conflicts with fidelity, follow fidelity.

Report what each source argues. Do not endorse, refute, fact-check, or add outside context. The summary speaks in the author's voice: a reader of a summary knows its claims and opinions are the author's, so state them directly, without "the author argues" or the author's name. Mark only views that belong to someone else (quotations, allegations, objections, and views the author describes or rejects), so that none of them reads as the author's own.

## The source as printed

The summary reproduces what the source says, including its errors. If the source prints a wrong date, a misspelled name, or figures that do not add up, the summary keeps the source's version. Do not correct the author from your own knowledge, and do not use your knowledge to judge whether a claim is true. Silently correcting the source is itself an error. If something in the source looks like an extraction artifact, such as a broken word or stray character, rather than the author's text, report it and do not guess.

Misprints are handled by kind:

- A misprint that changes a fact (a date, a figure, a name) stays as printed.
- A letter-level typo whose intended word is unmistakable ("shilllings", "teh") is written correctly in the summary's own prose, and exactly as printed inside quotation marks.
- A garbled or incomplete passage is summarized only as far as its sense is clear. Never supply a missing word, figure, or completion; report it. Where a printed phrase admits two readings, keep a wording that stays neutral between them.
- Rulings the coordinator or the user makes on a printed fault are listed in `settled.md`, in the section for the source. Follow them, and do not report them again.

## Preservation rule (binding)

In earlier runs, the most common errors made a summary more confident or more assertive than its source, and every such summary was inside its word budget. These source features must survive into the summary with their force intact. Losing any of them is a material error, not a style trim, and preservation outranks the word budget.

The rule governs what a summary keeps. A whole minor point may still be left out, hedge and all. What may not happen is keeping a claim while dropping its hedge, contrast, condition, frame, or the evidence it rests on. (In one run a drafting model read the rule as forbidding any cut to a hedged claim, overran its budgets by a fifth to a third, and then met them by cutting main arguments whole.)

- **(a) Contrast reversals.** Where the source qualifies or reverses a claim ("But", "Yet", "However", "Even so", "Nevertheless", "In truth", "Although", "On the other hand"), the reversal appears in the summary wherever the first half appears, attached to the same scope. Dropping the second half leaves the concession standing as the author's whole view.
- **(b) Epistemic modality.** Hedges ("perhaps", "probably", "seemingly", "apparently", "tended to", "often", "not necessarily", "may have"), counterfactual mood ("would have been"), estimate markers ("it is reckoned", "it is estimated"), and scope words ("some", "most", "only", "main", "modern", "certain", "always", "in effect") keep the source's strength. They are meaning, never "unnecessary adverbs". When you split a source sentence, a hedge or frame that governed the whole of it ("it may be said", "perhaps", "according to X") goes into each resulting sentence. The author's statements about how strongly the text itself is asserted belong here too: a disclaimer that it is not final truth, or that something is a sketch, a hypothesis, or open to discussion, qualifies everything around it, so it is never a minor point to cut for length.
- **(c) Attribution markers.** "According to X", "purportedly", "in X's view", and free-indirect framing. The narrative voice belongs to the author, so a claim the source attributes to someone else keeps its marker and never moves into it, and a view the author describes in order to reject stays marked as someone else's. The author's own explicit judgments ("was right to", "reasonably judged") must not be deleted. Resolve a pronoun to the actor the source means, never to the nearest noun. Never attach the author's comment to another speaker's words with a colon or an apposition, which carries the comment into the speaker's mouth: the reported words end their sentence, and the author's comment starts a new one. The author's own claims need no attribution (see "Naming the author").
- **(d) Aggregation ban.** No total, average, ratio, or conversion may appear that the source does not itself state. Where the source prints components separately, keep them separate. Do not round.
- **(e) Claim-evidence pairing.** If a claim is cut, its supporting evidence is cut with it; if evidence is kept, the claim it supports is kept. Evidence left without its claim reads as a non-sequitur even when every sentence is accurate.
- **(f) Statements the author does not assert.** Not every sentence in the author's prose is the author's claim. Hypotheticals and thought experiments ("suppose", "imagine"), positions taken up for argument's sake ("one might say", "granted", "on this view"), views the author held earlier and dropped, other people's views given in free indirect style, irony, and questions all keep a frame showing they are not the author's settled position. The summary speaks in the author's voice, so an unframed statement reads as the author's assertion, and dropping the frame turns it into one. For irony, state what the source means, at its strength; if you cannot tell whether a passage is ironic, keep the source's framing and flag it. A question the source leaves open stays open ("Whether the closure was deliberate is left open"). Never answer it.
- **(g) Conditions, negation, sequence, and reach.** A condition ("if", "unless", "only when", "provided that") stays attached to its claim. A negation keeps its scope: "not all" never becomes "none", and "not because A but because B" keeps both halves. Order words ("before", "after", "until", "by 1930", "at first", "eventually") keep the source's sequence, and two events are never set side by side in a way that implies an order or a cause the source does not give. Reach words keep their reach: "one of the largest" never becomes "the largest", and one example never becomes a general claim. Example markers ("for example", "such as", "to mention only", "particularly") are reach words: drop one and the example reads as the whole. Verbs of agency and degree keep their strength: "contributed to" is not "caused", "designed to regulate" is not "regulated", "seeks to" is not "does", "similar" is not "the same", and "under the impulse of" is not "founded".

Quotations match the source exactly. Do not add quotations the source does not have, and do not print a source quotation without quotation marks (a block quotation, below, uses `> ` instead). Text inside quotation marks is always the source's exact words: never condense or correct it. Where the exact words are not needed, give an attributed paraphrase without quotation marks, at the quotation's strength.

## Block quotations (binding)

In a chapter source, a paragraph that starts with `> ` is a block quotation: another person's words (an interviewee, a writer, a poem or song, an epigraph at the head of a chapter), set off from the author's text. Consecutive `> ` paragraphs are one quotation; verse is often one paragraph per stanza or line. The author's lead-in before it and commentary after it are the author's own prose.

A summary handles each block quotation in exactly one of these ways:

- **Reproduce it whole and unchanged**, as a Markdown block quotation with every paragraph starting `> `, introduced by a sentence that names the speaker as the source does. Copy every word, spelling, capital, ellipsis, bracket, and punctuation mark as printed, dialect and errors included. Leave out only the parenthetical citation or dash attribution that ends it, such as "(Marlow 1986, 82)" or "—Ada Penhale 1937, 16", because the summary carries no citations.
- **Or drop it entirely.**
- **Under REGISTER: modern only (see "Register"), or give it as attributed paraphrase**: plain modern prose inside an ordinary paragraph, marked throughout as the quoted speaker's view (rule (c)) and at its strength, with no quotation marks and no `> `. Use it where the author's argument needs the quotation's content but not its exact words, and its old wording would stop a present-day reader. It is still all or nothing: the whole quotation verbatim as a block, or its content in paraphrase with no quoted words, or nothing.

Apart from that one option, never paraphrase, condense, excerpt, or partially quote a block quotation, and never restate what it says in your own words or in the author's voice. The author's own sentences about it, the lead-in and the analysis that follows, are summarized like any other prose. When you drop a quotation, keep what the author says about it only if that stands on its own without the quotation's content. Reproduce a quotation only when the author's argument turns on its words: it counts toward the word budget.

## Naming the author (binding)

In an earlier run, one book's summary named its author about once every 80 words. Sentence after sentence opened "X argues", "X notes", "X's view is". Two things caused it: agents attributed every claim to the author, and a later fix replaced every "he" with the name, because the source never gendered the author. Every sentence was accurate, and the summary was tiring to read.

- **State the author's views directly.** The summary's narrative voice is the author's. Write the author's claims, opinions, and judgments as plain statements, with no "the author argues", "X notes", "X believes", or "in the author's view". Do not add the author's name to show that a statement is an opinion: the source's own hedges and evaluative words carry that, and rule (b) keeps them.
- **Name the author only where a sentence needs it,** at most once per paragraph. A sentence needs it when the author is an actor in the events ("Penhale moved to Leeds in 1930"), or to mark the return to the author's view after another speaker's view in the same paragraph. Start a new paragraph for the author's reply where you can instead.
- **Every form counts.** The name, "the author", "the authors", a possessive ("X's view"), and a pronoun are all references. Don't swap the name for one of them to get around the limit. Rewrite instead: make the claim, the event, or the group the subject of the sentence. A reference to the work ("the essay", "the chapter") is one more reference, so use it sparingly.
- **Attribution clarity outranks the limit.** When a paragraph reports several speakers and the author's view has to be told apart from theirs more than once, a further brief reference is allowed. Never let a claim drift between speakers to save a name.
- **Other voices get the marker.** In an interview collection or an edited volume, the narrative voice belongs to the person the AUTHOR line in your prompt names for the unit, such as the interviewee or the essay's author. Mark everyone else, interviewer included.
- **Pronouns follow the convention set for each source** (the coordinator puts it in your prompt). Never infer gender from a name. When the source never genders its author, as is common in a book written in the first person, use no pronoun for the author. Never substitute the name for every pronoun.
- **First-person passages** (memoir, an author's preface): where the author is the subject of the events, name the author once and carry on. Do not turn every "I" into the name. Where the author argues in the first person ("I fail to see", "we must"), keep it as the author's voice when the AUTHOR line in your prompt says the first person stays: recasting "I fail to see any alternative" as "Penhale fails to see any alternative" reads as a criticism of the author, so the third person can change the meaning.
- **A marker covers its own sentence,** and later sentences only when they carry it forward ("on this view", "in their account", reported speech). A paragraph that continues another speaker's view re-marks it in its first sentence, and every switch from another speaker's view back to the author's is marked.
- **This does not weaken rules (c) and (f).** Attribution drift means moving someone else's claim into the narrative voice, where it reads as the author's, or deleting the marker that separates another speaker's view, a hypothetical, or a position taken up for argument's sake from the author's own view. A plain statement of the author's own view is not drift. When you restore a missing marker, attach it to the other speaker's view, not to the author's.

The check script `Work/check_author_refs.py` flags paragraphs with more than one reference. It counts names and "the author", not pronouns, so read for pronoun chains too. A paragraph it passes can still carry a reference it does not need: remove an "X argues" that only prefaces the author's own view.

## Shape of a summary (binding)

A summary condenses its source in the source's own order. Think of it as two pages of the source becoming about one page of summary: the same content in the same sequence, denser, with minor material left out.

- **Follow the source's order.** Summarize the source passage by passage, from start to finish. Do not regroup material by theme, move a conclusion to the front, or gather scattered points into one place.
- **Add no structure the source lacks.** Do not invent an introduction, an overview, a "main ideas" or "key arguments" section, a list of takeaways, or a closing summary. A summary opens with what the source opens with, and has an introduction or a conclusion only where the source has one.
- **Headings.** Use the `##` chapter heading your prompt gives. Use a `###` heading only where the source itself has a section heading at that point, with the source's wording. Never add a heading of your own.
- **Make room by leaving things out, not by squeezing sentences.** When the budget is tight, drop whole minor points first: secondary examples, digressions, repetition, and asides. Do not strip the words a sentence needs to read clearly, such as articles, connecting words, and the nouns that pronouns refer to. A sentence that needs a second reading saves nothing.
- **Notes.** A chapter source may end with a notes block, headed "Notes to this chapter (printed as footnotes in the source):" or "(printed at the back of the book):". Where a note adds substance to the text, put that substance into the summary at the point where the note's number appears, as ordinary prose with no note number, at the note's own strength. Leave out notes that only cite sources. Never summarize the notes block as a section of its own.
- **Tables.** Where the argument depends on a table, give the figures it uses in prose, exactly as printed, with what each one measures. Never reproduce the table, and never total, average, or round its figures (rule (d)).
- **Extraction escapes.** A backslash at the start of a source paragraph (`\#`, `\>`) was added in extraction so the text is not read as Markdown. It is not the author's; do not copy it into a summary or a quotation. Do not start a summary paragraph with `#` or `>` either, since Markdown would read it as a heading or a block quotation: rephrase so the paragraph opens with a word.
- **Connect points only as the source does.** Use the connecting word the source supports ("because", "so", "by contrast", "later"). Never add a causal or contrastive link the source does not make; where the source simply moves on, start a new paragraph.

## Register (binding)

Older prose is hard for a present-day reader to follow, so the rules for clarity depend on when the English you are summarizing was written. Your prompt gives a REGISTER for the chapter, set by the coordinator from the date of that English text (for a translation, the date of the translation, not of the original).

- **REGISTER: source.** The English dates from 1950 or later. Write plain, current prose under the Style rules below: recast a sentence the source built hard to read wherever the source makes the meaning certain, and otherwise keep the source's own vocabulary.
- **REGISTER: modern.** The English dates from before 1950 (a nineteenth- or early twentieth-century text or translation), or is a later translation that reads as antiquated. Write the summary in clear modern English that a present-day reader follows on first reading. A summary that only shortens the source's sentences and keeps its vocabulary and syntax has not done this job.

Rewording changes how a thing is said, never what is said. Every rule in this file still applies to the reworded sentence, and fidelity outranks modern wording wherever the two conflict.

Under REGISTER: modern, modernize:

- **Sentence structure.** Break long periodic sentences into several. Bring subject and verb together. Undo inverted word order. Each new sentence keeps every qualification its source sentence carried, and a hedge or frame that governed the whole source sentence goes into each of them (rules (a), (b), (g)).
- **Archaic and obsolete words and forms.** "Hitherto" becomes "until now", "wherefore" becomes "so", "whilst" becomes "while", "viz." becomes "namely", "shew" becomes "show", "connexion" becomes "connection", "it behoves us" becomes "we must".
- **Formal, bookish, and translated-sounding prose.** Old translations are often as hard to read as old English. Where an everyday word or construction says the same thing at the same strength, use it: "insofar as" becomes "to the extent that" or "because", "untenable" becomes "does not hold up", "herein lay" becomes "this was", and "the former" and "the latter" become the nouns they mean. Unpack noun chains and abstract nouns doing a verb's work ("the affirmation of the central principle" becomes "insisting on the central principle"), stacked "of" phrases, and "It is ... that" openings. Test each sentence: would a careful present-day writer of serious nonfiction put it this way? If not, recast it.
- **Dated idiom and ceremonial address** that obscure the point ("Gentlemen, permit me to observe"). Keep the point, and keep who is being addressed where the argument needs it.
- **Period terms for groups of people** that read today as offensive or misleading: follow the decision recorded in `settled.md` (General). Where it says to render them in current usage, use the current term that matches the source's meaning, in the summary's own prose only; words inside quotation marks stay exactly as printed.

In every register, keep exactly as the source has them:

- **Terms of art** and every word the source defines or uses in a special sense (Style, below). A word whose meaning has shifted since the source was written (the name of a party or movement, a political or economic term, an old office or unit) keeps the source's word and the source's meaning: never swap in a modern word that now means something else, and never explain it from outside knowledge.
- **Names, titles, and places** of people, places, organizations, publications, and events, as printed, including old transliterations and old place names. Add no present-day equivalent ("now known as"): that is outside context.
- **Headings.** Chapter titles and section headings are names, not prose to modernize.
- **The source's spelling convention.** British spelling stays British. Under REGISTER: modern, only obsolete spellings change.
- **Numbers, dates, currencies, and units** as printed, with no conversion (rule (d)).
- **The author's vantage in time.** "Now", "at present", "recent", and "in our day" mean the author's present. Keep them relative to the author's time, and never turn them into dates or into today's world.
- **Strength and tone.** A hedge keeps its strength in modern words ("it may well be doubted whether" becomes "it is very doubtful whether"), never a flat statement. A fierce polemic stays fierce, irony stays irony, and a cautious claim stays cautious: do not soften, sharpen, or explain away anything while rewording.
- **Images.** Metaphors and figures of speech are the author's rhetoric, not dated wording: keep them, and reword only the words around them. Where a translated figure reads oddly in English, use the plain word that carries the same sense and force.
- **Quotations.** Text in quotation marks and block quotations is never reworded (see "Quotations" above and "Block quotations").

Rewording adds nothing. Do not explain historical references the source assumes its reader knows (an event, a person, a party): that would be outside context.

## Style

The goal is prose that is clear and concise for a reader who has not read the source. Everything in this section serves that goal. The Requirements below always apply. The Guidance patterns are judgment: a sentence that is plain but clear is finished, so do not rework it to satisfy a Guidance item, and never make a passage awkward or roundabout to avoid one of those patterns.

### Requirements

- Never address the reader. Write in the third person, except where the author's own first person stays (see "First-person passages").
- Do not use em dashes in summary prose. Text inside quotation marks and block quotations keeps its original punctuation, and extracted source text is never edited.
- Write in paragraphs, with a blank line between paragraphs, before and after every heading, and around every block quotation and list; without it Markdown runs them together. Use a list only where the source passage is itself a list. Apart from the headings described in "Shape of a summary" and a reproduced block quotation (`> `), the only Markdown in a summary is italics, as single asterisks (`*The Grey Harbour*`), for titles of works, foreign words, and words the source itself italicises for emphasis. Never use `**` or `_`, which print literally.
- State the author's views directly (see "Naming the author"). Clearly mark views that belong to others: quoted speakers, opponents, cited writers, and allegations. Do not present a quoted opponent's view as the author's.
- Keep qualifications and distinctions. Do not turn association into causation, possibility into certainty, or a single example into a general claim.
- Explain source-defined terms for a reader who has not read the original, using only the source. Keep each term of art in the source's word: never swap it for a plainer word with different connotations, or for a neighbouring term, because the source may rest an argument on the difference. Use a plain synonym only where the source treats the two as the same.
- Keep the author's metaphors and figures when you reword, rather than flattening them into literal statement. A dropped image is an omission, not an error, so restoring one never justifies words above a ceiling.
- Keep every sentence parseable on first reading. Compression produces garden-path sentences, dangling modifiers, gapped verbs, and pronouns whose antecedent was cut. Name the actor when a pronoun could point two ways.
- Every pronoun, "this" or "these", "which", and "the X" that points back must point at the noun the source means. When the nearest preceding noun of the same number is a different one, repeat the source's noun. After any cut or insertion, check the first pronoun or "the X" in the next sentence: it may now point at the wrong thing.
- Correlatives are complete and parallel ("either ... or", "neither ... nor", "not only ... but also"); a comparative names what it is compared with; a list whose items contain commas uses semicolons; a restrictive or non-restrictive clause keeps the source's punctuation, because the comma changes which things the clause covers.
- Summary prose is the summary's own, not quotation. A hard construction copied from the source (a gapped verb, a stacked clause, an old word order) is recast in plain wording wherever the source makes the meaning certain. Text inside quotation marks and block quotations, deliberate rhetorical figures, and genuine ambiguity in the source's meaning stay as they are. Under REGISTER: modern, go further and modernize the wording throughout (see "Register").
- Recast the source's references to its own layout ("the preceding pages", "see below", "in Chapter 9", "this book") so they name what was said, or cut them: a reader of the summary has no pages to turn to.
- Add no editorial commentary, outside fact-checking, or unsupported content.

### Guidance

These patterns usually make a summary less clear. Use judgment: where the plain way to say something matches one of them, say it plainly.

- **Filler and throat-clearing.** Phrases that announce a point instead of making it: "It is important to note that", "It is worth noting", "When it comes to", "At its core", "The reality is", "Here's why". Make the point.
- **Meta commentary.** "This chapter explores", "The author then turns to", "As we will see". Report what the chapter says, not that it says something. Keep a signpost the source itself gives.
- **Empty emphasis.** Intensifiers that add no meaning: "really", "truly", "deeply", "fundamentally", "crucially", "importantly". Keep any word that expresses uncertainty, frequency, degree, or scope, as rule (b) requires, and keep the source's own evaluative words.
- **Vague declaratives.** "The implications are significant", "The reasons are structural". Name the implication or the reason the source gives, or cut the sentence.
- **Stock phrases and jargon.** "Plays a key role in", "serves as", "navigate challenges", "unpack", "landscape", "deep dive". Use the plain word, unless it is the source's own term.
- **Formulaic contrasts and reveals.** "Not X, but Y", "The question isn't X. It's Y.", "It wasn't X. It wasn't Y. It was Z." State the point directly. When the source draws a real contrast, keep it (rule (a)) and state it plainly.
- **Rhetorical setups and fragments.** Rhetorical questions you add, "Think about it:", staccato fragments for drama ("And Y. And Z."). Write complete sentences. A question the source asks and leaves open is not a rhetorical setup: keep it open (rule (f)).
- **Passive voice and vague actors.** Prefer active voice when the source names the actor. Use passive voice when the actor is unknown, unspecified, or irrelevant, and never invent an actor to avoid it. The same goes for abstractions doing human verbs ("the decision emerged"): name the person if the source does, otherwise keep the source's framing.
- **Repeated conclusions.** A sentence that restates what the paragraph or chapter has just said ("In short", "Ultimately", "Taken together"). End on the last substantive point. Keep a conclusion the source itself draws.
- **Slogans and pull-quote endings.** A punchy closing line such as "It was a system built on fear." Besides reading as filler, it often adds emphasis or a judgment the source does not make, which is a fidelity error. Close with the source's own point, at the source's strength.
- **Forced groups of three.** Lists of three adjectives, examples, or clauses added for cadence. Give as many items as the source supports; when the source lists three, keep all three.
- **Monotonous rhythm.** Several sentences of the same shape in a row, or paragraphs that all open or close the same way. Vary sentence length naturally, never at the cost of clarity.
