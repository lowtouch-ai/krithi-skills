#!/usr/bin/env python3
"""Smoke test for review-pr's scripts (offline: a temp git repo, saved PR JSON and a fake gh).
Run: python3 tests/review-pr/test_review_pr.py"""
import hashlib, json, os, stat, subprocess, sys, tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
S = root / "skills/review-pr/scripts"
tmp = Path(tempfile.mkdtemp())
env = {**os.environ, "KRITHI_HOME": str(tmp / "krithi")}
problems = []


def expect(cond, msg):
    if not cond:
        problems.append(msg)


def py(script, *a, cwd=None):
    r = subprocess.run([sys.executable, str(S / script), *map(str, a)], capture_output=True, text=True, cwd=cwd, env=env)
    try:
        j = json.loads(r.stdout)
    except ValueError:
        j = {}
    return r, j


def g(repo, *a):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *a],
                          check=True, capture_output=True, text=True).stdout.strip()


# ---------- a repository that followed the process ----------
repo = tmp / "repo"
subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
(repo / "README.md").write_text("# shop\n\nCommit messages and PR descriptions must be descriptive.\n\n"
                                "<!-- repo-readme-generator: commit=abc1234 date=2026-11-02 -->\n")
(repo / "AGENTS.md").write_text("# Agents\n")
(repo / "src").mkdir()
(repo / "src/invoice.py").write_text("def total(items):\n    return sum(items[:-1])\n")
g(repo, "add", "."); g(repo, "commit", "-q", "-m", "initial")
base_sha = g(repo, "rev-parse", "HEAD")
g(repo, "switch", "-q", "-c", "fix/ABC-12-invoice-total")
pp = repo / "docs/plan-prompts"
pp.mkdir(parents=True)
(pp / "ABC-12-codex-plan-prompt.md").write_text("> **PLAN MODE ONLY.** Do not modify.\n# ABC-12: totals\n## Objective\nFix totals.\n")
plan = ("# Plan\n## Current architecture\nx\n## Root cause\nx\n## Files to modify\n- `src/invoice.py`: fix sum\n- `src/report.py`: reuse\n"
        "## Recommended implementation\nx\n## Dependencies and impact\nx\n## Risks\nx\n## Testing strategy\nx\n"
        "## Rollout and compatibility\nx\n## Acceptance criteria\nx\n## Open questions\nnone\n")
(pp / "ABC-12-implementation-plan.md").write_text(plan)
(pp / "ABC-12-implementation-plan.prev.md").write_text(plan.replace("reuse", "old"))
(repo / "src/invoice.py").write_text("def total(items):\n    return sum(items)\n")
(repo / "tests").mkdir()
(repo / "tests/test_invoice.py").write_text("from src.invoice import total\n\ndef test_total():\n    assert total([1, 2, 3]) == 6\n")
(repo / "pyproject.toml").write_text("[project]\nname = 'shop'\n\n[tool.pytest.ini_options]\ntestpaths = ['tests']\n")
g(repo, "add", "."); g(repo, "commit", "-q", "-m", "fix: include the last line item in totals")
head_sha = g(repo, "rev-parse", "HEAD")

body = ("## Summary\nFixes ABC-12: totals dropped the last item. Closes #7.\n\n## Changes\n- sum all items\n\n"
        "## Review notes\n- none\n\n## Documentation\nNo documentation changes needed.\n\n"
        "## Testing\n- [x] `pytest`: 12 passed\n\n## Breaking changes / deployment notes\nNone\n")
good = {
    "number": 21, "title": "fix: include the last line item in totals", "body": body,
    "url": "https://github.com/acme/shop/pull/21", "state": "OPEN", "isDraft": False, "author": {"login": "dev1"},
    "baseRefName": "main", "headRefName": "fix/ABC-12-invoice-total", "headRefOid": head_sha, "baseRefOid": base_sha,
    "files": [{"path": "src/invoice.py", "additions": 1, "deletions": 1}, {"path": "tests/test_invoice.py", "additions": 4, "deletions": 0},
              {"path": "docs/plan-prompts/ABC-12-implementation-plan.md", "additions": 20, "deletions": 0}],
    "commits": [{"oid": head_sha, "messageHeadline": "fix: include the last line item in totals",
                 "messageBody": "Totals skipped the last item because of a slice; plan reviewed and revised once.\n\n- sum all items\n\nTesting:\n- pytest: 12 passed\n\nRefs: ABC-12"}],
    "closingIssuesReferences": [{"number": 7, "url": "https://github.com/acme/shop/issues/7", "repository": {"nameWithOwner": "acme/shop"}}],
    "statusCheckRollup": [{"name": "tests", "conclusion": "SUCCESS", "status": "COMPLETED"}],
}
(tmp / "good.json").write_text(json.dumps(good))
r, j = py("pr_evidence.py", "--pr-json", tmp / "good.json", "--repo-dir", repo)
expect(r.returncode == 0, f"pr_evidence failed: {r.stderr[-400:]}")
st = {k: v["suggested_status"] for k, v in j.get("process", {}).items()}
expect(j.get("head_tree", {}).get("source") == "local git", f"head tree should be read from local git: {j.get('head_tree')}")
for step in ("readme_generator", "prompt_builder", "codex_plan_mode", "plan_review", "implementation", "build_and_test", "prepare_pr", "pr_submission"):
    expect(st.get(step) == "Verified", f"followed-process PR: {step} should be Verified, got {st.get(step)}")
expect("ABC-12" in j.get("tickets", []), "ticket key ABC-12 should be found")
tr = j.get("process", {}).get("implementation", {}).get("plan_traceability") or {}
expect(tr.get("planned_and_changed") == ["src/invoice.py"] and tr.get("planned_not_changed") == ["src/report.py"], f"plan traceability: {tr}")
expect(j.get("file_groups", {}).get("tests") == ["tests/test_invoice.py"], "test files grouped")
expect(j.get("ci", {}).get("passed") == 1, "CI summary")
expect(len(j.get("process", {}).get("codex_plan_mode", {}).get("plan_headings_found", [])) == 10, "all ten plan headings")
bc = {(c["phase"], c["cmd"]) for c in j.get("build_commands", [])}
expect(("test", "python3 -m pytest -q") in bc and ("install", "python3 -m pip install -e .") in bc, f"build/test commands detected for automatic run: {bc}")

# ---------- a bare PR: no artifacts, nothing claimed -> Not Evidenced, never 'skipped' ----------
g(repo, "switch", "-q", "main")
g(repo, "switch", "-q", "-c", "wip")
(repo / "src/invoice.py").write_text("def total(items):\n    return sum(items) or 0\n")
g(repo, "commit", "-q", "-am", "update")
bare_sha = g(repo, "rev-parse", "HEAD")
(repo / "README.md").write_text("# shop\n")  # no generator footer in this branch
g(repo, "commit", "-q", "-am", "readme")
bare_sha = g(repo, "rev-parse", "HEAD")
bare = {**good, "number": 22, "title": "update", "body": "", "headRefName": "wip", "headRefOid": bare_sha,
        "files": [{"path": "src/invoice.py", "additions": 1, "deletions": 1}],
        "commits": [{"oid": bare_sha, "messageHeadline": "update", "messageBody": ""}],
        "closingIssuesReferences": [], "statusCheckRollup": []}
(tmp / "bare.json").write_text(json.dumps(bare))
r, j = py("pr_evidence.py", "--pr-json", tmp / "bare.json", "--repo-dir", repo)
st = {k: v["suggested_status"] for k, v in j.get("process", {}).items()}
for step in ("prompt_builder", "codex_plan_mode", "plan_review", "build_and_test", "prepare_pr", "pr_submission"):
    expect(st.get(step) == "Not Evidenced", f"bare PR: {step} should be Not Evidenced, got {st.get(step)}")
expect("skipp" not in r.stdout.lower() and "violat" not in r.stdout.lower(), "evidence output must never say skipped/violated")
expect("leaves no artifact" in j["process"]["plan_review"]["note"], "plan review note must explain that approval leaves no artifact")
expect(j.get("build_commands") == [], f"no recognised build files -> no commands to run: {j.get('build_commands')}")

# head commit unavailable: evidence is unavailable, not absent
(tmp / "gone.json").write_text(json.dumps({**bare, "headRefOid": "0" * 40}))
r, j = py("pr_evidence.py", "--pr-json", tmp / "gone.json", "--repo-dir", repo)
expect(r.returncode == 0 and j.get("head_tree", {}).get("error"), "unreadable head tree is reported")
expect("unavailable, not absent" in (j.get("process", {}).get("prompt_builder", {}).get("note") or ""), "unreadable tree must say unavailable, not absent")

# ---------- scorecard ----------
def card(ratings, findings=()):
    data = {"factors": {k: {"rating": v, "evidence": "e" if v is not None else ""} for k, v in ratings.items()}, "findings": list(findings)}
    p = tmp / "ratings.json"
    p.write_text(json.dumps(data))
    return py("scorecard.py", p)


allfive = dict(functional=5, quality=5, testing=5, process=5, documentation=5)
r, j = card(allfive)
expect(j.get("weighted_score") == 5.0 and j.get("recommendation") == "Approve", f"all fives approve: {j}")
r, j = card(dict(functional=4, quality=3, testing=3, process=2, documentation=4))
expect(j.get("weighted_score") == 3.25, f"weighted score 4*.3+3*.25+3*.2+2*.15+4*.1 = 3.25, got {j.get('weighted_score')}")
expect(j.get("recommendation") == "Request Changes", "score below 3.5 requests changes")
crit = [{"id": "F1", "severity": "Critical", "status": "Confirmed", "title": "SQL injection"}]
r, j = card(allfive, crit)
expect(j.get("recommendation") == "Request Changes", "a confirmed Critical must override a 5.0 score")
r, j = card(allfive, [{"id": "F1", "severity": "High", "status": "Needs verification"}])
expect(j.get("recommendation") == "Needs Further Verification", "an unverified High needs verification")
r, j = card(allfive, [{"id": "F1", "severity": "High", "status": "Withdrawn"}])
expect(j.get("recommendation") == "Approve", "a withdrawn finding does not block")
r, j = card({**allfive, "process": None})
expect(j.get("recommendation") == "Needs Further Verification" and j.get("weighted_score") == 5.0, f"unrated factor: {j}")
r, j = card({**allfive, "testing": 2})
expect(j.get("recommendation") == "Request Changes", "a factor below 3 blocks approval")
r, j = card({**allfive, "testing": 7})
expect(r.returncode == 2, "rating out of range is rejected")
r, _ = py("scorecard.py", tmp / "ratings.json", "--markdown")
r, j = card(dict(functional=4, quality=4, testing=4, process=3, documentation=4))
r2 = subprocess.run([sys.executable, str(S / "scorecard.py"), tmp / "ratings.json", "--markdown"], capture_output=True, text=True)
expect("| **Overall (weighted)** |" in r2.stdout and "**Recommendation: Approve**" in r2.stdout, "markdown scorecard")

# ---------- review log and comment posting ----------
r, j = py("review_log.py", "init", "--gh-repo", "acme/shop", "--pr", 21)
d = Path(j.get("dir", tmp / "missing"))
expect(str(d).startswith(str(tmp / "krithi" / "reviews" / "acme__shop" / "PR-21")), f"review dir under KRITHI_HOME: {d}")
(tmp / "report.md").write_text("# report v1\n")
r, j = py("review_log.py", "save", "--dir", d, "--report", tmp / "report.md", "--scorecard", tmp / "ratings.json", "--head-sha", head_sha)
expect(j.get("version") == 1, "first version")
r, j = py("review_log.py", "init", "--gh-repo", "acme/shop", "--pr", 21)
expect(j.get("last_reviewed_head") == head_sha and j.get("latest_version") == 1, f"re-init reports the last reviewed head: {j}")
r, j = py("review_log.py", "feedback", "--dir", d, "--kind", "incorrect-finding", "--finding", "F2", "--text", "F2 is guarded upstream")
learn = tmp / "krithi/review-pr/learning-log.jsonl"
expect(learn.is_file() and "F2 is guarded upstream" in learn.read_text(), "feedback goes to the learning log")
r, j = py("review_log.py", "save", "--dir", d, "--report", tmp / "report.md")
expect(r.returncode != 0, "a revision without --changes is refused")
r, j = py("review_log.py", "save", "--dir", d, "--report", tmp / "report.md", "--changes", "Withdrew F2; quality 3 -> 4")
expect(j.get("version") == 2, "second version")
hist = subprocess.run([sys.executable, str(S / "review_log.py"), "history", "--dir", d], capture_output=True, text=True, env=env).stdout
expect("incorrect-finding" in hist and "Withdrew F2" in hist, "history lists feedback and revision")

# fake gh: records calls, answers pr view and pr comment
fake = tmp / "gh"
calls = tmp / "gh-calls.txt"
fake.write_text(f"""#!/bin/sh
echo "$@" >> "{calls}"
case "$1 $2" in
  "pr view") echo '{{"number":21,"url":"https://github.com/acme/shop/pull/21","headRefOid":"{head_sha}","state":"OPEN"}}';;
  "pr comment") echo "https://github.com/acme/shop/pull/21#issuecomment-555";;
esac
""")
fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
(tmp / "draft.md").write_text("## PR review — Approve\n")
r, j = py("post_comment.py", "prepare", "--dir", d, "--body", tmp / "draft.md")
h = j.get("sha256")
expect(h == hashlib.sha256(b"## PR review \xe2\x80\x94 Approve\n").hexdigest(), "prepare prints the comment's SHA-256")
post = ["post", "--dir", d, "--gh-repo", "acme/shop", "--pr", 21, "--gh", fake, "--reviewed-sha", head_sha]
r, j = py("post_comment.py", *post, "--sha256", h)
expect(r.returncode == 2 and "not approved" in j.get("refused", ""), "posting before approval is refused")
r, j = py("review_log.py", "approve", "--dir", d, "--auto")
expect(r.returncode != 0, "automatic approval without --reason is refused")
r, j = py("review_log.py", "approve", "--dir", d, "--auto", "--reason", "quality gate passed")
expect((j.get("recorded") or {}).get("by") == "auto", f"automatic approval is labelled: {j}")
(d / "comment.md").write_text("## PR review — Approve (edited)\n")
r, j = py("post_comment.py", *post, "--sha256", h)
expect(r.returncode == 2 and "changed since it was approved" in j.get("refused", ""), "edited comment is refused")
(d / "comment.md").write_text("## PR review — Approve\n")
r, j = py("post_comment.py", "post", "--dir", d, "--gh-repo", "acme/other", "--pr", 21, "--gh", fake, "--sha256", h)
expect(r.returncode == 2 and "not acme/other#21" in j.get("refused", ""), "wrong PR is refused")
r, j = py("post_comment.py", "post", "--dir", d, "--gh-repo", "acme/shop", "--pr", 21, "--gh", fake, "--sha256", h, "--reviewed-sha", "deadbeef")
expect(r.returncode == 2 and "new commits" in j.get("refused", ""), "new commits since review are refused")
expect(not calls.exists() or "pr comment" not in calls.read_text(), "nothing may be posted by refused calls")
r, j = py("post_comment.py", *post, "--sha256", h)
expect(r.returncode == 0 and j.get("url", "").endswith("#issuecomment-555"), f"posting returns the comment URL: {j} {r.stderr[-200:]}")
r, j = py("post_comment.py", *post, "--sha256", h)
expect(r.returncode == 2 and "already posted" in j.get("refused", ""), "the same comment is not posted twice")
expect(calls.read_text().count("pr comment") == 1, "exactly one comment posted")
r, j = py("review_log.py", "status", "--dir", d)
expect(j.get("approved") is True and j.get("approved_by") == "auto" and (j.get("published") or {}).get("status") == "posted", f"status: {j}")
hist = subprocess.run([sys.executable, str(S / "review_log.py"), "history", "--dir", d], capture_output=True, text=True, env=env).stdout
expect("by auto: quality gate passed" in hist, "history shows who approved")

# ---------- line comments: one GitHub review (event COMMENT) with comments on diff lines ----------
def review_dir(pr):
    r, j = py("review_log.py", "init", "--gh-repo", "acme/shop", "--pr", pr)
    rd = Path(j["dir"])
    py("review_log.py", "save", "--dir", rd, "--report", tmp / "report.md", "--scorecard", tmp / "ratings.json", "--head-sha", head_sha)
    py("review_log.py", "approve", "--dir", rd, "--auto", "--reason", "quality gate passed")
    return rd

patch = "@@ -10,3 +10,4 @@ def total(items):\n     s = 0\n-    for i in items[:-1]:\n+    for i in items:\n+        s += i.price\n     return s"
rcalls = tmp / "gh-review-calls.txt"
fail_flag = tmp / "review-fails"
fake2 = tmp / "gh2"
fake2.write_text(f"""#!/bin/sh
echo "$@" >> "{rcalls}"
case "$*" in
  "pr view"*) echo '{{"number":22,"url":"https://github.com/acme/shop/pull/22","headRefOid":"{head_sha}","state":"OPEN"}}';;
  "pr comment"*) cp "$7" "{tmp}/sent-fallback.md"; echo "https://github.com/acme/shop/pull/22#issuecomment-777";;
  "api repos/"*"/files"*) printf '%s\\n' '{json.dumps({"filename": "src/invoice.py", "patch": patch})}';;
  "api -X POST repos/"*"/reviews"*) if [ -f "{fail_flag}" ]; then echo 'Line could not be resolved (HTTP 422)' >&2; exit 1; fi
     cp "$6" "{tmp}/sent-review.json"; echo '{{"id": 99, "html_url": "https://github.com/acme/shop/pull/22#pullrequestreview-99"}}';;
esac
""")
fake2.chmod(fake2.stat().st_mode | stat.S_IEXEC)
expect(sorted(json.loads(subprocess.run([sys.executable, "-c",
       f"import sys; sys.path.insert(0, {str(S)!r}); import post_comment, json; print(json.dumps(sorted(post_comment.diff_lines({patch!r}))))"],
       capture_output=True, text=True).stdout or "[]")) == [10, 11, 12, 13], "diff_lines returns new-side added and context lines")

inline = [{"path": "src/invoice.py", "line": 11, "body": "**F1 [High · Confirmed]** total skips the last item.\n\n**Fix:** iterate over all items."},
          {"path": "./src/invoice.py", "line": 12, "start_line": 11, "body": "Range comment"},
          {"path": "src/other.py", "line": 5, "body": "**Question:** is this guarded upstream?"}]
(tmp / "inline.json").write_text(json.dumps(inline))
(tmp / "bad-inline.json").write_text(json.dumps([{"path": "a.py", "body": "no line"}]))

d2 = review_dir(22)
r, j = py("post_comment.py", "prepare", "--dir", d2, "--body", tmp / "draft.md", "--inline", tmp / "bad-inline.json")
expect(r.returncode == 2 and "needs path" in j.get("error", ""), "invalid inline comments are rejected")
r, j = py("post_comment.py", "prepare", "--dir", d2, "--body", tmp / "draft.md", "--inline", tmp / "inline.json")
h2 = j.get("sha256")
expect(j.get("inline_comments") == 3 and h2 != h, "prepare counts line comments and hashes them with the summary")
saved = (d2 / "inline.json").read_text()
(d2 / "inline.json").write_text(saved.replace("total skips", "TOTAL SKIPS"))
post2 = ["post", "--dir", d2, "--gh-repo", "acme/shop", "--pr", 22, "--gh", fake2, "--reviewed-sha", head_sha]
r, j = py("post_comment.py", *post2, "--sha256", h2)
expect(r.returncode == 2 and "changed since it was approved" in j.get("refused", ""), "an edited line comment is refused")
(d2 / "inline.json").write_text(saved)
r, j = py("post_comment.py", *post2, "--sha256", h2)
expect(r.returncode == 0 and j.get("kind") == "review" and j.get("url", "").endswith("pullrequestreview-99"), f"review posted: {j} {r.stderr[-300:]}")
expect(j.get("inline_posted") == 2 and j.get("moved_to_summary") == 1, f"lines outside the diff move to the summary: {j}")
sent = json.loads((tmp / "sent-review.json").read_text()) if (tmp / "sent-review.json").exists() else {}
expect(sent.get("event") == "COMMENT" and sent.get("commit_id") == head_sha, "review is COMMENT only, pinned to the reviewed head")
expect([c["line"] for c in sent.get("comments", [])] == [11, 12] and sent["comments"][1].get("start_line") == 11
       and sent["comments"][1]["path"] == "src/invoice.py", "line and range comments go on the diff lines")
expect("src/other.py:5" in sent.get("body", "") and "outside this PR's diff" in sent.get("body", ""), "outside-diff comment is in the summary")
expect("pr comment" not in rcalls.read_text(), "no plain comment when the review succeeds")
r, j = py("post_comment.py", *post2, "--sha256", h2)
expect(r.returncode == 2 and "already posted" in j.get("refused", ""), "the same review is not posted twice")

fail_flag.write_text("1")
d3 = review_dir(23)
r, j = py("post_comment.py", "prepare", "--dir", d3, "--body", tmp / "draft.md", "--inline", tmp / "inline.json")
r, j = py("post_comment.py", "post", "--dir", d3, "--gh-repo", "acme/shop", "--pr", 23, "--gh", fake2, "--reviewed-sha", head_sha, "--sha256", j.get("sha256"))
fb = (tmp / "sent-fallback.md").read_text() if (tmp / "sent-fallback.md").exists() else ""
expect(r.returncode == 0 and j.get("status") == "posted-fallback" and "422" in j.get("review_error", ""), f"refused review falls back to one comment: {j}")
expect(fb.count("src/invoice.py:1") == 2 and "src/other.py:5" in fb, "fallback comment carries every line comment")
r, j = py("post_comment.py", "prepare", "--dir", d3, "--body", tmp / "draft.md")
expect(not (d3 / "inline.json").exists() and j.get("inline_comments") == 0, "preparing without --inline clears old line comments")

# Fully automated: script output must never tell the agent to go and ask the reviewer
for f in ("post_comment.py", "review_log.py", "pr_evidence.py", "scorecard.py"):
    src = (S / f).read_text().lower()
    for phrase in ("get approval", "reviewer agrees", "ask the reviewer?", "confirm with the reviewer", "show the reviewer"):
        expect(phrase not in src, f"{f} must not route decisions to the reviewer ({phrase!r})")

print("OK" if not problems else "PROBLEMS:\n- " + "\n- ".join(problems))
sys.exit(1 if problems else 0)
