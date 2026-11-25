#!/usr/bin/env python3
"""Optional motion-graphics layer: render a clip's keyword cards with HyperFrames as a transparent overlay.

Usage:
  render_motion.py --status                      report whether the layer is ready (JSON)
  render_motion.py --setup                       install HyperFrames and its headless Chrome (needs the user's OK)
  render_motion.py --clips clips.resolved.json --id 1 --out overlay.webm [--brand brand.json] [--preview]
                                                 render one clip's cards on their own (for testing the look)

render_shorts.py calls this itself when --motion is auto (ready) or on. Nothing here is required: without
Node 22+ and the installed layer, render_shorts.py draws the same cards with ffmpeg subtitles instead.

HyperFrames (HeyGen, Apache 2.0) turns an HTML page with seekable animations into video. This script writes
that page from the clip's cards and brand.json (colours and fonts), renders a transparent WebM, and
render_shorts.py lays it over the clip with ffmpeg. Everything is pinned and local: the packages are
installed once into <KRITHI_HOME or ~/.krithi>/video/motion, usage telemetry is switched off, and the
animation library is copied from that install, so a render needs no network.
Prints JSON; exit 0 on success.
"""
import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vlib import clip_keep, kept_before, load_json  # noqa: E402
import cardlayout  # noqa: E402
from fontmetrics import Font  # noqa: E402

HF_VERSION = "0.9.88"
GSAP_VERSION = "3.12.5"
SKILL_DIR = Path(__file__).resolve().parent.parent
OVERLAY_FPS = 30
PRE = 0.1  # animations start this long before the word, so the card is in place on it


def motion_home():
    return Path(os.environ.get("KRITHI_HOME") or Path.home() / ".krithi") / "video" / "motion"


def hf_bin(home=None):
    home = home or motion_home()
    return home / "node_modules" / ".bin" / ("hyperframes.cmd" if os.name == "nt" else "hyperframes")


def gsap_file(home=None):
    return (home or motion_home()) / "node_modules" / "gsap" / "dist" / "gsap.min.js"


def quiet_env():
    env = dict(os.environ)
    env.update({"HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1", "NO_COLOR": "1", "CI": "1"})
    return env


def node_major():
    node = shutil.which("node")
    if not node:
        return None
    try:
        out = subprocess.run([node, "-v"], capture_output=True, text=True, timeout=15).stdout.strip()
        return int(out.lstrip("v").split(".")[0])
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def chrome_installed():
    base = Path.home() / ".cache" / "hyperframes" / "chrome"
    return base.is_dir() and any(base.rglob("chrome-headless-shell*"))


def status():
    """{'ready': bool, 'detail': str, 'fix': str}: whether the motion layer can render right now."""
    major = node_major()
    if major is None:
        return {"ready": False, "detail": "Node.js not found", "fix": "install Node.js 22 or newer, then run render_motion.py --setup"}
    if major < 22:
        return {"ready": False, "detail": f"Node.js {major} is too old", "fix": "install Node.js 22 or newer, then run render_motion.py --setup"}
    if not hf_bin().exists() or not gsap_file().exists():
        return {"ready": False, "detail": "HyperFrames is not installed", "fix": "python3 <skill-dir>/scripts/render_motion.py --setup"}
    if not chrome_installed():
        return {"ready": False, "detail": "the headless Chrome HyperFrames needs is not installed", "fix": "python3 <skill-dir>/scripts/render_motion.py --setup"}
    return {"ready": True, "detail": f"HyperFrames {HF_VERSION}", "fix": ""}


def setup():
    major = node_major()
    if major is None or major < 22:
        return {"ok": False, "error": "Node.js 22 or newer is required", "fix": "install Node.js 22+ from nodejs.org"}
    home = motion_home()
    home.mkdir(parents=True, exist_ok=True)
    (home / "package.json").write_text(json.dumps(
        {"name": "krithi-video-motion", "private": True,
         "dependencies": {"hyperframes": HF_VERSION, "gsap": GSAP_VERSION}}, indent=2), encoding="utf-8")
    npm = shutil.which("npm")
    if not npm:
        return {"ok": False, "error": "npm not found", "fix": "install Node.js 22+ (it includes npm)"}
    r = subprocess.run([npm, "install", "--no-audit", "--no-fund", "--loglevel=error"], cwd=home, env=quiet_env(),
                       capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        return {"ok": False, "error": "npm install failed", "detail": (r.stderr or r.stdout)[-600:]}
    r = subprocess.run([str(hf_bin(home)), "browser", "ensure"], cwd=home, env=quiet_env(), capture_output=True, text=True, timeout=1200)
    if r.returncode != 0:
        return {"ok": False, "error": "could not install the headless Chrome", "detail": (r.stderr or r.stdout)[-600:]}
    return {"ok": True, "home": str(home), **status()}


# ---------------------------------------------------------------- the page

def build_page(cards, layouts, colors, fonts, W, H, duration):
    """The HTML for a transparent overlay: one panel per card, laid out by cardlayout.py (the same geometry the built-in
    cards use), every term on the card from the start in a muted colour that lights up as it is spoken.

    cards: [{label, chain, start, end, items:[{text, at}]}] in overlay seconds. layouts: cardlayout.layout() of each card.
    colors: {magenta, green, navy, surface, white}. fonts: [(family, weight, file name under assets/fonts)]."""
    e = html.escape
    px = lambda v: f"{v:.1f}px"
    css, body, js = [], [], []
    for n, (c, L) in enumerate(zip(cards, layouts), 1):
        start, end = max(0.0, float(c["start"]) - PRE), float(c["end"])
        pills = []
        for k, it in enumerate(c["items"]):
            if c.get("chain") and k:
                pills.append(f'<span class="arrow" id="c{n}a{k}"></span>')
            pills.append(f'<span class="pill" id="c{n}p{k}">{e(it["text"])}</span>')
        body.append(
            f'<div id="c{n}" class="clip wrap" data-start="{start:.3f}" data-duration="{end - start:.3f}" data-track-index="0">'
            f'<div class="card" id="c{n}c"><div class="line"></div><div class="label" id="c{n}l">{e(c["label"])}</div>'
            f'<div class="pills">{"".join(pills)}</div></div></div>')
        css.append(
            f'#c{n} {{ bottom: {px(H - L["bottom"])}; }}'
            f' #c{n}c {{ width: {px(L["panel_w"])}; padding: {px(L["pad_y"])} {px(L["pad_x"])} {px(L["pad_y"] * 0.9)}; border-radius: {px(min(L["ph"] * 0.5, L["panel_w"] * 0.07))}; }}'
            f' #c{n}c .label {{ font-size: {px(L["label_em"])}; height: {px(L["label_band"])}; line-height: {px(L["label_band"] * 0.84)}; }}'
            f' #c{n}c .pills {{ gap: {px(L["gap"])}; }}'
            f' #c{n}c .pill {{ font-size: {px(L["pill_em"])}; height: {px(L["ph"])}; line-height: {px(L["ph"])}; padding: 0 {px(L["pad_pill"])}; }}'
            f' #c{n}c .arrow {{ border-left-width: {px(L["arrow_h"] * 0.5)}; border-right-width: {px(L["arrow_h"] * 0.5)}; border-top-width: {px(L["arrow_h"] * 0.6)}; margin: {px(-L["gap"] * 0.3)} 0; }}')
        s = W / 1080.0
        js.append(f'tl.fromTo("#c{n}c", {{y: {40 * s:.0f}, opacity: 0, scale: 0.95}}, {{y: 0, opacity: 1, scale: 1, duration: 0.28, ease: "back.out(1.5)"}}, {start:.3f});')
        js.append(f'tl.fromTo("#c{n}l", {{x: {-24 * s:.0f}, opacity: 0}}, {{x: 0, opacity: 1, duration: 0.3, ease: "power3.out"}}, {start + 0.12:.3f});')
        for k, it in enumerate(c["items"]):
            t_i = max(float(it["at"]) - PRE, start)
            nxt = float(c["items"][k + 1]["at"]) if k + 1 < len(c["items"]) else t_i + 1.1
            t_act = min(max(nxt - PRE, t_i + 0.5), end)
            # every term is on the card from the start in a muted colour; it lights up magenta as it is spoken, then turns white
            js.append(f'tl.to("#c{n}p{k}", {{backgroundColor: "{colors["magenta"]}", color: "{colors["white"]}", opacity: 1, duration: 0.18}}, {t_i:.3f});')
            js.append(f'tl.fromTo("#c{n}p{k}", {{scale: 1}}, {{scale: 1.05, duration: 0.12, yoyo: true, repeat: 1, ease: "power1.out", immediateRender: false}}, {t_i:.3f});')
            if t_act < end - 0.01:
                js.append(f'tl.to("#c{n}p{k}", {{backgroundColor: "{colors["white"]}", color: "{colors["navy"]}", duration: 0.25}}, {t_act:.3f});')
        js.append(f'tl.fromTo("#c{n}c", {{y: 0, opacity: 1}}, {{y: {50 * s:.0f}, opacity: 0, duration: 0.3, ease: "power2.in", immediateRender: false}}, {max(start, end - 0.3):.3f});')
    faces = "\n".join(
        f'@font-face {{ font-family: "{fam}"; font-weight: {wt}; src: url("assets/fonts/{fn}"); }}' for fam, wt, fn in fonts)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={W}, height={H}" />
    <script src="assets/gsap.min.js"></script>
    <style>
      {faces}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: {W}px; height: {H}px; overflow: hidden; background: transparent; }}
      #root {{ position: relative; width: {W}px; height: {H}px; font-family: "Brand", sans-serif; }}
      .wrap {{ position: absolute; left: 0; right: 0; display: flex; justify-content: center; }}
      .card {{ position: relative; background: {colors["surface"]}f2; box-shadow: 0 {px(W * 0.012)} {px(W * 0.03)} rgba(0,0,0,.4); text-align: center; }}
      .line {{ position: absolute; left: 5.5%; right: 5.5%; top: 0; height: {px(max(3, W * 0.0037))}; background: {colors["magenta"]}; border-radius: 0 0 4px 4px; }}
      .label {{ color: {colors["green"]}; font-weight: 600; letter-spacing: {cardlayout.LABEL_SPACING}em; text-transform: uppercase; white-space: nowrap; }}
      .pills {{ display: flex; flex-direction: column; align-items: center; }}
      .pill {{ background: rgba(255,255,255,.16); color: rgba(255,255,255,.55); font-weight: 600; border-radius: 999px; white-space: nowrap; }}
      .arrow {{ width: 0; height: 0; border-left-style: solid; border-right-style: solid; border-top-style: solid;
                border-left-color: transparent; border-right-color: transparent; border-top-color: rgba(255,255,255,.35); }}
      {chr(10).join("      " + x for x in css).strip()}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{duration:.3f}" data-width="{W}" data-height="{H}">
      {"".join(body)}
    </div>
    <script>
      const tl = gsap.timeline({{ paused: true }});
      {chr(10).join("      " + j_ for j_ in js).strip()}
      window.__timelines["main"] = tl;
      tl.seek(0);
    </script>
  </body>
</html>
"""


def write_project(proj, cards, brand, res, W, H, duration):
    """Write index.html and its assets (fonts from brand.json, the animation library) into `proj`."""
    (proj / "assets" / "fonts").mkdir(parents=True, exist_ok=True)
    fonts = []
    for wt, key in ((600, "semibold"), (700, "bold")):
        src = res(brand["fonts"].get(key) or brand["fonts"]["regular"])
        shutil.copy(src, proj / "assets" / "fonts" / src.name)
        fonts.append(("Brand", wt, src.name))
    shutil.copy(gsap_file(), proj / "assets" / "gsap.min.js")
    col = lambda k: brand["colors"][k]
    colors = {"magenta": col("primary"), "green": col("secondary"), "navy": col("background"),
              "surface": col("surface"), "white": col("text")}
    F, ccfg = Font(res(brand["fonts"].get("semibold") or brand["fonts"]["regular"])), cardlayout.settings(brand)
    layouts = [cardlayout.layout(c, W, H, F, ccfg) for c in cards]
    (proj / "index.html").write_text(build_page(cards, layouts, colors, fonts, W, H, duration), encoding="utf-8")
    (proj / "hyperframes.json").write_text(json.dumps({"name": "cards"}), encoding="utf-8")
    (proj / "meta.json").write_text(json.dumps({"id": "cards", "name": "cards"}), encoding="utf-8")


def hf_render(proj, out, nice=True):
    """Render the HyperFrames project in `proj` to a transparent WebM at `out`. Returns an error message, or None when it worked."""
    cmd = [str(hf_bin()), "render", "--format", "webm", "--fps", str(OVERLAY_FPS), "--output", str(out)]
    if nice and os.name != "nt" and shutil.which("nice"):
        cmd = ["nice", "-n", "15", *cmd]
    r = subprocess.run(cmd, cwd=proj, env=quiet_env(), capture_output=True, text=True, timeout=3600)
    if r.returncode != 0 or not Path(out).exists() or Path(out).stat().st_size == 0:
        text = re.sub(r"\s+", " ", (r.stderr or r.stdout))
        why = "exit code %d" % r.returncode if r.returncode else "no output file was written"
        return f"HyperFrames render failed ({why}): " + (text[:300] + " ... " if len(text) > 700 else "") + text[-300:]
    return None


def render_scenes_overlay(scenes, brand, res, W, panel_h, work, ecfg, nice=True):
    """Render the explainer's panel scenes (clip seconds; see scenes.py) to a transparent WebM the size of the panel.

    Returns (path, offset_seconds, error); the caller delays the overlay by `offset`."""
    import scenes as scn
    st = status()
    if not st["ready"]:
        return None, 0.0, f"{st['detail']} ({st['fix']})"
    t0 = max(0.0, min(sc["start"] for sc in scenes) - PRE - 0.1)
    t1 = max(sc["end"] for sc in scenes) + 0.1
    shifted = [{**sc, "start": sc["start"] - t0, "end": sc["end"] - t0,
                "els": [None if t is None else t - t0 for t in sc.get("els", [])]} for sc in scenes]
    work = Path(work).resolve()
    proj = work / "scenes"
    if proj.exists():
        shutil.rmtree(proj)
    (proj / "assets" / "fonts").mkdir(parents=True)
    fonts = []
    for fam, wt, key in (("Brand", 600, "semibold"), ("Mono", 500, "mono_medium"), ("Mono", 700, "mono")):
        src = res(brand["fonts"].get(key) or brand["fonts"].get("bold") or brand["fonts"]["regular"])
        shutil.copy(src, proj / "assets" / "fonts" / src.name)
        fonts.append((fam, wt, src.name))
    shutil.copy(gsap_file(), proj / "assets" / "gsap.min.js")
    col = lambda k: brand["colors"][k]
    colors = {"accent": col("secondary"), "accent2": col("primary"), "text": col("text"), "dim": ecfg["scene_dim"],
              "card": ecfg["scene_card"], "border": ecfg["scene_border"]}
    (proj / "index.html").write_text(scn.build_page(shifted, colors, fonts, W, panel_h, t1 - t0), encoding="utf-8")
    (proj / "hyperframes.json").write_text(json.dumps({"name": "scenes"}), encoding="utf-8")
    (proj / "meta.json").write_text(json.dumps({"id": "scenes", "name": "scenes"}), encoding="utf-8")
    out = work / "scenes.webm"
    err = hf_render(proj, out, nice)
    return (None, 0.0, err) if err else (out, t0, None)


def render_overlay(cards, brand, res, W, H, work, nice=True):
    """Render `cards` (clip seconds) to a transparent WebM. Returns (path, offset_seconds, error).

    Only the stretch from the first card to the last is rendered; the caller delays the overlay by `offset`."""
    st = status()
    if not st["ready"]:
        return None, 0.0, f"{st['detail']} ({st['fix']})"
    t0 = max(0.0, min(c["start"] for c in cards) - PRE - 0.1)
    t1 = max(c["end"] for c in cards) + 0.1
    shifted = [{**c, "start": c["start"] - t0, "end": c["end"] - t0,
                "items": [{**i, "at": i["at"] - t0} for i in c["items"]]} for c in cards]
    work = Path(work).resolve()  # the render runs inside the project folder, so every path must be absolute
    proj = work / "motion"
    if proj.exists():
        shutil.rmtree(proj)
    proj.mkdir(parents=True)
    write_project(proj, shifted, brand, res, W, H, t1 - t0)
    out = work / "cards.webm"
    err = hf_render(proj, out, nice)
    return (None, 0.0, err) if err else (out, t0, None)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--clips")
    ap.add_argument("--id", type=int)
    ap.add_argument("--analysis")
    ap.add_argument("--brand")
    ap.add_argument("--out")
    ap.add_argument("--preview", action="store_true")
    a = ap.parse_args()
    if a.status:
        print(json.dumps(status()))
        return 0 if status()["ready"] else 1
    if a.setup:
        r = setup()
        print(json.dumps(r, indent=2))
        return 0 if r["ok"] else 1
    if not (a.clips and a.id and a.out):
        print(json.dumps({"ok": False, "error": "give --status, --setup, or --clips, --id and --out"}))
        return 1
    from render_long import DEFAULT_BRAND, load_brand
    brand, res = load_brand(a.brand or DEFAULT_BRAND)
    clip = next((c for c in load_json(a.clips)["clips"] if c["id"] == a.id), None)
    if not clip or not clip.get("cards"):
        print(json.dumps({"ok": False, "error": "that clip has no cards"}))
        return 1
    analysis = load_json(a.analysis) if a.analysis else None
    keep = clip_keep(clip, analysis)
    cards = [{"label": k["label"], "chain": k.get("chain", False), "start": kept_before(keep, k["start"]), "end": kept_before(keep, k["end"]),
              "items": [{"text": i["text"], "at": kept_before(keep, i["at"])} for i in k["items"]]} for k in clip["cards"]]
    W, H = (540, 960) if a.preview else (1080, 1920)
    work = Path(a.out).resolve().parent / (Path(a.out).stem + "-work")
    t = time.time()
    path, offset, err = render_overlay(cards, brand, res, W, H, work)
    if err:
        print(json.dumps({"ok": False, "error": err}))
        return 1
    shutil.move(str(path), a.out)
    shutil.rmtree(work, ignore_errors=True)
    print(json.dumps({"ok": True, "overlay": a.out, "start_offset": round(offset, 3), "seconds_taken": round(time.time() - t, 1)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
