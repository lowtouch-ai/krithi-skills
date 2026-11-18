#!/usr/bin/env python3
"""Offline tests for validate-pr's scripts: temp git repos, saved PR JSON, a synthetic Playwright report, local HTTP
servers. No network, no GitHub, no browser. Run: python3 tests/validate-pr/test_validate_pr.py"""
import importlib.util, json, os, socket, subprocess, sys, tempfile, time
from pathlib import Path

root = Path(__file__).resolve().parents[2]
S = root / "skills/validate-pr/scripts"
tmp = Path(tempfile.mkdtemp())
env = {**os.environ, "VALIDATE_PR_ARTIFACTS": str(tmp / "artifacts"), "GH_TOKEN": "ghp_shouldnotleak"}
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


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, S / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(S))
    spec.loader.exec_module(m)
    return m


def pr_json(owner, repo, n, sha, **kw):
    return {"number": n, "title": "Cart quantity validation", "body": "Closes #7", "url": f"https://github.com/{owner}/{repo}/pull/{n}",
            "state": "OPEN", "isDraft": False, "author": {"login": "dev1"}, "baseRefName": "main", "headRefName": "feat/qty",
            "headRefOid": sha, "baseRefOid": "0" * 40, "files": [{"path": "src/cart.ts"}], "closingIssuesReferences": [],
            "headRepository": {"name": repo}, "headRepositoryOwner": {"login": owner}, "isCrossRepository": False,
            "maintainerCanModify": False, "additions": 10, "deletions": 2, "changedFiles": 1, **kw}


# ---------- run_store: identity-based, separate folders ----------
sha1, sha2 = "a" * 40, "b" * 40
for name, data in (("acme", pr_json("Acme", "Shop", 12, sha1)), ("other", pr_json("other-org", "shop", 12, sha1)),
                   ("acme2", pr_json("Acme", "Shop", 12, sha2))):
    (tmp / f"{name}.json").write_text(json.dumps(data))
r, a1 = py("run_store.py", "init", "--pr", "https://github.com/acme/shop/pull/12", "--pr-json", tmp / "acme.json")
expect(r.returncode == 0, f"run_store init failed: {r.stderr[-300:]} {r.stdout[-300:]}")
r, o1 = py("run_store.py", "init", "--pr", "other-org/shop#12", "--pr-json", tmp / "other.json")
time.sleep(1.1)
r, a2 = py("run_store.py", "init", "--pr", "acme/shop#12", "--pr-json", tmp / "acme2.json")
run1, run_other, run2 = Path(a1["run_dir"]), Path(o1["run_dir"]), Path(a2["run_dir"])
expect(run1.parts[-5:-1] == ("github", "acme", "shop", "pr-12"), f"path should be github/<owner>/<repo>/pr-<n>: {run1}")
expect(run_other.parts[-4] == "other-org" and run_other.parent != run1.parent, "same PR number in another repo must get its own folder")
expect(run1 != run2 and run1.parent == run2.parent, "two runs of one PR must be separate folders under the same PR folder")
expect(run1.name.endswith(sha1[:12]) and run2.name.endswith(sha2[:12]), f"run folder names carry the tested commit: {run1.name}, {run2.name}")
expect(a2["previous_run"] == str(run1) and a2["previous_tested_commit_sha"] == sha1, "second run must point at the first (retest)")
m1 = json.loads((run1 / "metadata.json").read_text())
for k, v in (("pr_url", "https://github.com/Acme/Shop/pull/12"), ("repository_url", "https://github.com/Acme/Shop"),
             ("tested_commit_sha", sha1), ("validation_status", "in-progress"), ("pr_number", 12)):
    expect(m1.get(k) == v, f"metadata {k} should be {v!r}, got {m1.get(k)!r}")
expect(m1.get("started_at"), "metadata needs a timestamp")
expect(all((run1 / s).is_dir() for s in ("results", "screenshots", "traces", "logs", "defects", "report")), "run subfolders")
r, lst = py("run_store.py", "list", "--pr", "acme/shop#12")
expect(len(lst.get("runs", [])) == 2, f"list should show both runs of acme/shop#12: {lst}")
r, _ = py("run_store.py", "set", "--run", run1, "--json", '{"tested_commit_sha": "c"}')
expect(r.returncode != 0, "the tested commit of a run must not be changeable")

# ---------- inspect_repo ----------
app = tmp / "app"
(app / "src/app/cart").mkdir(parents=True)
(app / "package.json").write_text(json.dumps({"scripts": {"dev": "next dev -p 3001", "build": "next build", "start": "next start -p 3001"},
                                              "dependencies": {"next": "15"}}))
(app / "package-lock.json").write_text("{}")
(app / "src/app/cart/page.tsx").write_text("export default function P(){return null}")
(app / ".env.example").write_text("DATABASE_URL=postgres://localhost/db\nNEXTAUTH_SECRET=\n")
r, ins = py("inspect_repo.py", "--repo-dir", app, "--changed-files", "src/app/cart/page.tsx")
expect(r.returncode == 0, f"inspect_repo failed: {r.stderr[-300:]}")
expect(any(s.get("framework") == "Next.js" for s in ins.get("stacks", [])), f"Next.js should be detected: {ins.get('stacks')}")
expect(any(c["port"] == 3001 and "start" in c["cmd"] for c in ins.get("launch_candidates", [])), f"start on 3001: {ins.get('launch_candidates')}")
expect(any(s["cmd"] == "npm ci" for s in ins.get("setup_commands", [])), "npm ci with a lockfile")
expect(ins.get("playwright", {}).get("runner") == "none" and ins["playwright"]["proposed_layout"]["testDir"] == "tests/e2e", "proposed layout for a repo without Playwright")
expect({"route": "/cart", "file": "src/app/cart/page.tsx"} in ins.get("routes_for_changes", []), f"route for changed page: {ins.get('routes_for_changes')}")
expect("postgres" in ins.get("requirements", {}).get("services", []), "postgres service hint from .env.example")
pyapp = tmp / "pyapp"
pyapp.mkdir()
(pyapp / "requirements.txt").write_text("flask\npytest-playwright\n")
(pyapp / "web.py").write_text("from flask import Flask\napp = Flask(__name__)\n")
r, ins2 = py("inspect_repo.py", "--repo-dir", pyapp)
expect(any("flask --app web:app" in c["cmd"] for c in ins2.get("launch_candidates", [])), f"flask launch: {ins2.get('launch_candidates')}")
expect(ins2.get("playwright", {}).get("runner") == "python", "pytest-playwright should select the python runner")
empty = tmp / "empty"; empty.mkdir(); (empty / "notes.txt").write_text("x")
r, ins3 = py("inspect_repo.py", "--repo-dir", empty)
expect(not ins3.get("launch_candidates") and ins3.get("notes"), "unknown stack: no candidates and a note to record a blocker")

# ---------- app_runner: launch failure, success, port conflict, cleanup ----------
r, j = py("app_runner.py", "start", "--run", run1, "--cwd", tmp, "--name", "web", "--url", f"http://127.0.0.1:{free_port()}",
          "--timeout", "10", "--", f"{sys.executable} -c \"import sys; print('DATABASE_URL is not set'); sys.exit(3)\"")
expect(r.returncode == 3 and j.get("status") == "BLOCKED", f"an app that exits must be BLOCKED (exit 3): {r.returncode} {j}")
expect("DATABASE_URL is not set" in j.get("log_tail", ""), "the blocker must carry the app log tail")
mb = json.loads((run1 / "metadata.json").read_text())["app"]
expect(mb.get("ready") is False and "exited with code 3" in (mb.get("blocker") or {}).get("reason", ""), f"blocker in metadata: {mb}")
r, j = py("app_runner.py", "step", "--run", run1, "--cwd", tmp, "--name", "install", "--",
          sys.executable, "-c", "import os; print('TOKEN=' + str(os.environ.get('GH_TOKEN')))")
expect(r.returncode == 0 and "TOKEN=None" in (run1 / "logs/setup-install.log").read_text(), "GH_TOKEN must be stripped from launched commands")
port = free_port()
r, j = py("app_runner.py", "start", "--run", run2, "--cwd", tmp, "--name", "web", "--url", f"http://127.0.0.1:{port}", "--timeout", "20",
          "--", f"{sys.executable} -m http.server {port} --bind 127.0.0.1")
expect(r.returncode == 0 and j.get("status") == "READY", f"http.server should be READY: {r.returncode} {j} {r.stderr[-300:]}")
r2, j2 = py("app_runner.py", "start", "--run", run_other, "--cwd", tmp, "--name", "web", "--url", f"http://127.0.0.1:{port}",
            "--", f"{sys.executable} -m http.server {port}")
expect(r2.returncode == 3 and "already in use" in j2.get("reason", ""), "a port already in use must block, not test another app")
r, j = py("app_runner.py", "stop-all", "--run", run2)
time.sleep(0.5)
with socket.socket() as s:
    expect(s.connect_ex(("127.0.0.1", port)) != 0, "stop-all must free the port")

# ---------- test_plan: traceability ----------
repo = tmp / "repo"
subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
(repo / "src").mkdir(); (repo / "src/cart.ts").write_text("export const max = 99;\n")
(repo / "package.json").write_text(json.dumps({"name": "shop", "scripts": {"start": "node s.js"}, "devDependencies": {}}, indent=2))
g(repo, "add", "."); g(repo, "commit", "-q", "-m", "init")
(repo / "docs/test-plans").mkdir(parents=True)
(repo / "tests/e2e").mkdir(parents=True)
plan = """# Test plan: PR #12

## Requirements and acceptance criteria

| ID | Requirement / acceptance criterion | Source |
|---|---|---|
| R1 | Quantity can be 1 to 99 | Issue #7 |
| AC2 | 0 shows an error | Issue #7 |

## Test cases

| ID | Scenario | Category | Requirement | Priority | Execution | Spec |
|---|---|---|---|---|---|---|
| TC-01 | Set quantity 3 | positive | R1 | Required | Automated | tests/e2e/cart.spec.ts |
| TC-02 | Enter 0 | negative | AC2 | Required | Automated | tests/e2e/cart.spec.ts |
| TC-03 | Enter 99 and 100 | boundary | R1 | Optional | Automated | tests/e2e/cart.spec.ts |
| TC-04 | Screen reader reads the error | accessibility | AC2 | Required | Manual | — |
"""
(repo / "docs/test-plans/pr-12-test-plan.md").write_text(plan)
spec = ("import { test, expect } from './fixtures/validate-fixtures';\n"
        "test('TC-01 sets quantity', async ({ page }) => {});\ntest('TC-02 rejects 0', async ({ page }) => {});\n"
        "test('TC-03 boundaries', async ({ page }) => {});\n")
(repo / "tests/e2e/cart.spec.ts").write_text(spec)
r, tp = py("test_plan.py", "check", "--plan", "docs/test-plans/pr-12-test-plan.md", "--repo-dir", repo, "--ui-changed", "--run", run1)
expect(r.returncode == 0 and not tp.get("errors"), f"a traceable plan must pass: {tp.get('errors')}")
expect(any("TC-04" in w and "Manual" in w for w in tp.get("warnings", [])), "Required+Manual must be warned")
expect(tp["coverage"]["AC2"]["manual"] == ["TC-04"], "coverage should list manual cases per requirement")
expect((run1 / "report/test-plan-parsed.json").is_file(), "--run records the parsed plan in the run folder")
(repo / "tests/e2e/cart.spec.ts").write_text(spec.replace("TC-03 boundaries", "boundaries") + "test('TC-09 extra', async () => {});\n")
r, tp = py("test_plan.py", "check", "--plan", "docs/test-plans/pr-12-test-plan.md", "--repo-dir", repo)
errs = " ".join(tp.get("errors", []))
expect(r.returncode == 1 and "TC-03" in errs and "TC-09" in errs, f"missing TC title and unplanned TC must fail: {tp.get('errors')}")
(repo / "tests/e2e/cart.spec.ts").write_text(spec)

# ---------- run_playwright: collection from a Playwright JSON report ----------
rp = load_module("run_playwright")
ex = run1 / "results" / "exec-01-initial"
ex.mkdir(parents=True)
shot = tmp / "shot.png"; shot.write_bytes(b"\x89PNG fake")
trace = tmp / "trace.zip"; trace.write_bytes(b"PK fake")
report = {"suites": [{"title": "cart.spec.ts", "file": "tests/e2e/cart.spec.ts", "specs": [], "suites": [{"title": "Cart", "specs": [
    {"title": "TC-01 sets quantity", "file": "tests/e2e/cart.spec.ts", "line": 2, "tests": [{"projectName": "chromium", "status": "expected",
     "results": [{"status": "passed", "duration": 900, "attachments": [{"name": "screenshot", "contentType": "image/png", "path": str(shot)}]}]}]},
    {"title": "TC-02 rejects 0", "file": "tests/e2e/cart.spec.ts", "line": 3, "tests": [{"projectName": "chromium", "status": "unexpected",
     "results": [{"status": "failed", "duration": 1200, "errors": [{"message": "\x1b[31mError: expect(locator).toHaveText(expected)\x1b[39m\nExpected: \"Quantity must be at least 1\"\nReceived: \"\""}],
                  "attachments": [{"name": "screenshot", "contentType": "image/png", "path": str(shot)},
                                  {"name": "trace", "contentType": "application/zip", "path": str(trace)},
                                  {"name": "console-errors", "contentType": "application/json", "body": json.dumps(["pageerror: boom"])}]}]}]},
    {"title": "untagged smoke", "file": "tests/e2e/cart.spec.ts", "line": 9, "tests": [{"projectName": "chromium", "status": "skipped", "results": [{"status": "skipped"}]}]},
]}]}]}
(ex / "playwright-report.json").write_text(json.dumps(report))
tests, errs = rp.collect_node(run1, ex, 1)
by = {t["test_case"]: t for t in tests}
expect(by["TC-01"]["outcome"] == "passed" and by["TC-02"]["outcome"] == "failed", f"outcomes: {[(t['test_case'], t['outcome']) for t in tests]}")
expect("\x1b" not in (by["TC-02"]["error"] or "") and by["TC-02"]["failure_hint"].startswith("application"), f"ANSI stripped, assertion hint: {by['TC-02']}")
ev = by["TC-02"]["evidence"]
expect(ev["screenshots"] and ev["traces"] and ev["browser_logs"], f"TC-02 evidence copied into the run folder: {ev}")
expect(all((run1 / p).is_file() and p.startswith(("screenshots/", "traces/", "logs/")) for k in ev for p in ev[k]), "evidence paths are run-relative and exist")
expect(by["TC-02"]["title"] == "Cart › TC-02 rejects 0", f"describe titles are kept, file titles dropped: {by['TC-02']['title']}")
summ = rp.merge_summary(run1, {"id": "exec-01-initial"}, tests)
expect(summ["test_cases"] == {"TC-01": "passed", "TC-02": "failed"} and summ["totals"]["skipped"] == 1, f"summary: {summ['test_cases']} {summ['totals']}")
rerun = [dict(by["TC-02"], outcome="passed", error=None)]
summ = rp.merge_summary(run1, {"id": "exec-02-rerun"}, rerun)
expect(summ["test_cases"]["TC-02"] == "passed" and len(summ["executions"]) == 2, "a rerun's result replaces the earlier one; both executions are kept")
summ = rp.merge_summary(run1, {"id": "exec-03-rerun"}, [dict(by["TC-02"])])
renamed = [dict(by["TC-01"], title="Cart › TC-01 sets quantity to 3", outcome="failed")]
summ = rp.merge_summary(run1, {"id": "exec-04-renamed"}, renamed)
expect([t["title"] for t in summ["tests"] if t["test_case"] == "TC-01"] == ["Cart › TC-01 sets quantity to 3"] and summ["test_cases"]["TC-01"] == "failed",
       "a renamed test supersedes its old result for the same TC")
expect(any(t["title"] == "Cart › TC-01 sets quantity" for t in summ["superseded"]), "the old result is kept under superseded")
r, _ = py("run_playwright.py", "run", "--run", run_other, "--cwd", repo, "--base-url", "http://127.0.0.1:1")
expect(r.returncode == 2 and "not recorded as ready" in r.stdout, "tests must not run when the app is not ready")

# ---------- defects ----------
shot_rel = by["TC-02"]["evidence"]["screenshots"][0]
bad = {"title": "Zero accepted", "classification": "application", "confidence": "confirmed", "test_case": "TC-02",
       "expected": "error", "actual": "no error", "steps": ["open /cart", "type 0"], "evidence": [shot_rel]}
(tmp / "bad.json").write_text(json.dumps(bad))
r, j = py("defects.py", "add", "--run", run1, "--file", tmp / "bad.json")
expect(r.returncode == 2 and "severity" in json.dumps(j), "an application defect without severity/requirement is refused")
good = {**bad, "severity": "High", "requirement": "AC2"}
(tmp / "good.json").write_text(json.dumps([good, {**good, "title": "Missing file", "evidence": ["screenshots/nope.png"]}]))
r, j = py("defects.py", "add", "--run", run1, "--file", tmp / "good.json")
expect(r.returncode == 2 and "does not exist" in json.dumps(j), "evidence that does not exist is refused (and nothing is recorded)")
auto = {"title": "Locator matched 2 buttons", "classification": "test-automation", "confidence": "confirmed", "test_case": "TC-03",
        "expected": "one Save button", "actual": "strict mode violation", "steps": ["run TC-03"], "evidence": [shot_rel]}
(tmp / "good.json").write_text(json.dumps([good, auto]))
r, j = py("defects.py", "add", "--run", run1, "--file", tmp / "good.json")
expect(r.returncode == 0 and j.get("added") == ["D-1", "D-2"], f"defects recorded: {j}")
expect((run1 / "defects/D-1.md").is_file() and "## Steps to reproduce" in (run1 / "defects/D-1.md").read_text(), "a Markdown page per defect")
md = json.loads((run1 / "metadata.json").read_text())["defects"]
expect(md["application_confirmed_open"] == 1 and md["by_severity"]["High"] == 1 and md["test_automation_open"] == 1, f"metadata defect counts: {md}")
r, j = py("defects.py", "update", "--run", run1, "--id", "D-1", "--set", '{"severity": "Medium"}')
expect(r.returncode == 2, "a reviewer change needs a reason")
r, j = py("defects.py", "update", "--run", run1, "--id", "D-1", "--set", '{"severity": "Medium"}', "--reason", "workaround exists")
expect(r.returncode == 0 and "High" in j.get("change", ""), f"severity change recorded: {j}")
py("defects.py", "update", "--run", run1, "--id", "D-1", "--set", '{"severity": "High"}', "--reason", "re-checked: AC2 is an acceptance criterion")

# retest: run2 (new commit) -- TC-02 now passes, a new defect appears on TC-01
(run2 / "results/summary.json").write_text(json.dumps({"test_cases": {"TC-01": "failed", "TC-02": "passed"}, "tests": [], "executions": []}))
(run2 / "screenshots/x.png").write_bytes(b"x")
new = {**good, "title": "Total not updated", "test_case": "TC-01", "requirement": "R1", "evidence": ["screenshots/x.png"]}
(tmp / "new.json").write_text(json.dumps(new))
py("defects.py", "add", "--run", run2, "--file", tmp / "new.json")
r, cmp_ = py("defects.py", "compare", "--run", run2, "--previous", run1)
states = {(x["previous_id"], x["state"]) for x in cmp_.get("rows", [])}
expect(("D-1", "Resolved") in states and (None, "New") in states, f"retest comparison: {cmp_.get('rows')}")
expect(cmp_.get("previous_commit") == sha1 and cmp_.get("current_commit") == sha2, "comparison names both commits")
expect((run1 / "defects/D-1.md").is_file(), "the previous run's evidence is preserved")

# ---------- verdict (decide_status is the reviewer's policy; these are the cases the definitions settle) ----------
vd = load_module("verdict")


def facts(**kw):
    base = {"app_ready": True, "app_blocker": None, "setup_failures": [], "tests_executed": True, "execution_error": None, "plan_errors": [],
            "required_automated": ["TC-01", "TC-02"], "required_manual": [], "outcomes": {"TC-01": "passed", "TC-02": "passed"},
            "required_without_result": [], "required_not_passed": {}, "blocking_defects": [], "confirmed_app_defects": [],
            "unconfirmed_app_defects": [], "defects_by_test_case": {}, "pre_existing_defects": []}
    base.update(kw)
    return base


try:
    cases = [
        ("all required pass, nothing open", facts(), "Passed"),
        ("app did not launch", facts(app_ready=False, app_blocker="exited 3", tests_executed=False, outcomes={},
                                     required_without_result=["TC-01", "TC-02"]), "Blocked"),
        ("confirmed High defect", facts(outcomes={"TC-01": "passed", "TC-02": "failed"}, required_not_passed={"TC-02": "failed"},
                                        blocking_defects=["D-1"], confirmed_app_defects=[{"id": "D-1", "severity": "High", "test_case": "TC-02"}],
                                        defects_by_test_case={"TC-02": [{"id": "D-1", "classification": "application", "confidence": "confirmed", "severity": "High"}]}), "Failed"),
        ("required manual case left", facts(required_manual=["TC-04"]), "Needs Manual Verification"),
        ("confirmed Medium on a Required case", facts(outcomes={"TC-01": "passed", "TC-02": "failed"}, required_not_passed={"TC-02": "failed"},
         confirmed_app_defects=[{"id": "D-1", "severity": "Medium", "test_case": "TC-02"}],
         defects_by_test_case={"TC-02": [{"id": "D-1", "classification": "application", "confidence": "confirmed", "severity": "Medium"}]}), "Failed"),
        ("confirmed Medium on an Optional case", facts(outcomes={"TC-01": "passed", "TC-02": "passed", "TC-03": "failed"},
         confirmed_app_defects=[{"id": "D-1", "severity": "Medium", "test_case": "TC-03"}]), "Passed"),
        ("High defect wins over a blocked case", facts(outcomes={"TC-01": "failed"}, required_without_result=["TC-02"],
         required_not_passed={"TC-01": "failed"}, blocking_defects=["D-1"]), "Failed"),
        ("required case skipped (missing credentials)", facts(outcomes={"TC-01": "passed", "TC-02": "skipped"},
         required_not_passed={"TC-02": "skipped"}), "Blocked"),
        ("required case failed on a test problem", facts(outcomes={"TC-01": "passed", "TC-02": "failed"}, required_not_passed={"TC-02": "failed"},
         defects_by_test_case={"TC-02": [{"id": "D-2", "classification": "test-automation", "confidence": "confirmed", "severity": None}]}),
         "Needs Manual Verification"),
        ("required case fails only on a pre-existing High defect", facts(outcomes={"TC-01": "passed", "TC-02": "failed"},
         required_not_passed={"TC-02": "failed"}, pre_existing_defects=["D-3"],
         confirmed_app_defects=[{"id": "D-3", "severity": "High", "test_case": "TC-02"}],
         defects_by_test_case={"TC-02": [{"id": "D-3", "classification": "application", "confidence": "confirmed", "severity": "High",
                                          "pre_existing": True}]}), "Needs Manual Verification"),
        ("required case failed on an environment issue", facts(outcomes={"TC-01": "passed", "TC-02": "failed"},
         required_not_passed={"TC-02": "failed"},
         defects_by_test_case={"TC-02": [{"id": "D-5", "classification": "environment", "confidence": "confirmed", "severity": None}]}), "Blocked"),
        ("tests never executed", facts(tests_executed=False, outcomes={}, execution_error="browsers missing"), "Blocked"),
    ]
    for name, f, want in cases:
        got, reasons = vd.decide_status(f)
        expect(got == want, f"verdict '{name}': expected {want}, got {got} ({reasons})")
        expect(reasons and all(isinstance(x, str) and x for x in reasons), f"verdict '{name}': needs non-empty reasons")
except NotImplementedError:
    print("NOTE: verdict.decide_status() is not implemented yet; verdict cases skipped")

# ---------- commit_tests: only test artifacts, only the approved change ----------
(repo / "src/cart.ts").write_text("export const max = 100;\n")  # an 'app fix' the skill must never commit
r, j = py("commit_tests.py", "prepare", "--run", run2, "--worktree", repo, "--", "src/cart.ts", "tests/e2e/cart.spec.ts")
expect(r.returncode == 2 and "src/cart.ts" in j.get("not_test_artifacts", []), f"application code must be refused: {j}")
(repo / "tests/e2e/login.spec.ts").write_text("const password = 'hunter2hunter2';\n")
r, j = py("commit_tests.py", "prepare", "--run", run2, "--worktree", repo, "--", "tests/e2e/login.spec.ts")
expect(r.returncode == 2 and j.get("possible_secrets"), "hard-coded credentials must be refused")
(repo / "tests/e2e/login.spec.ts").unlink()
pkg = json.loads((repo / "package.json").read_text())
pkg["devDependencies"]["@playwright/test"] = "1.50.0"
(repo / "package.json").write_text(json.dumps(pkg, indent=2))
r, prep = py("commit_tests.py", "prepare", "--run", run2, "--worktree", repo, "--", "docs/test-plans", "tests/e2e/cart.spec.ts", "package.json")
expect(r.returncode == 0 and prep.get("files", {}).get("package.json") == "dev dependencies", f"plan, spec and devDependency change allowed: {prep} {r.stderr[-300:]}")
expect((run2 / "report/test-changes.patch").is_file(), "the patch is saved in the run folder for the reviewer")
pkg["dependencies"] = {"left-pad": "1"}
(repo / "package.json").write_text(json.dumps(pkg, indent=2))
r, j = py("commit_tests.py", "prepare", "--run", run2, "--worktree", repo, "--", "package.json")
expect(r.returncode == 2, "a runtime dependency change in package.json is not a test change")
del pkg["dependencies"]
(repo / "package.json").write_text(json.dumps(pkg, indent=2))
r, prep = py("commit_tests.py", "prepare", "--run", run2, "--worktree", repo, "--", "docs/test-plans", "tests/e2e/cart.spec.ts", "package.json")
(tmp / "msg.txt").write_text("test(e2e): add validation plan and Playwright tests for PR #12\n")
r, j = py("commit_tests.py", "commit", "--run", run2, "--worktree", repo, "--sha256", "0" * 64, "--message-file", tmp / "msg.txt")
expect(r.returncode == 2 and "not the one the reviewer approved" in j.get("refused", ""), "commit with a different hash is refused")
r, j = py("commit_tests.py", "commit", "--run", run2, "--worktree", repo, "--sha256", prep["sha256"], "--message-file", tmp / "msg.txt")
expect(r.returncode == 0 and j.get("committed"), f"approved commit: {j} {r.stderr[-300:]}")
committed = g(repo, "show", "--name-only", "--format=", "HEAD").splitlines()
expect("src/cart.ts" not in committed and "tests/e2e/cart.spec.ts" in committed, f"only test artifacts committed: {committed}")
expect(g(repo, "status", "--porcelain", "src/cart.ts"), "the application change stays uncommitted")
# push to the PR head branch (a local bare repo stands in for GitHub)
remote = tmp / "remote"
subprocess.run(["git", "clone", "-q", "--bare", str(repo), str(remote) + ".git"], check=True)
mp = json.loads((run2 / "metadata.json").read_text())
mp["head_repository"]["url"] = str(remote)
mp["head_ref"] = "feat/qty"
(run2 / "metadata.json").write_text(json.dumps(mp))
r, j = py("commit_tests.py", "push", "--run", run2, "--worktree", repo, "--sha256", prep["sha256"])
expect(r.returncode == 0 and j.get("branch") == "feat/qty", f"push to the PR branch: {j} {r.stderr[-300:]}")
r, j = py("commit_tests.py", "push", "--run", run2, "--worktree", repo, "--sha256", prep["sha256"])
expect(r.returncode == 2, "the same commit is not pushed twice")
mp["head_repository"].update(is_fork=True, maintainer_can_modify=False)
(run2 / "metadata.json").write_text(json.dumps(mp))
hist = [json.loads(l) for l in (run2 / "history.jsonl").read_text().splitlines()]
(run2 / "history.jsonl").write_text("".join(json.dumps(e) + "\n" for e in hist if e["event"] != "test_changes_pushed"))
r, j = py("commit_tests.py", "push", "--run", run2, "--worktree", repo, "--sha256", prep["sha256"])
expect(r.returncode == 2 and "handover" in j, "a fork without maintainer edits gets the patch, not a push")

if problems:
    print(f"FAILED ({len(problems)}):")
    for p in problems:
        print(" -", p)
    sys.exit(1)
print("validate-pr: all checks passed")
