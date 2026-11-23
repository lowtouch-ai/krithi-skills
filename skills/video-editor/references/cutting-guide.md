# Cutting guide

How to turn `analysis.json` and `transcript.md` into a cut list. The scripts find candidates; you decide. Guru's rule of thumb: **cut everything where nothing is happening, including short pauses.** This file is a first draft; refine it from real feedback.

## What to cut

1. **Pre-roll and tail.** Setup chatter before the session ("can you hear me", "are we recording", "should we start", a countdown) and the goodbye after the last real point ("so we can stop recording now"). Find the first sentence that belongs in the video and the last; cut everything outside, keeping about 0.3 s before the first word and 0.5 s after the last. (These edge paddings are for the start and end of the whole video; the 0.15 s in a candidate's `cut` is the room kept inside a gap. They are different things.)
2. **Dead air.** The rule is: **cut every pause, dead_stretch, lead_in and tail_out candidate**, however short (they are all at least 0.7 s of nothing). Take the candidate's `cut` span as given; it already keeps about 0.15 s of room on each side so speech is not clipped. Skip a candidate only when it is `keep_suggested` (see below) or it is one of the exceptions in "What to keep".
3. **False starts and retakes.** An abandoned sentence plus its restart ("so what I wanted to... let me rephrase"). Keep the clean take, usually the last, and cut the restart cue with the botched one. Never keep a take that trails off.
4. **Spoken notes to the editor or each other** ("cut that", "let's do that again", "can you see my screen?").
5. **Long filler runs.** A string of "um, so, yeah, okay" that is dead air in speech form. Isolated fillers stay: cutting them makes a visible jump.

## What to keep

- A pause that lands a point (before a punchline, after a hard question).
- Emphatic repetition ("never, never") and rhetorical doubling ("the first piece is, is this"): these look like stutters to a detector and are not.
- Asides, jokes, laughs, a deliberate beat.
- Any gap marked `keep_suggested`. It has one of two reasons (see the `note`). **Picture changed:** a silent demo, slide or layout switch may be on screen. **Speech suspected (`speech_suspected`, with a `gap_median_db`):** the audio in the gap is not silent, so Whisper may have missed speech, or another person is talking. Do not cut these unless you have read the words just before and after and can say what is in the gap. If a sentence ends unfinished right before a gap, or a gap that long sits mid-answer, assume speech was missed. This rule beats the dead-air rule. Look at what was said before and after. Keep it unless you can tell it is nothing (for example, a producer switching layouts during dead air); if you cut one, say so in the summary.
- The recorded order. Do not rearrange unless the user asks.

## When unsure
Keep it and flag it in the summary ("kept the 4 s pause at 06:10, it follows the pricing question; cut it?"). Do not make the user hunt for a bad cut.

## Notes from the user
"Focus on the pricing discussion": keep that section whole and cut the rest harder, or ask whether to remove other sections entirely. "Skip the first 10 minutes": cut them as one `skipped` cut. If a note conflicts with these rules, follow the note and say so.

## Mechanics
- Every cut needs `start`, `end`, a `kind` (`pre_roll`, `tail`, `pause`, `dead_stretch`, `false_start`, `retake`, `note`, `filler`, `skipped`) and a `reason` a person can read.
- `keep` is the source of truth; `cuts` explain it. Gaps between kept ranges must each be explained by a cut.
- A kept range must not start or end inside a word. If the validator reports one, move the edge to the word boundary it names.
- Do not cut a one-second hole in the middle of a sentence to remove a breath; cut whole pauses between sentences or thoughts.
- Chapters: place one at each real topic shift, using the time of the first word of that topic. The first is at 0, and there are at least three, each at least 10 s long. If the video is too short, leave chapters out and say why.

## Reviewing
Quote the words before and after each non-trivial cut in the summary so the user can judge it without scrubbing the video. Group tiny pause cuts into one line ("41 pauses under 3 s, 62 s total") and list long ones individually.
