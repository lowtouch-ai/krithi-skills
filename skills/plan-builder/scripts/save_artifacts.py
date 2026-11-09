#!/usr/bin/env python3
"""Save ticket artifacts outside the source repository and verify them.

Usage: save_artifacts.py --ticket ABC-123 [--base DIR] [--init] [FILE ...]

Layout: <base>/<TICKET>/files/<artifact>   and the prompt goes in <base>/<TICKET>/
Default base: <git-root>/../plan-builder/artifacts  (or <cwd>/../plan-builder/artifacts
outside git). PLAN_BUILDER_HOME overrides the base. Refuses any destination inside a git
work tree. Never overwrites; collisions get a numeric suffix. Prints JSON.
"""
import argparse, hashlib, json, os, re, shutil, subprocess, sys
from pathlib import Path

TICKET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def git(args, cwd):
    try:
        r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=15)
        return r.returncode, r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def nearest_existing(p: Path) -> Path:
    p = p.resolve()
    while not p.exists() and p != p.parent:
        p = p.parent
    return p


def inside_git_worktree(p: Path) -> bool:
    rc, out = git(["rev-parse", "--is-inside-work-tree"], nearest_existing(p))
    return rc == 0 and out == "true"


def default_base() -> Path:
    env = os.environ.get("PLAN_BUILDER_HOME")
    if env:
        return Path(env).expanduser().resolve()
    rc, top = git(["rev-parse", "--show-toplevel"], Path.cwd())
    root = Path(top) if rc == 0 and top else Path.cwd()
    return (root / ".." / "plan-builder" / "artifacts").resolve()


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticket", required=True)
    ap.add_argument("--base")
    ap.add_argument("--init", action="store_true", help="only create/print the folders")
    ap.add_argument("files", nargs="*")
    a = ap.parse_args()

    if not TICKET_RE.match(a.ticket):
        print(json.dumps({"ok": False, "error": f"invalid ticket id {a.ticket!r}: use letters, digits, '-' or '_'"}))
        return 2
    base = Path(a.base).expanduser().resolve() if a.base else default_base()
    ticket_dir = base / a.ticket
    files_dir = ticket_dir / "files"
    if inside_git_worktree(ticket_dir):
        print(json.dumps({"ok": False, "error": f"{ticket_dir} is inside a git work tree; choose a folder outside any repository (--base or PLAN_BUILDER_HOME)"}))
        return 2
    files_dir.mkdir(parents=True, exist_ok=True)

    saved, failed = [], []
    for f in a.files:
        src = Path(f).expanduser()
        try:
            if not src.is_file():
                raise FileNotFoundError("not a file or not found")
            dest = unique(files_dir / re.sub(r"[^\w.\- ]", "_", src.name))
            shutil.copy2(src, dest)
            if not dest.is_file() or dest.stat().st_size != src.stat().st_size or sha256(dest) != sha256(src):
                raise OSError("verification failed (size or hash mismatch)")
            saved.append({"source": str(src.resolve()), "path": str(dest.resolve()), "bytes": dest.stat().st_size, "sha256": sha256(dest)})
        except Exception as e:  # report per file, keep going
            failed.append({"source": str(src), "error": str(e)})

    print(json.dumps({
        "ok": not failed,
        "ticket_dir": str(ticket_dir),
        "files_dir": str(files_dir),
        "prompt_path": str(ticket_dir / f"{a.ticket}-codex-plan-prompt.md"),
        "saved": saved,
        "failed": failed,
    }, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
