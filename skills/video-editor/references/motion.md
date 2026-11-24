# Motion graphics (optional layer)

Keyword cards normally come from ffmpeg subtitle drawing: reliable and quick, but limited to simple shapes and fades. With the optional layer, `render_shorts.py` renders the cards with HyperFrames and lays the result over the clip.

## What it is
- **HyperFrames** (HeyGen, Apache 2.0, free): an HTML page with seekable animations rendered to video. `render_motion.py` writes that page from the clip's cards and `brand.json` (colours, fonts), renders a transparent WebM, and `render_shorts.py` composites it with ffmpeg. Captions, lower third and end card are unchanged.
- **Pinned and local.** `render_motion.py --setup` installs HyperFrames 0.9.88 and GSAP 3.12.5 into `<KRITHI_HOME or ~/.krithi>/video/motion` and the headless Chrome into `~/.cache/hyperframes` (about 300 MB in total, once per machine). Usage telemetry is switched off on every call, and the page loads nothing from the network.
- **Fallback.** Without Node.js 22+ or the install, or if the render fails, the clip is drawn with the built-in cards and the report's `warnings` say so. `--motion on` turns that fallback into an error.

## When to use it
Ask the user once, when the clips have cards: "I can draw the cards with HyperFrames for richer motion; it needs a one-time download of about 300 MB and takes longer to render. Use it?" Do not install it without a yes.

## Cost
A card overlay renders only from the first card to the last, at low priority. Measure with the first clip's `seconds_taken` and tell the user the rest will take about the same each. On the slowest machines run clips one at a time.

## Changing the look
The card design lives in `build_page()` in `render_motion.py`: layout and sizes scale from a 1080 px wide design, colours and fonts come from `brand.json`. Test a design on its own with `render_motion.py --clips clips.resolved.json --id 1 --out overlay.webm --preview`, then render a clip and look at frames from the finished video.
