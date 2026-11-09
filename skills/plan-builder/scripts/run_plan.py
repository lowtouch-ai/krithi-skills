#!/usr/bin/env python3
"""Run a saved plan-builder prompt in a read-only Codex session and save the plan.

Usage: run_plan.py --ticket ABC-123 [--root DIR] [--prompt FILE] [--feedback TEXT] [--timeout SECONDS]

Runs `codex exec -s read-only --ephemeral -C <root> -o <tmp> -` with the prompt on stdin
(Codex's own Plan Mode has no non-interactive form; the read-only sandbox plus the prompt's
PLAN MODE ONLY clause stand in for it). Saves the plan to
<root>/docs/plan-prompts/<TICKET>-implementation-plan.md (the previous one is kept as
<TICKET>-implementation-plan.prev.md), compares `git status` before and after, and checks the
plan's headings. With --feedback, the previous plan and the reviewer's comments are appended to
the prompt so Codex revises the plan. Never stages or commits. Prints JSON.
"""
import argparse, json, re, shutil, subprocess, sys, tempfile
from pathlib import Path

PROMPT_DIR = "docs/plan-prompts"
TICKET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
HEADINGS = [
    ("Current architecture", r"current architecture"),
    ("Root cause / Design approach", r"root cause|design approach"),
    ("Files to modify", r"files to (?:modify|change)"),
    ("Recommended implementation", r"recommended implementation"),
    ("Dependencies and impact", r"dependenc\w+|impact"),
    ("Risks and regression areas", r"risks?"),
    ("Testing strategy", r"test"),
    ("Rollout and compatibility", r"rollout|compatibility"),
    ("Acceptance criteria", r"acceptance criteria"),
    ("Open questions", r"open questions"),
]


def git(args, cwd):
    try:
        r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=30)
        return r.returncode, r.stdout
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def status(root: Path):
    rc, out = git(["status", "--porcelain", "--untracked-files=all"], root)
    return set(out.splitlines()) if rc == 0 else None


def out(d, code=0):
    print(json.dumps(d, indent=2))
    return code


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticket", required=True)
    ap.add_argument("--root")
    ap.add_argument("--prompt")
    ap.add_argument("--feedback")
    ap.add_argument("--timeout", type=int, default=1800)
    a = ap.parse_args()
    if not TICKET_RE.match(a.ticket):
        return out({"ok": False, "error": "invalid ticket id"}, 2)

    root = Path(a.root).resolve() if a.root else Path.cwd().resolve()
    rc, top = git(["rev-parse", "--show-toplevel"], root)
    if not a.root and rc == 0 and top.strip():
        root = Path(top.strip()).resolve()
    prompt_file = Path(a.prompt) if a.prompt else root / PROMPT_DIR / f"{a.ticket}-codex-plan-prompt.md"
    plan_file = root / PROMPT_DIR / f"{a.ticket}-implementation-plan.md"
    if not prompt_file.is_file():
        return out({"ok": False, "reason": "prompt_missing", "error": f"{prompt_file} not found"}, 2)
    if not shutil.which("codex"):
        return out({"ok": False, "reason": "codex_not_found",
                    "error": "codex CLI not found; follow the prompt in the current session instead"}, 3)

    text = prompt_file.read_text(encoding="utf-8")
    if a.feedback:
        prev = plan_file.read_text(encoding="utf-8") if plan_file.is_file() else "(no previous plan)"
        text += ("\n\n---\n\n## Revision request\nBelow is the previous plan and the reviewer's feedback. "
                 "Revise the plan to address the feedback. Still PLAN MODE ONLY: do not modify any file. "
                 "Return the complete revised plan, using the same headings.\n\n"
                 f"### Previous plan\n{prev}\n\n### Reviewer feedback\n{a.feedback}\n")

    before = status(root)
    tmp = Path(tempfile.mkdtemp()) / "plan.md"
    cmd = ["codex", "exec", "-s", "read-only", "--ephemeral", "-C", str(root), "-o", str(tmp), "-"]
    try:
        r = subprocess.run(cmd, input=text, capture_output=True, text=True, timeout=a.timeout, cwd=str(root))
    except subprocess.TimeoutExpired:
        return out({"ok": False, "reason": "timeout", "error": f"codex exec exceeded {a.timeout}s"}, 4)
    except OSError as e:
        return out({"ok": False, "reason": "codex_failed", "error": str(e)}, 4)
    after = status(root)

    plan = tmp.read_text(encoding="utf-8") if tmp.is_file() else ""
    if r.returncode != 0 or not plan.strip():
        return out({"ok": False, "reason": "codex_failed", "exit_code": r.returncode,
                    "error": (r.stderr or "no plan produced")[-600:]}, 4)

    changed = sorted(after - before) if before is not None and after is not None else None
    heads = " | ".join(
        re.sub(r"[#*`]", "", ln).strip().lower()
        for ln in plan.splitlines()
        if len(ln.strip()) < 100 and re.match(r"^\s*(#{1,6}\s|\*\*|\d+[.)]\s)", ln)
    )
    missing = [name for name, pat in HEADINGS if not re.search(pat, heads)]

    plan_file.parent.mkdir(parents=True, exist_ok=True)
    if plan_file.is_file():
        shutil.copy2(plan_file, plan_file.with_suffix(".prev.md"))
    plan_file.write_text(plan, encoding="utf-8")
    return out({
        "ok": True,
        "plan_path": plan_file.relative_to(root).as_posix(),
        "plan_absolute_path": str(plan_file),
        "revised": bool(a.feedback),
        "repo_changed_during_run": changed,
        "missing_headings": missing,
        "unlabelled_findings_warning": not re.search(r"\b(confirmed|assumption)\b", plan, re.I),
        "bytes": len(plan.encode("utf-8")),
    })


if __name__ == "__main__":
    sys.exit(main())
