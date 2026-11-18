# Triage and defect reporting

Every failed, blocked or unexpectedly skipped test is triaged before anything is reported. `run_playwright.py` gives a `failure_hint`; it is a starting point, never the answer.

## 1. Classify each failure

Look at the error, the screenshot at the failure, the trace (`npx playwright show-trace <zip>`: DOM snapshot, network, console at each step), the browser console log and the app log for the same moment.

| Class | Typical evidence | What it means |
|---|---|---|
| **application** | The UI or API does the wrong thing against a requirement: wrong value shown, missing error, wrong redirect, 5xx in the app log, uncaught exception in the console caused by app code. The trace shows the test did what a user would do. | A defect in the PR (or in code it touches). |
| **test-automation** | Locator matches nothing or several elements while the screenshot shows the right UI; wrong assumption about text or timing; test depends on another test; syntax/import error; test data collision. | The test is wrong. Fix the test, re-run, and keep a record (do not report it as a defect of the app). |
| **environment** | Connection refused, app crashed for a missing service/credential, browser not installed, port conflict, a skipped test with a missing env var. | The run could not exercise the behaviour. The related cases are Blocked. |

Confirm before you classify as application:
1. Re-run the single test once (`run_playwright.py run --grep "TC-07" --label rerun-TC-07`). A pass on rerun with no code change is a **flaky** result: investigate the race (often test-automation, sometimes a real app race; say which and why).
2. Reproduce the behaviour by reading the trace or by a short manual check with Playwright (navigate, act, observe). Quote what you saw.
3. Check the requirement: is the expected behaviour really required (plan → requirement → source)? If the requirement is inferred or ambiguous, the confidence is at most **likely**.
4. Check it is not pre-existing and out of scope: run the same check against the base commit in a second worktree, or on pages the PR does not change that share the same code (for example the same check on an older post). A pre-existing defect is still reported, with `"pre_existing": true` and notes saying where else it was seen; it does not fail the PR (verdict.py) unless the PR makes it worse, in which case it is not pre-existing.

Confidence: **confirmed** (reproduced and the evidence shows it), **likely** (strong evidence, could not reproduce directly or requirement inferred), **needs-verification** (suspicion only). Only confirmed application defects can fail the validation.

## 2. Severity (application defects)

| Severity | Use when |
|---|---|
| Critical | Data loss or corruption, security hole (auth bypass, other user's data, stored XSS), crash or build failure, the main workflow of the PR cannot be completed. |
| High | An acceptance criterion is not met; wrong results users rely on; a regression in a workflow next to the change; an accessibility failure that blocks keyboard or screen-reader users from the workflow. |
| Medium | Partial or edge-case failure with a workaround; a boundary case wrong; error message missing or misleading; accessibility issue that degrades but does not block. |
| Low | Cosmetic, wording, minor console noise without user impact. |

Critical and High confirmed defects block acceptance.

## 3. Writing a defect

Write a JSON object (or a list) and record it with `defects.py add --run <run> --file <defect.json>`:

```json
{
  "title": "Quantity 0 is accepted and the line disappears",
  "classification": "application",
  "severity": "High",
  "confidence": "confirmed",
  "test_case": "TC-02",
  "requirement": "AC2",
  "expected": "Entering 0 shows \"Quantity must be at least 1\" and the quantity stays 1 (AC2, issue #7).",
  "actual": "The line is removed from the cart and no message is shown. The app log shows DELETE /api/cart/lines/3 returning 204.",
  "steps": ["Start the app at commit 1a2b3c4 (npm run start)", "Open /cart with one item", "Type 0 in Quantity and press Enter",
            "Observe: the line disappears, no alert"],
  "evidence": ["screenshots/exec-01/TC-02__rejects-a-quantity-of-0__chromium__1.png",
               "traces/exec-01/TC-02__rejects-a-quantity-of-0__chromium__2.zip", "logs/app-web.log"],
  "notes": "Reproduced twice. Not present on base 9f8e7d6."
}
```

- Steps start from a clean state and name the commit; a person must be able to reproduce without the test.
- Evidence paths are relative to the run folder and must exist (`add` refuses otherwise). Cite the app log lines in `actual` (quote them; never paste secrets).
- When you fix a test-automation problem in the run, record it and then set it to `fixed` with the reason (`defects.py update --set '{"status": "fixed"}' --by skill`), so the report shows what was corrected and why.
- Test-automation and environment entries are recorded too (classification set accordingly; severity optional), so the report shows what limited the validation.

## 4. Reviewer challenges

When the reviewer disputes a defect, re-examine the evidence (trace, screenshot, requirement source) rather than simply agreeing or defending. Then record the outcome with a reason:

```bash
defects.py update --run <run> --id D-2 --set '{"status": "withdrawn"}' --reason "Reviewer: AC2 was changed in issue comment 2026-11-17; the new behaviour (remove line) is intended. Confirmed in the issue thread." --by reviewer
defects.py update --run <run> --id D-3 --set '{"severity": "Medium"}' --reason "Workaround exists via the remove button; not an acceptance criterion." --by reviewer
```

If a challenge shows the plan or the test was wrong, update the plan and the test, re-run the affected cases (`--label rerun-...`), and re-compute the verdict.
