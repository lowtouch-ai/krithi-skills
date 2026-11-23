#!/usr/bin/env python3
"""Validate a cut list and show what it does to the timeline.

Usage: validate_cutlist.py CUTLIST.json [--transcript transcript.json] [--summary]

Checks (errors stop a render, warnings are for the user to read):
  - structure: version, source.duration, keep ranges sorted, non-overlapping, inside the media
  - every gap between keep ranges is explained by a cut with a reason (warning if not)
  - no keep boundary falls inside a spoken word (needs --transcript)
  - chapters (if any): first lands at 0:00, at least 3, each at least 10 s long, inside kept video
Prints JSON: ok, errors, warnings, output duration, removed seconds, chapters mapped to output time.
Exit code 0 when ok, 1 otherwise.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vlib import TOL, fmt_clock, hms, kept_before, in_keep, load_json, output_duration, words_of  # noqa: E402

MIN_CHAPTERS = 3
MIN_CHAPTER_SECONDS = 10.0


def validate(cl, transcript=None):
    errors, warnings = [], []
    if cl.get("version") != 1:
        errors.append("version must be 1")
    dur = (cl.get("source") or {}).get("duration")
    if not isinstance(dur, (int, float)) or dur <= 0:
        errors.append("source.duration must be a positive number")
        dur = None
    keep = cl.get("keep")
    if not isinstance(keep, list) or not keep:
        errors.append("keep must be a non-empty list")
        return errors, warnings, {}
    clean = []
    for i, k in enumerate(keep):
        try:
            s, e = float(k["start"]), float(k["end"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"keep[{i}] needs numeric start and end")
            continue
        if e <= s:
            errors.append(f"keep[{i}] ends ({e}) before it starts ({s})")
        if s < 0 or (dur and e > dur + TOL):
            errors.append(f"keep[{i}] ({s}-{e}) is outside the media (0-{dur})")
        clean.append({"start": s, "end": e})
    if errors:
        return errors, warnings, {}
    for a, b in zip(clean, clean[1:]):
        if b["start"] < a["end"] - 1e-9:
            errors.append(f"keep ranges overlap or are out of order around {hms(b['start'])}")
    if errors:
        return errors, warnings, {}

    cuts = cl.get("cuts") or []
    for i, c in enumerate(cuts):
        for f in ("start", "end", "kind", "reason"):
            if f not in c or c[f] in ("", None):
                errors.append(f"cuts[{i}] is missing {f}")
    if errors:
        return errors, warnings, {}

    # every removed span should be explained by a cut
    gaps = []
    prev = 0.0
    for k in clean:
        if k["start"] - prev > TOL:
            gaps.append((prev, k["start"]))
        prev = k["end"]
    if dur and dur - prev > TOL:
        gaps.append((prev, dur))
    for g0, g1 in gaps:
        covered = any(c["start"] - TOL <= g0 and c["end"] + TOL >= g1 for c in cuts)
        if not covered:
            warnings.append(f"{hms(g0)} to {hms(g1)} is removed but no cut explains it")
    for i, c in enumerate(cuts):
        if in_keep(clean, (c["start"] + c["end"]) / 2) and not any(
            abs(c["start"] - g0) <= TOL or abs(c["end"] - g1) <= TOL for g0, g1 in gaps
        ):
            warnings.append(f"cuts[{i}] ({hms(c['start'])} to {hms(c['end'])}) overlaps kept video")

    # no boundary inside a word
    if transcript is not None:
        ws = words_of(transcript)
        for k in clean:
            for edge, name in ((k["start"], "starts"), (k["end"], "ends")):
                for w in ws:
                    if w["start"] + TOL < edge < w["end"] - TOL:
                        errors.append(
                            f"a kept range {name} inside the word '{w['word']}' at {hms(edge)}; move the cut to {hms(w['start'] if name == 'starts' else w['end'])}"
                        )
                        break

    out_dur = output_duration(clean)
    info = {
        "output_seconds": round(out_dur, 3),
        "output_hms": hms(out_dur),
        "removed_seconds": round((dur or 0) - out_dur, 3) if dur else None,
        "pieces": len(clean),
    }

    # chapters
    chapters = cl.get("chapters") or []
    mapped = []
    if chapters:
        prev_out = None
        for i, ch in enumerate(chapters):
            at = float(ch.get("at", -1))
            if at < 0:
                errors.append(f"chapters[{i}] needs a non-negative 'at'")
                continue
            if not ch.get("title"):
                errors.append(f"chapters[{i}] needs a title")
            o = kept_before(clean, at)
            if not in_keep(clean, at):
                warnings.append(f"chapter '{ch.get('title')}' starts in a cut; moved to the next kept moment")
            if prev_out is not None and o < prev_out - 1e-9:
                errors.append(f"chapters[{i}] is out of order")
            prev_out = o
            mapped.append({"at_out": round(o, 3), "time": fmt_clock(o), "title": ch.get("title", "")})
        if mapped:
            if mapped[0]["at_out"] > TOL:
                errors.append("first chapter must be at 00:00 in the output (YouTube requirement)")
            if len(mapped) < MIN_CHAPTERS:
                errors.append(f"YouTube needs at least {MIN_CHAPTERS} chapters, found {len(mapped)}")
            ends = [m["at_out"] for m in mapped[1:]] + [out_dur]
            for m, end in zip(mapped, ends):
                if end - m["at_out"] < MIN_CHAPTER_SECONDS - 1e-9:
                    errors.append(f"chapter '{m['title']}' at {m['time']} is shorter than {int(MIN_CHAPTER_SECONDS)} s")
    info["chapters_out"] = mapped
    return errors, warnings, info


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cutlist")
    ap.add_argument("--transcript")
    a = ap.parse_args()
    try:
        cl = load_json(a.cutlist)
        tr = load_json(a.transcript) if a.transcript else None
    except (OSError, ValueError) as e:
        print(json.dumps({"ok": False, "error": f"cannot read input: {e}"}))
        return 1
    errors, warnings, info = validate(cl, tr)
    print(json.dumps({"ok": not errors, "errors": errors, "warnings": warnings, **info}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
