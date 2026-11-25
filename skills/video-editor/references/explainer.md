# Explainer style (split-screen)

A second look for short clips, modelled on the team's "tips" video: a dark graphic panel fills the top of the 9:16 frame, the speaker fills the lower part in a close, steady crop, and captions are monospace and upper case at the seam between them. It suits tips, steps and lists, where graphics can show what the speaker is saying. The default `reel` style stays the default.

## Choosing it
Only when the user asks in words ("split-screen", "explainer", "graphics above the speaker", "like the Codex tips video"). If the request could mean either style, ask one short question. For list or step-by-step content you may offer it at the approval step, but never switch on your own. The same transcript serves both styles, so a user can ask for the other style later without transcribing again.

## What it draws
- **Layout:** the picture starts 40% of the way down. The speaker is cropped to the picture's shape and zoomed a little (`speaker_zoom`), with the face about 40% down it. A soft gradient (the seam) joins the panel to the picture.
- **Panel:** a dark gradient with an optional `panel_title` label at the top left. It holds animated **scenes** (below); with no scenes it shows the brand wordmark.
- **Captions:** monospace (JetBrains Mono), upper case, up to four words at a time, centred at the seam. Words listed in the clip's `highlights` are drawn in the accent colour. A caption that is too wide is drawn smaller.
- **Name tag:** bottom left with an accent bar, for the first few seconds.
- **Call-to-action pill:** a magenta pill at the bottom left of the panel (`cta`).
- **Recap end card:** a dark card with the wordmark, a label, the points and a follow line (`recap`). Without a `recap` the normal end card is used.
- **Not drawn:** keyword cards (the panel replaces them) and the blurred cover title.

## Panel scenes (templates)
A clip's `scenes` list puts animated graphics in the panel, each starting when its `say` words are spoken and staying until the next scene starts. Pick the scene type that shows what the speaker is saying; fill in short text, and give parts their own `say` so they appear as the speaker reaches them (parts without one are spread evenly). Aim for about one scene every 10 seconds, at least 3 seconds each. Optional `tag` (up to 14 characters, such as "STEP 1") is drawn as a small outlined label above the scene.

| type | data | use it for |
|---|---|---|
| `terminal` | `title`, `lines`: up to 6 of `{kind: cmd \| out \| ok \| dim, text, say}`; a `cmd` line is typed | a command and its result |
| `tree` | `title`, `rows`: up to 6 of `{text, depth 0 to 3, kind: dir \| file, hl, say}`; `hl` marks the row | a folder or outline |
| `flow` | `label`, `nodes`: up to 4 of `{title, sub, say}` joined by arrows, or `rows` (up to 2) of `{label, nodes}` | a process, a chain of steps |
| `title` | `label`, `icon` (up to 4 characters), `name`, `items`: up to 3 of `{n, text, say}` | an opening or a list of points |
| `checklist` | `title`, `heading`, `toggles` (up to 3 chips; `active` is the lit one), `items`: up to 5 of `{text, say, state: done \| todo, flag}` (a `flag` of up to 2 characters marks the row), and an optional `bubble`: `{text, say}` | a plan or a review, with a question raised on one step |
| `bubble` | `bubbles`: up to 3 of `{from: user \| agent, text, say}` (text up to 60 characters) | a question and an answer, or a prompt |
| `steps` | `label`, `steps`: up to 4 of `{title, sub, say}` (sub up to 40 characters), numbered | a short numbered process |

Text limits: node and item titles 34 characters, subtitles 24, lines and rows 38. A scene must also fit the panel: the checker estimates its height and refuses one that is too tall (for example a checklist of 5 items with a question bubble and a tag); use fewer lines, or drop the tag. Invented example:
```json
{"type": "flow", "say": "every pull request", "tag": "STEP 1",
 "data": {"label": "From idea to release", "nodes": [
   {"title": "Plan", "sub": "write it down", "say": "plan"},
   {"title": "Build", "sub": "small changes", "say": "build"},
   {"title": "Review", "sub": "a second pair of eyes", "say": "review"}]}}
```
### When no template fits: the `custom` scene
Use it only when the six templates cannot show the point, and say so at the approval step so the user can ask for a template instead. A custom scene is a small piece of HTML and CSS plus timed reveals, with no script:
```json
{"type": "custom", "say": "words that start it", "tag": "THE SETUP",
 "data": {"html": "<div class=\"cmp\"><div id=\"a\" class=\"col\"><b>Before</b></div><div id=\"b\" class=\"col\"><b>After</b></div></div>",
          "css": ".cmp{display:flex;gap:24px} .col{flex:1;background:var(--card);border:2px solid var(--border);border-radius:18px;padding:30px;text-align:center}",
          "anim": [{"el": "a", "say": "before", "effect": "rise"}, {"el": "b", "say": "after", "effect": "pop"}]}}
```
- **Allowed markup:** div, span, b, i, em, strong, p, br, ul, li, and simple SVG shapes (svg, path, rect, circle, ellipse, line, polyline, polygon, g, text). Attributes: id, class, style and SVG drawing attributes. No scripts, links, images, event handlers or `url()`; nothing is fetched. At most 5000 characters of html and 3000 of css.
- **Look:** use the variables `--accent`, `--accent2`, `--text`, `--dim`, `--card`, `--border` and the fonts `Brand` (headings) and `Mono` (code and labels), so the scene matches the others. Content is about 940 px wide. Selectors are scoped to the scene automatically; style your own elements only.
- **Timing:** `anim` lists reveals: `el` is an id in your html, `say` the words where it appears, `effect` one of fade, rise, pop, slide, wipe (up to 12). Elements not listed are visible from the start.
- **Height:** `validate_clips.py` measures the scene in a browser (when HyperFrames is installed) and refuses one taller than the panel allows (about 490 px, tag included).

Scenes are drawn with HyperFrames, so the explainer needs it installed (`render_motion.py --setup`). Without it the render says so and shows the backdrop. 

## Shape of a tips-style explainer
The reference video follows this shape, and the template parts build it:
1. **Opening:** a `title` scene at the first words: a label ("TOPIC · 3 TIPS"), an icon and a name, and optionally the points as `items` that appear as they are announced.
2. **One scene per point,** each with a `tag` such as "TIP 01", "TIP 02", so the viewer sees where they are. Choose `terminal`, `tree` or `flow` to show the point.
3. **Call-to-action pills:** `"cta": [{"text": "DM lowtouch.ai", "say": "words where it appears", "seconds": 4}]`, text up to 24 characters, shown 2 to 8 seconds. One or two per clip.
4. **Recap end card:** `"recap": {"label": "3 tips", "items": [{"n": "01", "text": "Docs first"}, ...], "follow": "Follow lowtouch.ai for more AI agent tips"}`, one to four items (up to 34 characters each); it stays 5 seconds (`recap_seconds`).

## What to write in clips.json
Everything in `formats.md`, plus `scenes`, `cta`, `recap`, `highlights` (the product names and key terms the viewer should catch, a handful per clip) and `panel_title` (two to four words). Check clips with `validate_clips.py --style explainer`: the length range is 30 to 150 seconds, with 20 to 180 allowed (`shorts.explainer.length` in `brand.json`).

## Where the numbers live
`brand.json` under `shorts.explainer`: panel share, seam height, speaker zoom, caption size and spacing, panel colours and the length range. The captions' font is `fonts.mono`. Change them there, not in code.
