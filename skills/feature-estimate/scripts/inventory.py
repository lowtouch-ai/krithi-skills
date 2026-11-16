#!/usr/bin/env python3
"""Codebase inventory: runs migration-estimate's inventory.py unchanged, saving under ~/.krithi/feature-estimate/<repo>/.
Usage: inventory.py [ROOT] [--out FILE]
"""
import os, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _base

argv = sys.argv[1:]
if "--out" not in argv:
    pos = [a for a in argv if not a.startswith("-")]
    root = Path(pos[0]).resolve() if pos else _base.repo_top()
    home = Path(os.environ["KRITHI_HOME"]).expanduser() if os.environ.get("KRITHI_HOME") else Path.home() / ".krithi"
    argv += ["--out", str(home / "feature-estimate" / re.sub(r"[^A-Za-z0-9_.-]", "_", root.name) / "inventory.json")]
_base.run("inventory", argv)
