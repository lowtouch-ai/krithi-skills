#!/usr/bin/env python3
"""Check that this machine can run the video-editor skill, and say exactly what to fix.

Usage: check_env.py [--need long|shorts|all]   (default: all)

Reports ffmpeg/ffprobe, the libass `subtitles` filter (burned-in captions) and libx264/aac encoders,
a transcriber (faster-whisper, whisper.cpp or the openai-whisper CLI), face tracking (OpenCV) for
9:16 reframing, the bundled brand fonts, and a hardware hint. Read-only; installs nothing.
Prints JSON; exit 0 when everything needed for --need is present, 1 otherwise.
"""
import argparse
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from setup_env import venv_python  # noqa: E402


def run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def has_module(name):
    """True if importable in this interpreter or in the skill's virtualenv."""
    try:
        if importlib.util.find_spec(name) is not None:
            return True
    except (ImportError, ValueError):
        pass
    vpy = venv_python()
    if vpy.exists():
        code, _ = run([str(vpy), "-c", f"import {name}"])
        return code == 0
    return False


def install_hint(what):
    system = platform.system()
    if what == "ffmpeg":
        if system == "Darwin":
            return "brew install ffmpeg-full   (the plain 'ffmpeg' formula lacks libass, so captions fail)"
        if system == "Windows":
            return "winget install Gyan.FFmpeg   (the full build, not Essentials)"
        return "sudo apt install ffmpeg   (or your distro's package)"
    if what == "faster-whisper":
        return "python3 <skill-dir>/scripts/setup_env.py   (creates a virtualenv outside the repo; the model downloads on first use)"
    if what == "opencv":
        return "python3 <skill-dir>/scripts/setup_env.py   (installs OpenCV into the same virtualenv)"
    return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--need", choices=["long", "shorts", "all"], default="all")
    a = ap.parse_args()

    checks = []

    def add(name, ok, detail="", fix="", required=True):
        checks.append({"name": name, "ok": bool(ok), "detail": detail, "fix": "" if ok else fix, "required": required})

    add("python>=3.8", sys.version_info >= (3, 8), platform.python_version(), "install Python 3.8 or newer")

    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    add("ffmpeg", ffmpeg, ffmpeg or "not found on PATH", install_hint("ffmpeg"))
    add("ffprobe", ffprobe, ffprobe or "not found on PATH", install_hint("ffmpeg"))
    if ffmpeg:
        _, ver = run([ffmpeg, "-version"])
        _, filters = run([ffmpeg, "-hide_banner", "-filters"])
        _, encoders = run([ffmpeg, "-hide_banner", "-encoders"])
        add("ffmpeg version", True, ver.splitlines()[0] if ver else "unknown")
        add("libass (subtitles filter)", " subtitles " in filters,
            "burned-in captions", "this ffmpeg build lacks libass. " + install_hint("ffmpeg"))
        add("libx264", "libx264" in encoders, "H.264 video", "this ffmpeg build lacks libx264. " + install_hint("ffmpeg"))
        add("aac", " aac " in encoders, "AAC audio", "this ffmpeg build lacks aac. " + install_hint("ffmpeg"))

    transcriber = None
    if has_module("faster_whisper"):
        transcriber = "faster-whisper"
    elif shutil.which("whisper-cli") or shutil.which("whisper-cpp"):
        transcriber = "whisper.cpp"
    elif shutil.which("whisper"):
        transcriber = "openai-whisper CLI"
    add("transcriber", transcriber, transcriber or "none found", install_hint("faster-whisper"))

    cv = has_module("cv2")
    add("OpenCV (face tracking)", cv, "9:16 reframing" if cv else "needed for 9:16 reframing",
        install_hint("opencv"), required=a.need in ("shorts", "all"))

    fonts = SKILL_DIR / "assets" / "brand" / "fonts"
    missing = [f for f in ("Poppins-Regular.ttf", "Poppins-Bold.ttf") if not (fonts / f).is_file()]
    add("brand fonts", not missing, str(fonts), "bundled fonts missing: " + ", ".join(missing))

    hw = {"cpus": os.cpu_count(), "gpu": bool(shutil.which("nvidia-smi")), "os": platform.system()}
    for c in checks:
        if c["name"] == "OpenCV (face tracking)" and a.need == "long":
            c["required"] = False
    blocking = [c for c in checks if c["required"] and not c["ok"]]
    note = None
    if not hw["gpu"]:
        note = "No NVIDIA GPU found: transcription runs on CPU. Use the 'small' model for speed or 'large-v3' for quality."
    print(json.dumps({"ok": not blocking, "need": a.need, "checks": checks, "hardware": hw, "note": note,
                      "fix_first": [c["fix"] for c in blocking]}, indent=2))
    return 0 if not blocking else 1


if __name__ == "__main__":
    sys.exit(main())
