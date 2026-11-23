# Keyword cards

Short panels that appear under the captions and name the idea being spoken. They were modelled on a reel the team made: a navy card with a thin magenta top line, a small green all-caps **label**, and white **pills**. Each pill appears at the moment its words are spoken, and the pill being spoken is magenta. With `chain: true`, arrows join the pills (a sequence such as Build, Runtime, Deployment).

## When to use them
Use them for explanatory moments that name things: a list of qualities, the steps of a process, a contrast between two ideas. Do not force them onto a story or an opinion with no named things. Use 0 to 3 cards per clip: none for a clip that tells a story or gives an opinion with no named things, and never more than one every 8 seconds. About one card every 10 to 15 seconds reads well; the checker warns if they are crowded, and warns if the first one starts inside the 3 second title overlay.

## What a card is
- **`label`**: 1 to 7 words, up to 36 characters. It is a short heading that **summarises what was said** ("THE HUMAN BRINGS", "LOG EVERYTHING"). It may paraphrase. It must not add a claim, a name or a number that the speaker did not say. The user approves it.
- **`items`**: 1 to 4 pills. Each has `text` (what is shown, up to 26 characters, usually the speaker's own term) and `say` (the exact words as spoken in the clip). The checker finds `say` in the transcript, rejects the card if those words are not spoken in the clip, rejects items that are not in the order they are spoken, and takes the pill's timing from the word. Each item is searched for **after the previous item**, so an earlier use of the same word does not count (if "coding" is said before the first item, pick words said later). The resolved clip lists each card's and pill's time in the finished clip (`clip_start`, `clip_at`, after dead-air pauses are removed) so you can check them against the video.
- **`chain`**: true when the items are steps in order.
- Numbers in a label or pill must appear in the clip's words. Follow `copy-style.md`: no em dashes, no hype words.

## How to choose
1. Read the clip's sentences and mark each place where the speaker names a thing or a list.
2. Group one idea into one card; give it a label; list its terms in spoken order.
3. Keep pills short (a term, not a sentence).
4. Show the user the card list (label, pills and the second each appears) as part of the clip approval step, and drop any they do not want.

The name tag and the cards share the bottom of the frame. On a clip with cards the name shows from the end of the cover until half a second before the first card, if that leaves at least 3 seconds; otherwise it is skipped (the render report says which). The speaker's name never shows at the same time as a card.
