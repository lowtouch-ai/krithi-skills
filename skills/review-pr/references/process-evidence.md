# Development process evidence

The Krithi workshop process has eight steps. Each skill in this repository leaves specific traces; `scripts/pr_evidence.py` looks for them and suggests a status, and you decide the final status from the evidence.

## Statuses

| Status | Use when |
|---|---|
| **Verified** | A strong, objective artifact shows the step happened (a file the skill writes, a CI result, a template only that skill produces). |
| **Partially Verified** | Some evidence, but weak, indirect or self-reported (a claim in the PR body, a file that exists but does not match the ticket, CI not run). |
| **Not Evidenced** | No evidence found in the repository, the PR, the commits, the linked issues or the artifacts provided. **This is not proof the step was skipped.** Say what was searched and what would count as evidence. |
| **Not Applicable** | The step does not apply to this PR, with the reason (for example a one-line typo fix needs no plan; a docs-only PR has no build). |

Rules:
- Never write "skipped", "did not follow" or "violated" for a Not Evidenced step. Write "no evidence found in <places searched>".
- Distinguish **claimed** from **verified**: "Tests: 48 passed" in a PR body is a claim; a green CI check or a test you ran is verification.
- Evidence found anywhere reachable counts: PR and issue comments, readable tracker tickets, run links in the PR body, `~/.krithi/<TICKET>/` on this machine. Evidence provided later (a Codex transcript, a Krithi run log, a screenshot) counts too: re-grade as a new version.
- Krithi-generated PRs may record steps elsewhere (the orchestration run, Jira/Azure DevOps updates). Search those places automatically (SKILL.md step 5) and list them under "places searched" before marking a step Not Evidenced. Never stop to ask.

## What each step leaves behind

| # | Step | Strong evidence | Weaker evidence | Notes |
|---|---|---|---|---|
| 1 | **README Generator** (`repo-readme-generator`) | `README.md` ends with `<!-- repo-readme-generator: commit=<sha> date=<YYYY-MM-DD> -->` | README contains the "commit messages and PR descriptions must be descriptive" note; `AGENTS.md` and a `docs/` suite (architecture.md, codebase-map.md, development-guide.md); README/AGENTS.md changed in this PR | Usually run once per repository, often in an earlier PR, so it is evidenced by the head tree, not this diff. A footer commit older than the PR is normal. |
| 2 | **Prompt-Builder** (`plan-builder` prompt) | `docs/plan-prompts/<TICKET>-codex-plan-prompt.md` named after this PR's ticket and containing the `PLAN MODE ONLY` clause | A plan prompt for a different/unmatched ticket; `~/.krithi/<TICKET>/` on this machine (only when reviewing on the author's machine); PR body mentions plan-builder | The prompt file may be left uncommitted; if it is missing, add a question for the author to the comment's Questions section. |
| 3 | **Codex Plan Mode** | `docs/plan-prompts/<TICKET>-implementation-plan.md` with most of plan-builder's ten headings (Current architecture, Root cause/Design approach, Files to modify, Recommended implementation, Dependencies and impact, Risks, Testing strategy, Rollout, Acceptance criteria, Open questions) | A plan with few headings; PR body mentions Plan Mode | A plan pasted into the PR body or ticket also counts. |
| 4 | **Plan Review** | `<TICKET>-implementation-plan.prev.md` (plan-builder keeps the previous plan when the reviewer asked for changes) | PR body or commits say the plan was reviewed/approved; plan file changed across commits | Approving the plan as-is ("build it") leaves **no artifact**. Without a revision trace, Not Evidenced is expected; put a question to the author in the comment, do not penalise heavily. |
| 5 | **Implementation** | Changed files match the plan's "Files to modify" (`plan_traceability`) | Code changed but no plan to compare with | Changed-but-not-planned files are worth a question (scope creep or an incomplete plan), not a finding by themselves. |
| 6 | **Build and Automated Testing** | CI checks on the head commit all passed; or you ran the build/tests yourself (SKILL.md step 3) | `Testing:` section in commit bodies (prepare-pr); Testing section in PR body with commands and results; test files changed | CI failing → Partially Verified, and a finding if caused by this PR. Claims only → Partially Verified. |
| 7 | **prepare-pr** | PR body with prepare-pr's sections (Summary, Changes, Review notes, Documentation, Testing, Breaking changes / deployment notes; at least five) | Commit bodies with `Testing:`; descriptive commit bodies; feature branch with a prefix; ≤72-char imperative subjects; "Review notes" listing pre-PR review findings | If the repo has a PR template, prepare-pr fills that instead; judge against the template's sections. |
| 8 | **PR Submission** | Linked issue (GitHub closing reference or `#n`) or a ticket key, a substantive description, and validation evidence | Short description; ticket mentioned only in the branch name | A draft PR is not ready for final review; say so. |

## Grading process compliance (factor 4)

Rate from the eight statuses, weighting the steps that most affect quality (plan, plan review, build/test) more than formatting:

| Rating | Pattern |
|---|---|
| 5 | Every applicable step Verified. |
| 4 | Core steps (2, 3, 6, 7, 8) Verified; others Partially Verified or explained. |
| 3 | Most steps at least Partially Verified; one core step Not Evidenced. |
| 2 | Several core steps Not Evidenced; process largely not traceable from what is available. |
| 1 | Positive evidence the process was bypassed (for example the PR says the plan was skipped, or tests were deleted to pass). Absence of evidence alone never gives a 1. |

If most steps are Not Evidenced only because artifacts are not accessible to the reviewer (uncommitted plan files, a private ticket system), rate `null` (not enough evidence) and list the missing artifacts as questions to the author in the comment, rather than scoring 2.
