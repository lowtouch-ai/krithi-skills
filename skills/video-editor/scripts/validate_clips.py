#!/usr/bin/env python3
"""Resolve and check a proposed clip list (short-form moments).

Usage: validate_clips.py CLIPS.json --sentences sentences.json [--analysis analysis.json]
                         [--transcript transcript.json] [--out clips.resolved.json]

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
With the levels file written by analyse.py (found next to --analysis), each clip's start and end are moved to where the
sound has really stopped, so a word is never cut off. Writes the resolved list (with start, end, seconds, effective_seconds, text) to --out.
Prints JSON; exit 0 when there are no errors.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vlib import Levels, clip_keep, copy_problems, hms, kept_before, load_json, save_json, words_of  # noqa: E402

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


CARD_LEAD, CARD_HOLD = 0.0, 2.4  # a card appears exactly when its first term is spoken
MAX_ITEMS, MAX_ITEMS_CHAIN, MAX_LABEL_WORDS, MAX_LABEL_CHARS, MAX_ITEM_CHARS = 5, 4, 7, 36, 26  # a card with arrows between its steps is taller, so it holds one fewer


def find_phrase(words, phrase, after=None):
    """(start, end) of the first spoken `phrase` at or after time `after`, or None. Returns the earliest earlier match
    as a second value when the phrase is only found before `after`.

    Words are compared as letters only, so "sub-agents", "sub agents" and "subagents" are the same phrase, and a
    hyphenated transcript word counts as one word."""
    want = "".join(norm(phrase))
    if not want:
        return None, None
    flat = ["".join(norm(w["word"])) for w in words]
    earlier = None
    for i in range(len(words)):
        acc = ""
        for j in range(i, min(len(words), i + len(phrase.split()) + 3)):
            acc += flat[j]
            if acc == want:
                hit = (words[i]["start"], words[j]["end"])
                if after is None or hit[0] >= after - 1e-6:
                    return hit, None
                earlier = earlier or hit
                break
            if not want.startswith(acc):
                break
    return None, earlier


def resolve_cards(clip, tag, cw, text, start, end, errors, warnings, keep=None, levels=None):
    """Check a clip's keyword cards and give every item the time its words are spoken (source seconds)."""
    out, cards = [], clip.get("cards") or []
    clip_start = start
    text_low = text.lower()
    for ci, card in enumerate(cards, 1):
        ctag = f"{tag} card {ci}"
        label = str(card.get("label", "")).strip()
        items = card.get("items") or []
        if not label or len(label.split()) > MAX_LABEL_WORDS or len(label) > MAX_LABEL_CHARS:
            errors.append(f"{ctag}: label must be 1 to {MAX_LABEL_WORDS} words and at most {MAX_LABEL_CHARS} characters")
        limit = MAX_ITEMS_CHAIN if card.get("chain") else MAX_ITEMS
        if not items or len(items) > limit:
            errors.append(f"{ctag}: needs 1 to {limit} items" + (f" ({MAX_ITEMS_CHAIN} when the items are linked by arrows)" if limit == MAX_ITEMS_CHAIN else "")
                          + "; for a longer list use two cards, or merge two items (for example \"Quality and compliance checks\")")
            continue
        for f, v in (("label", label), *((f"item {k}", it.get("text", "")) for k, it in enumerate(items, 1))):
            for p in copy_problems(str(v)):
                errors.append(f"{ctag}: {f} {p}")
            for num in re.findall(r"\d+", str(v)):
                if num not in text_low:
                    errors.append(f"{ctag}: {f} contains the number {num}, which is not in the clip")
        res_items, last_t = [], None
        for k, it in enumerate(items, 1):
            t, say = str(it.get("text", "")).strip(), str(it.get("say", "")).strip()
            if not t or len(t) > MAX_ITEM_CHARS:
                errors.append(f"{ctag} item {k}: text must be 1 to {MAX_ITEM_CHARS} characters")
                continue
            if not say:
                errors.append(f"{ctag} item {k} ('{t}'): 'say' (the words spoken) is required")
                continue
            hit, earlier = find_phrase(cw, say, last_t)
            if hit is None:
                if earlier is not None:
                    errors.append(f"{ctag} item {k} ('{t}'): the words \"{say}\" are only spoken earlier ({earlier[0] - clip_start:.1f} s into the clip), "
                                  f"before the previous item; items must be in the order they are spoken, so use words said after it")
                else:
                    errors.append(f"{ctag} item {k} ('{t}'): the words \"{say}\" are not spoken in this clip")
                continue
            last_t = hit[0]
            at = hit[0]
            if levels is not None:  # land on the sound, not on Whisper's estimate, when the word follows a pause
                on = levels.onset_near(at)
                if on is not None:
                    at = on
            res_items.append({"text": t, "say": say, "at": round(at, 3)})
        if not res_items:
            continue
        lab_core = " ".join(norm(label))
        for it in res_items:
            pill_core = " ".join(norm(it["text"]))
            if lab_core and pill_core and (lab_core == pill_core or lab_core in pill_core or pill_core in lab_core):
                warnings.append(f"{ctag}: the label \"{label}\" repeats the pill \"{it['text']}\"; make the label a heading that adds context "
                                f"(for example \"The first week\" over \"Set up laptop\") and keep the pill as the term")
                break
        out.append({"label": label.upper(), "chain": bool(card.get("chain")), "items": res_items,
                    "start": round(max(start, res_items[0]["at"] - CARD_LEAD), 3),
                    "end": round(min(end - 0.3, res_items[-1]["at"] + CARD_HOLD), 3)})
    out.sort(key=lambda c: c["start"])
    if keep:  # where each card and pill lands in the finished clip, after dead-air pauses are removed
        for c in out:
            c["clip_start"], c["clip_end"] = round(kept_before(keep, c["start"]), 2), round(kept_before(keep, c["end"]), 2)
            for it in c["items"]:
                it["clip_at"] = round(kept_before(keep, it["at"]), 2)
    for x, y in zip(out, out[1:]):
        if y["start"] - x["start"] < 3.0 and y["start"] >= x["items"][-1]["at"] + 0.8:
            warnings.append(f"{tag}: the card '{x['label']}' is replaced by '{y['label']}' only {y['start'] - x['start']:.1f} s after it appears, "
                            f"so it is on screen for under 3 s; merge them into one card or drop one")
        if y["start"] < x["items"][-1]["at"] + 0.8:
            errors.append(f"{tag}: cards '{x['label']}' and '{y['label']}' are too close together (the first needs about a second after its last item)")
        elif y["start"] < x["end"]:
            x["end"] = round(y["start"] - 0.25, 3)
    if out and out[0]["start"] - start < 3.0:
        warnings.append(f"{tag}: the first card starts inside the title overlay (first 3 seconds); move its words later or drop it")
    if len(out) > 1 and (end - start) / len(out) < 8.0:
        warnings.append(f"{tag}: {len(out)} cards in {end - start:.0f} s is crowded; about one every 10 to 15 seconds reads better")
    return out


def check(clips, sents, analysis, levels=None, tx_words=None, unreliable=(), limits=None):
    hard_min, hard_max, soft_min, soft_max = limits or (HARD_MIN, HARD_MAX, SOFT_MIN, SOFT_MAX)
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
        edge_notes = []
        if levels is not None:
            # Whisper's word times can end early or start late: move each edge to where the sound has really stopped.
            if levels.loud(end):
                lim = (next_start - 0.03) if b + 1 in by_id else last["end"] + 1.0
                q = levels.next_quiet(end, min(lim, end + 1.0))
                if q is not None:
                    end = min(q + 0.12, lim)
                else:
                    edge_notes.append("sound is still going at the clip's end; check the last word by eye")
            if levels.loud(start):
                lim = (prev_end + 0.03) if a - 1 in by_id else 0.0
                q = levels.prev_quiet(start, max(lim, start - 1.0))
                if q is not None:
                    start = max(q - 0.10, lim, 0.0)
                else:
                    edge_notes.append("sound is already going at the clip's start; check the first word by eye")
        raw = end - start
        trimmed = pause_seconds(analysis, start, end) if c.get("trim_pauses", True) else 0.0
        eff = raw - trimmed
        text = " ".join(by_id[k]["text"] for k in range(a, b + 1) if k in by_id)

        if eff < hard_min or eff > hard_max:
            errors.append(f"{tag}: {eff:.0f}s is outside {hard_min:.0f}-{hard_max:.0f}s")
        elif eff < soft_min or eff > soft_max:
            warnings.append(f"{tag}: {eff:.0f}s is outside the usual {soft_min:.0f}-{soft_max:.0f}s")
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
        for note in edge_notes:
            warnings.append(f"{tag}: {note}")
        for u in unreliable:
            if u["start"] < end and u["end"] > start:
                warnings.append(f"{tag}: Whisper could not transcribe {hms(u['start'])} to {hms(u['end'])} reliably "
                                f"(it heard \"{u['old'][:60]}...\"); the captions there may be wrong, so listen to it or pick another stretch")
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
        cards = []
        if c.get("cards"):
            if tx_words is None:
                errors.append(f"{tag}: cards need the transcript; pass --transcript")
            else:
                cw = [w for w in tx_words if start - 0.05 <= w["start"] <= end + 0.05]
                cards = resolve_cards(c, tag, cw, text, start, end, errors, warnings, clip_keep({**c, "start": start, "end": end}, analysis), levels)
        out.append({**c, "cards": cards, "start": round(start, 3), "end": round(end, 3), "seconds": round(raw, 1),
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
    ap.add_argument("--levels", help="fine audio levels from analyse.py (default: next to --analysis)")
    ap.add_argument("--transcript", help="transcript.json; required for keyword cards (their pills are timed to the spoken words)")
    ap.add_argument("--out")
    ap.add_argument("--style", choices=["reel", "explainer"], default="reel", help="explainer clips may run longer (see shorts.explainer.length in brand.json)")
    ap.add_argument("--brand", help="brand.json, for the explainer length limits (default: the bundled one)")
    a = ap.parse_args()
    try:
        data = load_json(a.clips)
        clips = data["clips"] if isinstance(data, dict) else data
        sents = load_json(a.sentences)["sentences"]
        analysis = load_json(a.analysis) if a.analysis else None
        lv_path = a.levels or (str(Path(a.analysis).with_suffix("")) + ".levels.json" if a.analysis else None)
        levels = Levels.load(lv_path) if lv_path and Path(lv_path).is_file() else None
        tdata = load_json(a.transcript) if a.transcript else None
        words = words_of(tdata) if tdata else None
        unreliable = [r for r in (tdata or {}).get("meta", {}).get("repairs", []) if r.get("status") not in ("repaired", "filled", "nothing heard") and "start" in r]
    except (OSError, ValueError, KeyError) as e:
        print(json.dumps({"ok": False, "error": f"cannot read input: {e}"}))
        return 1
    limits = None
    if a.style == "explainer":
        import explainer
        from render_long import DEFAULT_BRAND, load_brand
        ln = explainer.settings(load_brand(a.brand or DEFAULT_BRAND)[0])["length"]
        limits = (float(ln["hard_min"]), float(ln["hard_max"]), float(ln["soft_min"]), float(ln["soft_max"]))
    errors, warnings, resolved = check(clips, sents, analysis, levels, words, unreliable, limits)
    if a.out and not errors:
        save_json(a.out, {"version": 1, "clips": resolved})
    print(json.dumps({"ok": not errors, "errors": errors, "warnings": warnings, "clips": len(resolved), "edges_snapped_to_audio": levels is not None,
                      "resolved": resolved if not errors else [], "out": a.out if not errors else None}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
