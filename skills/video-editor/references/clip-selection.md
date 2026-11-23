# Choosing short-form moments

How to turn `sentences.md` into a proposal of 30 to 90 second clips. The team's reference: the "Hype vs Reality" reel, a 68 second clip with a contrarian opening and concrete proof. A first draft; refine it with the team's feedback on what they post.

## What makes a clip work
Judge a candidate on these four, in this order:
1. **Hook.** The first sentence must make a stranger stay: a contrarian claim, a specific number, a question they already have, or the middle of tension ("Most companies are stuck in pilots."). It must not open on a connective ("so", "and", "but"), a filler ("yeah", "okay"), or the tail of an answer to a question the viewer never heard.
2. **Self-contained.** Someone with no context understands it fully. No pronouns pointing at something said earlier, no "like I said", no setup that sits outside the clip. If it needs the previous five minutes, it is not a clip.
3. **Payoff.** Something lands: a conclusion, a reversal, a concrete rule, a number that reframes the topic. If you cannot name what the viewer walks away with, score it under 50 and do not propose it.
4. **Quotable.** At least one sentence a person would repeat or screenshot.

## Boundaries
- A leading "so" is fine when it begins the question that gives the clip its hook ("So, is that really true?"). Otherwise start a sentence later.
- Start on the first word of a complete thought; end on the last word of one, ideally the strongest line, not a trailing qualification. Clips are chosen by sentence id (`from`, `to`), so they always start and end on whole sentences.
- Do not stretch a clip to reach a length. A tight 35 second clip beats a padded 80 second one. Do not join two unrelated good moments.
- Clips are 30 to 90 seconds **after** dead-air pauses inside them are removed. Over 90 or under 30 is allowed with a stated reason; under 20 or over 120 is rejected.
- Clips must not overlap. Prefer moments spread across the recording.
- A stumble inside a clip (a false start, a repeated word) is a cost: mention it in the reason, and prefer a cleaner stretch if two are close.

## Scoring (0 to 100, be harsh)
- 85 to 100: would really perform. Strong hook, complete arc, a quotable line.
- 70 to 84: solid. Real payoff, hook could be sharper.
- 50 to 69: watchable but unremarkable. Weak hook or diffuse payoff.
- Under 50: do not propose it. Returning three good clips beats ten padded ones. Saying "nothing here is worth clipping" is a correct answer.

## Each proposed clip needs
- `from` and `to`: sentence ids.
- `hook`: the opening words, copied from the transcript as written. Upper or lower case and punctuation are ignored when the checker compares them with the clip's real start, so a wrong start is caught but you do not need to match commas.
- `title`: under 60 characters, specific, in the speaker's own terms ("Why most companies are stuck in pilots"), not a topic label ("Discussion about AI adoption").
- `caption`: the post text, built only from what was said. No claim the speaker did not make. At most two hashtags.
- `reason`: one or two sentences naming the hook and the payoff, and any weakness. Written for the person who will decide whether to keep it.
- `score`.

Follow `copy-style.md` for the title and caption: no em dashes, no hype words, no "not just X, it's Y".

## Using the user's notes
"Focus on the pricing discussion": propose clips from that section first, and say if the rest has nothing worth clipping. "Skip the first 10 minutes": ignore sentences before then. A named speaker: use only that speaker's sentences when labels exist.

## Presenting the proposal (the approval step)
Show a table, ranked: number, time, length, score, title, hook, and the reason. Then ask which to render, and whether to change any start, end, title or caption. Wait for the answer. Nothing is rendered until the user chooses.
