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
    "recap_seconds": 5.0,      # how long the recap end card stays
    "scene_card": "#0E1140",   # panel scenes: window and node colours
    "scene_border": "#262B6E",
    "scene_dim": "#8D93C6",
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


def make_panel(brand, res, W, H, cfg, work, run_ffmpeg, logo_on=True, full=False, name="panel"):
    """The panel background as one PNG: a dark gradient with a soft purple glow and, unless scenes fill the panel, the brand
    wordmark. Returns (path, error)."""
    (r0, g0, b0), (r1, g1, b1), (rg, gg, bg) = _rgb(cfg["panel_top"]), _rgb(cfg["panel_bottom"]), _rgb(cfg["panel_glow"])
    py = H if full else int(H * cfg["panel_share"])
    lerp = lambda a, b: f"{a}+({b}-{a})*Y/{py}"
    glow = f"exp(-(pow(X-0.80*W,2)+pow(Y-0.10*H,2))/pow(0.55*W,2))"
    glow2 = f"0.5*exp(-(pow(X-0.05*W,2)+pow(Y-0.45*H,2))/pow(0.45*W,2))"
    comp = lambda a, b, g: f"({lerp(a, b)})+({g}-({lerp(a, b)}))*0.55*({glow}+{glow2})"
    out = work / f"{name}.png"
    logo = res(brand["logo"]["wordmark"])
    lw = int(W * (0.40 if full else 0.30))
    import subprocess
    px = subprocess.run(["ffmpeg", "-v", "error", "-i", str(logo), "-vf", "crop=1:1:5:5,format=rgb24", "-f", "rawvideo", "-"],
                        capture_output=True).stdout[:3]
    key = "0x%02X%02X%02X" % tuple(px) if len(px) == 3 else "0x041250"
    bg_src = f"color=c=black:s={W}x{H}:r=1:d=1,format=gbrp,geq=r='{comp(r0, r1, rg)}':g='{comp(g0, g1, gg)}':b='{comp(b0, b1, bg)}'"
    if logo_on:
        code, err = run_ffmpeg(["-f", "lavfi", "-i", bg_src, "-i", str(logo), "-filter_complex",
                                f"[1:v]colorkey={key}:0.14:0.10,scale={lw}:-1,format=rgba,colorchannelmixer=aa=0.55[l];"
                                f"[0:v][l]overlay=(W-w)/2:{('H*0.30-h/2' if full else f'{py}*0.5-h/2')}:format=auto,format=yuv420p",
                                "-frames:v", "1", str(out)])
    else:
        code, err = run_ffmpeg(["-f", "lavfi", "-i", bg_src, "-vf", "format=yuv420p", "-frames:v", "1", str(out)])
    return (out, None) if code == 0 else (None, err[-400:])


def make_seam(brand, W, H, cfg, work, run_ffmpeg):
    """A strip of the panel colour fading to clear, laid over the top of the speaker's picture. Returns (path, error)."""
    r, g, b = _rgb(cfg["panel_bottom"])
    h = max(8, int(round(H * cfg["seam"] / 2.0)) * 2)
    out = work / "seam.png"
    code, err = run_ffmpeg(["-f", "lavfi", "-i", f"color=c=black:s={W}x{h}:r=1:d=1,format=gbrap,geq=r={r}:g={g}:b={b}:a='255*pow(1-Y/{h},1.6)'",
                            "-frames:v", "1", str(out)])
    return (out, None) if code == 0 else (None, err[-400:])


def style_lines(infos, fonts, H, white, accent, muted, cfg, mono_fs):
    """ASS style lines for the explainer's captions, name tag, panel title, call to action and recap.
    infos: {"mono", "reg", "semi"} -> (family, bold); fonts: the same keys -> fontmetrics.Font (to turn an em size into an ASS size)."""
    fam, b = infos["mono"]
    rfam, rb = infos["reg"]
    sfam, sb = infos["semi"]
    asz = lambda key, em: int(H * em / fonts[key].em(1))
    sp = cfg["caption_spacing"] * mono_fs
    st = lambda name, f, size, bold, col, al=5, spacing=0.0: (
        f"Style: {name},{f},{size},{col},&H00FFFFFF&,&H00000000&,&H00000000&,{-1 if bold else 0},0,0,0,100,100,{spacing:.1f},0,1,0,0,{al},0,0,0,1")
    return [
        st("ExpCap", fam, mono_fs, b, white, 5, sp),
        st("ExpName", sfam, int(H * 0.0285), sb, "&H00FFFFFF&", 7),
        st("ExpRole", rfam, int(H * 0.0215), rb, muted, 7),
        st("ExpPanel", rfam if rfam else fam, int(H * 0.017), False, muted, 7, 0.12 * H * 0.017),
        st("ExpCta", fam, asz("mono", 0.0165), b, white, 5, 0.04 * asz("mono", 0.0165)),
        st("ExpRecapLabel", fam, asz("mono", 0.0135), b, muted, 5, 0.18 * asz("mono", 0.0135)),
        st("ExpRecap", sfam, asz("semi", 0.0265), sb, white, 5),
        st("ExpFollow", rfam, asz("reg", 0.0225), rb, muted, 5),
    ]


def cta_events(ev, W, H, video_y, ctas, Fm, mag, white, safe, rrect, cap=None):
    """The call-to-action pill (for example "DM lowtouch.ai") at the bottom left of the panel. ctas: [{text, start, end}] in clip seconds."""
    em = H * 0.0165
    size = int(em / Fm.em(1))
    for c in ctas:
        txt = safe(c["text"])
        w = int(Fm.width(c["text"], size) + 0.9 * em * 2)
        h = int(em * 2.5)
        x, y = int(W * 0.065), video_y - int(H * 0.042) - h
        a, b = c["start"], c["end"] if cap is None else min(c["end"], cap)
        if b <= a:
            continue
        fad = "\\fad(250,250)"
        ev(6, a, b, "Shape", f"{{\\pos({x},{y})\\p1\\1c{mag}\\bord0{fad}}}{rrect(w, h, h * 0.5)}{{\\p0}}")
        ev(7, a, b, "ExpCta", f"{{\\an5\\pos({x + w // 2},{y + h // 2}){fad}}}{txt}")


def recap_rows(items, Fs, size, W):
    """Lay the recap items out in centred rows, as many as fit across 88% of the width. Returns a list of rows of items."""
    gap = Fs.width("   ", size)
    rows, cur, cw = [], [], 0.0
    for it in items:
        w = Fs.width(f"{it['n']} {it['text']}", size)
        if cur and cw + gap + w > W * 0.88:
            rows.append(cur)
            cur, cw = [], 0.0
        cur.append(it)
        cw += (gap if len(cur) > 1 else 0) + w
    if cur:
        rows.append(cur)
    return rows


def recap_events(ev, W, H, recap, e0, e1, white, accent, Fs, size, safe):
    """The recap end card: a label, the points (numbers in the accent colour) and a follow line."""
    fad = "\\fad(400,0)"
    if recap.get("label"):
        ev(2, e0, e1, "ExpRecapLabel", f"{{\\pos({W // 2},{int(H * 0.435)}){fad}}}{safe(recap['label'].upper())}")
    items = [{"n": safe(i.get("n") or f"{k + 1:02d}"), "text": safe(i["text"])} for k, i in enumerate(recap.get("items") or [])]
    y = H * 0.472
    for row in recap_rows(items, Fs, size, W):
        text = "   ".join("{\\1c%s}%s{\\1c%s} %s" % (accent, it["n"], white, it["text"]) for it in row)
        ev(2, e0, e1, "ExpRecap", f"{{\\pos({W // 2},{int(y)}){fad}}}{text}")
        y += H * 0.0345
    if recap.get("follow"):
        ev(2, e0, e1, "ExpFollow", f"{{\\pos({W // 2},{int(H * 0.585)}){fad}}}{safe(recap['follow'])}")


def check_extras(clip, tag, words, start, find_phrase, errors, warnings):
    """Check a clip's call-to-action pills and recap. Returns (ctas, recap): ctas with `at` (source seconds), recap as written."""
    ctas, last = [], None
    for k, c in enumerate(clip.get("cta") or [], 1):
        t = str(c.get("text", "")).strip()
        if not t or len(t) > 24:
            errors.append(f"{tag} cta {k}: text must be 1 to 24 characters")
            continue
        sec = float(c.get("seconds", 4))
        if not 2 <= sec <= 8:
            errors.append(f"{tag} cta {k}: seconds must be 2 to 8")
            continue
        say = str(c.get("say", "")).strip()
        if not say:
            errors.append(f"{tag} cta {k}: 'say' (the words where it appears) is required")
            continue
        hit, earlier = find_phrase(words, say, last)
        if hit is None:
            errors.append(f"{tag} cta {k}: the words \"{say}\" are " + ("only spoken before the previous pill" if earlier else "not spoken in this clip"))
            continue
        last = hit[0]
        ctas.append({"text": t, "seconds": sec, "at": round(hit[0], 3)})
    recap = clip.get("recap")
    if recap:
        items = recap.get("items") or []
        if len(str(recap.get("label", ""))) > 34 or len(str(recap.get("follow", ""))) > 60:
            errors.append(f"{tag} recap: label is at most 34 characters and follow at most 60")
        if not 1 <= len(items) <= 4:
            errors.append(f"{tag} recap: needs 1 to 4 items")
        for k, it in enumerate(items, 1):
            if not str(it.get("text", "")).strip() or len(str(it["text"])) > 34:
                errors.append(f"{tag} recap item {k}: text must be 1 to 34 characters")
    return ctas, recap


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
