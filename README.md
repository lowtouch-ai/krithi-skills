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

The skills in this repository are reusable building blocks for that kind of work: accessibility scanning, security auditing, agent-ready documentation, ticket-to-plan prompt building, migration effort estimation and pull request preparation.

## Skills

| Skill | What it does |
|---|---|
| [`repo-readme-generator`](#repo-readme-generator) | Creates or updates a repo's README, or a full documentation suite with `AGENTS.md` and diagrams, from verified evidence. |
| [`appsec-static-audit`](#appsec-static-audit) | Source-code-only security audit of one repository or several (OWASP, SSO, secrets, dependencies and SBOM, IaC, CI/CD, PII/FTI) with a timestamped enterprise report, SARIF output and a CI gate, mapped to NIST 800-53, IRS Pub 1075 and EOTSS. |
| [`wave-a11y-scan`](#wave-a11y-scan) | WAVE-style accessibility scan of a project's source code with a client-ready report (WCAG 2.x, Section 508 note). |
| [`plan-builder`](#plan-builder) | Turns a ticket (text, screenshot, HTML, Markdown, logs) into a ready-to-paste Codex Plan Mode prompt; supporting artifacts are saved under `~/.krithi/<TICKET>/` (outside the repo) and referenced by verified absolute paths; the prompt is saved under `docs/plan-prompts/`. |
| [`migration-estimate`](#migration-estimate) | Reads a codebase and estimates migration or modernisation effort the Krithi way: high-level PRD, detailed PRDs, stories and sprints, with a human-team vs Krithi timeline side by side, an approximate go-live allowance, and a self-review for coverage; all Markdown under `docs/migration-estimate/`. |
| [`prepare-pr`](#prepare-pr) | Takes finished, tested work to a pull request: reviews the change (bugs, security, quality, performance, requirements) and fixes what you approve, runs the tests, updates only the docs the change affects, checks the branch name fits the work, commits only in-scope files with a detailed message, then asks before pushing and opening the PR. |

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

WAVE-style accessibility scan of a project's source code (HTML, templates, JSX/TSX, Vue, Svelte, Astro) with a client-ready report (WCAG 2.x, Section 508 note). The report also covers the [Mass.gov web testing checklist](https://accessibility.mass.gov/testing-checklists/web-testing-checklist/): each of its 50 items is marked as checked by the scan, partly checked, or manual-only, with a manual test for the rest. It also adds a static subset of axe-core rules, lists contrast checks left for a person, and points to the tools Mass.gov recommends (axe DevTools, WAVE, Accessibility Insights, ANDI, contrast checkers). Findings carry file and line. It needs only Python 3; no browser or install. Automated checks do not prove code is accessible; manual keyboard and screen-reader testing is still required. Details: [`SKILL.md`](skills/wave-a11y-scan/SKILL.md).

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

Estimates the effort to migrate or modernise the application in the current repository: it reads the code, writes a high-level PRD in Kriti-REQ's PRD format (use cases, business rules, roles, data, citations, confidence), breaks it into detailed PRDs, converts each into stories and counts sprints. Five stories make one sprint of two engineers; a human team runs a sprint in 10 working days and Krithi in 2, so the same sprint count is five times faster (40 sprints = 80 weeks vs 16 weeks). The estimate covers development and testing only; QA sign-off, production deployment and data migration are listed separately with an approximate 20% go-live allowance. All numbers are computed by a script from the PRDs. Before finishing, the skill checks the PRDs against the codebase for missed modules, integrations and features, scores the gap the way Kriti-REQ's quality check does, reworks above 30%, re-runs the estimate and records the check in `review.md`. Details: [`SKILL.md`](skills/migration-estimate/SKILL.md).

### Install

```
$skill-installer install https://github.com/lowtouch-ai/krithi-skills/tree/main/skills/migration-estimate
```

### Test

Open Codex at the root of the application repository and run:

```
$migration-estimate estimate the migration effort for this codebase
```

Output, in the repository: `docs/migration-estimate/00-high-level-prd.md`, one `prd-NN-<slug>.md` per detailed PRD, `estimate-summary.md` and `review.md`. The codebase inventory is saved outside the repository under `~/.krithi/migration-estimate/<repo>/`.

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

## Uninstalling from inside Codex

`$skill-installer` can only list and install skills; it has no uninstall command. You can still ask Codex to do the removal in plain language:

```
Delete the skill folder ~/.codex/skills/appsec-static-audit
```

Codex runs the delete for you. The folder is outside your project, so Codex asks you to approve the command. Restart Codex afterwards so the skill list refreshes. Do not remove the skills in `~/.codex/skills/.system/` (for example `skill-installer`); Codex manages those. If you use Codex inside WSL, the skills live in the WSL home directory, not the Windows one.
