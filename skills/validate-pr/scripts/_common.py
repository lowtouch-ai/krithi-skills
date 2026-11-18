"""Shared helpers for validate-pr's scripts: run folders, metadata.json and the run's event history.

A run folder is created by run_store.py init and looks like:
  <artifacts>/github/<owner>/<repo>/pr-<n>/run-<UTC timestamp>-<sha12>/
      metadata.json  history.jsonl  results/  screenshots/  traces/  logs/  defects/  report/
"""
import json, os, re, subprocess
from datetime import datetime, timezone
from pathlib import Path

RUN_SUBDIRS = ("results", "screenshots", "traces", "logs", "defects", "report")
STATUSES = ("Passed", "Failed", "Blocked", "Needs Manual Verification")
# Removed from the environment of everything the skill launches (the app, its build, the tests).
SECRET_ENV = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "NPM_TOKEN", "PYPI_TOKEN", "AWS_ACCESS_KEY_ID",
              "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AZURE_CLIENT_SECRET", "GOOGLE_APPLICATION_CREDENTIALS",
              "OPENAI_API_KEY", "ANTHROPIC_API_KEY")
SECRET_RE = re.compile(r"\b(ghp|gho|ghs|ghu|github_pat)_[A-Za-z0-9_]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{32,}"
                       r"|\bAKIA[0-9A-Z]{16}\b|xox[baprs]-[A-Za-z0-9-]{10,}")


def artifacts_base():
    """$VALIDATE_PR_ARTIFACTS, else $KRITHI_HOME/validate-pr-artifacts, else ~/.krithi/validate-pr-artifacts."""
    if os.environ.get("VALIDATE_PR_ARTIFACTS"):
        return Path(os.environ["VALIDATE_PR_ARTIFACTS"]).expanduser()
    return Path(os.environ.get("KRITHI_HOME") or Path.home() / ".krithi").expanduser() / "validate-pr-artifacts"


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_dir(path):
    d = Path(path).expanduser().resolve()
    if not (d / "metadata.json").is_file():
        raise SystemExit(json.dumps({"error": f"{d} is not a validate-pr run folder (no metadata.json); run run_store.py init"}))
    return d


def load_meta(d):
    return json.loads((Path(d) / "metadata.json").read_text(encoding="utf-8"))


def save_meta(d, meta):
    meta["updated_at"] = now()
    tmp = Path(d) / "metadata.json.tmp"
    tmp.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    tmp.replace(Path(d) / "metadata.json")


def merge_meta(d, patch):
    """Deep-merge `patch` into metadata.json (dicts merge, everything else replaces)."""
    meta = load_meta(d)

    def merge(a, b):
        for k, v in b.items():
            if isinstance(v, dict) and isinstance(a.get(k), dict):
                merge(a[k], v)
            else:
                a[k] = v
    merge(meta, patch)
    save_meta(d, meta)
    return meta


def log_event(d, ev):
    ev = {"at": now(), **ev}
    with (Path(d) / "history.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev) + "\n")
    return ev


def events(d):
    p = Path(d) / "history.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.is_file() else []


def clean_env(extra=None):
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV}
    env.update(extra or {})
    return env


def run(cmd, cwd=None, env=None, timeout=None):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd, env=env, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def rel(d, p):
    """Path of p relative to the run folder, with forward slashes (for reports and evidence lists)."""
    try:
        return Path(p).resolve().relative_to(Path(d).resolve()).as_posix()
    except ValueError:
        return str(p)


def out(obj, code=0):
    print(json.dumps(obj, indent=2))
    return code
