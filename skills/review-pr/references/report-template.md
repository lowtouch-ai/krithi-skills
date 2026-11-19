# Review report and GitHub comment templates

## Review report (`report-v<k>.md`)

Write for the reviewer first: every statement must be traceable to evidence (file:line, commit, CI check, artifact path). Leave out empty sections except where noted.

```markdown
# PR review: <owner>/<repo>#<n> — <PR title>

| | |
|---|---|
| PR | <url> (<state>, <draft?>) |
| Author | <login> · Branch `<head>` → `<base>` |
| Head commit reviewed | `<full sha>` |
| Requirements source | <linked issue / ticket / plan prompt / request context / PR description / inferred from the change> · confidence <High / Medium / Low> |
| Review version | v<k> · <date> · automated review (quality gate: passed / failed) |
| Recommendation | **<Approve / Request Changes / Needs Further Verification>** · weighted score **<x.xx> / 5** |

## Summary
<3 to 5 sentences: what the PR does, whether it meets the requirements, the most important issues, and the recommendation.>

## Requirements coverage
| # | Requirement / acceptance criterion | Status | Where / evidence |
|---|---|---|---|
| R1 | ... | Met / Partly met / Not met / Cannot verify | `path:line`, test name |

## Findings
<Confirmed findings only, most severe first, in the review-guide format. If none: "No confirmed defects.">

### F1 [High · Confirmed] `path:line` — <title>
- **Category:** Functional / Security / Accessibility / Testing / Maintainability
- **Failure:** <input/state → wrong result>
- **Evidence:** <what you traced or ran>
- **Recommended fix:** <concrete change>

## Needs verification
<Likely / Needs-verification items, each phrased as a question with what would confirm or rule it out. If none, omit.>

## Missing test scenarios
- <scenario: input → expected result, and which test file it belongs in>

## Development process compliance
| # | Step | Status | Evidence | Gaps / what would verify it |
|---|---|---|---|---|
| 1 | README Generator | Verified | `README.md` footer commit=abc123 date=2026-11-02 | — |
| 2 | Prompt-Builder | Not Evidenced | Searched docs/plan-prompts/, PR body, commits, linked issue | Commit `docs/plan-prompts/<T>-codex-plan-prompt.md` or attach it |
| ... | | | | |

<One line: Not Evidenced means no evidence was found in the places searched, not that the step was skipped.>

## Scorecard
<Table printed by `scorecard.py --markdown`.>

## Required changes before merge
1. <Each Confirmed Critical/High finding, and each requirement Not met.>

## Suggested improvements (non-blocking)
- <Medium/Low findings, process gaps, documentation gaps.>

## What was checked
- Diff: <n> files, +<a>/−<d>; files read beyond the diff: <list or count>.
- Tests/build: <commands run and results, or "not run: <reason>">; CI: <summary>.
- Tools: <e.g. wave-a11y-scan on changed UI files, appsec-static-audit; or none>.
- Not checked: <areas and why>.

## Automated decisions
- <Each default rule applied instead of asking: requirements source and any inferred R<k>; tickets not readable; commands run or skipped and why; files only skimmed; PR state (draft/closed); re-review of which head.>

## Review history
<Output of `review_log.py history`: versions, gate repairs, automatic approval, any later reviewer feedback.>
```

## GitHub review summary (`comment.md`)

Shorter than the report, written to the PR author, neutral and specific. No internal reviewer notes, scores reasoning about the person, or anything not supported by evidence. GitHub's limit is 65,536 characters.

```markdown
## PR review — <Approve / Request changes / Needs further verification>

<2 to 3 sentence summary.>

### Scorecard
| Factor | Weight | Rating |
|---|---:|---:|
| Functional correctness and requirements coverage | 30% | 4 |
| Code quality, security and accessibility | 25% | 3 |
| Testing and validation | 20% | 3 |
| Development process compliance | 15% | 2 |
| PR documentation and review readiness | 10% | 4 |
| **Overall (weighted)** | | **3.30 / 5** |

### Required changes
1. **[High]** [`path:line`](https://github.com/<o>/<r>/blob/<full-sha>/<path>#L<a>-L<b>) — <problem> (see the line comment).

### Findings
<Remaining confirmed findings, one line each with severity and link; "see the line comment" when one exists, otherwise the fix.>

### Questions
<Needs-verification items without a specific line, as questions to the author. Those with a line are line comments.>

### Development process
| Step | Status | Gap |
|---|---|---|
<Only steps not Verified, with what evidence to add. Note: "Not evidenced" means we could not find evidence, not that the step was skipped.>

### Missing tests
- <scenario>

<sub>Reviewed at <short sha> with the krithi-skills `review-pr` skill; findings were validated against the code before posting.</sub>
```

## Line comments (`inline.json`)

A JSON list; one entry per Confirmed finding and per Likely / Needs-verification item that points at a specific line. `line` is the line in the PR's head version of the file; add `start_line` for a range. Lines not in the PR's diff are moved into the summary automatically.

```json
[
  {
    "path": "src/billing/invoice.py",
    "line": 142,
    "body": "**F3 [High · Confirmed]** Total excludes the last line item\n\n`items[:-1]` drops the final item, so an invoice with one item totals 0. Reproduced with `tests/test_invoice.py::test_single_item`.\n\n**Fix:** iterate over `items`.\n\n```suggestion\n    for item in items:\n```"
  },
  {
    "path": "src/api/routes.py",
    "start_line": 30,
    "line": 34,
    "body": "**Question (needs verification):** is `user_id` validated before this query? If not, ... What would confirm it: ..."
  }
]
```

Each body: severity and status, a one-line title, the failure and its evidence, then the fix. Add a GitHub `suggestion` block only when the exact replacement for exactly those lines is known. Same tone rules as the summary: neutral, about the code, no secrets.
