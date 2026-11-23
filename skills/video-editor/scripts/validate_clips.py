#!/usr/bin/env python3
"""Resolve and check a proposed clip list (short-form moments).

Usage: validate_clips.py CLIPS.json --sentences sentences.json [--analysis analysis.json]
                         [--out clips.resolved.json]

CLIPS.json (written by the agent), one entry per proposed clip:
  {"id": 1, "from": 120, "to": 134, "title": "...", "caption": "...", "reason": "...",
   "hook": "the first words, verbatim", "score": 84, "trim_pauses": true}
`from` and `to` are sentence ids from sentences.json, so a clip always starts and ends on a whole
sentence. This script turns them into start and end times (a small lead-in and tail, never reaching
into the neighbouring sentence), works out the length after dead-air pauses inside the clip are
removed (needs --analysis), and checks:
  errors    length outside 20-120 s, hook not matching the opening words, overlapping clips, missing
            title/reason/caption, a title over 60 characters, more than 2 hashtags, copy-style problems
  warnings  length outside 30-90 s, opens mid-thought ("so", "and", "this"...) or points back to
            earlier context ("like I said"), a filler word in the first words
Writes the resolved list (with start, end, seconds, effective_seconds, text) to --out.
Prints JSON; exit 0 when there are no errors.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vlib import copy_problems, hms, load_json, save_json  # noqa: E402

LEAD, TAIL = 0.15, 0.35
HARD_MIN, HARD_MAX, SOFT_MIN, SOFT_MAX = 20.0, 120.0, 30.0, 90.0
WEAK_OPENERS = {"so", "and", "but", "because", "also", "then", "which", "that", "this", "it", "they", "he", "she",
                "those", "these", "anyway", "yeah", "okay", "ok", "well", "um", "uh", "right", "like"}
BACK_REFS = ("like i said", "as i said", "as i mentioned", "like i mentioned", "earlier we", "as we saw", "going back to")


def norm(s):
    return re.sub(r"[^a-z0-9' ]+", "", s.lower().replace("-", " ")).split()


def pause_seconds(analysis, start, end):
    """Seconds of removable dead air inside [start, end] (candidates not marked keep_suggested)."""
    total = 0.0
    for c in (analysis or {}).get("candidates", []):
        if c.get("keep_suggested") or c.get("kind") in ("lead_in", "tail_out"):
            continue
        c0, c1 = c["cut"]
        total += max(0.0, min(end, c1) - max(start, c0))
    return total


def check(clips, sents, analysis):
    errors, warnings, out = [], [], []
    by_id = {s["id"]: s for s in sents}
    for i, c in enumerate(clips):
        tag = f"clip {c.get('id', i + 1)}"
        try:
            a, b = int(c["from"]), int(c["to"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"{tag}: needs integer 'from' and 'to' sentence ids")
            continue
        if a not in by_id or b not in by_id or b < a:
            errors.append(f"{tag}: sentence range {a}-{b} is not valid")
            continue
        first, last = by_id[a], by_id[b]
        prev_end = by_id[a - 1]["end"] if a - 1 in by_id else 0.0
        next_start = by_id[b + 1]["start"] if b + 1 in by_id else last["end"] + TAIL
        start = max(first["start"] - LEAD, (prev_end + first["start"]) / 2 if prev_end else 0.0)
        end = min(last["end"] + TAIL, (last["end"] + next_start) / 2 if b + 1 in by_id else last["end"] + TAIL)
        raw = end - start
        trimmed = pause_seconds(analysis, start, end) if c.get("trim_pauses", True) else 0.0
        eff = raw - trimmed
        text = " ".join(by_id[k]["text"] for k in range(a, b + 1) if k in by_id)

        if eff < HARD_MIN or eff > HARD_MAX:
            errors.append(f"{tag}: {eff:.0f}s is outside {HARD_MIN:.0f}-{HARD_MAX:.0f}s")
        elif eff < SOFT_MIN or eff > SOFT_MAX:
            warnings.append(f"{tag}: {eff:.0f}s is outside the usual {SOFT_MIN:.0f}-{SOFT_MAX:.0f}s")
        words = norm(text)
        hook = norm(c.get("hook", ""))
        if not hook:
            errors.append(f"{tag}: 'hook' (the opening words, verbatim) is required")
        elif words[: len(hook)] != hook:
            errors.append(f"{tag}: hook does not match the opening words, which are: \"{' '.join(text.split()[:len(hook) + 3])}\"")
        if words and words[0] in WEAK_OPENERS:
            warnings.append(f"{tag}: opens with '{words[0]}', which sounds mid-thought; start a sentence later or confirm it stands alone")
        low = text.lower()
        for ph in BACK_REFS:
            if ph in low:
                warnings.append(f"{tag}: refers back to earlier context ('{ph}'); may not stand alone")
                break
        for f in ("title", "caption", "reason"):
            if not str(c.get(f, "")).strip():
                errors.append(f"{tag}: '{f}' is required")
        if len(str(c.get("title", ""))) > 60:
            errors.append(f"{tag}: title is over 60 characters")
        if len(re.findall(r"#\w+", str(c.get("caption", "")))) > 2:
            errors.append(f"{tag}: caption has more than 2 hashtags")
        for f in ("title", "caption"):
            for p in copy_problems(str(c.get(f, ""))):
                errors.append(f"{tag}: {f} {p}")
        out.append({**c, "start": round(start, 3), "end": round(end, 3), "seconds": round(raw, 1),
                    "effective_seconds": round(eff, 1), "at": hms(start), "text": text})
    ordered = sorted(out, key=lambda x: x["start"])
    for x, y in zip(ordered, ordered[1:]):
        if y["start"] < x["end"]:
            errors.append(f"clips {x.get('id')} and {y.get('id')} overlap ({hms(y['start'])} to {hms(x['end'])})")
    return errors, warnings, out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clips")
    ap.add_argument("--sentences", required=True)
    ap.add_argument("--analysis")
    ap.add_argument("--out")
    a = ap.parse_args()
    try:
        data = load_json(a.clips)
        clips = data["clips"] if isinstance(data, dict) else data
        sents = load_json(a.sentences)["sentences"]
        analysis = load_json(a.analysis) if a.analysis else None
    except (OSError, ValueError, KeyError) as e:
        print(json.dumps({"ok": False, "error": f"cannot read input: {e}"}))
        return 1
    errors, warnings, resolved = check(clips, sents, analysis)
    if a.out and not errors:
        save_json(a.out, {"version": 1, "clips": resolved})
    print(json.dumps({"ok": not errors, "errors": errors, "warnings": warnings, "clips": len(resolved),
                      "resolved": resolved if not errors else [], "out": a.out if not errors else None}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
