#!/usr/bin/env python3
"""Smoke test for prepare-pr's pr_context.py. Run: python3 tests/prepare-pr/test_prepare_pr.py"""
import json, subprocess, sys, tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
ctx = str(root / "skills/prepare-pr/scripts/pr_context.py")
tmp = Path(tempfile.mkdtemp())
problems = []


def expect(cond, msg):
    if not cond:
        problems.append(msg)


def g(repo, *a):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *a], check=True, capture_output=True)


def run(*a, cwd):
    r = subprocess.run([sys.executable, ctx, *a], capture_output=True, text=True, cwd=cwd)
    return r, (json.loads(r.stdout) if r.stdout.strip().startswith("{") else {})


# a bare "remote" with main, and a clone on a feature branch
remote = tmp / "remote.git"
subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
seed = tmp / "seed"
subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
(seed / "README.md").write_text("# demo\n\nRun `app --verbose`.\n")
(seed / "app.py").write_text("def total(items):\n    return sum(items)\n")
(seed / "package.json").write_text(json.dumps({"scripts": {"test": "jest", "lint": "eslint ."}}))
(seed / ".github").mkdir()
(seed / ".github/pull_request_template.md").write_text("## Summary\n")
g(seed, "add", ".")
g(seed, "commit", "-q", "-m", "feat: initial commit")
g(seed, "remote", "add", "origin", str(remote))
g(seed, "push", "-q", "-u", "origin", "main")
repo = tmp / "repo"
subprocess.run(["git", "clone", "-q", str(remote), str(repo)], check=True)
g(repo, "switch", "-q", "-c", "fix/ABC-1-invoice-total")
(repo / "app.py").write_text("def total(items):\n    return sum(i for i in items if i)\n")
g(repo, "commit", "-q", "-am", "fix: skip empty items")
(repo / "README.md").write_text("# demo\n\nRun `app --quiet`.\n")      # unstaged
(repo / "notes.txt").write_text("scratch\n")                          # untracked
(repo / "src").mkdir()

# not a repository -> exit 2 with a one-line JSON error
r, j = run(cwd=tmp)
expect(r.returncode == 2 and "error" in j and "Traceback" not in r.stderr, "outside a repo: exit 2 with an error message")

# context from a subfolder
r, j = run(cwd=repo / "src")
expect(r.returncode == 0, f"context failed: {r.stderr[-300:]}")
expect(Path(j.get("repo_root", "")) == repo.resolve(), "repo_root must be the git top-level")
expect(j.get("branch") == "fix/ABC-1-invoice-total" and j.get("default_branch") == "main", "branch and default branch")
expect(j.get("base_ref") == "origin/main", "base ref should be origin/main")
expect([c["subject"] for c in j.get("commits_on_branch", [])] == ["fix: skip empty items"], "commits on branch")
wt = j.get("working_tree", {})
expect([u["path"] for u in wt.get("unstaged", [])] == ["README.md"], "README.md should be unstaged")
expect(wt.get("untracked") == ["notes.txt"], "notes.txt should be untracked")
expect(any(c["path"] == "app.py" for c in j.get("changed_vs_base", [])), "app.py should differ from base")
bi = j.get("branch_info") or {}
expect(bi.get("protected") is False and bi.get("type") == "fix", f"branch_info for a fix branch: {bi}")
expect({"npm test", "npm run lint"} <= {t["command"] for t in j.get("test_commands", [])}, "package.json test and lint commands")
expect(j.get("pr_templates") == [".github/pull_request_template.md"], "PR template detection")
expect(j.get("upstream") is None and j.get("upstream_is_default_branch") is False, "new branch has no upstream")
expect(j.get("conventions", {}).get("conventional_commits") is False, "one commit is not enough to call it a convention")
expect("README.md" in j.get("docs", {}).get("tracked_markdown", []), "tracked markdown listing")

# a branch tracking origin/main is flagged (bare git push would target main)
g(repo, "branch", "--set-upstream-to", "origin/main")
_, j = run(cwd=repo)
expect(j.get("upstream_is_default_branch") is True, "upstream pointing at the default branch must be flagged")
g(repo, "branch", "--unset-upstream")

# on main: protected
g(repo, "stash", "-q", "--include-untracked")
g(repo, "switch", "-q", "main")
_, j = run(cwd=repo)
expect((j.get("branch_info") or {}).get("protected") is True, "main must be protected")
g(repo, "switch", "-q", "fix/ABC-1-invoice-total")
g(repo, "stash", "pop", "-q")

# --scan-staged: clean stage passes, secrets and .env block, value never echoed
g(repo, "add", "README.md")
r, j = run("--scan-staged", cwd=repo)
expect(r.returncode == 0 and j.get("problems") == [], f"clean stage should pass: {j}")
key = "AKIA" + "ABCDEFGHIJKLMNOP"
(repo / "config.py").write_text(f'AWS_KEY = "{key}"\n')
(repo / ".env").write_text("TOKEN=x\n")
(repo / ".env.example").write_text("TOKEN=\n")
g(repo, "add", "config.py", ".env", ".env.example")
r, j = run("--scan-staged", cwd=repo)
kinds = {(p["path"], p["kind"]) for p in j.get("problems", [])}
expect(r.returncode == 1, "staged secrets must exit 1")
expect(("config.py", "AWS access key") in kinds, "AWS key must be found in config.py")
expect((".env", "sensitive file name") in kinds, ".env must be blocked")
expect(not any(p == ".env.example" for p, _ in kinds), ".env.example must be allowed")
expect(key not in r.stdout, "the secret value must never be printed")
line = next((p.get("line") for p in j.get("problems", []) if p["path"] == "config.py"), None)
expect(line == 1, f"secret line number should be 1, got {line}")

# a merge in progress is reported
g(repo, "reset", "-q")
(Path(subprocess.run(["git", "-C", str(repo), "rev-parse", "--absolute-git-dir"], capture_output=True, text=True).stdout.strip()) / "MERGE_HEAD").write_text("0" * 40 + "\n")
_, j = run(cwd=repo)
expect("merge" in j.get("operation_in_progress", []), "merge in progress must be reported")

print("OK" if not problems else "PROBLEMS:\n- " + "\n- ".join(problems))
sys.exit(1 if problems else 0)
