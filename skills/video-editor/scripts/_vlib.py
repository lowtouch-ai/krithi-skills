"""Shared helpers for the video-editor scripts. Python 3.8+, standard library only.

Time is always seconds (float) on the SOURCE timeline unless a name says "out" (final video).
"""
import json
import re
import signal
from pathlib import Path

TOL = 0.05  # seconds of slack when comparing boundaries

try:  # piping a script into head or less should end quietly, not print a BrokenPipeError
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
except (AttributeError, ValueError, OSError):
    pass


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


def merge_fragments(words):
    """Join tokens that Whisper split from the word before them: '-based', '.ai', "'s". Keeps times consistent."""
    out = []
    for w in words:
        t = w["word"]
        glue = bool(out) and (t.startswith("-") and len(t) > 1 and t[1].isalpha()
                              or t.startswith(".") and len(t) > 1 and t[1].isalpha()
                              or t.startswith("'") and len(t) > 1)
        if glue and w["start"] - out[-1]["end"] < 0.5:
            out[-1] = {**out[-1], "word": out[-1]["word"] + t, "end": w["end"]}
        else:
            out.append(dict(w))
    return out


class Levels:
    """Fine-grained audio levels saved next to analysis.json, used to put cuts on real silence.

    Windows carry their real times (ffmpeg's window length is not a round number): either `t0` and `step`
    for evenly spaced windows, or an explicit `t` list.
    """

    def __init__(self, data):
        self.db = data["db"]
        self.thr = float(data["threshold_db"])  # below this a window counts as quiet
        if "t" in data:
            self.t = data["t"]
            diffs = sorted(b - a for a, b in zip(self.t, self.t[1:])) or [0.02]
            self.step = diffs[len(diffs) // 2]
        else:
            self.step = float(data["step"])
            self.t = None
            self.t0 = float(data.get("t0", 0.0))
        self.need = max(3, int(0.1 / self.step + 0.999))  # windows that make up a 100 ms quiet run

    @classmethod
    def load(cls, path):
        try:
            return cls(load_json(path))
        except (OSError, ValueError, KeyError):
            return None

    def _time(self, i):
        return self.t[i] if self.t is not None else self.t0 + i * self.step

    def _i(self, t):
        if self.t is not None:
            import bisect
            i = bisect.bisect_right(self.t, t) - 1
        else:
            i = int((t - self.t0) / self.step)
        return min(max(i, 0), len(self.db) - 1)

    def loud(self, t):
        return self.db[self._i(t)] >= self.thr

    def quiet_run(self, i):
        n = self.need
        return i >= 0 and i + n <= len(self.db) and all(v < self.thr for v in self.db[i:i + n])

    def next_quiet(self, t, limit):
        """Start time of the first 100 ms run of quiet windows at or after t (and before limit), or None."""
        i, end = self._i(t), self._i(limit)
        while i <= end:
            if self.quiet_run(i):
                return self._time(i)
            i += 1
        return None

    def prev_quiet(self, t, limit):
        """End time of the last 100 ms run of quiet windows ending at or before t (and after limit), or None."""
        i, lo = self._i(t), self._i(limit)
        while i >= lo:
            if self.quiet_run(i - self.need + 1):
                return self._time(i) + self.step
            i -= 1
        return None

    def longest_quiet_run(self, g0, g1, min_len=0.2):
        """(start, end) of the longest unbroken quiet stretch inside [g0, g1], or None. A loud burst in the middle
        of a gap (a missed word, a breath) splits it, and only the longest quiet part is returned."""
        i, end = self._i(g0), self._i(g1)
        best, run_start = None, None
        for j in range(i, end + 1):
            q = self.db[j] < self.thr
            if q and run_start is None:
                run_start = j
            if (not q or j == end) and run_start is not None:
                last = j if q else j - 1
                a_, b_ = self._time(run_start), self._time(last) + self.step
                if b_ - a_ >= min_len and (best is None or b_ - a_ > best[1] - best[0]):
                    best = (a_, b_)
                run_start = None
        return best


def _core(word):
    """Lower-case word without punctuation at its ends, for matching."""
    return re.sub(r"^[^\w]+|[^\w]+$", "", word.lower())


def apply_corrections(words, corrections):
    """Replace known mishearings in a word list: {"chat bots": "chatbots", "lotage": "lowtouch"}.

    Matches whole words (any case, ignoring punctuation at the ends), longest phrase first. Punctuation around the matched
    words is kept. Times stay with the words; when the replacement has a different number of words they are spread
    evenly over the original span. Returns (new_words, log) where log lists every change.
    """
    pats = sorted(((p.lower().split(), r.split()) for p, r in corrections.items() if p.strip()), key=lambda x: -len(x[0]))
    out, log, i = [], [], 0
    while i < len(words):
        hit = None
        for ptoks, rtoks in pats:
            n = len(ptoks)
            if i + n <= len(words) and [_core(w["word"]) for w in words[i:i + n]] == [_core(t) for t in ptoks]:
                hit = (n, rtoks)
                break
        if not hit:
            out.append(dict(words[i]))
            i += 1
            continue
        n, rtoks = hit
        span = words[i:i + n]
        lead = re.match(r"^[^\w]*", span[0]["word"]).group(0)
        trail = re.search(r"[^\w]*$", span[-1]["word"]).group(0)
        new = []
        for k, t in enumerate(rtoks):
            if len(rtoks) == n:
                base = span[k]
            else:
                a, b = span[0]["start"], span[-1]["end"]
                step = (b - a) / len(rtoks)
                base = {**span[0], "start": round(a + k * step, 3), "end": round(a + (k + 1) * step, 3)}
            new.append({**base, "word": (lead if k == 0 else "") + t + (trail if k == len(rtoks) - 1 else "")})
        log.append({"at": round(span[0]["start"], 2), "from": " ".join(w["word"] for w in span), "to": " ".join(w["word"] for w in new)})
        out.extend(new)
        i += n
    return out, log


def clip_keep(clip, analysis):
    """Kept ranges of a clip: its span minus the dead-air pauses inside it (source seconds)."""
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


def unreliable_spans(words, min_run=3, tiny=0.05, low_p=0.4, low_run=6, before=1, after=1):
    """Index ranges (first, last) of words whose timing or confidence says Whisper lost the thread.

    1. A run of at least `min_run` words with almost no duration (start close to end): the timing collapsed, which is
       how Whisper's invented phrases show up (17 words squeezed into one instant).
    2. A run of at least `low_run` words that are all low confidence (probability under `low_p`).
    Each range is widened by `before` words and `after` words (timing errors usually start a few words before the
    collapse, so a repair widens further back). Returns merged, sorted ranges.
    """
    n, found = len(words), []
    i = 0
    while i < n:
        j = i
        while j < n and words[j]["end"] - words[j]["start"] < tiny:
            j += 1
        if j - i >= min_run:
            found.append((i, j - 1))
        i = max(j, i + 1)
    i = 0
    while i < n:
        j = i
        while j < n and words[j].get("probability") is not None and words[j]["probability"] < low_p:
            j += 1
        if j - i >= low_run:
            found.append((i, j - 1))
        i = max(j, i + 1)
    found.sort()
    merged = []
    for a, b in found:
        a, b = max(0, a - before), min(n - 1, b + after)
        if merged and a <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged

