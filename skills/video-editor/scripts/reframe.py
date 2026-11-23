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


def crop_box(sw, sh, cx, cy, punch=1.0):
    """9:16 crop (x, y, w, h), even integers, inside a sw x sh frame, centred on a face at (cx, cy)."""
    ch = sh / punch
    cw = ch * 9 / 16
    if cw > sw:
        cw = float(sw)
        ch = cw * 16 / 9
    x = min(max(cx - cw / 2, 0), sw - cw)
    y = min(max(cy - ch * 0.42, 0), sh - ch)
    ev = lambda v: int(v) // 2 * 2
    return ev(x), ev(y), ev(cw), ev(ch)


def detect(video, ranges, punch_in=1.0):
    import cv2
    path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
    cascade = cv2.CascadeClassifier(path)
    if cascade.empty():
        raise RuntimeError("OpenCV's face model is missing; install opencv-python-headless 4.x (setup_env.py)")
    cap = cv2.VideoCapture(str(video))
    sw, sh = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    plan, prev_cx, prev_cy = [], None, None
    for i, (ls, le) in enumerate(ranges):
        faces, n, t = [], 0, ls + 0.05
        points = []
        while t < le:
            points.append(t)
            t += 1.0 / SAMPLE_FPS
        if not points:
            points = [(ls + le) / 2]
        for t in points:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            n += 1
            if not ok:
                continue
            scale = 640.0 / frame.shape[1]
            gray = cv2.cvtColor(cv2.resize(frame, (640, int(frame.shape[0] * scale))), cv2.COLOR_BGR2GRAY)
            found = cascade.detectMultiScale(gray, 1.1, 5, minSize=(40, 40))
            if len(found):
                x, y, w, h = max(found, key=lambda f: f[2] * f[3])
                faces.append(((x + w / 2) / scale, (y + h / 2) / scale))
        flag = None
        if faces:
            cx = statistics.median(f[0] for f in faces)
            cy = statistics.median(f[1] for f in faces)
            punch = punch_in if (punch_in > 1 and i % 2 == 1) else 1.0
            _, _, cw, _ = crop_box(sw, sh, cx, cy, punch)
            if prev_cx is not None and abs(cx - prev_cx) < DEAD_ZONE * cw:
                cx, cy = prev_cx, prev_cy
        else:
            flag = "no face found; kept the previous framing" if prev_cx is not None else "no face found; centred"
            cx, cy = (prev_cx, prev_cy) if prev_cx is not None else (sw / 2, sh * 0.42)
            punch = punch_in if (punch_in > 1 and i % 2 == 1) else 1.0
        prev_cx, prev_cy = cx, cy
        x, y, w, h = crop_box(sw, sh, cx, cy, punch)
        plan.append({"range": [round(ls, 3), round(le, 3)], "crop": {"x": x, "y": y, "w": w, "h": h},
                     "faces_found": len(faces), "samples": n, "flag": flag})
    cap.release()
    return {"source_size": [sw, sh], "pieces": plan}


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
