#!/usr/bin/env python3
"""Save ticket artifacts under ~/.krithi/<TICKET>/ (outside the repository) and verify them.

Usage: save_artifacts.py --ticket ABC-123 [--base DIR] [--root DIR] [--init] [FILE ...]

Layout:
  ~/.krithi/<TICKET>/<artifact>                            supporting files, grouped by ticket, outside any repo
  <repo>/docs/plan-prompts/<TICKET>-codex-plan-prompt.md   the generated prompt (inside the repo, under docs/)
Base for artifacts: ~/.krithi (override: KRITHI_HOME env var or --base). Refuses a base inside a
git work tree. Repo root for the prompt: git top-level of the cwd, or the cwd outside git (--root).
Never overwrites (collisions get a numeric suffix); verifies existence, size and SHA-256.
Prints JSON with absolute artifact paths and the repo-relative prompt path.
"""
import argparse, hashlib, json, os, re, shutil, subprocess, sys
from pathlib import Path

TICKET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
PROMPT_DIR = "docs/plan-prompts"


def git(args, cwd):
    try:
        r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=15)
        return r.returncode, r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def inside_git_worktree(p: Path) -> bool:
    q = p.resolve()
    while not q.exists() and q != q.parent:
        q = q.parent
    rc, out = git(["rev-parse", "--is-inside-work-tree"], q)
    return rc == 0 and out == "true"


def default_base() -> Path:
    env = os.environ.get("KRITHI_HOME")
    return Path(env).expanduser().resolve() if env else (Path.home() / ".krithi").resolve()


def repo_root(override):
    if override:
        return Path(override).expanduser().resolve()
    rc, top = git(["rev-parse", "--show-toplevel"], Path.cwd())
    return Path(top).resolve() if rc == 0 and top else Path.cwd().resolve()


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def unique(dest: Path) -> Path:
    if not dest.exists():
        return dest
    n = 2
    while True:
        c = dest.with_name(f"{dest.stem}-{n}{dest.suffix}")
        if not c.exists():
            return c
        n += 1


def fail(msg: str) -> int:
    print(json.dumps({"ok": False, "error": msg}))
    return 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticket", required=True)
    ap.add_argument("--base", help="artifact base folder (default: ~/.krithi or $KRITHI_HOME)")
    ap.add_argument("--root", help="repository root for the prompt (default: git top-level of the cwd)")
    ap.add_argument("--init", action="store_true", help="only create/print the folders")
    ap.add_argument("files", nargs="*")
    a = ap.parse_args()

    if not TICKET_RE.match(a.ticket):
        return fail(f"invalid ticket id {a.ticket!r}: use letters, digits, '-' or '_'")
    root = repo_root(a.root)
    base = Path(a.base).expanduser().resolve() if a.base else default_base()
    ticket_dir = base / a.ticket
    if inside_git_worktree(ticket_dir):
        return fail(f"{ticket_dir} is inside a git work tree; artifacts must live outside the repository (use --base or KRITHI_HOME)")
    prompt_file = root / PROMPT_DIR / f"{a.ticket}-codex-plan-prompt.md"
    ticket_dir.mkdir(parents=True, exist_ok=True)
    prompt_file.parent.mkdir(parents=True, exist_ok=True)

    saved, failed = [], []
    for f in a.files:
        src = Path(f).expanduser()
        try:
            if not src.is_file():
                raise FileNotFoundError("not a file or not found")
            dest = unique(ticket_dir / re.sub(r"[^\w.\- ]", "_", src.name))
            shutil.copy2(src, dest)
            if not dest.is_file() or dest.stat().st_size != src.stat().st_size or sha256(dest) != sha256(src):
                raise OSError("verification failed (size or hash mismatch)")
            saved.append({"source": str(src.resolve()), "path": str(dest.resolve()),
                          "bytes": dest.stat().st_size, "sha256": sha256(dest)})
        except Exception as e:  # report per file, keep going
            failed.append({"source": str(src), "error": str(e)})

    print(json.dumps({
        "ok": not failed,
        "repo_root": str(root),
        "artifacts_dir": str(ticket_dir),
        "prompt_path": prompt_file.relative_to(root).as_posix(),
        "prompt_absolute_path": str(prompt_file),
        "saved": saved,
        "failed": failed,
    }, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
