#!/usr/bin/env python3
"""Find transcript words that cannot be trusted: words with no sound behind them, and stretches where Whisper lost the thread
(collapsed word timing, runs of low confidence), which is how its invented phrases show up.

Usage: check_words.py --source source.json --transcript transcript.json [--levels analysis.levels.json]
                      [--below 25] [--drop]

For every word it takes the LOUDEST moment in a window around the word (Whisper's word times can be off by a few
hundred milliseconds, so an average would see partial silence) and compares it with the typical level of the
recording's words (their 70th percentile). A word whose loudest moment is more than --below dB under that typical level has no sound
behind it. Consecutive flagged words are grouped into spans and listed with their times and text.
By default nothing changes. With --drop the flagged words are removed from transcript.json (the original is kept in
transcript.original.json, each removal is logged in transcript.edits.json, transcript.md is rewritten). Run it before
analyse.py, because the dead-air analysis treats transcript words as speech.
Prints JSON; exit 0 on success.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vlib import Levels, hms, load_json, save_json, unreliable_spans  # noqa: E402

PAD = 0.20


def levels_from_audio(source):
    from analyse import audio_windows
    ts, dbs = [], []
    for c in source["clips"]:
        if c.get("has_audio"):
            for t_, d_ in audio_windows(c["path"], 800):
                ts.append(round(c["offset"] + t_, 4))
                dbs.append(round(d_, 1))
    return Levels({"t": ts, "db": dbs, "threshold_db": -45.0}) if ts else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source")
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--levels")
    ap.add_argument("--below", type=float, default=25.0)
    ap.add_argument("--drop", action="store_true")
    a = ap.parse_args()
    try:
        tp = Path(a.transcript)
        t = load_json(tp)
        if a.levels and Path(a.levels).is_file():
            L = Levels.load(a.levels)
        elif a.source:
            L = levels_from_audio(load_json(a.source))
        else:
            L = None
    except (OSError, ValueError, KeyError) as e:
        print(json.dumps({"ok": False, "error": f"cannot read input: {e}"}))
        return 1
    if L is None:
        print(json.dumps({"ok": False, "error": "need --source (or --levels) to measure the audio"}))
        return 1
    words = [(si, wi, w) for si, s in enumerate(t["segments"]) for wi, w in enumerate(s["words"])]
    if not words:
        print(json.dumps({"ok": False, "error": "the transcript has no words"}))
        return 1
    peaks = [max(L.db[L._i(w["start"] - PAD): L._i(w["end"] + PAD) + 1]) for _, _, w in words]
    ref = sorted(peaks)[int(0.7 * (len(peaks) - 1))]  # a high-ish percentile, so a minority of bad words cannot drag it down
    flagged = [(si, wi, w, p) for (si, wi, w), p in zip(words, peaks) if ref - p > a.below]
    spans, cur = [], []
    for item in flagged:
        if cur and item[2]["start"] - cur[-1][2]["end"] > 1.0:
            spans.append(cur)
            cur = []
        cur.append(item)
    if cur:
        spans.append(cur)
    report = [{"at": hms(sp[0][2]["start"]), "start": sp[0][2]["start"], "end": sp[-1][2]["end"],
               "text": " ".join(x[2]["word"] for x in sp), "words": len(sp),
               "loudest_db": round(max(x[3] for x in sp), 1)} for sp in spans]
    flat = [w for _, _, w in words]
    collapsed = [{"at": hms(flat[i]["start"]), "start": flat[i]["start"], "end": flat[j]["end"], "words": j - i + 1,
                  "text": " ".join(x["word"] for x in flat[i:j + 1])[:200]} for i, j in unreliable_spans(flat)]
    dropped = 0
    if a.drop and flagged:
        drop = {(si, wi) for si, wi, _, _ in flagged}
        orig = tp.with_name("transcript.original.json")
        if not orig.exists():
            shutil.copyfile(tp, orig)
        for si, s in enumerate(t["segments"]):
            s["words"] = [w for wi, w in enumerate(s["words"]) if (si, wi) not in drop]
            s["text"] = " ".join(w["word"] for w in s["words"])
        t["segments"] = [s for s in t["segments"] if s["words"]]
        save_json(tp, t)
        edits = tp.with_name("transcript.edits.json")
        prev = load_json(edits) if edits.exists() else []
        save_json(edits, prev + [{"at": r["start"], "from": r["text"], "to": "", "reason": "no sound behind these words"} for r in report])
        from transcribe import to_markdown
        tp.with_name("transcript.md").write_text(to_markdown(t), encoding="utf-8")
        dropped = len(flagged)
    print(json.dumps({"ok": True, "words_checked": len(words), "typical_peak_db": round(ref, 1), "threshold_below_db": a.below,
                      "unvoiced_words": len(flagged), "spans": report, "dropped": dropped,
                      "unreliable_stretches": collapsed,
                      "note": ("words in `spans` have no sound behind them (read them; --drop removes them). " if report else "no words without sound. ") +
                              ("`unreliable_stretches` have collapsed word timing or runs of low confidence: Whisper lost the thread there; "
                               "re-run transcribe.py with --force, which re-transcribes those stretches on their own" if collapsed else "no unreliable stretches")},
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
