#!/usr/bin/env python3
"""Render approved short-form clips as 9:16 videos. Needs ffmpeg (libass, libx264) and OpenCV.

Usage: render_shorts.py --source source.json --clips clips.resolved.json --transcript transcript.json
         --out-dir DIR [--ids 1,3] [--analysis analysis.json] [--brand brand.json]
         [--speaker "Name|Title"] [--punch-in 1.15] [--preview]
         [--cover static|animated] [--no-title] [--no-lower-third] [--no-end-card]

clips.resolved.json comes from validate_clips.py. For each chosen clip it writes
DIR/clip-NN-<title>/clip.mp4, clip.srt and meta.md (title, caption, reason). Each clip is built to
match the team's reference reel: 1080x1920; dead-air pauses inside the clip removed; the speaker kept in
frame by a face-aware crop that changes only at cuts; a title overlay for the first seconds, shown over
the blurred, navy-tinted video while the audio keeps playing; word-by-word captions (the current
word in the brand highlight colour, white text, dark outline, no box); a speaker lower third at the
bottom right; loudness normalised to the brand's short-form target; and a gradient end card with the
wordmark and web address. Everything comes from brand.json. --preview makes a small, fast version.
Prints JSON per clip. Never overwrites: use a fresh --out-dir.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def reexec_in_venv():
    try:
        import cv2  # noqa: F401
        return
    except ImportError:
        pass
    from setup_env import venv_python
    vpy = venv_python()
    if vpy.exists() and not os.environ.get("VE_REEXEC"):
        os.environ["VE_REEXEC"] = "1"
        os.execv(str(vpy), [str(vpy), __file__, *sys.argv[1:]])


from _vlib import load_json, words_of  # noqa: E402
import captions as cap  # noqa: E402
from render_long import (DEFAULT_BRAND, FADE, ass_color, ass_time, esc, font_info, load_brand,  # noqa: E402
                         measure_loudness, measured_duration, run_ffmpeg, split_by_clip)

TITLE_FADE = 0.35


def clip_keep(clip, analysis):
    """Kept ranges of a clip: its span minus the dead-air pauses inside it."""
    s, e = clip["start"], clip["end"]
    cuts = []
    if clip.get("trim_pauses", True) and analysis:
        for c in analysis.get("candidates", []):
            if c.get("keep_suggested") or c.get("kind") in ("lead_in", "tail_out"):
                continue
            c0, c1 = c["cut"]
            if c1 > s and c0 < e:
                cuts.append((max(c0, s), min(c1, e)))
    keep, pos = [], s
    for c0, c1 in sorted(cuts):
        if c0 - pos >= 0.1:
            keep.append({"start": pos, "end": c0})
        pos = max(pos, c1)
    if e - pos >= 0.1:
        keep.append({"start": pos, "end": e})
    return keep


def rrect(w, h, r):
    """ASS drawing path for a rounded rectangle."""
    k = r * 0.5523
    i = lambda v: int(round(v))
    return (f"m {i(r)} 0 l {i(w - r)} 0 b {i(w - r + k)} 0 {i(w)} {i(r - k)} {i(w)} {i(r)} l {i(w)} {i(h - r)} "
            f"b {i(w)} {i(h - r + k)} {i(w - r + k)} {i(h)} {i(w - r)} {i(h)} l {i(r)} {i(h)} "
            f"b {i(r - k)} {i(h)} 0 {i(h - r + k)} 0 {i(h - r)} l 0 {i(r)} b 0 {i(r - k)} {i(r - k)} 0 {i(r)} 0")


def kinetic_cover(ev, W, H, title, subtitle, T, t_sz, per_line, mag, green, safe):
    """Animated cover events (first T seconds): glowing title lines that pop in, a drifting wireframe
    ribbon (the brand's wave), a green rule that draws across, and a subtitle that slides up."""
    import textwrap
    n_lines = max(1, math.ceil(len(title) / max(per_line, 1)))
    lines = textwrap.wrap(title, math.ceil(len(title) / n_lines) + 1) or [title]  # balanced lines, no lone short word
    block = len(lines) * t_sz
    ty = H * 0.42
    ms = lambda x: int(x * 1000)
    out_at = ms(T) - 350
    for i in range(9):  # flowing wireframe ribbon, brightest in the middle, drifting upward
        y0 = int(H * 0.115 + i * H * 0.011)
        amp, dy = int(H * (0.045 + 0.004 * i)), int(H * (0.02 + 0.006 * i))
        path = "m -80 0 b %d %d %d %d %d %d" % (int(W * 0.30), -amp, int(W * 0.62), amp * 2, W + 80, dy)
        al = 0x48 + 14 * abs(i - 4)
        ev(0, 0, T, "Shape", "{\\an7\\move(0,%d,0,%d,0,%d)\\p1\\1a&HFF&\\3c%s\\3a&H%02X&\\bord3\\blur1\\t(%d,%d,\\3a&HFF&)}%s{\\p0}"
           % (y0 + int(H * 0.07), y0 - int(H * 0.05), ms(T), mag, min(al, 0xE0), out_at, ms(T), path))
    for i, line in enumerate(lines):
        y = int(ty - block / 2 + (i + 0.5) * t_sz)
        d = 40 + 150 * i
        glow = ("{\\an5\\pos(%d,%d)\\1a&HFF&\\3c%s\\bord9\\blur16\\3a&HFF&\\fscx72\\fscy72\\t(%d,%d,\\3a&H50&\\fscx110\\fscy110)"
                "\\t(%d,%d,\\fscx100\\fscy100)\\t(%d,%d,\\3a&HFF&)}%s" % (W // 2, y, mag, d, d + 230, d + 230, d + 380, out_at, ms(T), safe(line)))
        main = ("{\\an5\\pos(%d,%d)\\alpha&HFF&\\blur8\\fscx72\\fscy72\\t(%d,%d,\\alpha&H00&\\blur0\\fscx110\\fscy110)"
                "\\t(%d,%d,\\fscx100\\fscy100)\\t(%d,%d,\\alpha&HFF&)}%s" % (W // 2, y, d, d + 230, d + 230, d + 380, out_at, ms(T), safe(line)))
        ev(1, 0, T, "Title", glow)
        ev(2, 0, T, "Title", main)
    ry = int(ty + block / 2 + H * 0.016)
    rw, rh = int(W * 0.34), max(5, int(H * 0.0045))
    rx = (W - rw) // 2
    ev(2, 0, T, "Shape", "{\\an7\\pos(%d,%d)\\p1\\1c%s\\bord0\\clip(%d,%d,%d,%d)\\t(900,1300,\\clip(%d,%d,%d,%d))\\t(%d,%d,\\alpha&HFF&)}m 0 0 l %d 0 %d %d 0 %d{\\p0}"
       % (rx, ry, green, rx, ry - 2, rx, ry + rh + 2, rx, ry - 2, rx + rw, ry + rh + 2, out_at, ms(T), rw, rw, rh, rh))
    if subtitle:
        sy = int(ry + H * 0.062)
        ev(2, 0, T, "Sub", "{\\an5\\move(%d,%d,%d,%d,1050,1400)\\alpha&HFF&\\t(1050,1400,\\alpha&H00&)\\t(%d,%d,\\alpha&HFF&)}%s"
           % (W // 2, sy + int(H * 0.02), W // 2, sy, out_at, ms(T), safe(subtitle)))


def build_ass(brand, res, W, H, words_groups, title, subtitle, speaker, cfg, main_dur, flags):
    colors = brand["colors"]
    col = lambda n: colors.get(n, n if str(n).startswith("#") else "#FFFFFF")
    fonts = brand["fonts"]
    capc = brand.get("captions", {}).get("short", {})
    bold_fam, bold_b = font_info(res(fonts["bold"]))
    semi_fam, semi_b = font_info(res(fonts.get("semibold", fonts["bold"])))
    reg_fam, reg_b = font_info(res(fonts["regular"]))
    med_fam, med_b = font_info(res(fonts.get("medium", fonts["regular"])))
    cap_fam, cap_b = font_info(res(fonts[capc.get("font", "bold")]))
    white, hi = ass_color(col(capc.get("color", "text"))), ass_color(col(capc.get("highlight", "primary")))
    outline = ass_color(capc.get("outline", "#000000"))
    cap_sz = int(H * 0.054)  # ASS sizes are line heights; Poppins is tall, so letters render about 1.5x smaller
    tl = len(title)
    t_sz = int(H * (0.14 if tl <= 12 else 0.105 if tl <= 28 else 0.080))
    per_line = max(6, int(W * 0.92 / (t_sz / 1.5 * 0.58)))
    lines = max(1, math.ceil(tl / per_line))
    t_h = lines * t_sz * 1.0
    mag, green, navy = ass_color(col("primary")), ass_color(col("secondary")), ass_color(col("background"))
    st = lambda name, fam, sz, b, c, al=2, extra="0,0,0,0,100,100,0,0,1,0,0": (
        f"Style: {name},{fam},{sz},{c},&H00FFFFFF&,{outline},&H00000000&,{-1 if b else 0},{extra},{al},0,0,0,1")
    L = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        f"Style: Cap,{cap_fam},{cap_sz},{white},&H00FFFFFF&,{outline},&H00000000&,{-1 if cap_b else 0},0,0,0,100,100,0,0,1,{max(4, int(H * 0.0035))},0,2,{int(W * 0.06)},{int(W * 0.06)},{int(H * 0.26)},1",
        f"Style: Title,{bold_fam},{t_sz},{mag},&H00FFFFFF&,&H00000000&,&H00000000&,{-1 if bold_b else 0},0,0,0,100,100,0,0,1,0,0,5,{int(W * 0.07)},{int(W * 0.07)},0,1",
        f"Style: Sub,{med_fam},{int(H * 0.058)},{green},&H00FFFFFF&,&H00000000&,&H00000000&,{-1 if med_b else 0},0,0,0,100,100,0,0,1,0,0,5,{int(W * 0.07)},{int(W * 0.07)},0,1",
        f"Style: Name,{bold_fam},{int(H * 0.034)},&H00FFFFFF&,&H00FFFFFF&,&H00000000&,&H00000000&,{-1 if bold_b else 0},0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        f"Style: Role,{reg_fam},{int(H * 0.028)},{green},&H00FFFFFF&,&H00000000&,&H00000000&,{-1 if reg_b else 0},0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        f"Style: Shape,{reg_fam},20,&H00FFFFFF&,&H00FFFFFF&,&H00000000&,&H00000000&,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        f"Style: Url,{med_fam},{int(H * 0.031)},&H00FFFFFF&,&H00FFFFFF&,&H00000000&,&H00000000&,0,1,0,0,100,100,0,0,1,0,0,5,0,0,0,1",
        "", "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text"]
    ev = lambda layer, a, b, style, text: L.append(f"Dialogue: {layer},{ass_time(a)},{ass_time(b)},{style},,0,0,0,,{text}")
    safe = lambda s: s.replace("{", "(").replace("}", ")").replace("\\", "")
    T = float(cfg["title"].get("seconds", 3))
    ty = H * 0.42
    if flags["title"] and title and flags.get("cover", "static") == "animated":
        kinetic_cover(ev, W, H, title, subtitle, T, t_sz, per_line, mag, green, safe)
    elif flags["title"] and title:
            ev(2, 0, T, "Title", f"{{\\pos({W // 2},{int(ty)})\\fad({int(TITLE_FADE * 1000)},{int(TITLE_FADE * 1000)})}}{safe(title)}")
            ry = int(ty + t_h / 2 + H * 0.014)
            rw, rh = int(W * 0.30), max(4, int(H * 0.004))
            ev(2, 0, T, "Shape", f"{{\\pos({(W - rw) // 2},{ry})\\p1\\1c{green}\\bord0\\fad({int(TITLE_FADE * 1000)},{int(TITLE_FADE * 1000)})}}m 0 0 l {rw} 0 {rw} {rh} 0 {rh}{{\\p0}}")
            if subtitle:
                ev(2, 0, T, "Sub", f"{{\\pos({W // 2},{int(ry + H * 0.05)})\\fad({int(TITLE_FADE * 1000)},{int(TITLE_FADE * 1000)})}}{safe(subtitle)}")
    for grp in words_groups:
        for k, w in enumerate(grp):
            a = w["start"] if k else grp[0]["start"]
            b = grp[k + 1]["start"] if k + 1 < len(grp) else grp[-1]["end"]
            parts = [("{\\1c" + (hi if j == k else white) + "}") + safe(x["word"]) for j, x in enumerate(grp)]
            ev(3, a, b, "Cap", " ".join(parts))
    if flags["lower_third"] and speaker:
        a = T if flags["title"] else 0.5
        b = min(a + float(cfg["lower_third"].get("seconds", 16)), main_dur)
        bw, bh = int(W * 0.46), int(H * 0.085)
        bx, by = W - int(W * 0.035) - bw, int(H * 0.855)
        fad = "\\fad(300,300)"
        ev(4, a, b, "Shape", f"{{\\pos({bx},{by})\\p1\\1c{navy}\\1a&H1A&\\bord0{fad}}}{rrect(bw, bh, bh * 0.18)}{{\\p0}}")
        ev(5, a, b, "Shape", f"{{\\pos({bx + bw - int(W * 0.035)},{by + int(bh * 0.2)})\\p1\\1c{mag}\\bord0{fad}}}m 0 0 l {max(4, int(W * 0.008))} 0 {max(4, int(W * 0.008))} {int(bh * 0.6)} 0 {int(bh * 0.6)}{{\\p0}}")
        ev(5, a, b, "Name", f"{{\\pos({bx + int(bw * 0.07)},{by + int(bh * 0.10)}){fad}}}{safe(speaker[0])}")
        if len(speaker) > 1 and speaker[1]:
            ev(5, a, b, "Role", f"{{\\pos({bx + int(bw * 0.07)},{by + int(bh * 0.10 + H * 0.034 * 1.05)}){fad}}}{safe(speaker[1])}")
    if flags["end_card"]:
        e0, e1 = main_dur, main_dur + float(cfg["end_card"].get("seconds", 3))
        url = cfg["end_card"].get("url", "")
        if url:
            pw, ph = int(W * 0.44), int(H * 0.034)
            px, py = (W - pw) // 2, int(H * 0.483 - ph / 2)
            ev(2, e0, e1, "Shape", f"{{\\pos({px},{py})\\p1\\1a&HFF&\\3c&HFFFFFF&\\bord{max(2, int(H * 0.0018))}\\fad(350,0)}}{rrect(pw, ph, ph * 0.28)}{{\\p0}}")
            ev(3, e0, e1, "Url", f"{{\\pos({W // 2},{int(H * 0.483)})\\fad(350,0)}}{safe(url)}")
    return "\n".join(L) + "\n"


def make_end_card(brand, res, W, H, work):
    cfg = brand["shorts"]["end_card"]
    hexes = cfg.get("gradient", ["#0B1250", "#8A3378"])
    rgb = lambda h: tuple(int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    (r0, g0, b0), (r1, g1, b1) = rgb(hexes[0]), rgb(hexes[1])
    lerp = lambda a, b: f"{a}+({b}-{a})*Y/H"
    logo = res(brand["logo"]["wordmark"])
    px = subprocess.run(["ffmpeg", "-v", "error", "-i", str(logo), "-vf", "crop=1:1:5:5,format=rgb24", "-f", "rawvideo", "-"],
                        capture_output=True).stdout[:3]
    key = "0x%02X%02X%02X" % tuple(px) if len(px) == 3 else "0x041250"
    lw = int(W * float(cfg.get("logo_width", 0.7)))
    out = work / "endcard.png"
    code, err = run_ffmpeg(["-f", "lavfi", "-i",
                            f"color=c=black:s={W}x{H}:r=1:d=1,format=gbrp,geq=r='{lerp(r0, r1)}':g='{lerp(g0, g1)}':b='{lerp(b0, b1)}'",
                            "-i", str(logo), "-filter_complex",
                            f"[1:v]colorkey={key}:0.14:0.10,scale={lw}:-1[l];[0:v][l]overlay=(W-w)/2:H*0.42-h/2:format=auto,format=yuv420p",
                            "-frames:v", "1", str(out)])
    return (out, None) if code == 0 else (None, err[-400:])


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "clip"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True)
    ap.add_argument("--clips", required=True)
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--ids")
    ap.add_argument("--analysis")
    ap.add_argument("--brand", default=str(DEFAULT_BRAND))
    ap.add_argument("--speaker", help='"Name|Title" for the lower third')
    ap.add_argument("--punch-in", type=float, default=1.0)
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--no-title", action="store_true")
    ap.add_argument("--cover", choices=["static", "animated"], default="static",
                    help="static (default): plain title over the blurred video; animated: experimental kinetic title with a drifting ribbon, not recommended until the cover is redesigned")
    ap.add_argument("--no-lower-third", "--no-lower-thirds", dest="no_lower_third", action="store_true")
    ap.add_argument("--no-end-card", action="store_true")
    ap.add_argument("--keep-work", action="store_true")
    a = ap.parse_args()
    reexec_in_venv()
    from reframe import detect

    def die(msg, **kw):
        print(json.dumps({"ok": False, "error": msg, **kw}))
        return 1

    try:
        src, clips = load_json(a.source), load_json(a.clips)["clips"]
        transcript = load_json(a.transcript)
        analysis = load_json(a.analysis) if a.analysis else None
        brand, res = load_brand(a.brand)
    except (OSError, ValueError, KeyError) as e:
        return die(f"cannot read input: {e}")
    if "start" not in (clips[0] if clips else {}):
        return die("clips file is not resolved; run validate_clips.py --out first")
    if a.ids:
        want = {int(x) for x in a.ids.split(",")}
        clips = [c for c in clips if int(c["id"]) in want]
    if not clips:
        return die("no clips selected")
    out_root = Path(a.out_dir)
    if out_root.exists() and any(out_root.iterdir()):
        return die(f"{out_root} is not empty; use a new --out-dir (earlier renders are kept)")
    out_root.mkdir(parents=True, exist_ok=True)

    speaker = [s.strip() for s in a.speaker.split("|")] if a.speaker else None
    sizes = brand.get("output", {}).get("short", {})
    W, H = map(int, sizes.get("resolution", "1080x1920").lower().split("x"))
    fps, lufs = float(sizes.get("fps", 30)), float(sizes.get("lufs", -15))
    crf, preset = "17", "medium"
    if a.preview:
        W, H, crf, preset = 540, 960, "30", "veryfast"
    flags = {"cover": a.cover, "title": not a.no_title, "lower_third": not a.no_lower_third, "end_card": not a.no_end_card}
    cfg = brand["shorts"]
    snap = lambda t: round(t * fps) / fps
    all_words = words_of(transcript)
    results, clipsrc = [], src["clips"]

    for clip in clips:
        warnings = []
        d_out = out_root / f"clip-{int(clip['id']):02d}-{slug(clip['title'])}"
        work = d_out / "work"
        work.mkdir(parents=True, exist_ok=True)
        keep = clip_keep(clip, analysis)
        pieces = split_by_clip(keep, clipsrc)
        if not pieces:
            results.append({"id": clip["id"], "ok": False, "error": "no kept ranges inside the source"})
            continue

        # 1. face-aware crop per piece (grouped by source clip)
        plans = {}
        for ci in sorted({p[0] for p in pieces}):
            rng = [(ls, le) for (c, ls, le) in pieces if c == ci]
            try:
                plans[ci] = detect(clipsrc[ci]["path"], rng, a.punch_in)
            except (RuntimeError, ImportError) as e:
                return die(f"face detection failed: {e}")
        counters = {ci: 0 for ci in plans}

        # 2. cut and crop each piece on its own (memory stays flat)
        list_lines, main_dur = [], 0.0
        for i, (ci, ls, le) in enumerate(pieces):
            plan = plans[ci]["pieces"][counters[ci]]
            counters[ci] += 1
            if plan["flag"]:
                warnings.append(f"piece {i + 1} at {ls:.1f}s: {plan['flag']}")
            cx = plan["crop"]
            lsn, len_ = snap(ls), snap(le)
            d = max(len_ - lsn, 1 / fps)
            main_dur += d
            vf = (f"crop={cx['w']}:{cx['h']}:{cx['x']}:{cx['y']},scale={W}:{H}:flags=lanczos,setsar=1,fps={fps},format=yuv420p")
            cmd = ["-ss", f"{lsn:.4f}", "-i", clipsrc[ci]["path"]]
            if clipsrc[ci].get("has_audio"):
                amap = "0:a:0"
                af = (f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,afade=t=in:st=0:d={FADE},"
                      f"afade=t=out:st={max(d - FADE, 0):.4f}:d={FADE}")
            else:
                cmd += ["-f", "lavfi", "-t", f"{d:.4f}", "-i", "anullsrc=r=48000:cl=stereo"]
                amap, af = "1:a:0", "aresample=48000"
            pf = work / f"p{i:04d}.mkv"
            cmd += ["-t", f"{d:.4f}", "-map", "0:v:0", "-map", amap, "-vf", vf, "-af", af, "-c:v", "libx264",
                    "-crf", "14" if not a.preview else "30", "-preset", "superfast", "-threads", "4", "-pix_fmt", "yuv420p",
                    "-r", str(fps), "-c:a", "pcm_s16le", "-ar", "48000", str(pf)]
            code, err = run_ffmpeg(cmd)
            if code != 0:
                return die(f"ffmpeg failed on clip {clip['id']} piece {i + 1}", detail=err[-600:])
            list_lines.append("file '" + str(pf.resolve()).replace("'", "'\\''") + "'")
            print(f"clip {clip['id']} piece {i + 1}/{len(pieces)}", file=sys.stderr, flush=True)
        lst = work / "pieces.txt"
        lst.write_text("\n".join(list_lines) + "\n", encoding="utf-8")

        # 3. captions, overlay text, end card
        timed = cap.retime(all_words, keep)
        groups = cap.group(timed, brand.get("captions", {}).get("short", {}).get("max_words_per_line", 3))
        (d_out / "clip.srt").write_text(cap.to_srt(cap.group(timed)), encoding="utf-8")
        ass = build_ass(brand, res, W, H, groups, clip.get("overlay_title", clip["title"]), clip.get("subtitle", ""),
                        speaker, cfg, main_dur, flags)
        (work / "overlays.ass").write_text(ass, encoding="utf-8")
        inputs = ["-f", "concat", "-safe", "0", "-i", str(lst)]
        meas = measure_loudness(lst, lufs)
        if meas:
            ln = (f"loudnorm=I={lufs}:TP=-1.5:LRA=11:measured_I={meas['input_i']}:measured_TP={meas['input_tp']}:"
                  f"measured_LRA={meas['input_lra']}:measured_thresh={meas['input_thresh']}:offset={meas['target_offset']}:linear=true")
        else:
            warnings.append("could not measure loudness first; single pass used")
            ln = f"loudnorm=I={lufs}:TP=-1.5:LRA=11"
        T = float(cfg["title"].get("seconds", 3))
        g, vlab = [], "[0:v]"
        if flags["title"]:
            ov = cfg["title"].get("blur_overlay", "#041250").replace("#", "0x")
            al = cfg["title"].get("blur_alpha", 0.72)
            if a.cover == "animated":
                g.append(f"[0:v]split=2[base][cp];"
                         f"[cp]trim=0:{T},setpts=PTS-STARTPTS,boxblur=luma_radius={max(8, W // 28)}:luma_power=2,"
                         f"drawbox=x=0:y=0:w=iw:h=ih:color={ov}@{al}:t=fill,"
                         f"scale=w='trunc(iw*(1.16-0.16*min(t/{T},1))/2)*2':h='trunc(ih*(1.16-0.16*min(t/{T},1))/2)*2':eval=frame,"
                         f"crop={W}:{H},format=yuva420p,fade=t=out:st={T - 0.45:.2f}:d=0.45:alpha=1[blur];"
                         f"[base][blur]overlay=eof_action=pass[mv]")
            else:
                g.append(f"[0:v]boxblur=luma_radius={max(8, W // 28)}:luma_power=2:enable='lt(t,{T})',"
                         f"drawbox=x=0:y=0:w=iw:h=ih:color={ov}@{al}:t=fill:enable='lt(t,{T})'[mv]")
            vlab = "[mv]"
        g.append(f"[0:a]{ln}[ma]")
        total = main_dur
        if flags["end_card"]:
            card, err = make_end_card(brand, res, W, H, work)
            if card is None:
                return die("could not build the end card", detail=err)
            es = float(cfg["end_card"].get("seconds", 3))
            inputs += ["-loop", "1", "-framerate", str(fps), "-t", str(es), "-i", str(card)]
            g.append(f"[1:v]scale={W}:{H},setsar=1,fps={fps},format=yuv420p,fade=t=in:st=0:d=0.35[ev]")
            g.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{es},asetpts=PTS-STARTPTS[ea]")
            g.append(f"{vlab}[ma][ev][ea]concat=n=2:v=1:a=1[cv][ca]")
            vlab, alab, total = "[cv]", "[ca]", main_dur + es
        else:
            alab = "[ma]"
        g.append(f"{vlab}ass='{esc(work / 'overlays.ass')}':fontsdir='{esc(res(brand['fonts']['regular']).parent)}'[fv]")
        script = work / "filtergraph.txt"
        script.write_text(";\n".join(g), encoding="utf-8")
        out_mp4 = d_out / "clip.mp4"
        code, err = run_ffmpeg([*inputs, "-filter_complex_script", str(script), "-map", "[fv]", "-map", alab,
                                "-c:v", "libx264", "-crf", crf, "-preset", preset, "-pix_fmt", "yuv420p", "-r", str(fps),
                                "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out_mp4)])
        if code != 0:
            return die(f"ffmpeg failed on the final pass of clip {clip['id']}", detail=err[-800:], filtergraph=str(script))
        if flags["title"]:
            run_ffmpeg(["-ss", f"{float(cfg['title'].get('seconds', 3)) * 0.78:.2f}", "-i", str(out_mp4), "-frames:v", "1", "-q:v", "2", str(d_out / "cover.png")])
        measured = measured_duration(out_mp4)
        if measured is not None and abs(measured - total) > 0.5:
            warnings.append(f"measured length {measured:.2f}s differs from expected {total:.2f}s")
        (d_out / "meta.md").write_text(
            f"# {clip['title']}\n\n**Post caption**\n\n{clip.get('caption', '')}\n\n**Why this moment**\n\n{clip.get('reason', '')}\n\n"
            f"**Source:** {clip['at']} in the recording, about {clip.get('effective_seconds', '')} s before the end card.\n", encoding="utf-8")
        if not a.keep_work:
            import shutil
            shutil.rmtree(work, ignore_errors=True)
        faces = [p for pl in plans.values() for p in pl["pieces"]]
        results.append({"id": clip["id"], "ok": True, "video": str(out_mp4), "expected_seconds": round(total, 3),
                        "measured_seconds": measured, "pieces": len(pieces),
                        "faces_found": f"{sum(p['faces_found'] > 0 for p in faces)}/{len(faces)} pieces", "warnings": warnings})
    print(json.dumps({"ok": all(r["ok"] for r in results), "preview": a.preview, "clips": results}, indent=2))
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
