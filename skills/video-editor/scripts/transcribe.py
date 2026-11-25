#!/usr/bin/env python3
"""Transcribe a recording to word-level transcript.json (or import one you already have).

Usage:
  transcribe.py --source source.json --out-dir DIR [--model small] [--language auto]
                [--glossary "lowtouch.ai, Krithi"] [--brand brand.json] [--chunk-seconds 30]
  transcribe.py --import FILE --out-dir DIR [--duration SECONDS]

Writes DIR/transcript.json (words with start/end seconds on the combined timeline) and
DIR/transcript.md (readable, with [hh:mm:ss] markers). Runs locally with faster-whisper; audio
never leaves the machine. The model downloads on first use (small is about 0.5 GB).
The audio is transcribed in pieces of about --chunk-seconds (default 30, 0 = one pass), each cut at a pause: Whisper loses
its place in one long pass (it skips speech or squashes it into stretched words) but not in short ones.
Results are cached by audio, model, language and chunk size: running again with the same inputs is instant.

--import accepts Whisper-style JSON (segments[].words[]), a list of {text,startMs,endMs}
(Remotion / HyperFrames captions), or an SRT file. SRT has phrase timing only, so words are spread
evenly inside each cue and granularity is marked "phrase" (cuts then snap to cue edges).

If faster-whisper is not importable here, the script re-runs itself with the skill's virtualenv
(see setup_env.py). Prints JSON; exit 0 on success.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vlib import (apply_corrections, hms, load_json, merge_fragments, missing_speech_spans, save_json,  # noqa: E402
                   snap_to_sound, sound_threshold, unreliable_spans)

VERSION = 3


def reexec_in_venv():
    try:
        import faster_whisper  # noqa: F401
        return
    except ImportError:
        pass
    from setup_env import venv_python
    vpy = venv_python()
    if vpy.exists() and not os.environ.get("VE_REEXEC"):
        os.environ["VE_REEXEC"] = "1"
        os.execv(str(vpy), [str(vpy), __file__, *sys.argv[1:]])


def audio_wav(clip, work):
    Path(work).mkdir(parents=True, exist_ok=True)
    out = Path(work) / (Path(clip["path"]).stem + ".16k.wav")
    if not out.exists():
        print("extracting the audio...", file=sys.stderr, flush=True)
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-i", clip["path"], "-vn", "-ac", "1", "-ar", "16000",
                            "-c:a", "pcm_s16le", str(out)], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("could not extract audio: " + r.stderr[-300:])
    return out


def read_wav(path):
    """16 kHz mono PCM wav -> float32 numpy array (avoids depending on PyAV's decoder)."""
    import wave
    import numpy as np
    with wave.open(str(path), "rb") as w:
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def cache_key(clips, model, language, glossary=(), chunk=0.0):
    h = hashlib.sha256()
    for c in clips:
        p = Path(c["path"])
        h.update(f"{p.name}:{p.stat().st_size}:{c['duration']}".encode())
        with open(p, "rb") as f:
            h.update(f.read(4 << 20))
    h.update(f"|{model}|{language}|{sorted(glossary)}|c{chunk}|v{VERSION}".encode())
    return h.hexdigest()[:16]


def mean_p(words):
    ps = [w["probability"] for w in words if w.get("probability") is not None]
    return sum(ps) / len(ps) if ps else 0.0


def repair_unreliable(model, audio, offset, segments, decode, corrections, notes):
    """Re-transcribe stretches where Whisper lost the thread (collapsed word timing, runs of low confidence).

    The failure depends on the long-file context: the same stretch decoded alone, with a few seconds of context either
    side, usually comes out right. The new words replace the old only when they look healthier; every attempt is noted."""
    flat = [(si, w) for si, s in enumerate(segments) for w in s["words"]]
    spans = unreliable_spans([w for _, w in flat], before=4)
    if not spans:
        return segments
    ranges = []
    for a, b in spans:
        sa, sb = flat[a][0], flat[b][0]
        if ranges and sa <= ranges[-1][1]:
            ranges[-1][1] = max(ranges[-1][1], sb)
        else:
            ranges.append([sa, sb])
    out, cursor = [], 0
    dur = len(audio) / 16000.0
    for sa, sb in ranges:
        out.extend(segments[cursor:sa])
        old = segments[sa:sb + 1]
        # replace everything between the neighbouring good segments, so words the broken stretch swallowed come back
        A = (segments[sa - 1]["end"] - offset) if sa > 0 else 0.0
        B = (segments[sb + 1]["start"] - offset) if sb + 1 < len(segments) else dur
        w0, w1 = max(0.0, A - 2.5), min(dur, B + 2.5)
        new_segs = []
        try:
            for s in decode(audio[int(w0 * 16000): int(w1 * 16000)]):
                words = [{"word": x.word.strip(), "start": round(offset + w0 + x.start, 3), "end": round(offset + w0 + x.end, 3),
                          "probability": round(float(x.probability), 3)} for x in (s.words or []) if x.word.strip()]
                words = merge_fragments(words)
                if corrections:
                    words, _ = apply_corrections(words, corrections)
                words = [w for w in words if A + offset - 0.02 < w["start"] < B + offset]
                if words:
                    new_segs.append({"start": words[0]["start"], "end": words[-1]["end"],
                                     "text": " ".join(w["word"] for w in words), "words": words})
        except Exception as e:  # keep the original if the second decode fails
            notes.append({"at": round(offset + A, 2), "status": "kept", "reason": f"re-transcription failed: {e}"})
            out.extend(old)
            cursor = sb + 1
            continue
        old_words = [w for s in old for w in s["words"]]
        new_words = [w for s in new_segs for w in s["words"]]
        healthier = bool(new_words) and not unreliable_spans(new_words) and mean_p(new_words) >= mean_p(old_words)
        entry = {"at": round(offset + A, 2), "start": round(offset + A, 2), "end": round(offset + B, 2), "old": " ".join(w["word"] for w in old_words)[:200], "new": " ".join(w["word"] for w in new_words)[:200]}
        if healthier:
            notes.append({**entry, "status": "repaired"})
            out.extend(new_segs)
        else:
            notes.append({**entry, "status": "still unreliable"})
            out.extend(old)
        cursor = sb + 1
    out.extend(segments[cursor:])
    return out


def frame_db(audio, step=0.02):
    """Loudness (dB) of every `step` seconds of a 16 kHz mono array, as a plain list."""
    import numpy as np
    n = int(len(audio) / 16000.0 / step)
    if n <= 0:
        return []
    fr = audio[: n * int(16000 * step)].reshape(n, int(16000 * step))
    return (20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9)).tolist()


def fill_missing_speech(audio, offset, segments, decode, corrections, notes, db, step=0.02):
    """Whisper sometimes skips speech when it decodes a long file in one go (seconds of talking with no words). Find
    stretches that are loud but have no words, decode each on its own with a few seconds of context, and add the words
    it hears. The words come back when the stretch is decoded alone, which is the same remedy as for lost timing."""
    flat = [w for s in segments for w in s["words"]]
    if not flat:
        return segments
    thr = sound_threshold(db, step, flat, offset)
    spans = missing_speech_spans(flat, db, step, thr, offset)
    dur = len(audio) / 16000.0
    for g0, g1 in spans:
        w0, w1 = max(0.0, g0 - offset - 3.0), min(dur, g1 - offset + 3.0)
        entry = {"at": round(g0, 2), "start": round(g0, 2), "end": round(g1, 2), "old": "", "new": ""}
        try:
            words = []
            for s in decode(audio[int(w0 * 16000): int(w1 * 16000)]):
                words += [{"word": x.word.strip(), "start": round(offset + w0 + x.start, 3), "end": round(offset + w0 + x.end, 3),
                           "probability": round(float(x.probability), 3)} for x in (s.words or []) if x.word.strip()]
            words = merge_fragments(words)
            if corrections:
                words, _ = apply_corrections(words, corrections)
            words = [w for w in words if g0 < (w["start"] + w["end"]) / 2 < g1]  # only what lies in the hole
        except Exception as e:
            notes.append({**entry, "status": "kept", "reason": f"re-transcription failed: {e}"})
            continue
        if not words:
            notes.append({**entry, "status": "nothing heard"})
            continue
        segments.append({"start": words[0]["start"], "end": words[-1]["end"], "text": " ".join(w["word"] for w in words), "words": words})
        notes.append({**entry, "new": " ".join(w["word"] for w in words)[:200], "status": "filled"})
    segments.sort(key=lambda s: s["start"])
    return segments


def snap_segments(segments, db, offset, step=0.02):
    """Put every word's start and end on the sound (see _vlib.snap_to_sound)."""
    flat = [w for s in segments for w in s["words"]]
    if not flat:
        return segments
    thr = sound_threshold(db, step, flat, offset)
    new, _ = snap_to_sound(flat, db, step, thr, offset)
    it = iter(new)
    for s in segments:
        s["words"] = [next(it) for _ in s["words"]]
        s["start"], s["end"] = s["words"][0]["start"], s["words"][-1]["end"]
    return segments


def split_points(db, step, total, target=30.0, reach=6.0, min_quiet=0.2):
    """Where to cut the audio into pieces of about `target` seconds: in the longest quiet stretch within `reach` seconds of
    each target mark (or the quietest moment when there is none), so a word is never cut in half. Returns the cut times."""
    if not target or total <= target + reach or not db:
        return []
    ref = sorted(db)[int(0.9 * (len(db) - 1))]
    quiet = ref - 20.0
    cuts, t = [], 0.0
    while total - t > target + reach:
        lo, hi = int((t + target - reach) / step), min(len(db) - 1, int((t + target + reach) / step))
        best, run = None, None
        for i in range(lo, hi + 1):
            if db[i] < quiet:
                run = run if run is not None else i
            if (db[i] >= quiet or i == hi) and run is not None:
                end = i if db[i] < quiet else i - 1
                if (end - run + 1) * step >= min_quiet and (best is None or end - run > best[1] - best[0]):
                    best = (run, end)
                run = None
        if best:
            cut = (best[0] + best[1]) / 2.0 * step
        else:
            cut = min(range(lo, hi + 1), key=lambda i: db[i]) * step
        cuts.append(round(cut, 3))
        t = cut
    return cuts


def run_whisper(clips, model_name, language, work, glossary=(), corrections=None, notes=None, chunk=30.0):
    from faster_whisper import WhisperModel
    notes = notes if notes is not None else []
    cpu = os.cpu_count() or 4
    print("loading the speech model...", file=sys.stderr, flush=True)
    try:  # a model that is already on this machine loads without contacting the model hub
        model = WhisperModel(model_name, device="auto", compute_type="auto", cpu_threads=min(cpu, 8), local_files_only=True)
    except Exception:
        print("downloading the speech model (first use only)...", file=sys.stderr, flush=True)
        model = WhisperModel(model_name, device="auto", compute_type="auto", cpu_threads=min(cpu, 8))
    kw = dict(word_timestamps=True, vad_filter=True, vad_parameters={"min_silence_duration_ms": 500},
              condition_on_previous_text=False,
              initial_prompt=("Terms: " + ", ".join(glossary) + ".") if glossary else None,
              hotwords=" ".join(glossary) if glossary else None)
    segments, lang_seen = [], None
    for c in clips:
        audio = read_wav(audio_wav(c, work))
        db = frame_db(audio)
        total = len(audio) / 16000.0
        edges = [0.0] + split_points(db, 0.02, total, chunk) + [total]
        lang_use = None if language == "auto" else language
        last_note, clip_segments = 0.0, []
        for a0, a1 in zip(edges, edges[1:]):
            segs, info = model.transcribe(audio[int(a0 * 16000): int(a1 * 16000)], language=lang_use, **kw)
            lang_seen = lang_seen or info.language
            lang_use = lang_use or info.language  # detect once, on the first piece
            for s in segs:
                if a0 + s.end - last_note >= 60:  # a sign of life on a long file; stdout stays a single JSON object
                    print(f"transcribing... {a0 + s.end:.0f} s of {c['duration']:.0f} s", file=sys.stderr, flush=True)
                    last_note = a0 + s.end
                words = [{"word": w.word.strip(), "start": round(c["offset"] + a0 + w.start, 3), "end": round(c["offset"] + a0 + w.end, 3),
                          "probability": round(float(w.probability), 3)} for w in (s.words or []) if w.word.strip()]
                words = merge_fragments(words)
                if corrections:
                    words, _ = apply_corrections(words, corrections)
                if not words:
                    continue
                clip_segments.append({"start": round(c["offset"] + a0 + s.start, 3), "end": round(c["offset"] + a0 + s.end, 3),
                                      "text": s.text.strip(), "words": words})
        decode = lambda chunk, lg=(None if language == "auto" else language) or info.language: model.transcribe(chunk, language=lg, **kw)[0]
        clip_segments = fill_missing_speech(audio, c["offset"], clip_segments, decode, corrections, notes, db)
        clip_segments = repair_unreliable(model, audio, c["offset"], clip_segments, decode, corrections, notes)
        clip_segments = snap_segments(clip_segments, db, c["offset"])
        segments.extend(clip_segments)
    return segments, lang_seen or language


def parse_srt(text):
    segs = []
    for block in re.split(r"\n\s*\n", text.strip().replace("\r\n", "\n")):
        lines = block.split("\n")
        m = next((re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", l) for l in lines if "-->" in l), None)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        start, end = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000, g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        body = " ".join(l.strip() for l in lines[lines.index(next(l for l in lines if "-->" in l)) + 1:]).strip()
        segs.append((start, end, body))
    return segs


def spread_words(start, end, text):
    toks = text.split()
    if not toks:
        return []
    step = (end - start) / len(toks)
    return [{"word": t, "start": round(start + i * step, 3), "end": round(start + (i + 1) * step, 3)} for i, t in enumerate(toks)]


def import_transcript(path):
    raw = Path(path).read_text(encoding="utf-8-sig")
    granularity = "word"
    if path.lower().endswith(".srt"):
        segments = [{"start": s, "end": e, "text": t, "words": spread_words(s, e, t)} for s, e, t in parse_srt(raw)]
        return segments, "phrase", None
    data = json.loads(raw)
    if isinstance(data, list):  # Remotion / HyperFrames captions
        words = []
        for c in data:
            if "startMs" in c and "endMs" in c:
                words.append({"word": str(c.get("text", "")).strip(), "start": c["startMs"] / 1000, "end": c["endMs"] / 1000})
            elif "start" in c and "end" in c:
                words.append({"word": str(c.get("text", c.get("word", ""))).strip(), "start": float(c["start"]), "end": float(c["end"])})
        words = [w for w in words if w["word"]]
        segments, cur = [], []
        for w in words:
            if cur and (w["start"] - cur[-1]["end"] > 0.8 or re.search(r"[.!?]$", cur[-1]["word"])):
                segments.append(cur)
                cur = []
            cur.append(w)
        if cur:
            segments.append(cur)
        return [{"start": s[0]["start"], "end": s[-1]["end"], "text": " ".join(x["word"] for x in s), "words": s} for s in segments], "word", None
    segs = data.get("segments") if isinstance(data, dict) else None
    if segs is None:
        raise ValueError("unrecognised transcript JSON: expected segments[] or a list of {text,startMs,endMs}")
    out = []
    for s in segs:
        words = [{"word": str(w.get("word", w.get("text", ""))).strip(), "start": float(w["start"]), "end": float(w["end"])}
                 for w in s.get("words", []) or [] if "start" in w and "end" in w]
        words = [w for w in words if w["word"]]
        if not words and s.get("text"):
            words, granularity = spread_words(float(s["start"]), float(s["end"]), s["text"]), "phrase"
        if words:
            out.append({"start": float(s["start"]), "end": float(s["end"]), "text": str(s.get("text", "")).strip(), "words": words})
    return out, granularity, data.get("language") if isinstance(data, dict) else None


def to_markdown(t):
    """One line per sentence with its real start time, and long pauses marked (segments can start long before the speech)."""
    from sentences import split
    words = sorted((w for seg in t["segments"] for w in seg["words"]), key=lambda w: w["start"])
    lines = [f"# Transcript ({t['engine']}, {t['granularity']}-level, language {t.get('language') or 'unknown'})",
             "Lines are sentences with exact start times; use transcript.json for exact word edges.", ""]
    for s_ in split(words, 1.0):
        pause = f" [pause {s_['pause_before']:.0f}s]" if s_["pause_before"] >= 2 else ""
        spk = f" {s_['speaker']}:" if s_.get("speaker") else ""
        lines.append(f"[{hms(s_['start'])}]{pause}{spk} {s_['text']}")
    return "\n".join(lines) + "\n"


def main():
    t_start = time.time()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source")
    ap.add_argument("--import", dest="imp")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--model", default="small")
    ap.add_argument("--language", default="auto")
    ap.add_argument("--chunk-seconds", type=float, default=30.0, help="transcribe in pieces of about this many seconds, cut at pauses (0 = one pass)")
    ap.add_argument("--duration", type=float)
    ap.add_argument("--glossary", default="", help="comma-separated names/terms Whisper often mishears (e.g. 'lowtouch.ai, Krithi')")
    ap.add_argument("--brand", help="brand.json; its glossary list is added to --glossary, and its corrections (known mishearings) are applied")
    ap.add_argument("--force", action="store_true", help="ignore the cache")
    a = ap.parse_args()

    def die(msg, **kw):
        print(json.dumps({"ok": False, "error": msg, **kw}))
        return 1

    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tpath = out_dir / "transcript.json"

    if a.imp:
        try:
            segments, gran, lang = import_transcript(a.imp)
        except (OSError, ValueError, KeyError) as e:
            return die(f"cannot import {a.imp}: {e}")
        if not segments:
            return die("the imported transcript has no timed words")
        dur = a.duration or segments[-1]["end"]
        t = {"version": VERSION, "engine": "imported", "model": None, "language": lang, "granularity": gran,
             "duration": round(dur, 3), "segments": segments, "meta": {"imported_from": Path(a.imp).name}}
    else:
        if not a.source:
            return die("give --source (from probe.py) or --import")
        try:
            src = load_json(a.source)
        except (OSError, ValueError) as e:
            return die(f"cannot read source.json: {e}")
        clips = [c for c in src["clips"] if c.get("has_audio")]
        if not clips:
            return die("no clip has an audio track")
        glossary = [g.strip() for g in a.glossary.split(",") if g.strip()]
        if a.brand:
            try:
                glossary += [g for g in load_json(a.brand).get("glossary", []) if g not in glossary]
            except (OSError, ValueError) as e:
                return die(f"cannot read brand file: {e}")
        corrections = {}
        if a.brand:
            corrections = load_json(a.brand).get("corrections", {}) or {}
        key = cache_key(clips, a.model, a.language, glossary + sorted(f"{k}=>{v}" for k, v in corrections.items()), a.chunk_seconds)
        if tpath.exists() and not a.force:
            try:
                old = load_json(tpath)
                if old.get("meta", {}).get("key") == key:
                    print(json.dumps({"ok": True, "cached": True, "transcript": str(tpath), "segments": len(old["segments"]),
                                      "words": sum(len(s["words"]) for s in old["segments"])}))
                    return 0
            except (OSError, ValueError):
                pass
        reexec_in_venv()
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return die("faster-whisper is not installed", fix="python3 <skill-dir>/scripts/setup_env.py")
        try:
            repair_notes = []
            segments, lang = run_whisper(clips, a.model, a.language, out_dir / "proxy", glossary, corrections, repair_notes, a.chunk_seconds)
        except Exception as e:  # model download, decode, memory
            return die(f"transcription failed: {e}")
        t = {"version": VERSION, "engine": "faster-whisper", "model": a.model, "language": lang, "granularity": "word",
             "duration": src["duration"], "segments": segments, "meta": {"key": key, "repairs": repair_notes}}
    for i, s in enumerate(t["segments"]):
        s["id"] = i
    (out_dir / "proxy").mkdir(exist_ok=True)
    save_json(tpath, t)
    (out_dir / "transcript.md").write_text(to_markdown(t), encoding="utf-8")
    n_words = sum(len(s["words"]) for s in t["segments"])
    rep = t.get("meta", {}).get("repairs", [])
    took = round(time.time() - t_start, 1)
    print(json.dumps({"ok": True, "cached": False, "seconds_taken": took,
                      "seconds_per_audio_second": round(took / max(t["duration"], 1), 2) if took else None,
                      "repaired_stretches": sum(1 for r in rep if r.get("status") == "repaired"),
                      "filled_stretches": sum(1 for r in rep if r.get("status") == "filled"),
                      "sound_without_words": [{"at": r["at"], "seconds": round(r["end"] - r["start"], 1)} for r in rep if r.get("status") == "nothing heard"],
                      "still_unreliable": [{"at": r["at"], "heard": r["old"][:80]} for r in rep if r.get("status") not in ("repaired", "filled", "nothing heard")], "transcript": str(tpath), "readable": str(out_dir / "transcript.md"),
                      "engine": t["engine"], "granularity": t["granularity"], "language": t["language"],
                      "segments": len(t["segments"]), "words": n_words}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
