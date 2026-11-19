# krithi-skills

Reusable Codex skills from lowtouch.ai, built for the Krithi SDLC workflow.

## What is Krithi?

[Krithi](https://krithi.ai) is [lowtouch.ai](https://www.lowtouch.ai/agents/krithi/)'s agentic software delivery workflow. It turns a ticket into a reviewed pull request, running on the customer's own infrastructure (on-prem, private cloud or air-gapped), so code does not leave the customer's environment.

Work moves through four stages, and a human approves each one before anything merges to main:

| Stage | What happens |
|---|---|
| Plan | Requirements and sprint planning, with traceability back to legacy code and customer feedback. |
| Code | Code is generated and self-reviewed against the approved requirement. |
| Test | Playwright-based UI, API, performance and regression tests; defects go back to the coding stage. |
| Compliance audit | Security scans (SAST, dependency, secrets) and accessibility checks against standards such as OWASP ASVS and WCAG 2.2 AA. |

An orchestration agent routes each task to the model that suits it (Claude Code, Codex, Kimi or Gemma) and syncs status with Jira, Azure DevOps or ServiceNow. Krithi is aimed at engineering teams with a backlog and too few engineers, especially in regulated environments, for work such as legacy modernization, greenfield builds, data pipelines and platform migrations. lowtouch.ai also offers it as a managed service ([Velocity Pods](https://www.lowtouch.ai/agents/krithi/)), where its engineers run Krithi and own the review gates.

The skills in this repository are reusable building blocks for that kind of work: accessibility scanning, security auditing, agent-ready documentation, ticket-to-plan prompt building, migration effort estimation, pull request preparation, pull request review and pull request validation.

## Skills

| Skill | What it does |
|---|---|
| [`repo-readme-generator`](#repo-readme-generator) | Creates or updates a repo's README, or a full documentation suite with `AGENTS.md` and diagrams, from verified evidence. |
| [`appsec-static-audit`](#appsec-static-audit) | Source-code-only security audit of one repository or several (OWASP, SSO, secrets, dependencies and SBOM, IaC, CI/CD, PII/FTI) with a timestamped enterprise report, SARIF output and a CI gate, mapped to NIST 800-53, IRS Pub 1075 and EOTSS. |
| [`wave-a11y-scan`](#wave-a11y-scan) | WAVE-style accessibility scan of a project's source code with a client-ready report (WCAG 2.2, Section 508 note). |
| [`plan-builder`](#plan-builder) | Turns a ticket (text, screenshot, HTML, Markdown, logs) into a ready-to-paste Codex Plan Mode prompt; supporting artifacts are saved under `~/.krithi/<TICKET>/` (outside the repo) and referenced by verified absolute paths; the prompt is saved under `docs/plan-prompts/`. |
| [`migration-estimate`](#migration-estimate) | Reads a codebase and estimates migration or modernisation effort the Krithi way: high-level PRD, detailed PRDs, stories and sprints, with a human-team vs Krithi timeline side by side, an approximate go-live allowance, and a self-review for coverage; all Markdown under `docs/migration-estimate/`. It plans every migration onto Krithi's standard architecture (FastAPI, PostgreSQL, Redis, Next.js, Airflow; our AI stack when the app has AI agents). It also estimates the effort to fix an accessibility report and a security audit (`docs/remediation-estimate/`). |
| [`feature-estimate`](#feature-estimate) | Turns customer emails, meeting notes, bug reports, tickets and user stories into a requirements register (with traceability to the input), high-level and detailed PRDs, stories and sprints, estimated for a human team vs Krithi. It follows `migration-estimate` exactly and runs its scripts; only the input and the code scope differ (documented in `references/feature-delta.md`). Writes `docs/feature-estimate/`. Needs `migration-estimate` installed. |
| [`prepare-pr`](#prepare-pr) | Takes finished, tested work to a pull request: reviews the change (bugs, security, quality, performance, requirements) and fixes what you approve, runs the tests, updates only the docs the change affects, checks the branch name fits the work, commits only in-scope files with a detailed message, then asks before pushing and opening the PR. |
| [`review-pr`](#review-pr) | Reviews a pull request (a workshop participant's or one Krithi generated) against its requirements and the Krithi development process: validated findings with severity, file and line and a fix; a process compliance table for the eight workflow steps; a five-factor weighted scorecard and a recommendation. Fully automated from just the PR link: the reviewer needs no context and is never asked anything; requirements are inferred when not linked, the build and tests run in a sandbox, and an automatic quality gate checks the review before the comment is posted (only when you say `post`). |
| [`validate-pr`](#validate-pr) | Validates a pull request by testing it: works out the requirements, writes a test plan and Playwright tests into the repository (committed to the PR only after you approve the exact diff), builds and launches the app from the PR's exact commit for any stack, runs the tests, and saves screenshots, traces, console errors and app logs outside the repository per owner/repo/PR/run. Triages each failure as an application defect, a test problem or an environment issue, and computes Passed, Failed, Blocked or Needs Manual Verification. Supports reviewer challenges, extra scenarios, reruns and retests after fixes. |

In Codex, install a skill with the command in its section, then restart Codex. Skills are installed as folders under `~/.codex/skills/` (or `$CODEX_HOME/skills/` if you set `CODEX_HOME`).

## repo-readme-generator

Creates or updates a repo's README, or a full documentation suite with `AGENTS.md` and diagrams, from verified evidence. Details: [`SKILL.md`](skills/repo-readme-generator/SKILL.md).

### Install

```
$skill-installer install https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/repo-readme-generator
```

### Test

Open Codex in the folder you want to work on and run:

```
$repo-readme-generator create the README for this repo
```

For the full documentation suite:

```
$repo-readme-generator document this repo fully
```

### Update

To get the latest version, use either option, then restart Codex.

Option 1: ask the installer to update from the URL:

```
$skill-installer update https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/repo-readme-generator
```

Option 2: remove the installed folder and install it again:

```
rm -rf ~/.codex/skills/repo-readme-generator
```

```
$skill-installer install https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/repo-readme-generator
```

### Uninstall

```
rm -rf ~/.codex/skills/repo-readme-generator
```

## appsec-static-audit

Source-code-only security audit of one repository or several, for any organization or stack. A scanner finds candidates (injection and other OWASP issues with data-flow tracking, access control, SSO/JWT/SAML, sessions, secrets including git history, dependency vulnerabilities from a bundled OSV snapshot, SBOM, cryptography, PII/FTI handling, IaC, Docker/Kubernetes, GitHub Actions); the agent then reads the code, confirms or rejects each candidate and writes a timestamped Markdown report with tables, severity, file and line evidence, concrete fixes and mappings to NIST 800-53, IRS Pub 1075 and EOTSS. It needs only Python 3 and git, makes no network calls, never modifies the audited repositories, and writes `security-audit/security-audit-report_<timestamp>.md` plus `sbom.cdx.json`, `scan.json` and `triage.json` (and optionally a SARIF file). Details: [`SKILL.md`](skills/appsec-static-audit/SKILL.md).

### Install

```
$skill-installer install https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/appsec-static-audit
```

### Test

Open Codex in the folder you want to work on and run:

```
$appsec-static-audit audit this repository for security
```

### Sample prompts

Run these in Codex from the folder you want to audit (replace the paths and names with your own).

```
$appsec-static-audit audit this repository for security
```

Several repositories as one report:

```
$appsec-static-audit audit ../platform ../shared-libs ../installer as one workspace called "Acme Platform", exclude **/node_modules and **/target
```

Re-auditing the same code and proving nothing was lost:

```
$appsec-static-audit re-audit this repository into ./security-audit-new and compare with the previous review in ./security-audit-old: list every finding confirmed before and not confirmed now, and why.
```

### What you get

- **Report** (`security-audit-report_<timestamp>.md`): executive summary, scope and limitations, findings register, a control checklist per domain (No., Issue, Status, Evidence), detailed findings with exploit scenario, impact, evidence and fix, compliance mapping, dependencies and SBOM, remediation roadmap, and appendices for scan coverage (scanner fingerprint, repository revisions, per-component coverage and review status) and rejected candidates.
- **Stable IDs**: a finding keeps its `FND-nnn` number across re-scans, so an existing `triage.json` stays valid.
- **Honest status**: controls nobody reviewed show as `NOT ASSESSED`, never as a pass. Low-confidence candidates are capped at Medium until confirmed. The report states how many candidates were decided one by one versus by bulk rule.
- **Verification**: confirmed Critical and High findings can be re-checked blind by a second reader; the report records who agreed, who disputed and whether the verdict is tied to the exact packet reviewed.
- **Re-audits**: `--previous-triage` lists every earlier confirmed finding that this review does not confirm, with its status now.
- **Pipelines**: `--emit-sarif` for code-scanning tools, `--fail-on High` for CI gates, and a suppression policy file for accepted risks and known false positives.

### Update

To get the latest version, use either option, then restart Codex.

Option 1: ask the installer to update from the URL:

```
$skill-installer update https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/appsec-static-audit
```

Option 2: remove the installed folder and install it again:

```
rm -rf ~/.codex/skills/appsec-static-audit
```

```
$skill-installer install https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/appsec-static-audit
```

### Uninstall

```
rm -rf ~/.codex/skills/appsec-static-audit
```

On Windows (PowerShell):

```
Remove-Item -Recurse -Force "$env:USERPROFILE\.codex\skills\appsec-static-audit"
```

Files the skill wrote into your projects (`security-audit/`) are not removed with the skill; delete them separately if you no longer need them.

## wave-a11y-scan

WAVE-style accessibility scan of a project's source code (HTML, templates, JSX/TSX, Vue, Svelte, Astro) with a client-ready report (WCAG 2.2, Section 508 note). The report also covers the [Mass.gov web testing checklist](https://accessibility.mass.gov/testing-checklists/web-testing-checklist/): each of its 50 items is marked as checked by the scan, partly checked, or manual-only, with a manual test for the rest. A second checklist of 21 items covers WCAG 2.2 criteria (target size, focus not obscured, accessible authentication, dragging), other WCAG 2.1 criteria and React/Material-UI patterns, with matching source checks. It also adds a static subset of axe-core rules, lists contrast checks left for a person, and points to the tools Mass.gov recommends (axe DevTools, WAVE, Accessibility Insights, ANDI, contrast checkers). Findings carry file and line. It needs only Python 3; no browser or install. Automated checks do not prove code is accessible; manual keyboard and screen-reader testing is still required. Details: [`SKILL.md`](skills/wave-a11y-scan/SKILL.md).

### Install

```
$skill-installer install https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/wave-a11y-scan
```

### Test

Open Codex in the folder you want to work on and run:

```
$wave-a11y-scan scan this project
```

### Update

To get the latest version, use either option, then restart Codex.

Option 1: ask the installer to update from the URL:

```
$skill-installer update https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/wave-a11y-scan
```

Option 2: remove the installed folder and install it again:

```
rm -rf ~/.codex/skills/wave-a11y-scan
```

```
$skill-installer install https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/wave-a11y-scan
```

### Uninstall

```
rm -rf ~/.codex/skills/wave-a11y-scan
```

Files the skill wrote into your projects (`docs/a11y-report/`) are not removed with the skill.

## plan-builder

Converts a ticket for a bug, enhancement, new feature, removal, UI/accessibility change or refactor into a complete Codex Plan Mode prompt. It asks for the ticket number and any supporting artifacts, saves the artifacts to `~/.krithi/<TICKET>/` (outside the repository, checksum-verified, referenced by absolute path), writes `docs/plan-prompts/<TICKET>-codex-plan-prompt.md`, and tells Codex to investigate, analyze impact, dependencies, implementation strategy, risks and tests while staying in Plan Mode without modifying code. It then runs that prompt automatically in a read-only `codex exec` session, saves the plan to `docs/plan-prompts/<TICKET>-implementation-plan.md`, shows the full plan and asks whether to **build it** or **change it** (changes re-run the plan with your comments; build asks about the branch, then implements the approved plan, without committing). Details: [`SKILL.md`](skills/plan-builder/SKILL.md).

### Install

```
$skill-installer install https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/plan-builder
```

### Test

Open Codex in the repository the ticket applies to and run:

```
$plan-builder build a plan prompt for ABC-123 from this ticket: <paste text or give a screenshot/HTML/Markdown path>
```

The skill shows the plan and asks: build it, or change it. If the automatic plan run fails (no `codex` on the path, timeout), it falls back to the manual route: switch Codex to Plan mode (Shift+Tab or `/plan`) and paste the prompt, or say: `Read <prompt path> and follow it`.

### Update

To get the latest version, use either option, then restart Codex.

Option 1: ask the installer to update from the URL:

```
$skill-installer update https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/plan-builder
```

Option 2: remove the installed folder and install it again:

```
rm -rf ~/.codex/skills/plan-builder
```

```
$skill-installer install https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/plan-builder
```

### Uninstall

```
rm -rf ~/.codex/skills/plan-builder
```

Files the skill wrote (`~/.krithi/<TICKET>/` artifacts and `docs/plan-prompts/` prompts in your projects) are not removed with the skill.

## migration-estimate

Estimates the effort to migrate or modernise the application in the current repository: it reads the code, writes a high-level PRD in Kriti-REQ's PRD format (use cases, business rules, roles, data, citations, confidence), breaks it into detailed PRDs, converts each into stories and counts sprints. Five stories make one sprint of two engineers; a human team runs a sprint in 10 working days and Krithi in 2, so the same sprint count is five times faster (40 sprints = 80 weeks vs 16 weeks). The estimate covers development and testing only; QA sign-off, production deployment and data migration are listed separately with an approximate 20% go-live allowance. All numbers are computed by a script from the PRDs. Before finishing, the skill checks the PRDs against the codebase for missed modules, integrations and features, scores the gap the way Kriti-REQ's quality check does, reworks above 30%, re-runs the estimate and records the check in `review.md`.

**Target architecture.** Every estimate is planned on Krithi's standard architecture: FastAPI backend, PostgreSQL (one database and user per application), Redis, a Next.js UI that follows the design system (WCAG 2.1 AA), Airflow for scheduled, long-running and event-driven work, Vault for secrets and MinIO when files are stored; multi-tenancy plumbing only for multi-tenant apps. If the inventory finds AI agents, the plan uses our AI stack (agentomatic, agentvector, Ollama, agentconnector, DAGs as tools) and never Open WebUI. Each legacy screen group, endpoint group and scheduled job maps to a Next.js, FastAPI or Airflow DAG story, foundation stories are added, and anything that cannot follow the standard is recorded as a deviation. The script checks the mapping. See [`target-architecture.md`](skills/migration-estimate/references/target-architecture.md).

**Remediation estimates.** It also estimates the effort to fix what `wave-a11y-scan` and `appsec-static-audit` found. A script reads `docs/a11y-report/results.json` and the audit's SARIF (render the report with `--emit-sarif`), turns findings into fix stories (one rule in one folder, split above a cap, plus a verification story per report) and counts sprints on the same rules, human team vs Krithi, per report and combined, in `docs/remediation-estimate/`. Accessibility alerts and unconfirmed security leads are listed but not estimated unless asked. Run it with `$migration-estimate estimate the effort to fix the a11y report and the security audit`. Details: [`SKILL.md`](skills/migration-estimate/SKILL.md).

### Install

```
$skill-installer install https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/migration-estimate
```

### Test

Open Codex at the root of the application repository and run:

```
$migration-estimate estimate the migration effort for this codebase
$migration-estimate estimate the effort to fix the a11y report and the security audit
```

The first prompt writes, in the repository: `docs/migration-estimate/00-high-level-prd.md`, one `prd-NN-<slug>.md` per detailed PRD, `estimate-summary.md` and `review.md`. The codebase inventory is saved outside the repository under `~/.krithi/migration-estimate/<repo>/`.

The second prompt needs `docs/a11y-report/results.json` (from `wave-a11y-scan`) and the security audit's SARIF file (from `appsec-static-audit`, rendered with `--emit-sarif`). It writes `docs/remediation-estimate/`.

### Update

To get the latest version, use either option, then restart Codex.

Option 1: ask the installer to update from the URL:

```
$skill-installer update https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/migration-estimate
```

Option 2: remove the installed folder and install it again:

```
rm -rf ~/.codex/skills/migration-estimate
```

```
$skill-installer install https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/migration-estimate
```

### Uninstall

```
rm -rf ~/.codex/skills/migration-estimate
```

Files the skill wrote (`docs/migration-estimate/` in your projects and `~/.krithi/migration-estimate/`) are not removed with the skill.

## feature-estimate

Estimates the effort to build what a customer asked for: emails and threads, meeting notes and transcripts, bug reports, enhancement tickets, user stories and other feedback. It saves each input, extracts a requirements register (assumptions, open questions, and a quote tracing every requirement to its source), inspects the repository for the modules, integrations, APIs and data the changes touch, and then runs **exactly** the `migration-estimate` process: high-level PRD in Kriti-REQ's format, detailed PRDs, stories, sprints (5 stories = 1 sprint of 2 engineers; 10 working days for a human team vs 2 with Krithi), about 20% go-live allowance, and a self-review with rework above a 30% gap.

**One set of rules.** The skill contains no estimation logic. Its `estimate.py` and `inventory.py` run `migration-estimate`'s scripts (only the output folder and the summary title differ), so the two cannot produce different numbers. The one new check, `requirements.py`, confirms every requirement is covered by a story (or marked out of scope or deferred with a reason) and every story traces to a requirement; it never changes a count. The intentional differences are listed in [`feature-delta.md`](skills/feature-estimate/references/feature-delta.md): customer input instead of the codebase as the requirement, reading only the affected code, no foundation stories the application already has, building in the application's existing architecture (recorded as architecture deviations where it differs from Krithi's standard), and a `Requirements coverage` section in the review. `tests/feature-estimate/test_feature_estimate.py` runs the same PRDs through both skills and fails if anything differs.

### Install

`feature-estimate` uses `migration-estimate`'s scripts, so install both:

```
$skill-installer install https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/migration-estimate
```

```
$skill-installer install https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/feature-estimate
```

### Test

Open Codex at the root of the application repository and run, pasting or attaching the customer input:

```
$feature-estimate estimate this customer request: <paste the email, notes or ticket>
```

It writes `docs/feature-estimate/`: `inputs/`, `00-requirements.md`, `00-high-level-prd.md`, one `prd-NN-<slug>.md` per feature area, `estimate-summary.md` and `review.md`. The inventory is saved under `~/.krithi/feature-estimate/<repo>/`.

### Update

```
$skill-installer update https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/feature-estimate
```

### Uninstall

```
rm -rf ~/.codex/skills/feature-estimate
```

Files the skill wrote (`docs/feature-estimate/` in your projects and `~/.krithi/feature-estimate/`) are not removed with the skill.

## prepare-pr

Run it once the implementation is done and tested. It reviews every change against the original requirements (correctness, security, performance, maintainability), verifies each finding before reporting it, fixes the ones you approve and runs the relevant tests. It then updates only the documentation the change makes wrong, checks that the feature branch name matches the work (and offers a new branch if it does not), commits only the files that belong to this work with a commit message that explains what changed and why and how it was tested, and finally asks whether to push and open the PR. It stops for your answer before a new branch, a commit and a push; it never commits unrelated changes, force-pushes, bypasses hooks or pushes to the default branch, and it blocks staged secrets and `.env` files. It needs Python 3 and git; opening the PR needs the `gh` CLI (without it, the skill pushes and prints the PR title, body and compare link). Details: [`SKILL.md`](skills/prepare-pr/SKILL.md).

### Install

```
$skill-installer install https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/prepare-pr
```

### Test

Open Codex in the repository where you finished the work and run:

```
$prepare-pr
```

With the requirement or ticket, so the review checks against it:

```
$prepare-pr this implements ABC-123: invoices must include every line item in the total
```

If you answer **no** at the push question, the commit stays on your local feature branch and nothing is pushed.

### Update

To get the latest version, use either option, then restart Codex.

Option 1: ask the installer to update from the URL:

```
$skill-installer update https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/prepare-pr
```

Option 2: remove the installed folder and install it again:

```
rm -rf ~/.codex/skills/prepare-pr
```

```
$skill-installer install https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/prepare-pr
```

### Uninstall

```
rm -rf ~/.codex/skills/prepare-pr
```

Commits, branches and PRs the skill made are not removed with the skill.

## review-pr

Reviews one GitHub pull request, from a workshop participant or generated by Krithi, **fully automatically from just the PR link**. It is built for the case where person A opens a PR and hands it to person B, who knows nothing about it: B gives the link and is never asked a question. Every decision that used to be a question has a default rule, and each assumption is listed in the report under "Automated decisions".

It works out the requirements itself (request context, linked issues and their comments, tickets through any connected tracker, plan-builder prompt and plan, PR description; failing those, inferred from the change and labelled **(inferred)** with Low confidence). It reads the diff at the PR's head commit with the surrounding code, builds and runs the tests in a temporary detached worktree with secret environment variables removed (skip with `no-run`), and reviews functional correctness and regressions, security, accessibility (when UI files change), tests and missing scenarios, and maintainability. Every candidate is validated separately and labelled Confirmed, Likely or Needs verification; only confirmed findings count as defects. It checks for evidence of each step of the Krithi workflow (README Generator, Prompt-Builder, Codex Plan Mode, Plan Review, Implementation, Build and Testing, prepare-pr, PR Submission) and marks each Verified, Partially Verified, Not Evidenced or Not Applicable; Not Evidenced means no evidence was found, not that the step was skipped. A five-factor scorecard (functional 30%, quality/security/accessibility 25%, testing 20%, process 15%, PR documentation 10%) gives a weighted score from 1 to 5, and the recommendation (Approve, Request Changes, Needs Further Verification) is computed so that a confirmed Critical or High finding always means Request Changes.

Instead of asking the reviewer to approve, an automatic quality gate re-checks the review (citations exist at the head commit, every requirement and process step covered, recommendation matches the scorecard, neutral wording, no instructions taken from PR content, assumptions listed), repairs it up to twice, and only then approves it. The comment is posted to the PR only when the request says `post`; otherwise it is saved and the summary prints the command to post it. Reviews are kept under `~/.krithi/reviews/` (outside the repository). Needs Python 3, git and the `gh` CLI logged in. Details: [`SKILL.md`](skills/review-pr/SKILL.md).

### Install

```
$skill-installer install https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/review-pr
```

Then restart Codex.

### Test

Open Codex anywhere and give it only the PR link:

```
$review-pr review https://github.com/<owner>/<repo>/pull/<n>
```

To also post the review as a comment on the PR once the quality gate passes:

```
$review-pr review https://github.com/<owner>/<repo>/pull/<n> post
```

Optional: add an exercise brief or acceptance criteria if you happen to have them (never required):

```
$review-pr review PR 42; requirements: invoices must include every line item in the total, with tests for 0, 1 and many items
```

The skill itself asks nothing. If Codex still shows "allow this command?" prompts (for `gh`, `git fetch` or package installs), those come from Codex's approval setting. To run with no prompts, use `codex exec --sandbox danger-full-access '$review-pr review <PR link>'` or start Codex with `--ask-for-approval never --sandbox danger-full-access`, on a machine where giving the agent full access is acceptable.

If the skill does ask questions such as "what are the requirements?" or "shall I post?", you have a version from before it was automated; update it (below) and restart Codex.

What you get, for each review (in `~/.krithi/reviews/<owner>__<repo>/PR-<n>/`): `report-v<k>.md` (technical review, requirements coverage, process compliance table, scorecard, recommendation, feedback history), `scorecard-v<k>.json`, `evidence.json`, `history.jsonl`, and `comment.md` (posted only with `post`). If you later disagree with something, just say so (optional): the feedback is re-checked against the evidence and saved as a new version. Every feedback event is also added to `~/.krithi/review-pr/learning-log.jsonl`; ask `$review-pr improve the skill from the feedback log` to get proposed changes, which are applied only after you approve them and the tests pass.

### Update

To get the latest version, use either option, then restart Codex.

Option 1: ask the installer to update from the URL:

```
$skill-installer update https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/review-pr
```

Option 2: remove the installed folder and install it again:

```
rm -rf ~/.codex/skills/review-pr
```

```
$skill-installer install https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/review-pr
```

### Uninstall

```
rm -rf ~/.codex/skills/review-pr
```

Reviews and the feedback log in `~/.krithi/reviews/` and `~/.krithi/review-pr/`, and comments already posted on PRs, are not removed with the skill.

## validate-pr

Validates one GitHub pull request by running it, and complements `review-pr` (which reads it). Give it the PR link. It works out the requirements and acceptance criteria (linked issue, ticket, plan-builder files, PR description, or inferred and labelled), checks out the PR's exact head commit in an isolated worktree, and reads the change, the existing tests and the repository's conventions. It writes a **test plan** (requirements, test cases with positive, negative, boundary, accessibility and regression scenarios, Required or Optional, Automated or Manual) and **Playwright tests** whose titles carry the plan's test-case IDs; `test_plan.py` checks that every requirement has a test case and every automated case has a test. It then builds and launches the application for whatever stack it finds (Node, Python, JVM, .NET, Go, Ruby, PHP, static sites; monorepos by the folder the PR changes), waits until it answers, runs the tests with screenshots and traces forced on and no retries, and collects browser console errors and application logs.

Every failure is triaged as an **application defect** (with severity, requirement, expected and actual behaviour, reproduction steps and evidence), a **test-automation problem** (fixed in the test, never in the app) or an **environment issue**; defects the PR did not introduce are marked pre-existing. `verdict.py` computes the status from the evidence: **Passed**, **Failed**, **Blocked** (for example the app cannot start; the blocker, command, exit code and log tail are recorded, never a pass) or **Needs Manual Verification**. The skill never changes application code: `commit_tests.py` commits only test plans, tests, fixtures and test configuration, only the exact diff you approved, and asks again before a fast-forward push to the PR branch (fork PRs without maintainer edits get a patch instead).

**Two locations.** Committable artifacts (plan, specs, fixtures, Playwright config) go in the repository, following its conventions; if adding Playwright to the app would break its rules (a type-check that includes every `.ts` file, a lockfile policy), they go in a self-contained `e2e/` package. Execution evidence goes outside the repository, one folder per run, keyed by GitHub's owner, repository and PR number, so PR #12 in two repositories and every run of one PR stay separate:

```
~/.krithi/validate-pr-artifacts/github/<owner>/<repo>/pr-<n>/run-<UTC timestamp>-<sha12>/
    metadata.json   PR URL, repository URL, tested commit, timestamps, environment, app, tests, status
    results/  screenshots/  traces/  logs/  defects/  report/validation-report.md
```

Set `VALIDATE_PR_ARTIFACTS` to use another location. After the report you can challenge a defect (it is re-checked against the evidence and every change is recorded with its reason), ask for more scenarios, rerun selected tests, or retest after the author pushes fixes: a retest is a new run that marks each earlier defect Resolved, Still open or Needs verification. Needs Python 3.8+, git, the `gh` CLI logged in, and the application's own toolchain; Playwright browsers are installed when missing. Details: [`SKILL.md`](skills/validate-pr/SKILL.md).

### Install

```
$skill-installer install https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/validate-pr
```

Then restart Codex.

### Test

Open Codex in a clone of the repository the PR belongs to (or anywhere, with a full PR URL) and run:

```
$validate-pr validate https://github.com/<owner>/<repo>/pull/<n>
```

With acceptance criteria, and without offering to commit the tests:

```
$validate-pr validate PR 42 no-commit; acceptance criteria: quantity 0 shows "Quantity must be at least 1"
```

After the author pushes fixes:

```
$validate-pr retest https://github.com/<owner>/<repo>/pull/<n>
```

### Update

To get the latest version, use either option, then restart Codex.

Option 1: ask the installer to update from the URL:

```
$skill-installer update https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/validate-pr
```

Option 2: remove the installed folder and install it again:

```
rm -rf ~/.codex/skills/validate-pr
```

```
$skill-installer install https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/validate-pr
```

### Uninstall

```
rm -rf ~/.codex/skills/validate-pr
```

Validation evidence in `~/.krithi/validate-pr-artifacts/`, clones and worktrees in `~/.krithi/validate-pr/`, and test plans and tests committed to PRs are not removed with the skill.

## Uninstalling from inside Codex

`$skill-installer` can only list and install skills; it has no uninstall command. You can still ask Codex to do the removal in plain language:

```
Delete the skill folder ~/.codex/skills/appsec-static-audit
```

Codex runs the delete for you. The folder is outside your project, so Codex asks you to approve the command. Restart Codex afterwards so the skill list refreshes. Do not remove the skills in `~/.codex/skills/.system/` (for example `skill-installer`); Codex manages those. If you use Codex inside WSL, the skills live in the WSL home directory, not the Windows one.
