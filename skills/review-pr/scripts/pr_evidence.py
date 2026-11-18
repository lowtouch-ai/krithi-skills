#!/usr/bin/env python3
"""Collect a pull request's facts and the evidence of each Krithi development-process step, as JSON.

Read-only: never checks out, stages, commits, pushes or comments. It reads the PR through the gh CLI
(or a saved `gh pr view --json` file with --pr-json) and the PR's head tree through local git when the
head commit is present, otherwise through the GitHub API.

Usage:
  python3 pr_evidence.py --pr 42 [--gh-repo owner/name] [--repo-dir .] [--out FILE]
  python3 pr_evidence.py --pr-json pr.json --repo-dir <clone containing the head commit>   # offline

The `process` block gives, per step, the signals found (source; strength strong|moderate|weak|claimed|mention) and a SUGGESTED
status. The reviewer (agent) decides the final status; a missing signal is never proof a step was skipped.

Exit codes: 0 ok, 2 usage error or the PR could not be read.
"""
import argparse, base64, json, os, re, shutil, subprocess, sys
from pathlib import Path

PR_FIELDS = ("number,title,body,url,state,isDraft,author,baseRefName,headRefName,headRefOid,baseRefOid,"
             "files,commits,closingIssuesReferences,labels,statusCheckRollup,reviewDecision,additions,"
             "deletions,changedFiles,createdAt,updatedAt,headRepository,headRepositoryOwner")

# prepare-pr's PR body (skills/prepare-pr/references/commit-and-pr-format.md)
PREPARE_PR_SECTIONS = [("Summary", r"summary"), ("Changes", r"changes"), ("Review notes", r"review notes"),
                       ("Documentation", r"documentation"), ("Testing", r"testing|tests?"),
                       ("Breaking changes / deployment notes", r"breaking|deployment")]
# plan-builder's plan headings (skills/plan-builder/scripts/run_plan.py)
PLAN_HEADINGS = [("Current architecture", r"current architecture"), ("Root cause / Design approach", r"root cause|design approach"),
                 ("Files to modify", r"files to (?:modify|change)"), ("Recommended implementation", r"recommended implementation"),
                 ("Dependencies and impact", r"dependenc\w+|impact"), ("Risks and regression areas", r"risks?"),
                 ("Testing strategy", r"test"), ("Rollout and compatibility", r"rollout|compatibility"),
                 ("Acceptance criteria", r"acceptance criteria"), ("Open questions", r"open questions")]
README_FOOTER = re.compile(r"<!--\s*repo-readme-generator:\s*commit=(\w+)\s+date=([\d-]+)\s*-->")
DESCRIPTIVE_NOTE = re.compile(r"commit messages? and PR descriptions? must be descriptive", re.I)
TICKET = re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d{1,6})\b")
ISSUE_REF = re.compile(r"(?:^|[\s(])(?:([\w.-]+/[\w.-]+))?#(\d+)\b")
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec|e2e|cypress|playwright)(/|$)|[._-](test|spec)\.[a-z]+$|^test_.*\.py$|/test_[^/]*\.py$", re.I)
DOC_PATH = re.compile(r"\.(md|mdx|rst|txt|adoc)$|(^|/)docs/", re.I)
UI_PATH = re.compile(r"\.(html?|jsx|tsx|vue|svelte|astro|css|scss|less|hbs|ejs|erb|cshtml|razor|jsp)$", re.I)
VALIDATION_WORDS = re.compile(r"\b(\d+\s+(passed|passing|tests?)|all tests pass|pytest|npm (run )?test|jest|vitest|mvn|gradle|go test|cargo test|playwright|screenshot|manually (tested|verified|checked))\b", re.I)


def run(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd)
    return r.returncode, r.stdout, r.stderr


def git(repo, *args):
    code, out, _ = run(["git", "-C", str(repo), *args])
    return out if code == 0 else None


class Tree:
    """Read files at the PR head: local git first (fast, offline), then the GitHub API."""

    def __init__(self, repo_dir, gh_repo, sha, gh):
        self.repo_dir, self.gh_repo, self.sha, self.gh = repo_dir, gh_repo, sha, gh
        self.local = bool(repo_dir and sha and git(repo_dir, "cat-file", "-e", f"{sha}^{{commit}}") is not None)
        self.paths, self.source, self.error = [], None, None
        if self.local:
            self.paths = (git(repo_dir, "ls-tree", "-r", "--name-only", sha) or "").splitlines()
            self.source = "local git"
        elif gh and gh_repo and sha:
            code, out, err = run([gh, "api", f"repos/{gh_repo}/git/trees/{sha}?recursive=1"])
            if code == 0:
                data = json.loads(out)
                self.paths = [t["path"] for t in data.get("tree", []) if t.get("type") == "blob"]
                self.source = "GitHub API" + (" (truncated tree)" if data.get("truncated") else "")
            else:
                self.error = err.strip()[-300:]
        else:
            self.error = "head commit not available locally and no gh/GitHub repo to read it from"
        self._set = set(self.paths)

    def has(self, path):
        return path in self._set

    def read(self, path, limit=200_000):
        if not self.has(path):
            return None
        if self.local:
            return (git(self.repo_dir, "show", f"{self.sha}:{path}") or "")[:limit]
        code, out, _ = run([self.gh, "api", f"repos/{self.gh_repo}/contents/{path}?ref={self.sha}"])
        if code != 0:
            return None
        try:
            return base64.b64decode(json.loads(out).get("content", "")).decode("utf-8", "replace")[:limit]
        except (ValueError, KeyError):
            return None


def headings(text):
    """Lower-cased Markdown headings (and bold/numbered lines that act as headings), joined for regex search."""
    return " | ".join(re.sub(r"[#*`]", "", ln).strip().lower() for ln in (text or "").splitlines()
                      if len(ln.strip()) < 100 and re.match(r"^\s*(#{1,6}\s|\*\*|\d+[.)]\s)", ln))


def md_section(text, name):
    """Body of the first `## <name>` section (any heading level), or None."""
    m = re.search(rf"^#{{1,6}}\s*(?:{name})[^\n]*\n(.*?)(?=^#{{1,6}}\s|\Z)", text or "", re.I | re.M | re.S)
    return m.group(1).strip() if m else None


def sig(source, detail, strength):
    return {"source": source, "detail": detail, "strength": strength}


def mention(pattern, text, source, what):
    """A keyword match is only a claim, and in a repo whose subject is these tools it may just describe them.
    Quote the matched text so the reviewer can judge whether it is a statement about this PR's process."""
    m = re.search(pattern, text or "", re.I)
    if not m:
        return None
    a, b = max(0, m.start() - 70), min(len(text), m.end() + 70)
    excerpt = " ".join(text[a:b].split())
    return sig(source, f"{what}; check it is about this PR's process: \"...{excerpt}...\"", "mention")


def suggest(signals, applicable=True):
    """strong signal -> Verified; only moderate/weak/claimed -> Partially Verified; none -> Not Evidenced.
    Keyword mentions ("mention") never change the suggestion: the reviewer reads the quoted text and decides."""
    if not applicable:
        return "Not Applicable"
    kinds = {s["strength"] for s in signals} - {"mention"}
    if "strong" in kinds:
        return "Verified"
    return "Partially Verified" if kinds else "Not Evidenced"


def find_tickets(*texts):
    seen = []
    for t in texts:
        for k in TICKET.findall(t or ""):
            if k not in seen and not k.startswith(("SHA-", "UTF-", "ISO-", "RFC-", "CVE-", "WCAG-", "HTTP-")):
                seen.append(k)
    return seen


def plan_files(tree, tickets):
    """plan-builder files in the head tree, preferring those named after the PR's ticket."""
    prompts = [p for p in tree.paths if re.match(r"docs/plan-prompts/.+-codex-plan-prompt\.md$", p)]
    plans = [p for p in tree.paths if re.match(r"docs/plan-prompts/.+-implementation-plan\.md$", p)]
    prevs = [p for p in tree.paths if re.match(r"docs/plan-prompts/.+-implementation-plan\.prev\.md$", p)]

    def pick(paths):
        for t in tickets:
            hit = [p for p in paths if Path(p).name.startswith(t + "-")]
            if hit:
                return hit[0], True
        return (paths[0], False) if len(paths) == 1 else (None, False)
    return {"prompt": pick(prompts), "plan": pick(plans), "prev": pick(prevs),
            "all": sorted(prompts + plans + prevs)}


def backticked_paths(text):
    out = set()
    for m in re.findall(r"`([^`\s]+\.[A-Za-z0-9]{1,6})(?::\d+)?`", text or ""):
        if "/" in m or re.match(r"^[\w.-]+\.\w+$", m):
            out.add(m.lstrip("./"))
    return out


def evidence(pr, tree, changed_files, ci, linked_issues):
    body, title, branch = pr.get("body") or "", pr.get("title") or "", pr.get("headRefName") or ""
    commits = pr.get("commits") or []
    commit_text = "\n\n".join(f"{c.get('messageHeadline', '')}\n\n{c.get('messageBody', '')}" for c in commits)
    tickets = find_tickets(branch, title, body, commit_text, *(i.get("title", "") for i in linked_issues))
    pf = plan_files(tree, tickets)
    changed_paths = [f["path"] for f in changed_files]
    steps = {}

    # 1. README generator
    s = []
    readme = tree.read("README.md")
    if readme is None:
        if tree.paths:
            s_note = "README.md is not in the head tree"
        else:
            s_note = "head tree not readable"
    else:
        m = README_FOOTER.search(readme)
        if m:
            s.append(sig("README.md", f"repo-readme-generator footer: commit={m.group(1)} date={m.group(2)}", "strong"))
        if DESCRIPTIVE_NOTE.search(readme):
            s.append(sig("README.md", "contains repo-readme-generator's descriptive commit/PR note", "moderate"))
        s_note = None if s else "README.md exists but carries no repo-readme-generator footer"
    if tree.has("AGENTS.md"):
        s.append(sig("AGENTS.md", "AGENTS.md present (repo-readme-generator suite scope writes it)", "weak"))
    suite = [p for p in ("docs/architecture.md", "docs/codebase-map.md", "docs/development-guide.md", "docs/testing.md") if tree.has(p)]
    if suite:
        s.append(sig("docs/", f"documentation suite files: {', '.join(suite)}", "weak"))
    steps["readme_generator"] = {"signals": s, "note": s_note}

    # 2. Prompt builder (plan-builder prompt)
    s = []
    prompt_path, prompt_named = pf["prompt"]
    prompt_text = tree.read(prompt_path) if prompt_path else None
    if prompt_path:
        detail = f"{prompt_path}" + (" (named after the PR's ticket)" if prompt_named else " (only plan prompt in the repo; ticket not matched)")
        if prompt_text and "PLAN MODE ONLY" in prompt_text:
            detail += "; follows the plan-builder template (PLAN MODE ONLY clause)"
        s.append(sig("head tree", detail, "strong" if prompt_named else "moderate"))
    for t in tickets:
        home = Path(os.environ.get("KRITHI_HOME", Path.home() / ".krithi")) / t
        if home.is_dir():
            s.append(sig("local ~/.krithi", f"{home} exists on this machine (supporting artifacts; only meaningful when reviewing on the author's machine)", "weak"))
    m = mention(r"plan[- ]builder|plan prompt|prompt[- ]builder", body, "PR body", "mentions plan-builder / prompt builder")
    if m:
        s.append(m)
    steps["prompt_builder"] = {"signals": s, "note": None if s else "no docs/plan-prompts/*-codex-plan-prompt.md in the head tree"}

    # 3. Codex Plan Mode (implementation plan)
    s = []
    plan_path, plan_named = pf["plan"]
    plan_text = tree.read(plan_path) if plan_path else None
    plan_heading_hits = []
    if plan_path:
        hs = headings(plan_text)
        plan_heading_hits = [n for n, p in PLAN_HEADINGS if re.search(p, hs)]
        detail = f"{plan_path}; {len(plan_heading_hits)}/{len(PLAN_HEADINGS)} plan-builder headings"
        s.append(sig("head tree", detail, "strong" if plan_named and len(plan_heading_hits) >= 6 else "moderate"))
    m = mention(r"plan mode|implementation plan|codex plan", body + "\n" + commit_text, "PR body/commits", "mentions Plan Mode / implementation plan")
    if m:
        s.append(m)
    steps["codex_plan_mode"] = {"signals": s, "plan_headings_found": plan_heading_hits,
                                "note": None if s else "no docs/plan-prompts/*-implementation-plan.md in the head tree"}

    # 4. Plan review
    s = []
    prev_path, _ = pf["prev"]
    if prev_path:
        s.append(sig("head tree", f"{prev_path}: plan was revised with reviewer feedback (plan-builder keeps the previous plan)", "strong"))
    m = mention(r"plan (was )?(reviewed|approved|revised)|reviewed (the )?plan|approved (the )?plan|plan review", body + "\n" + commit_text,
                "PR body/commits", "says the plan was reviewed/approved")
    if m:
        s.append(m)
    if plan_path and plan_path in changed_paths:
        n = sum(1 for c in commits if plan_path in (c.get("messageBody", "") + c.get("messageHeadline", "")))
        s.append(sig("PR diff", f"{plan_path} is part of this PR" + (f" and named in {n} commit message(s)" if n else ""), "weak"))
    steps["plan_review"] = {"signals": s, "note": None if s else
                            "no revision trace; note that approving a plan without changes ('build it') leaves no artifact"}

    # 5. Implementation (traceable to the plan)
    s = []
    code_changes = [p for p in changed_paths if not DOC_PATH.search(p) and not TEST_PATH.search(p)]
    trace = None
    if code_changes:
        s.append(sig("PR diff", f"{len(code_changes)} non-doc, non-test file(s) changed", "moderate"))
    if plan_text:
        planned = backticked_paths(md_section(plan_text, r"files to (?:modify|change)") or plan_text)
        changed = set(changed_paths)
        hit = sorted(p for p in planned if p in changed or any(c.endswith("/" + p) for c in changed))
        trace = {"planned_files": sorted(planned), "planned_and_changed": hit,
                 "planned_not_changed": sorted(planned - set(hit)),
                 "changed_not_planned": sorted(c for c in changed if c not in planned and not any(c.endswith("/" + p) for p in planned) and not c.startswith("docs/plan-prompts/"))}
        if planned and hit:
            s.append(sig("plan vs diff", f"{len(hit)}/{len(planned)} planned files changed", "strong" if len(hit) >= max(1, len(planned) // 2) else "moderate"))
    steps["implementation"] = {"signals": s, "plan_traceability": trace,
                               "note": None if s else "no code changes in the diff"}

    # 6. Build and automated testing
    s = []
    if ci["total"]:
        strength = "strong" if ci["failed"] == 0 and ci["pending"] == 0 else "moderate"
        s.append(sig("CI checks", f"{ci['passed']} passed, {ci['failed']} failed, {ci['pending']} pending of {ci['total']}", strength))
    tested_commits = [c.get("oid", "")[:7] for c in commits if re.search(r"^Testing:\s*$", c.get("messageBody", ""), re.M)]
    if tested_commits:
        s.append(sig("commits", f"Testing: section (prepare-pr format) in {len(tested_commits)}/{len(commits)} commit(s): {', '.join(tested_commits)}", "claimed"))
    tsec = md_section(body, r"testing|tests?|validation")
    if tsec and VALIDATION_WORDS.search(tsec):
        s.append(sig("PR body", "Testing section lists commands/results", "claimed"))
    test_files = [p for p in changed_paths if TEST_PATH.search(p)]
    if test_files:
        s.append(sig("PR diff", f"{len(test_files)} test file(s) added/changed", "moderate"))
    steps["build_and_test"] = {"signals": s, "test_files_changed": test_files,
                               "note": None if s else "no CI checks, test files or test results found"}

    # 7. prepare-pr
    s = []
    hs = headings(body)
    sections = [n for n, p in PREPARE_PR_SECTIONS if re.search(p, hs)]
    if len(sections) >= 4:
        s.append(sig("PR body", f"prepare-pr body sections {len(sections)}/6: {', '.join(sections)}", "strong" if len(sections) >= 5 else "moderate"))
    elif sections:
        s.append(sig("PR body", f"some prepare-pr sections ({', '.join(sections)})", "weak"))
    if tested_commits:
        s.append(sig("commits", "commit body has prepare-pr's Testing: section", "moderate"))
    bodied = [c for c in commits if len((c.get("messageBody") or "").strip()) >= 80]
    if commits and len(bodied) == len(commits):
        s.append(sig("commits", "every commit has a descriptive body", "weak"))
    long_subj = [c.get("messageHeadline", "") for c in commits if len(c.get("messageHeadline", "")) > 72]
    if "/" in branch and branch not in ("main", "master"):
        s.append(sig("branch", f"feature branch `{branch}`", "weak"))
    m = mention(r"prepare[- ]pr", body + "\n" + commit_text, "PR body/commits", "mentions prepare-pr")
    if m:
        s.append(m)
    steps["prepare_pr"] = {"signals": s, "body_sections_found": sections,
                           "subjects_over_72_chars": long_subj,
                           "note": None if s else "PR body and commits do not follow prepare-pr's format"}

    # 8. PR submission (description, linked issue, validation evidence)
    s = []
    if len(body.strip()) >= 200:
        s.append(sig("PR body", f"description of {len(body.strip())} characters", "moderate"))
    elif body.strip():
        s.append(sig("PR body", "short description", "weak"))
    issues_only = [i for i in linked_issues if not i.get("is_pr")]
    prs_only = [i for i in linked_issues if i.get("is_pr")]
    if issues_only:
        s.append(sig("linked issues", ", ".join(f"#{i['number']}" for i in issues_only)
                     + ("" if any(i.get("closing") or i.get("title") for i in issues_only) else " (not verified to be issues)"),
                     "strong" if any(i.get("closing") or i.get("title") for i in issues_only) else "moderate"))
    if prs_only:
        s.append(sig("PR body", "references other PR(s), not issues: " + ", ".join(f"#{i['number']}" for i in prs_only), "weak"))
    if not issues_only and tickets:
        s.append(sig("ticket key", f"ticket key(s) referenced: {', '.join(tickets)}", "moderate"))
    if tsec and VALIDATION_WORDS.search(tsec):
        s.append(sig("PR body", "validation evidence in the Testing section", "moderate"))
    if pr.get("isDraft"):
        s.append(sig("PR state", "PR is a draft", "weak"))
    steps["pr_submission"] = {"signals": s, "note": None if s else "empty PR description, no linked issue"}

    for k, v in steps.items():
        v["suggested_status"] = suggest(v["signals"])
        v["mentions_to_judge"] = sum(1 for x in v["signals"] if x["strength"] == "mention")
    # A step that cannot be checked at all (tree unreadable) must not read as skipped.
    if not tree.paths:
        for k in ("readme_generator", "prompt_builder", "codex_plan_mode", "plan_review"):
            steps[k]["note"] = (steps[k]["note"] or "") + " (head tree could not be read: evidence unavailable, not absent)"
    return tickets, pf["all"], steps


def build_commands(tree):
    """Detect the documented install/build/test/lint commands at the PR head, so the review can run them
    without asking anyone. Returns a list of {"stack", "phase", "cmd", "source"}; empty if nothing is recognised."""
    cmds = []

    def add(stack, phase, cmd, source):
        cmds.append({"stack": stack, "phase": phase, "cmd": cmd, "source": source})

    pkg = tree.read("package.json")
    if pkg:
        try:
            scripts = (json.loads(pkg) or {}).get("scripts") or {}
        except ValueError:
            scripts = {}
        pm = "pnpm" if tree.has("pnpm-lock.yaml") else "yarn" if tree.has("yarn.lock") else "npm"
        add("node", "install", {"npm": "npm ci" if tree.has("package-lock.json") else "npm install",
                                "yarn": "yarn install --frozen-lockfile", "pnpm": "pnpm install --frozen-lockfile"}[pm], "package.json")
        for phase in ("build", "lint", "test"):
            if phase in scripts and "no test specified" not in str(scripts[phase]):
                add("node", phase, f"{pm} run {phase}" if phase != "test" else f"{pm} test", f"package.json scripts.{phase}")
    if tree.has("pyproject.toml") or tree.has("requirements.txt") or tree.has("setup.py"):
        src = next(p for p in ("pyproject.toml", "requirements.txt", "setup.py") if tree.has(p))
        if tree.has("requirements.txt"):
            add("python", "install", "python3 -m pip install -r requirements.txt", "requirements.txt")
        elif tree.has("pyproject.toml") or tree.has("setup.py"):
            add("python", "install", "python3 -m pip install -e .", src)
        if any(tree.has(p) for p in ("pytest.ini", "conftest.py", "tox.ini")) or "pytest" in (tree.read("pyproject.toml") or ""):
            add("python", "test", "python3 -m pytest -q", src)
        elif any(TEST_PATH.search(p) and p.endswith(".py") for p in tree.paths):
            add("python", "test", "python3 -m unittest discover", src)
    if tree.has("go.mod"):
        add("go", "build", "go build ./...", "go.mod"); add("go", "test", "go test ./...", "go.mod")
    if tree.has("Cargo.toml"):
        add("rust", "build", "cargo build", "Cargo.toml"); add("rust", "test", "cargo test", "Cargo.toml")
    if tree.has("pom.xml"):
        add("java", "test", "mvn -B test", "pom.xml")
    elif tree.has("gradlew") or tree.has("build.gradle") or tree.has("build.gradle.kts"):
        add("java", "test", "./gradlew test" if tree.has("gradlew") else "gradle test", "build.gradle")
    if not cmds:
        mk = tree.read("Makefile") or ""
        for phase in ("build", "lint", "test"):
            if re.search(rf"^{phase}\s*:", mk, re.M):
                add("make", phase, f"make {phase}", "Makefile")
    return cmds


def ci_summary(rollup):
    passed = failed = pending = 0
    checks = []
    for c in rollup or []:
        name = c.get("name") or c.get("context") or "check"
        concl = (c.get("conclusion") or c.get("state") or "").upper()
        status = (c.get("status") or "").upper()
        if concl in ("SUCCESS", "NEUTRAL", "SKIPPED"):
            passed += 1
        elif concl in ("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"):
            failed += 1
        else:
            pending += 1
        checks.append({"name": name, "result": concl or status or "PENDING", "url": c.get("detailsUrl") or c.get("targetUrl")})
    return {"total": len(checks), "passed": passed, "failed": failed, "pending": pending, "checks": checks}


def linked(pr, gh, gh_repo, fetch):
    """Closing issues from GitHub plus #refs in the body; fetch each issue's text when gh is available."""
    out, seen = [], set()
    for i in pr.get("closingIssuesReferences") or []:
        repo = (i.get("repository") or {}).get("nameWithOwner") or gh_repo
        out.append({"number": i.get("number"), "repo": repo, "url": i.get("url"), "closing": True})
        seen.add((repo, i.get("number")))
    for repo, num in ISSUE_REF.findall(pr.get("body") or ""):
        key = (repo or gh_repo, int(num))
        if key not in seen and key[1] != pr.get("number"):
            out.append({"number": key[1], "repo": key[0], "closing": False})
            seen.add(key)
    if fetch and gh:
        for i in out[:5]:
            code, o, _ = run([gh, "api", f"repos/{i['repo']}/issues/{i['number']}"])
            if code == 0:
                d = json.loads(o)
                i.update({"title": d.get("title"), "state": d.get("state"), "url": d.get("html_url"),
                          "is_pr": d.get("pull_request") is not None, "body": (d.get("body") or "")[:6000]})
            else:
                i["fetch_error"] = "could not read (private repo, or no access)"
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pr", help="PR number or URL")
    ap.add_argument("--gh-repo", help="owner/name (default: from the PR URL or the current repo)")
    ap.add_argument("--repo-dir", default=".", help="local clone used to read the head tree if it has the head commit")
    ap.add_argument("--pr-json", help="use a saved `gh pr view --json ...` file instead of calling gh")
    ap.add_argument("--no-issues", action="store_true", help="do not fetch linked issue text")
    ap.add_argument("--out", help="also write the JSON here")
    a = ap.parse_args()

    gh = shutil.which("gh")
    if a.pr_json:
        pr = json.loads(Path(a.pr_json).read_text(encoding="utf-8"))
    else:
        if not a.pr:
            ap.error("--pr or --pr-json is required")
        if not gh:
            print(json.dumps({"error": "the gh CLI is not installed; install it and run `gh auth login`, or pass --pr-json"}))
            return 2
        fields = PR_FIELDS.split(",")
        while True:
            cmd = [gh, "pr", "view", a.pr, "--json", ",".join(fields)] + (["--repo", a.gh_repo] if a.gh_repo else [])
            code, out, err = run(cmd, cwd=a.repo_dir if Path(a.repo_dir).is_dir() else None)
            bad = re.match(r'Unknown JSON field: "(\w+)"', err.strip())
            if code != 0 and bad and bad.group(1) in fields:
                fields.remove(bad.group(1))  # older gh versions lack some fields (e.g. baseRefOid)
                continue
            break
        if code != 0:
            print(json.dumps({"error": f"could not read PR {a.pr}: {err.strip()[:400]}"}))
            return 2
        pr = json.loads(out)
    url = pr.get("url") or ""
    m = re.search(r"github\.com/([^/]+/[^/]+)/pull/\d+", url)
    gh_repo = a.gh_repo or (m.group(1) if m else None)

    repo_dir = Path(a.repo_dir).resolve() if Path(a.repo_dir).is_dir() else None
    tree = Tree(repo_dir, gh_repo, pr.get("headRefOid"), gh if not a.pr_json else None)
    files = [{"path": f.get("path"), "additions": f.get("additions"), "deletions": f.get("deletions")} for f in pr.get("files") or []]
    ci = ci_summary(pr.get("statusCheckRollup"))
    issues = linked(pr, gh if not a.pr_json else None, gh_repo, not a.no_issues)
    tickets, plan_paths, steps = evidence(pr, tree, files, ci, issues)
    paths = [f["path"] for f in files]

    result = {
        "pr": {k: pr.get(k) for k in ("number", "title", "url", "state", "isDraft", "baseRefName", "headRefName",
                                      "headRefOid", "baseRefOid", "additions", "deletions", "changedFiles",
                                      "createdAt", "updatedAt", "reviewDecision")},
        "gh_repo": gh_repo,
        "author": (pr.get("author") or {}).get("login"),
        "body": pr.get("body") or "",
        "commits": [{"sha": (c.get("oid") or "")[:12], "subject": c.get("messageHeadline"), "body": c.get("messageBody")}
                    for c in pr.get("commits") or []],
        "files": files,
        "file_groups": {"code": [p for p in paths if not DOC_PATH.search(p) and not TEST_PATH.search(p)],
                        "tests": [p for p in paths if TEST_PATH.search(p)],
                        "docs": [p for p in paths if DOC_PATH.search(p)],
                        "ui": [p for p in paths if UI_PATH.search(p)]},
        "ci": ci,
        "linked_issues": issues,
        "tickets": tickets,
        "plan_builder_files": plan_paths,
        "head_tree": {"source": tree.source, "files": len(tree.paths), "error": tree.error,
                      "guidance_files": [p for p in ("AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md", ".github/CONTRIBUTING.md") if tree.has(p)]},
        "build_commands": build_commands(tree),
        "process": steps,
    }
    text = json.dumps(result, indent=2)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
