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
| Requirements source | <linked issue / ticket / plan prompt / reviewer-supplied text> |
| Review version | v<k> · <date> · reviewer: <name if given> |
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
1. <Each Confirmed Critical/High finding, and anything else the reviewer marks as required.>

## Suggested improvements (non-blocking)
- <Medium/Low findings, process gaps, documentation gaps.>

## What was checked
- Diff: <n> files, +<a>/−<d>; files read beyond the diff: <list or count>.
- Tests/build: <commands run and results, or "not run: <reason>">; CI: <summary>.
- Tools: <e.g. wave-a11y-scan on changed UI files, appsec-static-audit; or none>.
- Not checked: <areas and why>.

## Reviewer feedback history
<Output of `review_log.py history`.>
```

## GitHub comment (`comment.md`)

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
1. **[High]** [`path:line`](https://github.com/<o>/<r>/blob/<full-sha>/<path>#L<a>-L<b>) — <problem>. *Fix:* <fix>.

### Findings
<Remaining confirmed findings, one line each with severity, link and fix.>

### Questions
<Needs-verification items as questions to the author.>

### Development process
| Step | Status | Gap |
|---|---|---|
<Only steps not Verified, with what evidence to add. Note: "Not evidenced" means we could not find evidence, not that the step was skipped.>

### Missing tests
- <scenario>

<sub>Reviewed at <short sha> with the krithi-skills `review-pr` skill; findings were validated against the code before posting.</sub>
```
