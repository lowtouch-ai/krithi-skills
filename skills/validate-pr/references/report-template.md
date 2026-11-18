# Validation report template

Save as `<run>/report/validation-report.md`. Every result links to evidence in the run folder (relative links) and every test case links back to the committed plan and spec at the tested commit (`https://github.com/<owner>/<repo>/blob/<sha>/<path>`). Fill every section; write "None" rather than deleting one.

```markdown
# Validation report: <owner>/<repo> PR #<n>

**Status: <Passed | Failed | Blocked | Needs Manual Verification>**
<the reasons from verdict.py, one bullet each>

| | |
|---|---|
| GitHub owner / repository | <owner> / <repo> |
| Pull request | [#<n> <title>](<PR URL>) (<state>, <draft?>), author <login>, <base> ← <head> |
| Tested commit | [`<full sha>`](<repository URL>/commit/<sha>) |
| Run | `<run folder>` (started <UTC>, finished <UTC>) |
| Previous run | `<path>` at `<sha>` or "first run" |
| Test plan | [<plan path>](<repo URL>/blob/<sha or commit with tests>/<plan path>) (SHA-256 `<first 12>`) |
| Playwright tests | [<spec path>](<link>), ... |
| Test changes | prepared / committed `<sha>` / pushed to `<branch>` / not committed (patch: `report/test-changes.patch`) |

## Summary

3 to 5 sentences: what the PR does, what was validated, the outcome, and the most important defect or limitation.

## Test environment and application startup

| Item | Value |
|---|---|
| Machine | <os, arch> |
| Runtimes | <node, python, java...> |
| Playwright | <version>, browsers/projects <list> |
| Setup steps | `<cmd>` (<exit>, <s>s, [log](logs/setup-install.log)), ... |
| Launch | `<cmd>` in `<cwd>` (source: <README / webServer / detected>) |
| URL / ready | <url>, HTTP <status> after <s>s, [app log](logs/app-web.log) |
| Configuration | env vars set (names only), services used, stubs |
| Cleanup | processes stopped, worktree removed |

## Requirements and acceptance criteria coverage

| Requirement | Source | Test cases | Result |
|---|---|---|---|
| R1: ... | Issue #7 | TC-01, TC-03 | Met / Not met (D-2) / Partly / Not verified (Blocked) / Manual pending |

Requirements confidence: High / Medium / Low (inferred), and why.

## Results

| Passed | Failed | Blocked | Skipped | Flaky | Total |
|---:|---:|---:|---:|---:|---:|

| Test case | Scenario | Category | Priority | Result | Evidence | Defect |
|---|---|---|---|---|---|---|
| TC-01 | ... | positive | Required | passed | [screenshot](screenshots/...), [trace](traces/...) | — |
| TC-02 | ... | negative | Required | failed | [screenshot](...), [trace](...), [console](logs/browser/...) | D-1 |

Executions in this run: `exec-01-initial` (command, exit code), `exec-02-rerun-TC-02` ...

## Defects

By severity (open, confirmed application defects first):

| ID | Severity | Class | Confidence | Test case | Requirement | Title |
|---|---|---|---|---|---|---|

For each application defect: expected, actual, reproduction steps and evidence (from `defects/D-<n>.md`).

Test-automation issues (fixed or open) and environment issues are listed separately with their effect on coverage.

## Retest comparison (retests only)

From `defects.py compare --markdown`: Resolved / Still open / Needs verification / New, with the previous and current commit.

## Manual verification needed

Each Manual case and each Blocked case: steps, expected result, why it is not automated or not run.

## Environment limitations and untested scenarios

What could not be exercised and why (missing credentials, services, browsers, third-party calls stubbed, time limits).

## Recommendation

One paragraph for the reviewer: accept, request changes (list the defects that must be fixed), unblock (what to provide), or verify manually (which cases). The status above is computed by `verdict.py`; if your judgement differs, say so here without changing it.

## Validation history

From `history.jsonl`: executions, defect changes with reasons, reviewer feedback, commits and pushes.
```

## metadata.json fields (written by the scripts)

`pr_url`, `repository_url`, `owner`, `repository`, `pr_number`, `tested_commit_sha`, `base_commit_sha`, `head_ref`, `started_at`, `finished_at`, `validation_status`, `status_reasons`, `previous_run`, `environment`, `app` (setup steps, launch command, url, ready, blocker), `tests` (totals, outcome per test case), `committed_artifacts` (test plan path and SHA-256, spec SHA-256s, prepared patch hash, commit, push target), `defects` (counts), `retest` (comparison counts).
