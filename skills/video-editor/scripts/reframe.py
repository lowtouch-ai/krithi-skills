#!/usr/bin/env python3
"""Choose a 9:16 crop for each piece of a clip so the speaker stays in frame. Needs OpenCV (the virtualenv).

Usage: reframe.py VIDEO --ranges 12.0-18.5,19.2-30 [--punch-in 1.0]

For each time range (seconds in VIDEO) it samples frames twice a second, finds faces with OpenCV's
bundled detector, takes the median position of the largest face, and returns a crop box. The crop is
fixed inside a piece and only changes between pieces (at a cut, where a change is invisible), so the
picture never pans. A small dead zone keeps the framing identical from piece to piece unless the
speaker has really moved. If no face is found in a piece, the previous framing (or the centre) is
used and the piece is flagged. --punch-in 1.15 alternates a tighter crop on every second piece.
Prints JSON. Detection is simple: a good fit for one speaker facing the camera; several speakers or
a side-by-side layout need a person to check the result.
"""
import argparse
import json
import os
import statistics
import sys
from pathlib import Path

SAMPLE_FPS = 2.0
DEAD_ZONE = 0.06  # fraction of crop width


def crop_box(sw, sh, cx, cy, punch=1.0, aspect=9 / 16, face_at=0.42):
    """Crop (x, y, w, h) of width:height = `aspect` (9:16 by default), even integers, inside a sw x sh frame, with the
    face at (cx, cy) placed `face_at` of the way down the crop."""
    ch = sh / punch
    cw = ch * aspect
    if cw > sw:
        cw = float(sw)
        ch = cw / aspect
    x = min(max(cx - cw / 2, 0), sw - cw)
    y = min(max(cy - ch * face_at, 0), sh - ch)
    ev = lambda v: int(v) // 2 * 2
    return ev(x), ev(y), ev(cw), ev(ch)


def upright_size(w, h, rotation):
    """The size of a picture after its rotation flag is applied: a phone video stored 1920x1440 with a 90 or 270 degree
    flag plays as 1440x1920."""
    return (h, w) if int(rotation) % 180 == 90 else (w, h)


def open_upright(video):
    """Open `video` with OpenCV so that frames come out the way ffmpeg (and every player) shows them, with the rotation flag
    applied. OpenCV reads a phone video sideways unless asked, which put the face detection and the crop in the wrong
    coordinates. Returns (capture, read) where read(t_seconds) gives an upright frame or None, and the upright (width, height)."""
    import cv2
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
    meta = int(round(cap.get(cv2.CAP_PROP_ORIENTATION_META) or 0)) % 360
    # newer OpenCV rotates by itself once asked; older versions ignore the request, so the frame is turned here
    manual = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}.get(meta)
    raw_w, raw_h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    def read(t):
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            return None
        if manual is not None and (frame.shape[1], frame.shape[0]) == (raw_w, raw_h) and cap.get(cv2.CAP_PROP_ORIENTATION_AUTO) != 1.0:
            frame = cv2.rotate(frame, manual)
        return frame
    first = read(0.0)
    size = (first.shape[1], first.shape[0]) if first is not None else upright_size(raw_w, raw_h, meta)
    return cap, read, size


def fit_zoom(face_heights, sh, face_frac, max_zoom=1.6, fallback=1.0):
    """The zoom that makes the speaker's face `face_frac` of the crop's height, from the faces found (their heights in source
    pixels). One zoom serves the whole clip, so a cut between pieces never jumps in size. It is never below 1 (a crop cannot be
    taller than the picture) and never above `max_zoom` (more would look soft). With no faces, `fallback`."""
    if not face_heights or not face_frac:
        return fallback
    fh = statistics.median(face_heights)
    return max(1.0, min(max_zoom, sh * face_frac / max(fh, 1.0)))


def detect(video, ranges, punch_in=1.0, aspect=9 / 16, zoom=1.0, face_at=0.42, face_frac=None, max_zoom=1.6):
    """Crop plan per range. `aspect` is the crop shape (the explainer style uses a nearly square one). The zoom tightens every
    crop: fixed at `zoom`, or, when `face_frac` is given, chosen so the face takes that share of the crop's height (`fit_zoom`).
    `punch_in` alternates a tighter crop on every second piece."""
    import cv2
    path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
    cascade = cv2.CascadeClassifier(path)
    if cascade.empty():
        raise RuntimeError("OpenCV's face model is missing; install opencv-python-headless 4.x (setup_env.py)")
    cap, read_frame, (sw, sh) = open_upright(video)
    sampled = []  # per range: (faces as (cx, cy, face height) in source pixels, samples taken)
    for i, (ls, le) in enumerate(ranges):
        faces, n, t = [], 0, ls + 0.05
        points = []
        while t < le:
            points.append(t)
            t += 1.0 / SAMPLE_FPS
        if not points:
            points = [(ls + le) / 2]
        for t in points:
            frame = read_frame(t)
            n += 1
            if frame is None:
                continue
            scale = 640.0 / frame.shape[1]
            gray = cv2.cvtColor(cv2.resize(frame, (640, int(frame.shape[0] * scale))), cv2.COLOR_BGR2GRAY)
            found = cascade.detectMultiScale(gray, 1.1, 5, minSize=(40, 40))
            if len(found):
                x, y, w, h = max(found, key=lambda f: f[2] * f[3])
                faces.append(((x + w / 2) / scale, (y + h / 2) / scale, h / scale))
        sampled.append((faces, n))
    cap.release()
    base = fit_zoom([f[2] for fs, _ in sampled for f in fs], sh, face_frac, max_zoom, zoom)
    plan, prev_cx, prev_cy = [], None, None
    for i, ((ls, le), (faces, n)) in enumerate(zip(ranges, sampled)):
        flag = None
        punch = base * (punch_in if (punch_in > 1 and i % 2 == 1) else 1.0)
        if faces:
            cx = statistics.median(f[0] for f in faces)
            cy = statistics.median(f[1] for f in faces)
            _, _, cw, _ = crop_box(sw, sh, cx, cy, punch, aspect, face_at)
            if prev_cx is not None and abs(cx - prev_cx) < DEAD_ZONE * cw:
                cx, cy = prev_cx, prev_cy
        else:
            flag = "no face found; kept the previous framing" if prev_cx is not None else "no face found; centred"
            cx, cy = (prev_cx, prev_cy) if prev_cx is not None else (sw / 2, sh * 0.42)
        prev_cx, prev_cy = cx, cy
        x, y, w, h = crop_box(sw, sh, cx, cy, punch, aspect, face_at)
        plan.append({"range": [round(ls, 3), round(le, 3)], "crop": {"x": x, "y": y, "w": w, "h": h},
                     "faces_found": len(faces), "samples": n, "flag": flag})
    return {"source_size": [sw, sh], "zoom": round(base, 3), "pieces": plan}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--ranges", required=True, help="comma-separated START-END seconds")
    ap.add_argument("--punch-in", type=float, default=1.0)
    a = ap.parse_args()
    try:
        ranges = [tuple(float(x) for x in r.split("-")) for r in a.ranges.split(",") if r.strip()]
        print(json.dumps({"ok": True, **detect(a.video, ranges, a.punch_in)}, indent=2))
        return 0
    except (ValueError, RuntimeError, ImportError) as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
