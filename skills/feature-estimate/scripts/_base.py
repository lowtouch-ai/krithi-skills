"""Locate the migration-estimate skill, whose scripts feature-estimate reuses unchanged.

feature-estimate holds no estimation logic of its own. Sprint maths, PRD checks, coverage checks and review
thresholds all live in migration-estimate/scripts, so the two skills cannot drift apart.
Lookup order: $KRITHI_MIGRATION_ESTIMATE, a sibling folder (repository layout), then the Codex and Claude skill folders.
"""
import importlib.util, os, runpy, subprocess, sys
from pathlib import Path

LABEL = "Feature"
OUT_DIR = Path("docs") / "feature-estimate"


def migration_scripts() -> Path:
    here = Path(__file__).resolve()
    cands = [os.environ.get("KRITHI_MIGRATION_ESTIMATE"), here.parents[2] / "migration-estimate",
             Path.home() / ".codex/skills/migration-estimate", Path.home() / ".claude/skills/migration-estimate"]
    for c in cands:
        if c and (Path(c) / "scripts" / "estimate.py").is_file():
            return Path(c) / "scripts"
    sys.exit("feature-estimate needs the migration-estimate skill (its scripts are reused). Install it from "
             "https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/migration-estimate or set KRITHI_MIGRATION_ESTIMATE.")


def repo_top() -> Path:
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.cwd()


def load(name: str):
    """Import a migration-estimate script as a module (to reuse its parsing helpers)."""
    spec = importlib.util.spec_from_file_location(f"migration_{name}", migration_scripts() / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(name: str, argv: list):
    sys.argv = [name + ".py"] + argv
    runpy.run_path(str(migration_scripts() / f"{name}.py"), run_name="__main__")
