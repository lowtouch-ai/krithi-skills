"""Shared helpers for the video-editor scripts. Python 3.8+, standard library only.

Time is always seconds (float) on the SOURCE timeline unless a name says "out" (final video).
"""
import json
import re
from pathlib import Path

TOL = 0.05  # seconds of slack when comparing boundaries


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)


def hms(t, ms=False):
    """Format seconds as hh:mm:ss (or hh:mm:ss,mmm for SRT when ms=True)."""
    t = max(0.0, float(t))
    total_ms = int(round(t * 1000))
    h, rem = divmod(total_ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}" if ms else f"{h:02d}:{m:02d}:{s:02d}"


def fmt_clock(t, long_video=False):
    """mm:ss (or h:mm:ss for long videos), rounded DOWN to the second, so a chapter never starts after its topic."""
    t = int(max(0.0, float(t)) + 1e-6)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if (long_video or h) else f"{m:02d}:{s:02d}"


def parse_time(v):
    """Accept seconds (number or numeric string), mm:ss or hh:mm:ss."""
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s)
    parts = s.split(":")
    if len(parts) in (2, 3) and all(re.fullmatch(r"\d+(\.\d+)?", p) for p in parts):
        secs = 0.0
        for p in parts:
            secs = secs * 60 + float(p)
        return secs
    raise ValueError(f"cannot read time {v!r}")


def kept_before(keep, t):
    """Output-timeline position for source time t, given sorted non-overlapping keep ranges.

    A time inside a cut maps to the output position where that cut was removed.
    """
    out = 0.0
    for k in keep:
        if t >= k["end"]:
            out += k["end"] - k["start"]
        elif t > k["start"]:
            return out + (t - k["start"])
        else:
            break
    return out


def in_keep(keep, t):
    return any(k["start"] - 1e-9 <= t <= k["end"] + 1e-9 for k in keep)


def output_duration(keep):
    return sum(k["end"] - k["start"] for k in keep)


def words_of(transcript):
    """Flat list of {word,start,end,speaker?} from transcript.json (segments[].words[])."""
    out = []
    for seg in transcript.get("segments", []):
        for w in seg.get("words", []) or []:
            if "start" in w and "end" in w:
                item = {"word": str(w.get("word", "")).strip(), "start": float(w["start"]), "end": float(w["end"])}
                spk = w.get("speaker") or seg.get("speaker")
                if spk:
                    item["speaker"] = spk
                out.append(item)
    return out


def ok(**kw):
    return {"ok": True, **kw}


def fail(error, **kw):
    return {"ok": False, "error": error, **kw}


# ---- copy checks for generated text (titles, captions, chapter titles); see references/copy-style.md ----
BANNED_PHRASES = [
    "unlock", "supercharge", "elevate", "empower", "game-changer", "game changer", "revolutionary", "seamless",
    "robust", "cutting-edge", "dive deep", "deep dive", "delve", "leverage", "harness", "in today's",
    "excited to announce", "not just", "not only", "testament to", "tapestry",
]


def copy_problems(text):
    """Return a list of copy-style problems in a title or caption (empty list = clean)."""
    problems = []
    if "\u2014" in text:
        problems.append("contains an em dash; use a comma, period or parentheses")
    low = text.lower()
    for ph in BANNED_PHRASES:
        if re.search(r"(?<![a-z])" + re.escape(ph), low):
            problems.append(f"uses '{ph}' (banned hype or template phrase)")
    return problems
