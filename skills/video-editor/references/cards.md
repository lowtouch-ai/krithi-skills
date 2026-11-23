# Keyword cards

Short panels that appear under the captions and name the idea being spoken. They were modelled on a reel the team made: a navy card with a thin magenta top line, a small green all-caps **label**, and white **pills**. Each pill appears at the moment its words are spoken, and the pill being spoken is magenta. With `chain: true`, arrows join the pills (a sequence such as Plan, Build, Ship).

## When to use them
**Add cards by default to every clip that explains something**: the speaker is teaching, comparing, arguing for an idea or walking through steps. That is most business talks, and it includes opinions and explanations: an argument that names its ideas ("small reviews beat big ones", "the cutover plan") is explanatory. A card marks each idea as it is introduced, so a viewer watching on mute can follow the argument.

Leave cards off only for a clip that is purely a story or a personal anecdote with no named ideas. When you propose such a clip, or any clip with no cards, say so and why at the approval step, so the user can ask for cards. If the user says no cards, add none.

Two kinds of card, both welcome:
- **A list or a process.** The speaker names several things ("a laptop, an account, a first task") or steps ("plan, build, ship"). One card, one pill per item, `chain: true` for steps.
- **A single idea.** The speaker introduces one named concept ("code review", "a faster feedback loop"). One card with one pill. Do not skip these: they are what keeps the viewer oriented between the lists.

**How many.** On an explanatory clip aim for about one card every 12 to 15 seconds: roughly 4 or 5 cards in a 60 second clip, 5 or 6 in 75 seconds. Never more than one every 8 seconds (the checker warns). A clip with only one or two cards in a minute is probably missing ideas; read it again and mark each place where a new idea is named. A clip with none is right only when nothing in it is a named idea. If a clip's opening has no named idea (a long first stretch of setup), start the first card later: that is fine, but check that the rest of the clip is not under-marked.

Example (an invented 75 second clip about onboarding new engineers): "THE FIRST WEEK" with the pills "Set up laptop", "Meet the team", "Ship a small fix"; "WHY IT MATTERS" with "Fast feedback"; "HOW WE REVIEW" (a chain) with "Draft", "Review", "Merge".

## What a card is
**The label is a heading; the pill is the term. Do not repeat one as the other.** "THE FIRST WEEK" over the pill "Set up laptop" is right; "SET UP LAPTOP" over "Set up laptop" says the same thing twice (the checker warns). Give the label context the pill lacks: a category ("WHAT WE MEASURE"), a role ("THE OWNER'S PART"), a stage ("BEFORE LAUNCH"), a contrast. If the only thing to say is the term itself, drop the card or fold it into a neighbouring one.

Keep a card on screen for at least 3 seconds: if two ideas come within 3 seconds of each other, make them two pills on one card, not two cards (the checker warns).

- **`label`**: 1 to 7 words, up to 36 characters. It is a short heading that **summarises what was said** ("THE FIRST WEEK", "HOW WE REVIEW"). It may paraphrase. It must not add a claim, a name or a number that the speaker did not say. The user approves it.
- **`items`**: 1 to 4 pills. Each has `text` (what is shown, up to 26 characters, usually the speaker's own term) and `say` (the exact words as spoken in the clip). The checker finds `say` in the transcript, rejects the card if those words are not spoken in the clip, rejects items that are not in the order they are spoken, and takes the pill's timing from the word. Each item is searched for **after the previous item**, so an earlier use of the same word does not count (if "coding" is said before the first item, pick words said later). The resolved clip lists each card's and pill's time in the finished clip (`clip_start`, `clip_at`, after dead-air pauses are removed) so you can check them against the video.
- **`chain`**: true when the items are steps in order.
- Numbers in a label or pill must appear in the clip's words. Follow `copy-style.md`: no em dashes, no hype words.

## How to choose
1. Read the clip's sentences and mark each place where the speaker names a thing or a list.
2. Group one idea into one card; give it a label; list its terms in spoken order.
3. Keep pills short (a term, not a sentence).
4. Show the user the card list (label, pills and the second each appears) as part of the clip approval step, and drop any they do not want.

The name tag and the cards share the bottom of the frame. On a clip with cards the name shows from the end of the cover until half a second before the first card, if that leaves at least 3 seconds; otherwise it is skipped (the render report says which). The speaker's name never shows at the same time as a card.
