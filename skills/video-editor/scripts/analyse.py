#!/usr/bin/env python3
"""Find dead air: gaps with no speech, and whether anything is happening on screen during them.

Usage: analyse.py SOURCE.json [--transcript transcript.json] [--out analysis.json]
                  [--min-gap 0.7] [--pad 0.15] [--dead-stretch 20] [--noise-db -35]
                  [--motion auto]

SOURCE.json comes from probe.py (several clips form one timeline). Gaps in speech come from the
transcript's word times when given (robust against background noise); otherwise from ffmpeg
silencedetect. For every gap of at least --min-gap seconds it reports:
  kind          "pause" (shorter than --dead-stretch) or "dead_stretch"
  cut           the span to remove, shrunk by --pad on each side so speech is never clipped
  picture_active  true when the picture changed noticeably during the gap (slide change, layout
                  switch, demo): a silent demo is not dead air, so those are marked keep_suggested
                  for the agent to confirm. "Noticeably" means above --motion; the default "auto"
                  is the larger of 0.08 and 1.2 x the recording's own 99th-percentile score, so the
                  small movements of a talking head never count.
With a transcript it also measures the audio in each gap against the recording's own speech level: a gap
that is audibly not silent (speech the transcript missed, or another person talking) is marked
speech_suspected and keep_suggested.
Also reports lead_in (before the first word) and tail_out (after the last word).
These are CANDIDATES. The agent reviews each one and the user approves the cut list.
Prints JSON; writes it to --out when given.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vlib import hms, load_json, save_json, words_of  # noqa: E402


def silences(path, noise_db, min_d):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn",
                        "-af", f"silencedetect=n={noise_db}dB:d={min_d}", "-f", "null", "-"],
                       capture_output=True, text=True)
    out, start = [], None
    for line in r.stderr.splitlines():
        m = re.search(r"silence_start: (-?[\d.]+)", line)
        if m:
            start = max(0.0, float(m.group(1)))
        m = re.search(r"silence_end: ([\d.]+)", line)
        if m and start is not None:
            out.append((start, float(m.group(1))))
            start = None
    return out


def motion_scores(path, fps=2):
    """Per-sample picture-change scores [(time, score)], from a small, low-rate copy of the video."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-an",
                        "-vf", f"fps={fps},scale=320:-2,select='gte(scene,0)',metadata=print:file=-",
                        "-f", "null", "-"], capture_output=True, text=True)
    pts, out = None, []
    for line in r.stdout.splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            pts = float(m.group(1))
        m = re.search(r"lavfi\.scene_score=([\d.]+)", line)
        if m and pts is not None:
            out.append((pts, float(m.group(1))))
    return out


def audio_windows(path, n=4000):
    """Loudness of the audio in windows of n samples at 16 kHz (4000 = 0.25 s): [(time, dB)]. Silence is -120."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn", "-ac", "1", "-ar", "16000", "-af",
                        f"asetnsamples=n={n}:p=0,astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
                        "-f", "null", "-"], capture_output=True, text=True)
    t, out = None, []
    for line in r.stdout.splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            t = float(m.group(1))
        m = re.search(r"RMS_level=(-?[\d.]+|-inf)", line)
        if m and t is not None:
            out.append((t, -120.0 if m.group(1) == "-inf" else float(m.group(1))))
    return out


def gaps_from_words(words, total):
    ws = sorted(words, key=lambda w: w["start"])
    gaps = [(ws[i]["end"], ws[i + 1]["start"]) for i in range(len(ws) - 1) if ws[i + 1]["start"] > ws[i]["end"]]
    return gaps, (0.0, ws[0]["start"]) if ws else None, (ws[-1]["end"], total) if ws else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--transcript")
    ap.add_argument("--out")
    ap.add_argument("--min-gap", type=float, default=0.7)
    ap.add_argument("--pad", type=float, default=0.15)
    ap.add_argument("--dead-stretch", type=float, default=20.0)
    ap.add_argument("--noise-db", type=float, default=-35.0)
    ap.add_argument("--loud-fraction", type=float, default=0.40,
                    help="share of a gap that must be as loud as speech (15 dB below the speech level) to count as 'not silent'")
    ap.add_argument("--motion", default="auto", help="picture-change score that counts as activity, or 'auto'")
    a = ap.parse_args()
    try:
        src = load_json(a.source)
        clips = src["clips"]
        total = float(src["duration"])
    except (OSError, ValueError, KeyError) as e:
        print(json.dumps({"ok": False, "error": f"cannot read source.json: {e}"}))
        return 1

    # 1. gaps in speech, on the combined timeline
    basis, lead, tail = "silencedetect", None, None
    if a.transcript:
        try:
            ws = words_of(load_json(a.transcript))
        except (OSError, ValueError) as e:
            print(json.dumps({"ok": False, "error": f"cannot read transcript: {e}"}))
            return 1
        if ws:
            gaps, lead, tail = gaps_from_words(ws, total)
            basis = "transcript"
    if basis == "silencedetect":
        gaps = []
        for c in clips:
            if c.get("has_audio"):
                gaps += [(c["offset"] + s, c["offset"] + e) for s, e in silences(c["path"], a.noise_db, a.min_gap)]
            else:
                gaps.append((c["offset"], c["offset"] + c["duration"]))
        gaps.sort()
        if gaps and gaps[0][0] <= 0.05:
            lead, gaps = gaps[0], gaps[1:]
        if gaps and total - gaps[-1][1] <= 0.15:
            tail, gaps = gaps[-1], gaps[:-1]

    # 2. is the picture changing?
    motion = []
    for c in clips:
        if c.get("has_video"):
            motion += [(c["offset"] + t, s) for t, s in motion_scores(c["path"])]

    if a.motion == "auto":
        vals = sorted(s for _, s in motion)
        motion_thr = max(0.08, 1.2 * vals[int(0.99 * (len(vals) - 1))]) if vals else 0.08
    else:
        motion_thr = float(a.motion)

    # 2b. is the gap really silent? (catches speech the transcript missed, or another person talking)
    # Measured against this recording's own speech level, so it adapts to the microphone.
    levels, speech_ref = [], None
    if basis == "transcript":
        for c in clips:
            if c.get("has_audio"):
                levels += [(c["offset"] + t, db) for t, db in audio_windows(c["path"])]
        spans = sorted((w["start"], w["end"]) for w in ws)
        starts = [x[0] for x in spans]
        import bisect

        def in_word(t):
            i = bisect.bisect_right(starts, t) - 1
            return i >= 0 and spans[i][0] <= t <= spans[i][1]

        sp = sorted(db for t, db in levels if in_word(t))
        speech_ref = sp[len(sp) // 2] if len(sp) >= 40 and sp[len(sp) // 2] > -60 else None

    def gap_audio(g0, g1):
        """(median dB, fraction of loud windows, 80th percentile dB) for a gap, or None."""
        vs = sorted(db for t, db in levels if g0 + 0.1 <= t <= g1 - 0.1)
        if len(vs) < 2 or speech_ref is None:
            return None
        loud = sum(v > speech_ref - 15 for v in vs) / len(vs)
        return vs[len(vs) // 2], loud, vs[int(0.8 * (len(vs) - 1))]

    # 2c. fine levels (50 ms): put every cut on REAL silence. Whisper's word times can end early or start late,
    # so a cut placed at "the end of the word plus a margin" can clip the end of a word.
    fine, fine_data = None, None
    if basis == "transcript" and speech_ref is not None:
        ts, dbs = [], []
        for c in clips:
            if c.get("has_audio"):
                for t_, d_ in audio_windows(c["path"], 800):
                    ts.append(round(c["offset"] + t_, 4))
                    dbs.append(round(d_, 1))
        diffs = [y - x for x, y in zip(ts, ts[1:])]
        step = sorted(diffs)[len(diffs) // 2] if diffs else 0.02
        even = bool(diffs) and max(abs(d_ - step) for d_ in diffs) < 0.004
        fine_data = {"threshold_db": round(speech_ref - 15, 1), "speech_db": round(speech_ref, 1), "db": dbs}
        fine_data.update({"t0": ts[0], "step": round(step, 6)} if even else {"t": ts})
        from _vlib import Levels
        fine = Levels(fine_data)

    def active(g0, g1):
        return any(g0 <= t <= g1 and s >= motion_thr for t, s in motion)

    cands = []
    skipped = [0]

    def add(g0, g1, kind):
        if g1 - g0 < a.min_gap:
            return
        c0, c1 = (g0, g1 - a.pad) if kind == "lead_in" else (g0 + a.pad, g1) if kind == "tail_out" else (g0 + a.pad, g1 - a.pad)
        if fine is not None:
            run = fine.longest_quiet_run(g0, g1)
            if run is None:
                skipped[0] += 1  # no unbroken quiet stretch: nothing safe to cut
                return
            q0, q1 = run
            c0 = max(g0 if kind == "lead_in" else g0 + a.pad, q0 + (0 if kind == "lead_in" else a.pad))
            c1 = min(g1 if kind == "tail_out" else g1 - a.pad, q1 - (0 if kind == "tail_out" else a.pad))
        if c1 - c0 < 0.1:
            return
        act = active(g0, g1)
        au = gap_audio(g0, g1)
        db = au[0] if au else None
        sus = bool(au) and au[1] >= a.loud_fraction and au[2] >= speech_ref - 4
        note = ("audio in this gap is not silent (%.0f%% of it is as loud as speech); the transcript may have missed speech, or someone else is talking. Keep it unless you are sure." % (au[1] * 100)) if sus else (
            "picture changes during this gap (slide or demo?); likely worth keeping" if act else "")
        cands.append({
            "kind": kind, "gap": [round(g0, 3), round(g1, 3)], "gap_seconds": round(g1 - g0, 3),
            "cut": [round(c0, 3), round(c1, 3)], "cut_seconds": round(c1 - c0, 3),
            "at": hms(g0), "picture_active": act, "speech_suspected": sus,
            "gap_median_db": None if db is None else round(db, 1),
            "gap_loud_fraction": None if au is None else round(au[1], 2), "keep_suggested": act or sus, "note": note,
        })

    if lead:
        add(lead[0], lead[1], "lead_in")
    for g0, g1 in gaps:
        add(g0, g1, "dead_stretch" if g1 - g0 >= a.dead_stretch else "pause")
    if tail:
        add(tail[0], tail[1], "tail_out")

    removable = [c for c in cands if not c["keep_suggested"]]
    result = {
        "ok": True, "version": 1, "basis": basis, "duration": round(total, 3),
        "settings": {"min_gap": a.min_gap, "pad": a.pad, "dead_stretch": a.dead_stretch, "motion": round(motion_thr, 4),
                     "speech_level_db": None if speech_ref is None else round(speech_ref, 1), "loud_fraction": a.loud_fraction},
        "candidates": cands,
        "summary": {
            "candidates": len(cands),
            "pauses": sum(c["kind"] == "pause" for c in cands),
            "dead_stretches": sum(c["kind"] == "dead_stretch" for c in cands),
            "keep_suggested": sum(c["keep_suggested"] for c in cands),
            "speech_suspected": sum(c["speech_suspected"] for c in cands),
            "skipped_sound_throughout": skipped[0],
            "removable_seconds": round(sum(c["cut_seconds"] for c in removable), 3),
        },
    }
    if a.out:
        save_json(a.out, result)
        if fine_data:
            save_json(str(Path(a.out).with_suffix("")) + ".levels.json", fine_data)
            result["levels_file"] = str(Path(a.out).with_suffix("")) + ".levels.json"
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
