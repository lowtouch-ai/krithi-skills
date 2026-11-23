#!/usr/bin/env python3
"""Create the skill's Python virtualenv and install its packages (run only after the user agrees).

Usage: setup_env.py [--dry-run] [--no-shorts]

Creates <KRITHI_HOME or ~/.krithi>/video/venv (outside any repository) and installs
requirements.txt into it. --no-shorts skips OpenCV (long-form only). Safe to re-run.
ffmpeg is NOT installed here: it is a system program. check_env.py prints the right command for
this OS; the agent shows it to the user to run or approve.
Prints JSON; exit 0 on success.
"""
import argparse
import json
import os
import subprocess
import sys
import venv
from pathlib import Path

REQ = Path(__file__).resolve().parent.parent / "requirements.txt"


def venv_dir():
    return Path(os.environ.get("KRITHI_HOME") or Path.home() / ".krithi") / "video" / "venv"


def venv_python(d=None):
    d = d or venv_dir()
    p = d / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-shorts", action="store_true")
    a = ap.parse_args()

    d = venv_dir()
    lines = [l.split("#")[0].strip() for l in REQ.read_text().splitlines()]
    pkgs = [l for l in lines if l and not (a.no_shorts and l.startswith("opencv"))]
    plan = {"venv": str(d), "packages": pkgs}
    if a.dry_run:
        print(json.dumps({"ok": True, "dry_run": True, **plan}, indent=2))
        return 0
    try:
        if not venv_python(d).exists():
            venv.EnvBuilder(with_pip=True).create(str(d))
        r = subprocess.run([str(venv_python(d)), "-m", "pip", "install", "-q", *pkgs], capture_output=True, text=True)
        if r.returncode != 0:
            print(json.dumps({"ok": False, "error": "pip install failed", "output": r.stderr[-800:], **plan}))
            return 1
    except (OSError, subprocess.SubprocessError) as e:
        print(json.dumps({"ok": False, "error": str(e), **plan}))
        return 1
    print(json.dumps({"ok": True, "python": str(venv_python(d)), **plan}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
