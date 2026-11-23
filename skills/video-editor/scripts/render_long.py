#!/usr/bin/env python3
"""Render the long-form video from an approved cut list. Needs ffmpeg with libass and libx264.

Usage: render_long.py --source source.json --cutlist cutlist.json --out-dir DIR
         [--brand brand.json] [--transcript transcript.json]
         [--captions none|burn|srt|both] [--no-intro-outro] [--no-lower-thirds] [--preview]

Writes DIR/long.mp4 (refuses to overwrite: use a fresh DIR per run), plus DIR/long.srt when
captions are srt/both and DIR/chapters.txt when the cut list has chapters.
Two steps, both memory-safe for long recordings: (1) cut each kept range into its own small file
(scaled/padded to the brand size, audio edges faded 15 ms so joins do not click); (2) join them,
normalise loudness (two passes: measure, then apply), add the brand intro and outro cards, then draw lower thirds and burned-in
captions with libass (brand fonts and colours) in one final encode.
--preview makes a small, fast render (no intro/outro) for checking the cuts.
Prints JSON with the output path, expected and measured duration, and warnings.
"""
import argparse
import json
import subprocess
import sys
import struct
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vlib import hms, load_json, words_of  # noqa: E402
from validate_cutlist import validate  # noqa: E402
import captions as cap  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_BRAND = SKILL_DIR / "assets" / "brand" / "brand.json"
FADE = 0.015  # seconds, audio edge fade at each join


# ---------- brand ----------
def load_brand(path):
    path = Path(path)
    b = load_json(path)
    base = path.parent

    def res(rel):
        p = Path(rel)
        return p if p.is_absolute() else base / p

    return b, res


def font_info(path):
    """(family, bold) read from a TrueType file's name table, for libass."""
    data = Path(path).read_bytes()
    n_tables = struct.unpack(">H", data[4:6])[0]
    off = None
    for i in range(n_tables):
        tag, _, o, _ = struct.unpack(">4sIII", data[12 + 16 * i: 28 + 16 * i])
        if tag == b"name":
            off = o
    if off is None:
        return Path(path).stem, False
    _, count, str_off = struct.unpack(">HHH", data[off: off + 6])
    names = {}
    for i in range(count):
        pid, eid, lid, nid, ln, o = struct.unpack(">HHHHHH", data[off + 6 + 12 * i: off + 18 + 12 * i])
        if pid == 3 and nid in (1, 2):
            raw = data[off + str_off + o: off + str_off + o + ln]
            names[nid] = raw.decode("utf-16-be", "ignore")
    return names.get(1, Path(path).stem), "bold" in names.get(2, "").lower()


def ass_color(hex_rgb, alpha=0):
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return ("&H%02X%s%s%s&" % (alpha, b, g, r)).upper()


def ass_time(t):
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, c = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def build_ass(brand, res, W, H, cues, lower_thirds, offset):
    colors = brand["colors"]

    def col(name, default="#FFFFFF"):
        return colors.get(name, name if str(name).startswith("#") else default)

    fonts = brand["fonts"]
    cap_cfg = brand.get("captions", {}).get("long", {})
    lt_cfg = brand.get("lower_third", {})
    name_fam, name_bold = font_info(res(fonts[lt_cfg.get("name_font", "semibold")]))
    title_fam, title_bold = font_info(res(fonts[lt_cfg.get("title_font", "regular")]))
    cap_fam, cap_bold = font_info(res(fonts[cap_cfg.get("font", "medium")]))
    name_sz, title_sz, cap_sz = int(H * 0.042), int(H * 0.030), int(H * 0.040)
    box = ass_color(col(lt_cfg.get("box", "background")), 0x26)
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        f"Style: Name,{name_fam},{name_sz},{ass_color(col(lt_cfg.get('name_color', 'text')))},&H00FFFFFF&,&H00000000&,&H00000000&,{-1 if name_bold else 0},0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        f"Style: Title,{title_fam},{title_sz},{ass_color(col(lt_cfg.get('title_color', 'secondary')))},&H00FFFFFF&,&H00000000&,&H00000000&,{-1 if title_bold else 0},0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        f"Style: Box,{name_fam},{name_sz},{box},&H00FFFFFF&,&H00000000&,&H00000000&,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        f"Style: Bar,{name_fam},{name_sz},{ass_color(col(lt_cfg.get('accent_bar', 'primary')))},&H00FFFFFF&,&H00000000&,&H00000000&,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        f"Style: Cap,{cap_fam},{cap_sz},{ass_color(col(cap_cfg.get('color', 'text')))},&H00FFFFFF&,{ass_color(col(cap_cfg.get('box', 'background')), 0x40)},&H00000000&,{-1 if cap_bold else 0},0,0,0,100,100,0,0,3,{max(6, int(H * 0.008))},0,2,{int(W * 0.08)},{int(W * 0.08)},{int(H * 0.07)},1",
        "", "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]
    for lt in lower_thirds:
        start, end = lt["start"] + offset, lt["end"] + offset
        x, y = int(W * 0.05), int(H * 0.76)
        safe = lambda s_: str(s_).replace("{", "(").replace("}", ")").replace("\\", "")
        name, title = safe(lt["name"]), safe(lt.get("title", ""))
        w = int(max(len(name) * name_sz * 0.62, len(title) * title_sz * 0.58)) + int(W * 0.03) + 14
        h = int(name_sz * 1.25 + (title_sz * 1.4 if title else 0) + H * 0.02)
        pad = int(W * 0.012)
        fad = "\\fad(300,300)"
        t0, t1 = ass_time(start), ass_time(end)
        rect = lambda rw: "m 0 0 l %d 0 %d %d 0 %d" % (rw, rw, h, h)
        lines.append("Dialogue: 0,%s,%s,Box,,0,0,0,,{\\pos(%d,%d)\\p1%s}%s{\\p0}" % (t0, t1, x, y, fad, rect(w)))
        lines.append("Dialogue: 1,%s,%s,Bar,,0,0,0,,{\\pos(%d,%d)\\p1%s}%s{\\p0}" % (t0, t1, x, y, fad, rect(8)))
        lines.append("Dialogue: 2,%s,%s,Name,,0,0,0,,{\\pos(%d,%d)%s}%s" % (t0, t1, x + 8 + pad, y + int(H * 0.008), fad, name))
        if title:
            lines.append("Dialogue: 2,%s,%s,Title,,0,0,0,,{\\pos(%d,%d)%s}%s" % (t0, t1, x + 8 + pad, y + int(H * 0.008 + name_sz * 1.2), fad, title))
    for c in cues:
        text = " ".join(w["word"] for w in c).strip()
        body = cap.wrap(text.replace("{", "(").replace("}", ")").replace("\\", "")).replace("\n", "\\N")
        lines.append("Dialogue: 3,%s,%s,Cap,,0,0,0,,%s" % (ass_time(c[0]["start"] + offset), ass_time(c[-1]["end"] + offset), body))
    return "\n".join(lines) + "\n"


# ---------- timeline ----------
def split_by_clip(keep, clips):
    """Split keep ranges (combined timeline) at clip boundaries -> [(clip_index, local_start, local_end)]."""
    pieces = []
    for k in keep:
        t = k["start"]
        while t < k["end"] - 1e-6:
            idx = next((i for i, c in enumerate(clips) if c["offset"] - 1e-6 <= t < c["offset"] + c["duration"] - 1e-6), None)
            if idx is None:
                break
            c = clips[idx]
            end = min(k["end"], c["offset"] + c["duration"])
            pieces.append((idx, t - c["offset"], end - c["offset"]))
            t = end
    return pieces


def esc(path):
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def lower_third_events(brand, cl, transcript, keep, out_total):
    cfg = brand.get("lower_third", {})
    show, repeat = float(cfg.get("show_seconds", 5)), float(cfg.get("repeat_every_seconds", 600))
    speakers = {s["id"]: s for s in cl.get("speakers", []) if s.get("name")}
    events = []
    explicit = cl.get("lower_thirds")
    if explicit:
        for e in explicit:
            sp = speakers.get(e.get("speaker"), {})
            name = e.get("name") or sp.get("name")
            if name:
                o = cap_map(keep, float(e["at"]))
                events.append({"start": o, "end": min(o + float(e.get("seconds", show)), out_total), "name": name, "title": e.get("title", sp.get("title", ""))})
        return events
    if transcript:
        first_seen, last_shown = {}, {}
        for w in sorted(words_of(transcript), key=lambda x: x["start"]):
            spk = w.get("speaker")
            if spk not in speakers or not any(k["start"] <= w["start"] <= k["end"] for k in keep):
                continue
            o = cap_map(keep, w["start"])
            if spk not in last_shown or (repeat > 0 and o - last_shown[spk] >= repeat):
                last_shown[spk] = o
                events.append({"start": o, "end": min(o + show, out_total), "name": speakers[spk]["name"], "title": speakers[spk].get("title", "")})
    return events


def cap_map(keep, t):
    from _vlib import kept_before
    return kept_before(keep, t)


def run_ffmpeg(args):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", *args], capture_output=True, text=True)
    return r.returncode, r.stderr


def measure_loudness(list_path, lufs):
    """First loudnorm pass over the joined audio. Returns the measured values, or None on failure."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-f", "concat", "-safe", "0", "-i", str(list_path), "-vn",
                        "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    try:
        blob = r.stderr[r.stderr.rindex("{"): r.stderr.rindex("}") + 1]
        m = json.loads(blob)
        return {k: m[k] for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")}
    except (ValueError, KeyError):
        return None


def measured_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True)
    ap.add_argument("--cutlist", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--brand", default=str(DEFAULT_BRAND))
    ap.add_argument("--transcript")
    ap.add_argument("--captions", choices=["none", "burn", "srt", "both"])
    ap.add_argument("--no-intro-outro", action="store_true")
    ap.add_argument("--no-lower-thirds", "--no-lower-third", dest="no_lower_thirds", action="store_true")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--keep-work", action="store_true", help="keep the per-piece files (default: delete after a good render)")
    a = ap.parse_args()

    def die(msg, **kw):
        print(json.dumps({"ok": False, "error": msg, **kw}))
        return 1

    try:
        src, cl = load_json(a.source), load_json(a.cutlist)
        brand, res = load_brand(a.brand)
        transcript = load_json(a.transcript) if a.transcript else None
    except (OSError, ValueError) as e:
        return die(f"cannot read input: {e}")

    errors, warnings, info = validate(cl, transcript)
    if errors:
        return die("the cut list does not validate; run validate_cutlist.py", errors=errors)
    clips, keep = src["clips"], cl["keep"]
    out_dir = Path(a.out_dir)
    out_mp4 = out_dir / "long.mp4"
    if out_mp4.exists():
        return die(f"{out_mp4} already exists; use a new --out-dir (earlier renders are kept)")

    out_cfg = brand.get("output", {}).get("long", {})
    W, H = map(int, out_cfg.get("resolution", "1920x1080").lower().split("x"))
    fps = float(out_cfg.get("fps", 30))
    lufs = float(out_cfg.get("lufs", -16))
    crf, preset = "18", "medium"
    if a.preview:
        W, H, crf, preset = 854, 480, "30", "veryfast"
    bg = "0x" + brand["colors"].get("background", "#000000").lstrip("#")
    mode = a.captions or brand.get("captions", {}).get("long", {}).get("mode", "sidecar")
    mode = {"sidecar": "srt"}.get(mode, mode)

    pieces = split_by_clip(keep, clips)
    if not pieces:
        return die("no kept ranges fall inside the source clips")

    out_dir.mkdir(parents=True, exist_ok=True)
    snap = lambda t: round(t * fps) / fps
    norm_v = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={bg},setsar=1,fps={fps},format=yuv420p"
    norm_a = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"

    # Step 1: cut each kept piece on its own. One ffmpeg run per piece keeps memory flat however long
    # the recording is (a single graph with many trims of one input queues frames and exhausts RAM).
    work = out_dir / "pieces"
    work.mkdir(exist_ok=True)
    list_lines = []
    piece_crf = "30" if a.preview else "14"
    for i, (ci, ls, le) in enumerate(pieces):
        ls, le = snap(ls), snap(le)
        d = max(le - ls, 1 / fps)
        pf = work / f"p{i:04d}.mkv"
        cmd = ["-ss", f"{ls:.4f}", "-i", clips[ci]["path"]]
        if clips[ci].get("has_audio"):
            amap, af = "0:a:0", f"{norm_a},afade=t=in:st=0:d={FADE},afade=t=out:st={max(d - FADE, 0):.4f}:d={FADE}"
        else:
            cmd += ["-f", "lavfi", "-t", f"{d:.4f}", "-i", "anullsrc=r=48000:cl=stereo"]
            amap, af = "1:a:0", norm_a
        cmd += ["-t", f"{d:.4f}", "-map", "0:v:0", "-map", amap, "-vf", norm_v, "-af", af,
                "-c:v", "libx264", "-crf", piece_crf, "-preset", "superfast", "-threads", "4", "-pix_fmt", "yuv420p",
                "-r", str(fps), "-c:a", "pcm_s16le", "-ar", "48000", str(pf)]
        code, err = run_ffmpeg(cmd)
        if code != 0:
            return die(f"ffmpeg failed on piece {i + 1} of {len(pieces)}", detail=err[-800:])
        list_lines.append("file '" + str(pf.resolve()).replace("'", "'\\''") + "'")
        print(f"piece {i + 1}/{len(pieces)}", file=sys.stderr, flush=True)
    list_path = out_dir / "pieces.txt"
    list_path.write_text("\n".join(list_lines) + "\n", encoding="utf-8")
    main_dur = sum(snap(le) - snap(ls) for _, ls, le in pieces)

    # Step 2: one light pass over the joined pieces: loudness, intro/outro, captions, final encode.
    inputs = ["-f", "concat", "-safe", "0", "-i", str(list_path)]
    meas = measure_loudness(list_path, lufs)
    if meas:
        ln = (f"loudnorm=I={lufs}:TP=-1.5:LRA=11:measured_I={meas['input_i']}:measured_TP={meas['input_tp']}:"
              f"measured_LRA={meas['input_lra']}:measured_thresh={meas['input_thresh']}:offset={meas['target_offset']}:linear=true")
    else:
        warnings.append("could not measure loudness first; used a single pass, so the level may be off by about 1 LU")
        ln = f"loudnorm=I={lufs}:TP=-1.5:LRA=11"
    g = ["[0:v]null[mv]", f"[0:a]{ln}[ma]"]

    seq, offset, extra = [("[mv]", "[ma]")], 0.0, 0.0
    if not a.no_intro_outro and not a.preview:
        idx = 1
        for key, order in (("intro", "front"), ("outro", "back")):
            cfg = brand.get(key)
            if not cfg:
                continue
            card = res(cfg["card"])
            if not card.is_file():
                return die(f"{key} card not found: {card}")
            dur, fd = float(cfg.get("seconds", 3)), float(cfg.get("fade_seconds", 0.5))
            inputs += ["-loop", "1", "-framerate", str(fps), "-t", str(dur), "-i", str(card)]
            g.append(f"[{idx}:v]{norm_v},fade=t=in:st=0:d={fd},fade=t=out:st={max(dur - fd, 0):.3f}:d={fd}[{key}v]")
            g.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{dur},asetpts=PTS-STARTPTS[{key}a]")
            if order == "front":
                seq.insert(0, (f"[{key}v]", f"[{key}a]"))
                offset = dur
            else:
                seq.append((f"[{key}v]", f"[{key}a]"))
            extra += dur
            idx += 1
    if len(seq) > 1:
        g.append("".join(v + a_ for v, a_ in seq) + f"concat=n={len(seq)}:v=1:a=1[cv][ca]")
        vlab, alab = "[cv]", "[ca]"
    else:
        vlab, alab = "[mv]", "[ma]"

    # captions and lower thirds (one libass pass)
    keep_for_text = keep
    cues = []
    if transcript and mode in ("burn", "both", "srt"):
        timed = cap.retime(words_of(transcript), keep_for_text)
        cues = cap.group(timed)
        if mode in ("srt", "both"):
            # the video starts with the brand intro (offset seconds), so the sidecar file must start later too
            (out_dir / "long.srt").write_text(cap.to_srt(cap.shift(cues, offset)), encoding="utf-8")
    elif mode in ("burn", "both", "srt"):
        warnings.append("no transcript given, so no captions were made")
    lts = [] if a.no_lower_thirds else lower_third_events(brand, cl, transcript, keep, main_dur)
    burn_cues = cues if mode in ("burn", "both") else []
    if burn_cues or lts:
        ass = build_ass(brand, res, W, H, burn_cues, lts, offset)
        ass_path = out_dir / "overlays.ass"
        ass_path.write_text(ass, encoding="utf-8")
        fonts_dir = res(brand["fonts"]["regular"]).parent
        g.append(f"{vlab}ass='{esc(ass_path)}':fontsdir='{esc(fonts_dir)}'[fv]")
        vlab = "[fv]"

    script = out_dir / "filtergraph.txt"
    script.write_text(";\n".join(g), encoding="utf-8")
    cmd = [*inputs, "-filter_complex_script", str(script), "-map", vlab, "-map", alab,
           "-c:v", "libx264", "-crf", crf, "-preset", preset, "-pix_fmt", "yuv420p", "-r", str(fps),
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out_mp4)]
    code, err = run_ffmpeg(cmd)
    if code != 0:
        return die("ffmpeg failed", detail=err[-1200:], filtergraph=str(script))

    if not a.keep_work:
        import shutil
        shutil.rmtree(work, ignore_errors=True)
        if list_path.exists():
            list_path.unlink()

    if cl.get("chapters"):
        from chapters import fmt
        ch = info.get("chapters_out", [])
        if ch:
            long_video = (main_dur + extra) >= 3600
            (out_dir / "chapters.txt").write_text(
                "\n".join(f"{fmt(0 if n == 0 else c['at_out'] + offset, long_video)} {c['title'].strip()}" for n, c in enumerate(ch)) + "\n", encoding="utf-8")
            if offset:
                warnings.append("chapter times include the intro; the first chapter starts at 00:00 and covers it")

    expected = main_dur + extra
    measured = measured_duration(out_mp4)
    if measured is not None and abs(measured - expected) > 0.5:
        warnings.append(f"measured duration {measured:.2f}s differs from expected {expected:.2f}s")
    print(json.dumps({"ok": True, "video": str(out_mp4), "preview": a.preview, "captions": mode,
                      "pieces": len(pieces), "expected_seconds": round(expected, 3), "measured_seconds": measured,
                      "intro_outro_seconds": extra, "lower_thirds": len(lts), "warnings": warnings}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
