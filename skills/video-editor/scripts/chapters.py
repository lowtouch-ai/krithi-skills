#!/usr/bin/env python3
"""Write YouTube-ready chapter lines from an approved cut list.

Usage: chapters.py CUTLIST.json [--out chapters.txt]

Maps each chapter's source time through the cuts, then prints/writes lines like `00:00 Intro`
(`h:mm:ss` once the video passes an hour). Refuses if YouTube's rules fail (first at 00:00,
at least 3 chapters, each at least 10 s); run validate_cutlist.py first to see why.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vlib import fmt_clock, load_json  # noqa: E402
from validate_cutlist import validate  # noqa: E402


def fmt(t, long_video):
    return fmt_clock(t, long_video)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cutlist")
    ap.add_argument("--out")
    a = ap.parse_args()
    try:
        cl = load_json(a.cutlist)
    except (OSError, ValueError) as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    errors, _, info = validate(cl)
    if errors or not info.get("chapters_out"):
        print(json.dumps({"ok": False, "error": "; ".join(errors) or "no chapters in the cut list"}))
        return 1
    long_video = info["output_seconds"] >= 3600
    lines = [f"{fmt(c['at_out'], long_video)} {c['title'].strip()}" for c in info["chapters_out"]]
    text = "\n".join(lines) + "\n"
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text, encoding="utf-8")
    print(json.dumps({"ok": True, "chapters": len(lines), "lines": lines, "out": a.out}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
