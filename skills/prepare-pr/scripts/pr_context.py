#!/usr/bin/env python3
"""Collect the git facts prepare-pr needs, as JSON. Read-only: never stages, commits, switches or pushes.

Usage:
  python3 pr_context.py [--repo DIR] [--base BRANCH] [--check-gh]
  python3 pr_context.py --scan-staged [--repo DIR]     # secret / large-file check of what is staged

Exit codes: 0 ok, 1 --scan-staged found blocking problems, 2 usage or not a git repository.
"""
import argparse, json, os, re, shutil, subprocess, sys
from pathlib import Path

LARGE_BYTES = 5 * 1024 * 1024
SENSITIVE_NAMES = re.compile(r"(^|/)(\.env(\..*)?|id_rsa|id_ed25519|.*\.pem|.*\.p12|.*\.pfx|.*\.key|credentials(\.json)?|\.npmrc|\.pypirc|secrets?\.(ya?ml|json))$", re.I)
SAFE_ENV_SUFFIX = re.compile(r"\.env\.(example|sample|template|dist)$", re.I)
SECRET_PATTERNS = [
    ("private key", re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{60,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Anthropic/OpenAI key", re.compile(r"\bsk-(ant-)?[A-Za-z0-9_-]{32,}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("hard-coded credential", re.compile(r"""(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?token|client[_-]?secret)\b\s*[:=]\s*['"][^'"\s]{8,}['"]""")),
]
CONVENTIONAL = re.compile(r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([^)]+\))?!?: ")


def git(repo, *args, check=False):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout if r.returncode == 0 else ""


def default_branch(repo):
    ref = git(repo, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD").strip()
    if ref:
        return ref.rsplit("/", 1)[-1]
    for cand in ("main", "master", "develop", "trunk"):
        if git(repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{cand}") or git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{cand}"):
            return cand
    return None


def classify_branch(branch, default):
    """Decide what the current branch name means for this change.

    Returns a dict:
      protected: True if work must NOT be committed here (a new feature branch is required)
      type:      the conventional prefix if the name has one (feat, fix, docs, ...), else None
      words:     the descriptive words in the name, for the agent to compare with the diff
    """
    # Default policy: only the default branch and main/master are protected. Teams with other long-lived
    # branches (develop, release/*, ...) can extend this set; the agent judges name-vs-work fit from `words`.
    protected =branch in {default, "main", "master"}
    prefix, _, rest = branch.partition("/") if "/" in branch else (None, "", branch)
    words = [w for w in re.split(r"[-_/.]+", rest.lower()) if w and not w.isdigit()]
    return {"protected": protected, "type": prefix, "words": words}


def porcelain(repo):
    """Parse `git status --porcelain=v1 -z` into staged / unstaged / untracked / conflicted lists."""
    out = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    staged, unstaged, untracked, conflicted = [], [], [], []
    items = out.split("\0")
    i = 0
    while i < len(items):
        e = items[i]
        i += 1
        if len(e) < 4:
            continue
        x, y, path = e[0], e[1], e[3:]
        orig = None
        if x in "RC":
            orig = items[i] if i < len(items) else None
            i += 1
        if x == "?":
            untracked.append(path)
        elif x == "U" or y == "U" or (x, y) in {("A", "A"), ("D", "D")}:
            conflicted.append(path)
        else:
            if x not in " ?!":
                staged.append({"path": path, "status": x, **({"from": orig} if orig else {})})
            if y not in " ?!":
                unstaged.append({"path": path, "status": y})
    return staged, unstaged, untracked, conflicted


def in_progress(repo):
    gd = Path(git(repo, "rev-parse", "--absolute-git-dir").strip() or ".")
    states = {"MERGE_HEAD": "merge", "rebase-merge": "rebase", "rebase-apply": "rebase/am", "CHERRY_PICK_HEAD": "cherry-pick", "REVERT_HEAD": "revert", "BISECT_LOG": "bisect"}
    return [name for f, name in states.items() if (gd / f).exists()]


def detect_tests(root):
    """Test/lint commands declared by the project. The agent still checks AGENTS.md / README for the documented ones."""
    found = []
    pj = root / "package.json"
    if pj.is_file():
        try:
            scripts = json.loads(pj.read_text(encoding="utf-8")).get("scripts", {})
        except (ValueError, OSError):
            scripts = {}
        runner = "pnpm" if (root / "pnpm-lock.yaml").exists() else "yarn" if (root / "yarn.lock").exists() else "npm run"
        for k in ("test", "lint", "typecheck", "type-check", "check", "build"):
            if k in scripts:
                found.append({"kind": k, "command": f"{runner} {k}" if runner != "npm run" or k != "test" else "npm test", "source": "package.json"})
    if (root / "pyproject.toml").is_file() or (root / "pytest.ini").is_file() or (root / "setup.cfg").is_file() or (root / "tests").is_dir():
        txt = ""
        for f in ("pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini"):
            p = root / f
            if p.is_file():
                txt += p.read_text(encoding="utf-8", errors="replace")
        if "pytest" in txt or (root / "conftest.py").exists():
            found.append({"kind": "test", "command": "pytest", "source": "pytest config"})
        if "ruff" in txt:
            found.append({"kind": "lint", "command": "ruff check .", "source": "pyproject.toml"})
    mk = root / "Makefile"
    if mk.is_file():
        targets = set(re.findall(r"^([A-Za-z][\w.-]*):", mk.read_text(encoding="utf-8", errors="replace"), re.M))
        for t in ("test", "check", "lint"):
            if t in targets:
                found.append({"kind": t, "command": f"make {t}", "source": "Makefile"})
    for f, cmd in (("go.mod", "go test ./..."), ("Cargo.toml", "cargo test"), ("pom.xml", "mvn -q test"), ("build.gradle", "./gradlew test"), ("build.gradle.kts", "./gradlew test")):
        if (root / f).is_file():
            found.append({"kind": "test", "command": cmd, "source": f})
    return found


def added_lines(repo, cached):
    """Yield (path, line_no, text) for each added line in the staged (cached=True) or working-tree diff."""
    diff = git(repo, "diff", "--cached" if cached else "HEAD", "--unified=0", "--no-color", "--no-ext-diff")
    path, ln = None, 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            ln = int(m.group(1)) if m else 0
        elif line.startswith("+") and path:
            yield path, ln, line[1:]
            ln += 1


def scan_paths(repo, root, paths, cached):
    problems = []
    for p in paths:
        if SENSITIVE_NAMES.search(p) and not SAFE_ENV_SUFFIX.search(p):
            problems.append({"path": p, "kind": "sensitive file name", "blocking": True})
        f = root / p
        if f.is_file() and f.stat().st_size > LARGE_BYTES:
            problems.append({"path": p, "kind": f"large file ({f.stat().st_size // 1024} KiB)", "blocking": False})
    wanted = set(paths)
    for p, ln, text in added_lines(repo, cached):
        if p not in wanted:
            continue
        for name, rx in SECRET_PATTERNS:
            if rx.search(text):
                # report location and kind only; never echo the value
                problems.append({"path": p, "line": ln, "kind": name, "blocking": True})
                break
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", help="base branch for the PR (default: the remote's default branch)")
    ap.add_argument("--check-gh", action="store_true", help="also check that the gh CLI is installed and logged in")
    ap.add_argument("--scan-staged", action="store_true", help="only scan the staged changes for secrets and large files")
    a = ap.parse_args()

    if not shutil.which("git"):
        print(json.dumps({"error": "git is not installed"}))
        return 2
    top = git(a.repo, "rev-parse", "--show-toplevel").strip()
    if not top:
        print(json.dumps({"error": f"not a git repository: {os.path.abspath(a.repo)}"}))
        return 2
    root = Path(top)

    staged, unstaged, untracked, conflicted = porcelain(root)

    if a.scan_staged:
        probs = scan_paths(root, root, [s["path"] for s in staged if s["status"] != "D"], cached=True)
        print(json.dumps({"staged": [s["path"] for s in staged], "problems": probs}, indent=2))
        return 1 if any(p["blocking"] for p in probs) else 0

    branch = git(root, "symbolic-ref", "--quiet", "--short", "HEAD").strip()
    detached = not branch
    dflt = default_branch(root)
    base = a.base or dflt
    base_ref = None
    if base:
        for cand in (f"origin/{base}", base):
            if git(root, "rev-parse", "--verify", "--quiet", cand):
                base_ref = cand
                break
    merge_base = git(root, "merge-base", "HEAD", base_ref).strip() if base_ref else ""
    commits = []
    if merge_base:
        for line in git(root, "log", "--format=%h%x09%s", f"{merge_base}..HEAD").splitlines():
            sha, _, subj = line.partition("\t")
            commits.append({"sha": sha, "subject": subj})

    upstream = git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").strip() or None
    ahead = behind = None
    if upstream:
        lr = git(root, "rev-list", "--left-right", "--count", f"{upstream}...HEAD").split()
        if len(lr) == 2:
            behind, ahead = int(lr[0]), int(lr[1])

    changed_vs_base = []
    if merge_base:
        for line in git(root, "diff", "--numstat", merge_base).splitlines():
            add, dele, path = (line.split("\t", 2) + ["", ""])[:3]
            changed_vs_base.append({"path": path, "added": add, "deleted": dele})

    recent = git(root, "log", "-20", "--format=%s", base_ref or "HEAD").splitlines()
    conv = sum(1 for s in recent if CONVENTIONAL.match(s))
    trailers = sorted(set(re.findall(r"^(Co-authored-by|Signed-off-by|Refs|Closes|Fixes):", git(root, "log", "-20", "--format=%B", base_ref or "HEAD"), re.M | re.I)))
    prefixes = {}
    for b in git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes/origin").splitlines():
        b = b.split("origin/", 1)[-1]
        if "/" in b:
            prefixes[b.split("/", 1)[0]] = prefixes.get(b.split("/", 1)[0], 0) + 1

    md_tracked = [p for p in git(root, "ls-files", "*.md", "*.mdx", "*.rst").splitlines() if "node_modules/" not in p]
    pr_templates = [p for p in (".github/pull_request_template.md", ".github/PULL_REQUEST_TEMPLATE.md", "docs/pull_request_template.md", "PULL_REQUEST_TEMPLATE.md") if (root / p).is_file()]
    pr_templates += [str(p.relative_to(root)) for p in sorted((root / ".github" / "PULL_REQUEST_TEMPLATE").glob("*.md"))] if (root / ".github" / "PULL_REQUEST_TEMPLATE").is_dir() else []

    work_paths = sorted({s["path"] for s in staged} | {u["path"] for u in unstaged} | set(untracked))
    out = {
        "repo_root": str(root),
        "branch": branch or None,
        "detached_head": detached,
        "default_branch": dflt,
        "base": base,
        "base_ref": base_ref,
        "merge_base": merge_base or None,
        "branch_info": classify_branch(branch, dflt) if branch else None,
        "upstream": upstream,
        "upstream_is_default_branch": bool(upstream and dflt and upstream.split("/", 1)[-1] == dflt and branch != dflt),
        "ahead": ahead,
        "behind": behind,
        "operation_in_progress": in_progress(root),
        "remotes": git(root, "remote").split(),
        "commits_on_branch": commits,
        "working_tree": {"staged": staged, "unstaged": unstaged, "untracked": untracked, "conflicted": conflicted},
        "changed_vs_base": changed_vs_base,
        "risky_paths": scan_paths(root, root, [p for p in work_paths if (root / p).exists()], cached=False),
        "test_commands": detect_tests(root),
        "guidance_files": [p for p in ("AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md", ".github/CONTRIBUTING.md") if (root / p).is_file()],
        "pr_templates": pr_templates,
        "docs": {"tracked_markdown": md_tracked[:300], "tracked_markdown_count": len(md_tracked), "changelog": next((p for p in md_tracked if Path(p).name.upper().startswith("CHANGELOG")), None)},
        "conventions": {"conventional_commits": bool(recent) and conv >= max(3, len(recent) // 2), "recent_subjects": recent[:10], "trailers_seen": trailers, "branch_prefixes": dict(sorted(prefixes.items(), key=lambda kv: -kv[1]))},
    }
    if a.check_gh:
        gh = shutil.which("gh")
        authed = bool(gh) and subprocess.run([gh, "auth", "status"], capture_output=True, text=True).returncode == 0
        out["gh"] = {"installed": bool(gh), "authenticated": authed}
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
