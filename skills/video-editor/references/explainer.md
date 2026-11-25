# Explainer style (split-screen)

A second look for short clips, modelled on the team's "tips" video: a dark graphic panel fills the top of the 9:16 frame, the speaker fills the lower part in a close, steady crop, and captions are monospace and upper case at the seam between them. It suits tips, steps and lists, where graphics can show what the speaker is saying. The default `reel` style stays the default.

## Choosing it
Only when the user asks in words ("split-screen", "explainer", "graphics above the speaker", "like the Codex tips video"). If the request could mean either style, ask one short question. For list or step-by-step content you may offer it at the approval step, but never switch on your own. The same transcript serves both styles, so a user can ask for the other style later without transcribing again.

## What it draws
- **Layout:** the picture starts 40% of the way down. The speaker is cropped to the picture's shape and zoomed a little (`speaker_zoom`), with the face about 40% down it. A soft gradient (the seam) joins the panel to the picture.
- **Panel:** a dark gradient with an optional `panel_title` label at the top left. It holds animated **scenes** (below); with no scenes it shows the brand wordmark.
- **Captions:** monospace (JetBrains Mono), upper case, up to four words at a time, centred at the seam. Words listed in the clip's `highlights` are drawn in the accent colour. A caption that is too wide is drawn smaller.
- **Name tag:** bottom left with an accent bar, for the first few seconds.
- **Not drawn:** keyword cards (the panel replaces them) and the blurred cover title. The end card is unchanged.

## Panel scenes (templates)
A clip's `scenes` list puts animated graphics in the panel, each starting when its `say` words are spoken and staying until the next scene starts. Pick the scene type that shows what the speaker is saying; fill in short text, and give parts their own `say` so they appear as the speaker reaches them (parts without one are spread evenly). Aim for about one scene every 10 seconds, at least 3 seconds each. Optional `tag` (up to 14 characters, such as "STEP 1") is drawn as a small outlined label above the scene.

| type | data | use it for |
|---|---|---|
| `terminal` | `title`, `lines`: up to 7 of `{kind: cmd \| out \| ok \| dim, text, say}`; a `cmd` line is typed | a command and its result |
| `tree` | `title`, `rows`: up to 8 of `{text, depth 0 to 3, kind: dir \| file, hl, say}`; `hl` marks the row | a folder or outline |
| `flow` | `label`, `nodes`: up to 4 of `{title, sub, say}` joined by arrows, or `rows` (up to 2) of `{label, nodes}` | a process, a chain of steps |
| `title` | `label`, `icon` (up to 4 characters), `name`, `items`: up to 3 of `{n, text, say}` | an opening or a list of points |

Text limits: node and item titles 34 characters, subtitles 24, lines and rows 38. Invented example:
```json
{"type": "flow", "say": "every pull request", "tag": "STEP 1",
 "data": {"label": "From idea to release", "nodes": [
   {"title": "Plan", "sub": "write it down", "say": "plan"},
   {"title": "Build", "sub": "small changes", "say": "build"},
   {"title": "Review", "sub": "a second pair of eyes", "say": "review"}]}}
```
Scenes are drawn with HyperFrames, so the explainer needs it installed (`render_motion.py --setup`). Without it the render says so and shows the backdrop. A scene that no template fits is not supported yet; choose the closest template or leave the panel to the backdrop.

## What to write in clips.json
Everything in `formats.md`, plus `scenes`, `highlights` (the product names and key terms the viewer should catch, a handful per clip) and `panel_title` (two to four words). Check clips with `validate_clips.py --style explainer`: the length range is 30 to 150 seconds, with 20 to 180 allowed (`shorts.explainer.length` in `brand.json`).

## Where the numbers live
`brand.json` under `shorts.explainer`: panel share, seam height, speaker zoom, caption size and spacing, panel colours and the length range. The captions' font is `fonts.mono`. Change them there, not in code.
