# Explainer style (split-screen)

A second look for short clips, modelled on the team's "tips" video: a dark graphic panel fills the top of the 9:16 frame, the speaker fills the lower part in a close, steady crop, and captions are monospace and upper case at the seam between them. It suits tips, steps and lists, where graphics can show what the speaker is saying. The default `reel` style stays the default.

## Choosing it
Only when the user asks in words ("split-screen", "explainer", "graphics above the speaker", "like the Codex tips video"). If the request could mean either style, ask one short question. For list or step-by-step content you may offer it at the approval step, but never switch on your own. The same transcript serves both styles, so a user can ask for the other style later without transcribing again.

## What it draws
- **Layout:** the picture starts 40% of the way down. The speaker is cropped to the picture's shape and zoomed a little (`speaker_zoom`), with the face about 40% down it. A soft gradient (the seam) joins the panel to the picture.
- **Panel:** a dark gradient with the brand wordmark and an optional `panel_title` label at the top left. Animated scenes inside the panel come later; until then the panel is the brand backdrop.
- **Captions:** monospace (JetBrains Mono), upper case, up to four words at a time, centred at the seam. Words listed in the clip's `highlights` are drawn in the accent colour. A caption that is too wide is drawn smaller.
- **Name tag:** bottom left with an accent bar, for the first few seconds.
- **Not drawn:** keyword cards (the panel replaces them) and the blurred cover title. The end card is unchanged.

## What to write in clips.json
Everything in `formats.md`, plus `highlights` (the product names and key terms the viewer should catch, a handful per clip) and `panel_title` (two to four words). Check clips with `validate_clips.py --style explainer`: the length range is 30 to 150 seconds, with 20 to 180 allowed (`shorts.explainer.length` in `brand.json`).

## Where the numbers live
`brand.json` under `shorts.explainer`: panel share, seam height, speaker zoom, caption size and spacing, panel colours and the length range. The captions' font is `fonts.mono`. Change them there, not in code.
