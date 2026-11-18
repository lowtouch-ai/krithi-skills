#!/usr/bin/env python3
"""Put the generated test plan and Playwright tests on the PR branch, only after the reviewer approves the exact change.

  prepare  stage the given paths in the PR worktree, refuse anything that is not a test artifact, scan for secrets,
           and write report/test-changes.patch. Prints the diff stat and its SHA-256: show the reviewer the patch and
           ask. The hash is what they approve.
  commit   commit exactly the prepared change. Refuses if the staged change differs from the approved hash.
  push     push the commit to the PR's head branch (fast-forward only; never --force), after a second, separate yes.
           For a fork PR without "allow edits by maintainers", it refuses and leaves the patch to hand over.

Allowed paths (everything else is refused, so implementation code is never changed):
  - files in a test folder: tests/, test/, e2e/, playwright/, __tests__/, spec(s)/, cypress/, integration-tests/
  - *.spec.* / *.test.* / *.e2e.* files, conftest.py, test_*.py
  - test plans: docs/test-plans/ (or --plan-dir), *test-plan*.md
  - playwright.config.*, pytest.ini, .gitignore
  - package.json only when the change touches nothing but devDependencies and scripts; lockfiles with it
  - requirements-dev.txt, requirements-test.txt, dev-requirements.txt
  - --allow-config FILE for one more non-code config file (.json/.toml/.ini/.cfg/.yaml/.yml/.txt); recorded with --reason

Usage:
  commit_tests.py prepare --run D --worktree W [--plan-dir docs/test-plans] [--allow-config F --reason "..."] -- <paths...>
  commit_tests.py commit  --run D --worktree W --sha256 HASH --message-file M
  commit_tests.py push    --run D --worktree W --sha256 HASH

Exit codes: 0 ok, 1 git failed (output shown), 2 refused.
"""
import argparse, hashlib, json, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import SECRET_RE, events, load_meta, log_event, merge_meta, out, run_dir  # noqa: E402

TEST_DIR = re.compile(r"(^|/)(tests?|e2e|playwright|__tests__|specs?|cypress|integration-tests|test-plans)/", re.I)
TEST_FILE = re.compile(r"\.(spec|test|e2e)\.[cm]?[jt]sx?$|(^|/)conftest\.py$|(^|/)test_[^/]+\.py$|test-plan[^/]*\.md$", re.I)
CONFIG_OK = re.compile(r"(^|/)(playwright\.config\.[cm]?[jt]s|pytest\.ini|\.gitignore|requirements-(dev|test)\.txt|dev-requirements\.txt)$")
LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "bun.lock"}
EXTRA_OK_EXT = (".json", ".toml", ".ini", ".cfg", ".yaml", ".yml", ".txt")
CODE_EXT = re.compile(r"\.(py|[cm]?[jt]sx?|java|kt|go|rs|rb|php|cs|vue|svelte|html?|css|scss|sql)$", re.I)


def git(wt, *args, check=False):
    r = subprocess.run(["git", "-C", str(wt), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise SystemExit(json.dumps({"error": f"git {' '.join(args[:2])} failed", "output": (r.stdout + r.stderr)[-1500:]}))
    return r


def package_json_ok(wt, path):
    """True when package.json differs from HEAD only in devDependencies and scripts."""
    old = git(wt, "show", f"HEAD:{path}")
    try:
        a = json.loads(old.stdout) if old.returncode == 0 else {}
        b = json.loads((Path(wt) / path).read_text(encoding="utf-8"))
    except ValueError:
        return False
    keys = set(a) | set(b)
    return all(a.get(k) == b.get(k) for k in keys - {"devDependencies", "scripts"})


def classify(wt, path, plan_dir, allow_config):
    name = path.rsplit("/", 1)[-1]
    if plan_dir and (path + "/").startswith(plan_dir.rstrip("/") + "/"):
        return "test plan"
    if TEST_FILE.search(path) or TEST_DIR.search(path):
        return "test"
    if CONFIG_OK.search(path):
        return "test config"
    if name == "package.json":
        return "dev dependencies" if package_json_ok(wt, path) else None
    if name in LOCKFILES:
        return "lockfile"
    if allow_config and path == allow_config and path.endswith(EXTRA_OK_EXT) and not CODE_EXT.search(path):
        return "extra config (approved)"
    return None


def staged(wt):
    return [p for p in git(wt, "diff", "--cached", "--name-only", "-z").stdout.split("\0") if p]


def patch_hash(wt):
    p = git(wt, "diff", "--cached", "--binary", "--no-color").stdout
    return p, hashlib.sha256(p.encode("utf-8")).hexdigest()


def cmd_prepare(a):
    d = run_dir(a.run)
    wt = Path(a.worktree).resolve()
    paths = [p for p in (a.paths[1:] if a.paths[:1] == ["--"] else a.paths)]
    if not paths:
        return out({"refused": "name the files to include after --"}, 2)
    if a.allow_config and not (a.reason or "").strip():
        return out({"refused": "--allow-config needs --reason"}, 2)
    git(wt, "reset", "-q")  # start from an empty index: only the named paths are staged
    git(wt, "add", "--", *paths, check=True)
    files = staged(wt)
    kinds, refused = {}, []
    for f in files:
        k = classify(wt, f, a.plan_dir, a.allow_config)
        (refused.append(f) if k is None else kinds.__setitem__(f, k))
    secrets = []
    for f in files:
        fp = wt / f
        if fp.is_file() and fp.stat().st_size < 2_000_000:
            for n, ln in enumerate(fp.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if SECRET_RE.search(ln) or re.search(r"(?i)\b(password|passwd|secret|api[_-]?key|token)\b\s*[:=]\s*['\"][^'\"$\s{]{6,}['\"]", ln):
                    secrets.append(f"{f}:{n}")
        if Path(f).name.startswith(".env") or Path(f).name == ".validate-pr.playwright.config.ts":
            refused.append(f)
    if refused or secrets:
        git(wt, "reset", "-q")
        return out({"refused": "the change includes files validate-pr may not commit" if refused else "possible hard-coded credentials",
                    "not_test_artifacts": sorted(set(refused)), "possible_secrets": secrets,
                    "rule": "validate-pr commits only test plans, tests, fixtures and test configuration; it never changes application code, "
                            "and credentials come from environment variables"}, 2)
    patch, h = patch_hash(wt)
    pf = d / "report" / "test-changes.patch"
    pf.write_text(patch, encoding="utf-8")
    stat = git(wt, "diff", "--cached", "--stat").stdout
    merge_meta(d, {"committed_artifacts": {"prepared": {"sha256": h, "files": kinds, "patch": "report/test-changes.patch",
                                                         "allow_config_reason": a.reason}}})
    log_event(d, {"event": "test_changes_prepared", "sha256": h, "files": files})
    return out({"sha256": h, "files": kinds, "stat": stat, "patch": str(pf),
                "next": "show the reviewer the patch and ask for approval; then commit with --sha256 " + h})


def cmd_commit(a):
    d = run_dir(a.run)
    wt = Path(a.worktree).resolve()
    _, h = patch_hash(wt)
    if h != a.sha256:
        return out({"refused": "the staged change is not the one the reviewer approved (SHA-256 mismatch); prepare and show it again"}, 2)
    meta = load_meta(d)
    if meta.get("committed_artifacts", {}).get("prepared", {}).get("sha256") != h:
        return out({"refused": "this change was not prepared for this run"}, 2)
    msg = Path(a.message_file).read_text(encoding="utf-8")
    if not msg.strip():
        return out({"refused": "empty commit message"}, 2)
    branch = git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch == "HEAD":  # detached worktree at the tested commit: commit on a local branch named for the run
        local = f"validate-pr/pr-{meta['pr_number']}-{meta['tested_commit_sha'][:7]}"
        r = git(wt, "switch", "-c", local)
        if r.returncode != 0:
            r = git(wt, "switch", local)
            if r.returncode != 0:
                return out({"error": "could not create the local branch", "output": r.stderr[-800:]}, 1)
    r = subprocess.run(["git", "-C", str(wt), "commit", "-F", a.message_file], capture_output=True, text=True)
    if r.returncode != 0:
        return out({"error": "git commit failed (a hook may have rejected it; fix the cause and prepare again, never --no-verify)",
                    "output": (r.stdout + r.stderr)[-2000:]}, 1)
    sha = git(wt, "rev-parse", "HEAD").stdout.strip()
    merge_meta(d, {"committed_artifacts": {"commit_sha": sha, "approved_sha256": h, "branch": git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()}})
    log_event(d, {"event": "test_changes_committed", "commit": sha, "sha256": h})
    return out({"committed": sha, "parent": meta["tested_commit_sha"], "next": "ask separately before pushing"})


def cmd_push(a):
    d = run_dir(a.run)
    wt = Path(a.worktree).resolve()
    meta = load_meta(d)
    ca = meta.get("committed_artifacts", {})
    if not ca.get("commit_sha") or ca.get("approved_sha256") != a.sha256:
        return out({"refused": "nothing approved is committed for this run (commit first, with the approved hash)"}, 2)
    if any(e["event"] == "test_changes_pushed" and e.get("commit") == ca["commit_sha"] for e in events(d)):
        return out({"refused": "this commit was already pushed"}, 2)
    hr = meta["head_repository"]
    if hr.get("is_fork") and not hr.get("maintainer_can_modify"):
        return out({"refused": "fork PR without 'Allow edits by maintainers': the branch cannot be pushed to",
                    "handover": f"send the author report/test-changes.patch (apply with `git am` or `git apply`)", "patch": str(d / "report/test-changes.patch")}, 2)
    head_ref = meta["head_ref"]
    if meta["owner"].lower() == (hr.get("owner") or "").lower() and head_ref == meta["base_ref"]:
        return out({"refused": f"the PR's head branch is its base branch ({head_ref}); validate-pr never pushes to a base branch"}, 2)
    url = hr["url"] + ".git"
    r = git(wt, "push", url, f"HEAD:refs/heads/{head_ref}")
    if r.returncode != 0:
        why = "the PR branch has new commits since the tested commit; retest the new head (new run) instead of pushing over it" \
            if re.search(r"non-fast-forward|fetch first|rejected", r.stderr) else "push failed"
        log_event(d, {"event": "test_changes_push_failed", "reason": why})
        return out({"error": why, "output": r.stderr[-1500:]}, 1)
    log_event(d, {"event": "test_changes_pushed", "commit": ca["commit_sha"], "branch": head_ref, "remote": hr["url"]})
    merge_meta(d, {"committed_artifacts": {"pushed_to": f"{hr['url']}/tree/{head_ref}"}})
    return out({"pushed": ca["commit_sha"], "branch": head_ref, "pr_url": meta["pr_url"]})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare"); p.add_argument("--run", required=True); p.add_argument("--worktree", required=True)
    p.add_argument("--plan-dir", default="docs/test-plans"); p.add_argument("--allow-config"); p.add_argument("--reason")
    p.add_argument("paths", nargs=argparse.REMAINDER)
    p = sub.add_parser("commit"); p.add_argument("--run", required=True); p.add_argument("--worktree", required=True)
    p.add_argument("--sha256", required=True); p.add_argument("--message-file", required=True)
    p = sub.add_parser("push"); p.add_argument("--run", required=True); p.add_argument("--worktree", required=True)
    p.add_argument("--sha256", required=True)
    a = ap.parse_args()
    return {"prepare": cmd_prepare, "commit": cmd_commit, "push": cmd_push}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
