# Five-factor scorecard

Rate each factor 1 to 5 (5 is best) from **evidence you can cite**. If a factor cannot be judged from the available evidence, rate it `null` and say what is missing; `scripts/scorecard.py` then re-normalises the score over the rated factors and recommends Needs Further Verification.

| Key | Factor | Weight |
|---|---|---:|
| `functional` | Functional correctness and requirements coverage | 30% |
| `quality` | Code quality, security and accessibility | 25% |
| `testing` | Testing and validation | 20% |
| `process` | Development process compliance | 15% |
| `documentation` | PR documentation and review readiness | 10% |

Overall = Σ rating × weight (1.00 to 5.00). Only **Confirmed** findings affect ratings; Likely and Needs-verification items are listed but do not lower a rating.

## Anchors

### Functional correctness and requirements coverage (30%)
- **5**: every requirement and acceptance criterion met and traced to code; no regressions found.
- **4**: all requirements met; only Low/Medium issues in edge cases.
- **3**: main flow works; a secondary requirement partly met or a confirmed Medium correctness issue.
- **2**: a requirement not met or a confirmed High correctness bug / regression.
- **1**: main feature broken, or the PR does not address the requirement.

### Code quality, security and accessibility (25%)
- **5**: consistent with the codebase, clear, no security or accessibility issues found in the checked areas.
- **4**: minor maintainability issues (Low).
- **3**: Medium maintainability, performance or accessibility issues; no security issue above Low.
- **2**: a confirmed High security/accessibility issue, or significant duplication/inconsistency likely to cause bugs.
- **1**: confirmed Critical security issue (injection, auth bypass, leaked secret) or code that cannot be maintained.

### Testing and validation (20%)
- **5**: tests for every changed behaviour and acceptance criterion, CI green, meaningful assertions.
- **4**: good coverage of the main paths, CI green; a few edge-case scenarios missing.
- **3**: some tests, or CI green but key scenarios untested; or tests claimed but not verifiable.
- **2**: little or no test for changed behaviour; CI failing because of this PR.
- **1**: tests removed, skipped or weakened to pass, or claimed results that are false.

### Development process compliance (15%)
See the grading table in `process-evidence.md`. Absence of evidence alone never gives a 1.

### PR documentation and review readiness (10%)
- **5**: description explains what and why, links the issue, lists testing with results, notes risks; docs updated where the change makes them wrong; commits descriptive; PR not a draft; focused scope.
- **4**: minor gaps (for example no deployment notes where relevant).
- **3**: description present but thin; issue link or testing evidence missing.
- **2**: one-line description, no issue link, no validation evidence; or user-facing docs left wrong.
- **1**: empty description, unrelated changes mixed in, or not reviewable (huge mixed diff, conflicts).

## Recommendation (computed by `scorecard.py`)

Applied in this order; a high score never overrides a blocker:
1. Any **Confirmed Critical or High** finding → **Request Changes**.
2. Any **Critical or High** finding still Likely / Needs verification, or any factor unrated → **Needs Further Verification**.
3. Weighted score below **3.5**, or any factor below **3** → **Request Changes**.
4. Otherwise → **Approve** (Medium/Low findings are listed as suggested, non-blocking changes).

The automated review always uses the computed recommendation; a differing judgement goes in "Reviewer notes" only. If a human later disputes it through feedback, record the reason in the history and in the report.
