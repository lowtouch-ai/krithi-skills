#!/usr/bin/env python3
"""Build captions that match the FINAL video (after cuts) from the transcript.

Usage:
  captions.py TRANSCRIPT.json --cutlist CUTLIST.json --out long.srt
  captions.py TRANSCRIPT.json --range START END --out clip.srt [--max-words 3]   (a short clip)

Words outside the kept ranges are dropped; the rest are re-timed to the output timeline.
Cue rules: at most 2 lines of 42 characters, at most 6 s, a break at sentence ends and at pauses
over 0.8 s. With --max-words, cues are short and word-sized for vertical video.
Prints JSON with the cue count; writes SRT.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vlib import hms, kept_before, in_keep, load_json, words_of  # noqa: E402

MAX_CHARS = 42
MAX_LINES = 2
MAX_CUE_SECONDS = 6.0
PAUSE_BREAK = 0.8
SENTENCE_END = re.compile(r"[.!?]['\")\]]*$")


def retime(words, keep, offset=0.0):
    """Keep words whose midpoint is in a kept range and map them to output time."""
    out = []
    for w in words:
        mid = (w["start"] + w["end"]) / 2
        if not in_keep(keep, mid):
            continue
        s = kept_before(keep, max(w["start"], _range_start(keep, mid)))
        e = kept_before(keep, min(w["end"], _range_end(keep, mid)))
        if e <= s:
            e = s + 0.05
        out.append({**w, "start": s - offset, "end": e - offset})
    return out


def _range_start(keep, t):
    for k in keep:
        if k["start"] - 1e-9 <= t <= k["end"] + 1e-9:
            return k["start"]
    return t


def _range_end(keep, t):
    for k in keep:
        if k["start"] - 1e-9 <= t <= k["end"] + 1e-9:
            return k["end"]
    return t


def group(words, max_words=None):
    cues, cur = [], []

    def flush():
        if cur:
            cues.append(list(cur))
            cur.clear()

    for i, w in enumerate(words):
        if cur:
            gap = w["start"] - cur[-1]["end"]
            text_len = len(" ".join(x["word"] for x in cur + [w]))
            too_long = (max_words and len(cur) >= max_words) or (
                not max_words and (text_len > MAX_CHARS * MAX_LINES or w["end"] - cur[0]["start"] > MAX_CUE_SECONDS)
            )
            if gap > PAUSE_BREAK or too_long:
                flush()
        cur.append(w)
        if SENTENCE_END.search(w["word"]):
            flush()
    flush()
    return cues


def wrap(text):
    if len(text) <= MAX_CHARS:
        return text
    words = text.split()
    best, best_diff = None, None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        diff = abs(len(a) - len(b))
        if best_diff is None or diff < best_diff:
            best, best_diff = (a, b), diff
    return "\n".join(best) if best else text


def to_srt(cues, wrap_lines=True):
    lines = []
    for n, c in enumerate(cues, 1):
        text = " ".join(w["word"] for w in c).strip()
        text = wrap(text) if wrap_lines else text
        start, end = c[0]["start"], c[-1]["end"]
        lines.append(f"{n}\n{hms(start, ms=True)} --> {hms(end, ms=True)}\n{text}\n")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript")
    ap.add_argument("--cutlist")
    ap.add_argument("--range", nargs=2, type=float, metavar=("START", "END"))
    ap.add_argument("--max-words", type=int)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if bool(a.cutlist) == bool(a.range):
        print(json.dumps({"ok": False, "error": "give exactly one of --cutlist or --range"}))
        return 1
    try:
        words = words_of(load_json(a.transcript))
        if a.cutlist:
            keep = load_json(a.cutlist)["keep"]
            offset = 0.0
        else:
            keep = [{"start": a.range[0], "end": a.range[1]}]
            offset = 0.0
        timed = retime(words, keep, offset)
        cues = group(timed, a.max_words)
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(to_srt(cues, wrap_lines=not a.max_words), encoding="utf-8")
    except (OSError, ValueError, KeyError) as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    print(json.dumps({"ok": True, "cues": len(cues), "out": str(a.out)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
