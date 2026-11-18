# Test planning

How to turn a PR into a test plan that `scripts/test_plan.py check` accepts and that reviewers can trace.

## 1. Sources of requirements (best first)

1. Context in the request (exercise brief, acceptance criteria).
2. Linked issues (`metadata.json linked_issues`; read with `gh issue view <n> --repo <r> --comments`).
3. Tickets named in the PR (`ABC-123`), read with any connected tracker tool. Unreadable: say so and continue.
4. plan-builder files on the PR head: `docs/plan-prompts/<TICKET>-codex-plan-prompt.md` (Expected behavior, Acceptance criteria) and `<TICKET>-implementation-plan.md` (Acceptance criteria, Testing strategy, Risks and regression areas).
5. A review-pr report for the same PR, if one exists in `~/.krithi/reviews/<owner>__<repo>/PR-<n>/`: its requirements list (R1..Rn) and "missing test scenarios" are direct inputs.
6. PR title, description and commit messages (the author's claim).
7. Inferred from the diff: new unit tests, changed help text, changed routes and forms. Mark each **(inferred)** in the Source column.

Write each requirement as one checkable statement. Split acceptance criteria into their own rows (`AC1`, `AC2`) when the source lists them; otherwise use `R1..Rn`.

## 2. Understand the change

- Map changed files to **components** (page, form, API route, service, model) and to **user workflows** (what a user does that reaches this code). `inspect_repo.py` gives `routes_for_changes` for file-system routers; for other frameworks read the router (`urls.py`, `routes/*.ts`, controllers).
- Note what the change can break: callers of changed functions, shared components, changed API contracts, migrations. These become **regression** cases.
- Read the existing tests (unit and e2e) for the area: what is already covered, which helpers, page objects and fixtures exist. Reuse them; do not plan cases the existing suite already proves unless the PR changes that behaviour.

## 3. Scenario categories

Plan at least one case per relevant category, and say in the plan why a category does not apply.

| Category | What to cover |
|---|---|
| positive | Each acceptance criterion's main path, end to end through the UI (or the API for API-only changes). |
| negative | Invalid input, missing required fields, unauthorised user, server error shown to the user, double submit. |
| boundary | Empty, one, many; min/max lengths and values; pagination edges; long text; special characters and Unicode; time zones and dates where relevant. |
| accessibility | When UI changed: keyboard-only completion of the workflow, visible focus, accessible names (`getByRole` finds every control), form errors announced (`role=alert` / `aria-live`), and an axe scan of the changed page when `@axe-core/playwright` is available (WCAG 2.2 AA tags). |
| regression | Workflows next to the change that must still work: the callers, shared components, previous behaviour the PR did not mean to alter. |
| security | Only when the change touches auth, permissions or user input rendering: access without login, another user's data, script in input is shown as text. |

## 4. Required vs Optional, Automated vs Manual

- **Required**: the case proves an acceptance criterion, or guards a regression a reviewer would block on. The verdict depends on every Required case.
- **Optional**: nice to know; failures still produce defects but a missing result does not block.
- **Automated** unless automation is unreliable or impossible here: visual judgement (layout, brand), real email/SMS/payment, third-party SSO, screen-reader output, hardware, a dependency the local run cannot provide. Those are **Manual** with precise steps and the expected result, so a person can run them.

A Required Manual case means the best possible status is *Needs Manual Verification*. Do not hide such cases; list them.

## 5. IDs and traceability

- Test cases are `TC-01`, `TC-02`... in plan order. Never reuse an ID for a different scenario; on a retest, keep existing IDs and append new ones.
- Every Playwright test title starts with its ID: `test('TC-03 rejects a quantity of 0', ...)`. One TC may have several tests (for example one per browser project); one test belongs to exactly one TC.
- `test_plan.py check` fails if a requirement has no case, an Automated case has no test with its ID, or a spec uses an ID the plan does not define.

## 6. Where the plan goes

- Follow the repository: an existing `docs/test-plans/`, `docs/testing/`, `qa/` or similar folder (`inspect_repo.py` → `test_plans.existing_dirs`). Otherwise create `docs/test-plans/`.
- File name: `pr-<number>-test-plan.md`. On a retest of the same PR, update the same file and add a row to its Revision history.

## 7. Plan template

The two tables must keep these column headings and order; `test_plan.py` parses them.

```markdown
# Test plan: PR #<n> <PR title>

| | |
|---|---|
| Pull request | <PR URL> |
| Repository | <owner>/<repo> |
| Planned against commit | `<sha>` |
| Playwright tests | `<spec path>`, `<spec path>` |
| Fixtures and helpers | `<path>` |

## Scope

What the PR changes, in 2 to 4 sentences. Components and user workflows affected. What is out of scope and why.

## Requirements and acceptance criteria

| ID | Requirement / acceptance criterion | Source |
|---|---|---|
| R1 | A cart line's quantity can be changed between 1 and 99. | Issue #7 |
| AC2 | Entering 0 shows "Quantity must be at least 1" and keeps the previous value. | Issue #7 |
| R3 | Totals update when a quantity changes. (inferred) | Diff: `src/cart/total.ts` |

## Test cases

| ID | Scenario | Category | Requirement | Priority | Execution | Spec |
|---|---|---|---|---|---|---|
| TC-01 | Change quantity from 1 to 3; line and order totals update | positive | R1, R3 | Required | Automated | tests/e2e/cart-quantity.spec.ts |
| TC-02 | Enter 0; error shown, value restored | negative | AC2 | Required | Automated | tests/e2e/cart-quantity.spec.ts |
| TC-03 | Enter 99 and 100 | boundary | R1 | Required | Automated | tests/e2e/cart-quantity.spec.ts |
| TC-04 | Change quantity with the keyboard only; error is announced | accessibility | R1, AC2 | Required | Automated | tests/e2e/cart-quantity.spec.ts |
| TC-05 | Checkout still shows the updated total | regression | R3 | Required | Automated | tests/e2e/checkout.spec.ts |
| TC-06 | Screen reader reads the error message | accessibility | AC2 | Optional | Manual | — |

## Manual verification

For each Manual case: preconditions, numbered steps, expected result, and why it is not automated.

## Test data and environment

Users, roles and seed data needed; environment variables the tests read (names only, never values); services the app needs.

## Risks and assumptions

Inferred requirements, unreadable tickets, behaviour that could not be reached locally.

## Revision history

| Date | Commit | Change |
|---|---|---|
| 2026-11-18 | `<sha>` | Initial plan |
```
