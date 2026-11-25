"""The "explainer" style for short clips: a dark graphic panel on top, the speaker below, monospace captions at the seam.

Modelled on the team's split-screen reference (a tips video): the top part of the 9:16 frame is a panel (here a dark gradient
that later holds animated scenes), the speaker fills the lower part in a close, steady crop, a soft gradient joins them, and
captions are monospace, upper case, a few words at a time, with key terms in the accent colour. A name tag sits at the bottom left.

render_shorts.py uses this module when run with --style explainer. The proportions are in brand.json (shorts.explainer);
the defaults below are measured from the reference at 1080x1920 and scale with the output size.
"""

DEFAULTS = {
    "panel_share": 0.40,       # the speaker's picture starts this far down the frame
    "seam": 0.075,             # height of the soft gradient where panel and picture meet (share of the frame)
    "speaker_zoom": 1.25,      # how much tighter than full height the speaker is cropped
    "face_at": 0.40,           # where the face sits in the speaker's picture (share from the top)
    "caption_em": 0.0225,      # caption type size (em, share of the frame height)
    "caption_words": 4,        # most words in one caption
    "caption_y": 0.416,        # caption centre (share of the frame height): at the seam
    "caption_spacing": 0.05,   # letter spacing, em
    "caption_dim": "#9AA0C8",  # colour of caption words that are not highlighted when a keyword list is given
    "panel_top": "#05071E",    # panel gradient colours
    "panel_bottom": "#0A0E33",
    "panel_glow": "#3A1B5C",
    "name_tag_seconds": 5.0,
    "length": {"soft_min": 30, "soft_max": 150, "hard_min": 20, "hard_max": 180},
}


def settings(brand):
    return {**DEFAULTS, **(brand.get("shorts", {}).get("explainer") or {})}


def geometry(W, H, cfg):
    """(video_y, video_h): where the speaker's picture starts and how tall it is, even numbers."""
    y = int(round(H * cfg["panel_share"] / 2.0)) * 2
    return y, H - y


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def make_panel(brand, res, W, H, cfg, work, run_ffmpeg):
    """The panel background as one PNG: a dark gradient with a soft purple glow and the brand wordmark. Returns (path, error)."""
    (r0, g0, b0), (r1, g1, b1), (rg, gg, bg) = _rgb(cfg["panel_top"]), _rgb(cfg["panel_bottom"]), _rgb(cfg["panel_glow"])
    py = int(H * cfg["panel_share"])
    lerp = lambda a, b: f"{a}+({b}-{a})*Y/{py}"
    glow = f"exp(-(pow(X-0.80*W,2)+pow(Y-0.10*H,2))/pow(0.55*W,2))"
    glow2 = f"0.5*exp(-(pow(X-0.05*W,2)+pow(Y-0.45*H,2))/pow(0.45*W,2))"
    comp = lambda a, b, g: f"({lerp(a, b)})+({g}-({lerp(a, b)}))*0.55*({glow}+{glow2})"
    out = work / "panel.png"
    logo = res(brand["logo"]["wordmark"])
    lw = int(W * 0.30)
    import subprocess
    px = subprocess.run(["ffmpeg", "-v", "error", "-i", str(logo), "-vf", "crop=1:1:5:5,format=rgb24", "-f", "rawvideo", "-"],
                        capture_output=True).stdout[:3]
    key = "0x%02X%02X%02X" % tuple(px) if len(px) == 3 else "0x041250"
    code, err = run_ffmpeg(["-f", "lavfi", "-i",
                            f"color=c=black:s={W}x{H}:r=1:d=1,format=gbrp,geq=r='{comp(r0, r1, rg)}':g='{comp(g0, g1, gg)}':b='{comp(b0, b1, bg)}'",
                            "-i", str(logo), "-filter_complex",
                            f"[1:v]colorkey={key}:0.14:0.10,scale={lw}:-1,format=rgba,colorchannelmixer=aa=0.55[l];"
                            f"[0:v][l]overlay=(W-w)/2:{py}*0.5-h/2:format=auto,format=yuv420p",
                            "-frames:v", "1", str(out)])
    return (out, None) if code == 0 else (None, err[-400:])


def make_seam(brand, W, H, cfg, work, run_ffmpeg):
    """A strip of the panel colour fading to clear, laid over the top of the speaker's picture. Returns (path, error)."""
    r, g, b = _rgb(cfg["panel_bottom"])
    h = max(8, int(round(H * cfg["seam"] / 2.0)) * 2)
    out = work / "seam.png"
    code, err = run_ffmpeg(["-f", "lavfi", "-i", f"color=c=black:s={W}x{h}:r=1:d=1,format=gbrap,geq=r={r}:g={g}:b={b}:a='255*pow(1-Y/{h},1.6)'",
                            "-frames:v", "1", str(out)])
    return (out, None) if code == 0 else (None, err[-400:])


def style_lines(font_info_mono, font_info_reg, font_info_semi, H, white, accent, muted, cfg, mono_fs):
    """ASS style lines for the explainer's captions, name tag and panel title. `mono_fs` is the ASS size of the caption."""
    fam, b = font_info_mono
    rfam, rb = font_info_reg
    sfam, sb = font_info_semi
    sp = cfg["caption_spacing"] * mono_fs
    return [
        f"Style: ExpCap,{fam},{mono_fs},{white},&H00FFFFFF&,&H00000000&,&H00000000&,{-1 if b else 0},0,0,0,100,100,{sp:.1f},0,1,0,0,5,0,0,0,1",
        f"Style: ExpName,{sfam},{int(H * 0.0285)},&H00FFFFFF&,&H00FFFFFF&,&H00000000&,&H00000000&,{-1 if sb else 0},0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        f"Style: ExpRole,{rfam},{int(H * 0.0215)},{muted},&H00FFFFFF&,&H00000000&,&H00000000&,{-1 if rb else 0},0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        f"Style: ExpPanel,{rfam if rfam else fam},{int(H * 0.017 / 1.0)},{muted},&H00FFFFFF&,&H00000000&,&H00000000&,0,0,0,0,100,100,{0.12 * H * 0.017:.1f},0,1,0,0,7,0,0,0,1",
    ]


def caption_events(ev, F, W, H, groups, cfg, white, accent, dim, safe, keywords=None, ass_size=None):  # `dim` is kept for a later look where spoken words fade
    """Monospace captions: a few words at a time, upper case, centred at the seam. Key terms (`keywords`, lower-case words
    or short phrases the agent chose) are drawn in the accent colour; when a list is given the rest is white. Each caption
    fades in and out and stays until the next one starts (or a short hold)."""
    import re
    keys = {k.strip().lower() for k in (keywords or []) if k.strip()}
    singles = {w for k in keys for w in k.split()}
    base = ass_size
    cy = int(H * cfg["caption_y"])
    max_w = W * 0.92
    for gi, grp in enumerate(groups):
        text_words = [re.sub(r"[^\w'/.\-]", "", x["word"]).upper() or x["word"].upper() for x in grp]
        size = base
        total = F.width(" ".join(text_words), size) + cfg["caption_spacing"] * F.em(size) * len(" ".join(text_words))
        if total > max_w:
            size = max(int(base * max_w / total), int(base * 0.6))
        start = grp[0]["start"]
        nxt = groups[gi + 1][0]["start"] if gi + 1 < len(groups) else None
        end = grp[-1]["end"] + 0.25
        if nxt is not None:
            end = min(end, nxt)
        if end <= start:
            continue
        parts = []
        for x, shown in zip(grp, text_words):
            core = re.sub(r"[^\w'/.\-]", "", x["word"]).lower().strip(".")
            hit = core in singles or core.lstrip("/") in singles
            colour = accent if hit else white
            parts.append("{\\1c%s}%s" % (colour, safe(shown)))
        fade = "\\fad(110,110)"
        ev(3, start, end, "ExpCap", "{\\an5\\fs%d\\pos(%d,%d)%s}%s" % (size, W // 2, cy, fade, " ".join(parts)))


def name_tag_events(ev, W, H, speaker, cfg, navy, accent, safe, a, b):
    """Name tag at the bottom left with an accent bar, as in the reference."""
    if not speaker:
        return
    bw, bh = int(W * 0.40), int(H * 0.066)
    bx, by = int(W * 0.037), int(H * 0.955) - bh
    fad = "\\fad(300,300)"
    ev(4, a, b, "Shape", f"{{\\pos({bx},{by})\\p1\\1c{navy}\\1a&H26&\\bord0{fad}}}m 0 0 l {bw} 0 {bw} {bh} 0 {bh}{{\\p0}}")
    ev(5, a, b, "Shape", f"{{\\pos({bx},{by})\\p1\\1c{accent}\\bord0{fad}}}m 0 0 l {max(5, int(W * 0.007))} 0 {max(5, int(W * 0.007))} {bh} 0 {bh}{{\\p0}}")
    ev(5, a, b, "ExpName", f"{{\\pos({bx + int(W * 0.022)},{by + int(bh * 0.14)}){fad}}}{safe(speaker[0])}")
    if len(speaker) > 1 and speaker[1]:
        ev(5, a, b, "ExpRole", f"{{\\pos({bx + int(W * 0.022)},{by + int(bh * 0.14 + H * 0.0285 * 1.15)}){fad}}}{safe(speaker[1])}")


def panel_title_events(ev, W, H, text, cfg, safe, a, b):
    """A small mono label at the top left of the panel (for example "CODEX · 3 TIPS")."""
    if text:
        ev(2, a, b, "ExpPanel", f"{{\\pos({int(W * 0.03)},{int(H * 0.03)})\\fad(300,300)}}{safe(text.upper())}")
