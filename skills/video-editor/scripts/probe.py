#!/usr/bin/env python3
"""Read the media files for one session and write source.json.

Usage: probe.py FILE [FILE ...] [--out source.json] [--order as-given|name]

Several clips from one session become one timeline: ordered (natural filename order unless
--order as-given), each with an `offset` into the combined timeline. Reports per clip: duration,
video size, frame rate, rotation, whether the frame rate is variable, audio channels and rate.
Warns when clips differ in size or frame rate (they are normalised at render time).
Needs ffprobe. Never modifies the inputs. Prints JSON; exit 0 when every file was readable.
"""
import argparse
import json
import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vlib import save_json  # noqa: E402


def natural_key(p):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", Path(p).name)]


def frac(v):
    try:
        f = Fraction(v)
        return float(f) if f > 0 else 0.0
    except (ValueError, ZeroDivisionError, TypeError):
        return 0.0


def probe(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise ValueError((r.stderr or "ffprobe failed").strip().splitlines()[-1] if r.stderr.strip() else "ffprobe failed")
    d = json.loads(r.stdout)
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), None)
    dur = float(d.get("format", {}).get("duration") or (v or a or {}).get("duration") or 0)
    info = {"path": str(Path(path).resolve()), "duration": round(dur, 3), "has_video": bool(v), "has_audio": bool(a)}
    if v:
        rot = 0
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rot = int(sd["rotation"]) % 360
        rot = int((v.get("tags") or {}).get("rotate", rot)) % 360 if rot == 0 else rot
        w, h = int(v["width"]), int(v["height"])
        if rot in (90, 270):
            w, h = h, w
        avg, rfr = frac(v.get("avg_frame_rate")), frac(v.get("r_frame_rate"))
        info.update({"width": w, "height": h, "fps": round(avg or rfr, 3), "rotation": rot,
                     "variable_frame_rate": bool(avg and rfr and abs(avg - rfr) > 0.5),
                     "video_codec": v.get("codec_name")})
    if a:
        info.update({"audio_channels": int(a.get("channels", 0)), "audio_rate": int(a.get("sample_rate", 0) or 0),
                     "audio_codec": a.get("codec_name")})
    return info


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out")
    ap.add_argument("--order", choices=["as-given", "name"], default="name")
    a = ap.parse_args()

    files = list(a.files) if a.order == "as-given" else sorted(a.files, key=natural_key)
    clips, errors, warnings, offset = [], [], [], 0.0
    for f in files:
        if not Path(f).is_file():
            errors.append({"file": f, "error": "file not found"})
            continue
        try:
            info = probe(f)
        except (ValueError, OSError, subprocess.SubprocessError) as e:
            errors.append({"file": f, "error": str(e)})
            continue
        if not info["has_audio"]:
            warnings.append(f"{Path(f).name} has no audio track; it cannot be transcribed")
        if info.get("variable_frame_rate"):
            warnings.append(f"{Path(f).name} has a variable frame rate; renders are made at a constant rate")
        info["offset"] = round(offset, 3)
        offset += info["duration"]
        clips.append(info)
    sizes = {(c.get("width"), c.get("height")) for c in clips if c["has_video"]}
    rates = {c.get("fps") for c in clips if c["has_video"]}
    if len(sizes) > 1:
        warnings.append("clips differ in size; they will be scaled to the output size")
    if len(rates) > 1:
        warnings.append("clips differ in frame rate; they will be converted to the output rate")
    result = {"ok": not errors and bool(clips), "version": 1, "clips": clips,
              "duration": round(offset, 3), "warnings": warnings, "errors": errors}
    if a.out and result["ok"]:
        save_json(a.out, result)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
