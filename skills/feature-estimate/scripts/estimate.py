#!/usr/bin/env python3
"""Feature estimate: runs migration-estimate's estimate.py unchanged.

Only two defaults differ: the folder (docs/feature-estimate) and the summary title ("Feature estimate: ...").
Every rule, check, threshold and number comes from migration-estimate/scripts/estimate.py.
Usage: estimate.py [--dir docs/feature-estimate] [--inventory INVENTORY.json] [--write] [--review]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _base

argv = sys.argv[1:]
if "--dir" not in argv:
    argv += ["--dir", str(_base.repo_top() / _base.OUT_DIR)]
if "--label" not in argv:
    argv += ["--label", _base.LABEL]
_base.run("estimate", argv)
