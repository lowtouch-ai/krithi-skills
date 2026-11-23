#!/usr/bin/env python3
"""Split a transcript into numbered sentences, so clips can be proposed by sentence, not by guessed time.

Usage: sentences.py TRANSCRIPT.json --out sentences.json [--md sentences.md] [--gap 1.0]

A sentence ends at . ! ? (even inside a quote), at a pause longer than --gap seconds, or when the
speaker changes. Writes sentences.json (id, start, end, text, speaker, word counts) and a readable
sentences.md: `S12 [00:01:02] (8.4s) text`, with the pause before a sentence shown when it is long.
Prints JSON with the counts. Read-only on the transcript.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vlib import hms, load_json, save_json, words_of  # noqa: E402

END = re.compile(r"[.!?]['\")\]]*$")


def split(words, gap):
    sents, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if (END.search(w["word"]) or nxt is None or nxt["start"] - w["end"] > gap
                or (nxt.get("speaker") != w.get("speaker"))):
            sents.append(cur)
            cur = []
    out = []
    for n, s in enumerate(sents):
        prev_end = out[-1]["end"] if out else 0.0
        out.append({
            "id": n, "start": round(s[0]["start"], 3), "end": round(s[-1]["end"], 3),
            "text": " ".join(w["word"] for w in s).strip(), "words": len(s),
            "speaker": s[0].get("speaker"), "pause_before": round(max(0.0, s[0]["start"] - prev_end), 2),
        })
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript")
    ap.add_argument("--out", required=True)
    ap.add_argument("--md")
    ap.add_argument("--gap", type=float, default=1.0)
    a = ap.parse_args()
    try:
        t = load_json(a.transcript)
        words = sorted(words_of(t), key=lambda w: w["start"])
    except (OSError, ValueError) as e:
        print(json.dumps({"ok": False, "error": f"cannot read transcript: {e}"}))
        return 1
    if not words:
        print(json.dumps({"ok": False, "error": "the transcript has no timed words"}))
        return 1
    sents = split(words, a.gap)
    save_json(a.out, {"version": 1, "gap": a.gap, "sentences": sents})
    md = a.md or str(Path(a.out).with_suffix(".md"))
    lines = ["# Sentences (clip proposals refer to these ids)", ""]
    for s in sents:
        pause = f" [pause {s['pause_before']:.0f}s]" if s["pause_before"] >= 2 else ""
        spk = f" {s['speaker']}:" if s.get("speaker") else ""
        lines.append(f"S{s['id']} [{hms(s['start'])}] ({s['end'] - s['start']:.1f}s){pause}{spk} {s['text']}")
    Path(md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "sentences": len(sents), "sentences_json": a.out, "readable": md}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
