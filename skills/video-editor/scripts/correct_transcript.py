#!/usr/bin/env python3
"""Fix mistakes in a transcript, keeping the original and a log of every change.

Usage:
  correct_transcript.py TRANSCRIPT.json --suspects [--from S --to E] [--below 0.5]   list low-confidence words to review
  correct_transcript.py TRANSCRIPT.json --replace "some are most=some or most" [--replace ...] [--brand brand.json]

--replace takes "wrong words=right words" (whole words, any case, punctuation at the ends is kept; times stay with
the words). --brand also applies the brand's `corrections` list. The first change saves transcript.original.json
beside the transcript; every change is appended to transcript.edits.json; transcript.md is rewritten. After fixing
words inside clips, re-run sentences.py and validate_clips.py (a clip's `hook` must match the new opening words).
Prints JSON; exit 0 on success.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vlib import _core, apply_corrections, hms, load_json, merge_fragments, save_json  # noqa: E402

STOP = set("the and for are was were with that this have has had from they them their there then than what when where which while would could should about into over also just like very more most some such only other these those your you our out can will not but its it's i'm don't isn't".split())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript")
    ap.add_argument("--suspects", action="store_true")
    ap.add_argument("--from", dest="t0", type=float, default=0.0)
    ap.add_argument("--to", dest="t1", type=float, default=1e12)
    ap.add_argument("--below", type=float, default=0.5)
    ap.add_argument("--limit", type=int, default=40, help="show at most this many suspects, lowest confidence first")
    ap.add_argument("--replace", action="append", default=[])
    ap.add_argument("--brand")
    a = ap.parse_args()
    tp = Path(a.transcript)
    try:
        t = load_json(tp)
    except (OSError, ValueError) as e:
        print(json.dumps({"ok": False, "error": f"cannot read transcript: {e}"}))
        return 1
    if a.suspects:
        out = []
        for seg in t["segments"]:
            for w in seg["words"]:
                p = w.get("probability")
                core = _core(w["word"])
                if p is None or p >= a.below or not (a.t0 <= w["start"] <= a.t1):
                    continue
                if core in STOP or len(core) < 4:  # function words are often low-confidence and rarely the real mistake
                    continue
                out.append({"at": hms(w["start"]), "seconds": w["start"], "word": w["word"], "confidence": p})
        out.sort(key=lambda x: x["confidence"])
        shown = out[:a.limit]
        print(json.dumps({"ok": True, "suspects": sorted(shown, key=lambda x: x["seconds"]), "total_found": len(out),
                          "note": "content words Whisper was unsure of, lowest confidence first. This is only a hint: reading the clip's words is the real check "
                                  "(a confident mishearing like 'lease privilege' will not appear here)"}, indent=2))
        return 0
    corr = {}
    for r in a.replace:
        if "=" not in r:
            print(json.dumps({"ok": False, "error": f"--replace needs 'wrong=right', got {r!r}"}))
            return 1
        k, v = r.split("=", 1)
        corr[k.strip()] = v.strip()
    if a.brand:
        try:
            corr = {**(load_json(a.brand).get("corrections", {}) or {}), **corr}
        except (OSError, ValueError) as e:
            print(json.dumps({"ok": False, "error": f"cannot read brand file: {e}"}))
            return 1
    if not corr:
        print(json.dumps({"ok": False, "error": "nothing to do: give --replace or --brand"}))
        return 1
    log = []
    for seg in t["segments"]:
        seg["words"], lg = apply_corrections(merge_fragments(seg["words"]), corr)
        if lg:
            seg["text"] = " ".join(w["word"] for w in seg["words"])
        log += lg
    if log:
        orig = tp.with_name("transcript.original.json")
        if not orig.exists():
            shutil.copyfile(tp, orig)
        save_json(tp, t)
        edits = tp.with_name("transcript.edits.json")
        prev = load_json(edits) if edits.exists() else []
        save_json(edits, prev + log)
        from transcribe import to_markdown
        tp.with_name("transcript.md").write_text(to_markdown(t), encoding="utf-8")
    print(json.dumps({"ok": True, "changes": len(log), "log": log,
                      "next": "re-run sentences.py and validate_clips.py" if log else "no matches found"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
