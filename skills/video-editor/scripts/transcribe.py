#!/usr/bin/env python3
"""Transcribe a recording to word-level transcript.json (or import one you already have).

Usage:
  transcribe.py --source source.json --out-dir DIR [--model small] [--language auto]
                [--glossary "lowtouch.ai, Krithi"] [--brand brand.json]
  transcribe.py --import FILE --out-dir DIR [--duration SECONDS]

Writes DIR/transcript.json (words with start/end seconds on the combined timeline) and
DIR/transcript.md (readable, with [hh:mm:ss] markers). Runs locally with faster-whisper; audio
never leaves the machine. The model downloads on first use (small is about 0.5 GB).
Results are cached by audio, model and language: running again with the same inputs is instant.

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
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _vlib import hms, load_json, save_json  # noqa: E402

VERSION = 1


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


def cache_key(clips, model, language, glossary=()):
    h = hashlib.sha256()
    for c in clips:
        p = Path(c["path"])
        h.update(f"{p.name}:{p.stat().st_size}:{c['duration']}".encode())
        with open(p, "rb") as f:
            h.update(f.read(4 << 20))
    h.update(f"|{model}|{language}|{sorted(glossary)}|v{VERSION}".encode())
    return h.hexdigest()[:16]


def run_whisper(clips, model_name, language, work, glossary=()):
    from faster_whisper import WhisperModel
    cpu = os.cpu_count() or 4
    model = WhisperModel(model_name, device="auto", compute_type="auto", cpu_threads=min(cpu, 8))
    segments, lang_seen = [], None
    for c in clips:
        wav = audio_wav(c, work)
        segs, info = model.transcribe(read_wav(wav), language=None if language == "auto" else language,
                                      word_timestamps=True, vad_filter=True,
                                      vad_parameters={"min_silence_duration_ms": 500},
                                      condition_on_previous_text=False,
                                      initial_prompt=("Terms: " + ", ".join(glossary) + ".") if glossary else None,
                                      hotwords=" ".join(glossary) if glossary else None)
        lang_seen = lang_seen or info.language
        for s in segs:
            words = [{"word": w.word.strip(), "start": round(c["offset"] + w.start, 3), "end": round(c["offset"] + w.end, 3),
                      "probability": round(float(w.probability), 3)} for w in (s.words or []) if w.word.strip()]
            if not words:
                continue
            segments.append({"start": round(c["offset"] + s.start, 3), "end": round(c["offset"] + s.end, 3),
                             "text": s.text.strip(), "words": words})
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
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source")
    ap.add_argument("--import", dest="imp")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--model", default="small")
    ap.add_argument("--language", default="auto")
    ap.add_argument("--duration", type=float)
    ap.add_argument("--glossary", default="", help="comma-separated names/terms Whisper often mishears (e.g. 'lowtouch.ai, Krithi')")
    ap.add_argument("--brand", help="brand.json; its glossary list is added to --glossary")
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
        key = cache_key(clips, a.model, a.language, glossary)
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
            segments, lang = run_whisper(clips, a.model, a.language, out_dir / "proxy", glossary)
        except Exception as e:  # model download, decode, memory
            return die(f"transcription failed: {e}")
        t = {"version": VERSION, "engine": "faster-whisper", "model": a.model, "language": lang, "granularity": "word",
             "duration": src["duration"], "segments": segments, "meta": {"key": key}}
    for i, s in enumerate(t["segments"]):
        s["id"] = i
    (out_dir / "proxy").mkdir(exist_ok=True)
    save_json(tpath, t)
    (out_dir / "transcript.md").write_text(to_markdown(t), encoding="utf-8")
    n_words = sum(len(s["words"]) for s in t["segments"])
    print(json.dumps({"ok": True, "cached": False, "transcript": str(tpath), "readable": str(out_dir / "transcript.md"),
                      "engine": t["engine"], "granularity": t["granularity"], "language": t["language"],
                      "segments": len(t["segments"]), "words": n_words}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
