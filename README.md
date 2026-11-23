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

The skills in this repository are reusable building blocks for that kind of work: accessibility scanning, security auditing, agent-ready documentation, ticket-to-plan prompt building, migration effort estimation, pull request preparation, pull request review, pull request validation and video editing (long-form videos and short clips from raw recordings).

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
| [`review-pr`](#review-pr) | Reviews a pull request (a workshop participant's or one Krithi generated) against its requirements and the Krithi development process: validated findings with severity, file and line and a fix; a process compliance table for the eight workflow steps; a five-factor weighted scorecard and a recommendation. Revises the review from your feedback and keeps the history, then posts the approved comment to the PR only after you confirm the exact text. |
| [`validate-pr`](#validate-pr) | Validates a pull request by testing it: works out the requirements, writes a test plan and Playwright tests into the repository (committed to the PR only after you approve the exact diff), builds and launches the app from the PR's exact commit for any stack, runs the tests, and saves screenshots, traces, console errors and app logs outside the repository per owner/repo/PR/run. Triages each failure as an application defect, a test problem or an environment issue, and computes Passed, Failed, Blocked or Needs Manual Verification. Supports reviewer challenges, extra scenarios, reruns and retests after fixes. |
| [`video-editor`](#video-editor) | Turns a raw recording (podcast, webinar, training session; Zoom, Meet or Restream export) into a clean long-form video and a set of short vertical clips, locally with ffmpeg and Whisper. Transcribes, finds dead air and false starts, and proposes a cut list and a ranked list of 30 to 90 second moments; nothing renders until you approve each list. Long form: dead air and chatter cut, brand intro and outro, lower thirds, burned-in or SRT captions, loudness normalised, YouTube chapter timestamps. Shorts: 9:16 with the speaker kept in frame, word-by-word captions, title overlay, lower third, end card, plus a suggested title and post caption for each clip. |

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

Reviews one GitHub pull request, from a workshop participant or generated by Krithi, and takes the reviewer from the PR link to an approved review posted on the PR. It establishes the requirements (linked issue, ticket, plan-builder prompt and plan, or what you give it), reads the diff at the PR's head commit with the surrounding code, and reviews functional correctness and regressions, security, accessibility (when UI files change), tests and missing scenarios, and maintainability. Every candidate is validated separately and labelled Confirmed, Likely or Needs verification; only confirmed findings count as defects. It then checks for evidence of each step of the Krithi workflow (README Generator, Prompt-Builder, Codex Plan Mode, Plan Review, Implementation, Build and Testing, prepare-pr, PR Submission) in the repository, the PR, the commits and the linked tickets, and marks each Verified, Partially Verified, Not Evidenced or Not Applicable. Not Evidenced means no evidence was found, not that the step was skipped. A five-factor scorecard (functional 30%, quality/security/accessibility 25%, testing 20%, process 15%, PR documentation 10%) gives a weighted score from 1 to 5, and the recommendation (Approve, Request Changes, Needs Further Verification) is computed so that a confirmed Critical or High finding always means Request Changes, whatever the score. You can approve the review, correct findings or ratings, add context or ask for a re-review of an area. Each round is re-checked against the evidence, saved as a new version with what changed and why, and logged for improving the skill; the skill never edits its own instructions. Posting needs your yes to the exact comment, and the script refuses if the text changed after approval or the PR has new commits since the review. Reviews are kept under `~/.krithi/reviews/` (outside the repository). Needs Python 3, git and the `gh` CLI logged in. Details: [`SKILL.md`](skills/review-pr/SKILL.md).

### Install

```
$skill-installer install https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/review-pr
```

Then restart Codex.

### Test

Open Codex in a clone of the repository the PR belongs to (or anywhere, with a full PR URL) and run:

```
$review-pr review https://github.com/<owner>/<repo>/pull/<n>
```

With the exercise brief or acceptance criteria, so the review checks against them:

```
$review-pr review PR 42; requirements: invoices must include every line item in the total, with tests for 0, 1 and many items
```

What you get, for each review (in `~/.krithi/reviews/<owner>__<repo>/PR-<n>/`): `report-v<k>.md` (technical review, requirements coverage, process compliance table, scorecard, recommendation, feedback history), `scorecard-v<k>.json`, `evidence.json`, `history.jsonl`, and `comment.md` when you choose to publish. Every feedback event is also added to `~/.krithi/review-pr/learning-log.jsonl`; ask `$review-pr improve the skill from the feedback log` to get proposed changes, which are applied only after you approve them and the tests pass.

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

## video-editor

Turns a raw recording into finished videos with very little manual editing. Point the agent at a podcast, webinar or training session (MP4 or MOV, one file or several clips from one session) and it returns a clean long-form video and a set of short clips. Everything runs on your machine with ffmpeg and a Whisper model; nothing is uploaded and no paid editing service is involved.

It works transcript first. It transcribes the recording, finds the gaps where nothing is happening (short pauses and long dead stretches, keeping any silent stretch where the picture is changing), and the agent proposes a **cut list**: where the real content starts and ends, which gaps and false starts to remove, and chapter markers. You see the cuts with the words around each one and the reason, and approve or edit them. Only then does it render. For shorts, the agent reads the transcript and proposes the strongest **30 to 90 second moments**, each with a hook, a one-line reason, a score, a title and a post caption, and renders only the ones you choose. Scripts check every list (no cut inside a word, clip lengths, opening words, overlaps, copy style) before anything renders.

Branding lives in one file, `assets/brand/brand.json`: logos, fonts, colours, intro and outro cards, lower-third and caption styles, loudness targets and a glossary of names for Whisper. The bundled defaults are lowtouch.ai's; pass `--brand` to use another.

**Long form** (`long.mp4`, `long.srt`, `chapters.txt`): dead air, long pauses, false starts and the chatter before and after the session cut; brand intro and outro; lower thirds; burned-in or sidecar (SRT) captions as you choose; loudness normalised to -16 LUFS; chapter timestamps ready to paste into YouTube.

**Shorts** (one folder per clip: `clip.mp4`, `clip.srt`, `meta.md`): 1080x1920 with the speaker kept in frame by a face-aware crop that changes only at cuts; a title over the first seconds; word-by-word captions with the current word highlighted; a lower third; a gradient end card; loudness at -15 LUFS; and `meta.md` with the title, post caption and reason.

Re-running with different instructions is cheap. The transcript and the dead-air analysis are kept in `~/.krithi/video/<name>/`, so "find three more clips about security" or "cut more of the pauses" starts from the existing work instead of transcribing again.

**Limits to know about.** Face detection is simple: it suits one person facing the camera, and a panel or a side-by-side layout needs a check by eye. Speaker names are supplied by you, because Zoom, Meet and Restream files carry no speaker labels. Cutting false starts and choosing moments is the agent's judgement, so review the lists before approving. Export of the cut list to Premiere or DaVinci is not included yet.

**Needs:** Python 3.8+ (3.11 or 3.12 recommended), `ffmpeg` and `ffprobe` built with `libass` and `libx264`, about 1 GB of disk for the Python packages in a virtualenv under `~/.krithi/video/venv` (outside any repository), and about 0.5 GB for the default Whisper model, which downloads on first use. Transcription takes roughly 0.4 times the recording's length on a CPU-only laptop; a GPU is faster. Details: [`SKILL.md`](skills/video-editor/SKILL.md).

Install ffmpeg first if you do not have it (the skill checks and prints the right command for your system):

```
sudo apt install ffmpeg          # Debian or Ubuntu
brew install ffmpeg-full         # macOS (the plain "ffmpeg" formula has no libass, so captions fail)
winget install Gyan.FFmpeg       # Windows (the full build, not "Essentials")
```

### Install

In Codex:

```
$skill-installer install https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/video-editor
```

Then restart Codex.

In Claude Code, copy the skill folder into your personal skills folder:

```
git clone https://github.com/lowtouch-ai/krithi-skills.git
```

```
cp -r krithi-skills/skills/video-editor ~/.claude/skills/video-editor
```

Then start a new Claude Code session. The first time you use the skill it checks your machine and, with your agreement, sets up the Python virtualenv (`scripts/setup_env.py`).

### Test

Open Codex or Claude Code in any folder and run (in Codex use `$video-editor`; in Claude Code use `/video-editor`, or just describe what you want):

```
$video-editor edit /path/to/recording.mp4: a clean long video with SRT captions and a few shorts. The speaker is Alex Doe, Head of Product.
```

With notes:

```
$video-editor edit /path/to/webinar.mp4, focus on the pricing discussion and skip the first 10 minutes. Long video only, burned-in captions.
```

Several clips from one session:

```
$video-editor edit these clips as one session: /path/part1.mp4 /path/part2.mp4 /path/part3.mp4
```

After the first run, ask for changes without starting over:

```
$video-editor find three more clips about security
```

### What you get

Working files stay under `~/.krithi/video/<name>/` (set `KRITHI_HOME` to change `~/.krithi`):

```
~/.krithi/video/<name>/
    source.json  transcript.json  transcript.md  analysis.json
    cutlist.json  clips.json  sentences.md
    renders/<run-id>/
        long.mp4  long.srt  chapters.txt
        clip-01-<title>/  clip.mp4  clip.srt  meta.md
```

Each render goes to a new folder, so earlier versions are kept. Your original recording is never modified.

### Update

To get the latest version, use either option, then restart Codex or start a new Claude Code session.

Option 1: in Codex, ask the installer to update from the URL:

```
$skill-installer update https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/video-editor
```

Option 2: remove the installed folder and install it again (the virtualenv and your working files are not affected):

```
rm -rf ~/.codex/skills/video-editor
```

```
$skill-installer install https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/video-editor
```

For Claude Code, pull the repository and copy the folder again:

```
git -C krithi-skills pull
```

```
rm -rf ~/.claude/skills/video-editor && cp -r krithi-skills/skills/video-editor ~/.claude/skills/video-editor
```

### Uninstall

```
rm -rf ~/.codex/skills/video-editor ~/.claude/skills/video-editor
```

To also remove the virtualenv and your working files: `rm -rf ~/.krithi/video`.

## Uninstalling from inside Codex

`$skill-installer` can only list and install skills; it has no uninstall command. You can still ask Codex to do the removal in plain language:

```
Delete the skill folder ~/.codex/skills/appsec-static-audit
```

Codex runs the delete for you. The folder is outside your project, so Codex asks you to approve the command. Restart Codex afterwards so the skill list refreshes. Do not remove the skills in `~/.codex/skills/.system/` (for example `skill-installer`); Codex manages those. If you use Codex inside WSL, the skills live in the WSL home directory, not the Windows one.
