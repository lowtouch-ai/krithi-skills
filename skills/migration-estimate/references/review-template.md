# Review file: `review.md`

The self-review follows Kriti-REQ's quality check (`verify_prd_quality` in `kriti_req`): an independent pass, done after the PRDs are written and **not** in the same breath as writing them, that re-reads the PRDs against the code. Its focus is coverage and implementation accuracy, not re-reading citations. The estimate adds a story and sprint count check.

## How to review

Do these in a fresh pass. If your environment has sub-agents, give the audit to one that did not write the PRDs, as REQ does with a separate call.

1. **Code areas.** For every detailed PRD, confirm the source went past routes, controllers and UI text into the business-logic layer, the data model or migrations, permission/guard/middleware code, and config, tests and docs. Record the areas checked and any the PRD should have covered but shows no evidence of (**missed**).
2. **Implementation accuracy.** Re-read each business rule, permission and data statement against the code. Where the PRD and code disagree, the PRD is wrong: correct the PRD to match the code (the application is never changed). Record each as a **mismatch**.
3. **Confidence re-check.** Re-verify every Confidence & Open Questions item at 95% or more. Confirm it, or downgrade it with a reason.
4. **Features.** Enumerate features independently of the PRDs (routes and controllers, pages and templates, scheduled jobs and workers, reports and exports, CLI commands, stored procedures, outbound integrations) and confirm each maps to a story. `estimate.py --inventory` checks modules and manifest integrations mechanically; features are checked by you.
5. **Gap percentage.** Estimate, 0-100, how much of the PRD set is not reliably backed by the code (REQ's `gap_percentage`). **If it is over 30, rework**: read the missed areas now, fold them in, fix every mismatch and downgraded confidence, add or split stories, re-run `estimate.py`, then re-assess. The final gap percentage must be 30 or less.
6. **Stories and sprints.** Confirm every detailed PRD has stories and that `estimate.py`'s `total_stories` equals the stories you wrote.

## Template

`estimate.py --review` requires the headings below, a `Final total sprints: N` line matching the computed total, and a `Gap percentage (final): N` line of 30 or less.

```markdown
# Estimate review: {Application name}

Reviewed {YYYY-MM-DD}. Inventory: `{absolute inventory.json path}` ({N} modules, {N} integrations, {N} source files).

## Coverage against the codebase
- **Modules:** {N} of {N} inventory modules covered by a detailed PRD; {N} listed under Out of scope with reasons.
- **Integrations:** {N} of {N} from manifests are in the PRDs. Found by reading the code (not in manifests): {list, or "none"}.
- **Features:** {routes/controllers N, screens N, jobs N, reports N, ...}; every one maps to a story.
- **Code areas checked:** {business logic, data model, permissions, config, tests, ...}
- **Code areas missed (first pass):** {list, or "none"}

## Implementation accuracy
| PRD section | PRD said | Code actually does | Source |
|---|---|---|---|
{One row per mismatch, or one row: "None found."}

Confidence items at 95% or more: {N} re-checked, {N} confirmed, {N} downgraded ({item: new %, reason}).

## Stories and sprint count
- {N} detailed PRDs, each with at least one story.
- {N} stories, all in `### PRD-NN-SMM:` form, all counted by `estimate.py`.
- Final total sprints: {N}

## Gaps found and fixed
| # | Gap | Fix | Effect on estimate |
|---|---|---|---|
| 1 | {e.g. `src/jobs/` not covered} | {e.g. added PRD-07 with 4 stories} | {+1 sprint} |
{Or one row: "None found."}

- Gap percentage (first pass): {N}
- Gap percentage (final): {N}
- First pass: {N} stories, {N} sprints. Final: {N} stories, {N} sprints.

## Result
{One or two sentences: the estimate is complete against the codebase as inventoried, plus any residual limits (code that could not be read, features the client must confirm are still used).}
```
