# PRD templates

These follow Kriti-REQ's PRD content contract (`kriti_req` in `agent_workflows`: `_default_scan_prompt_body` and the design doc `Kriti-REQ_PRD.md`), so a PRD from this skill reads like one from Krithi. The estimate adds two things REQ does not have: **Source coverage** and **Stories**.

All files go in `docs/migration-estimate/` at the root of the repository being estimated. `estimate.py` checks the headings below, so keep them exactly as written. The "(checked ...)" notes explain the template; leave them out of the files. Replace every `{...}`.

## Kriti-REQ writing rules (apply to every PRD)

1. **Group by use case or feature area**, not a flat list or technical layers.
2. **Cite the source of every requirement, use case or sub-section**: the file or folder path in the repository, or the attachment it came from. Put citations in backticks at the end of the statement or in a `Source:` line.
3. **Plain English throughout.** The reader is a product manager or business reviewer with no code access. Never write a field name, enum or constant value, class or method name, endpoint or screen identifier, config or file name, or error code inline in a sentence; translate it into its business meaning ("an account can be active, inactive, or pending approval", not "the status field supports ACTIVE, INACTIVE, PENDING"). The citation carries the technical anchor.
4. **Read past the surface.** Do not stop at routes, controllers, UI text or i18n strings. Also read the service or business-logic layer a feature delegates to, the domain or database model and migrations it uses, any permission, guard or middleware code that gates it, and README, help, docs and tests where present. Mark something low-confidence only after checking those layers.
5. **Confidence percentages.** Every item under Confidence & Open Questions carries "Confidence: NN%", based strictly on how directly the code supports it. Reserve 95% or higher for something verified directly in the code with no assumption.

## High-level PRD: `00-high-level-prd.md`

```markdown
# High-level PRD: {Application name}

## Overview
{What the application does, for whom, and what the migration or modernisation is for, in plain English. Target platform if the user gave one; otherwise "Target platform not specified; the estimate assumes a like-for-like rebuild on a modern stack."}

## Current system
{Languages, frameworks, size (source files and lines from the inventory), how it is layered and deployed. This is the one section where technology names are expected; still no code identifiers.}

## Use cases and feature areas
{One bullet per use case or feature area, one or two plain-English sentences each, pointing to the detailed PRD that covers it, with its source citation.}

## Detailed PRDs   (checked: every PRD id here must have a file, and every file must be listed)
| ID | Use case / feature area | Scope | Main code paths |
|---|---|---|---|
| PRD-01 | {title} | {one line} | `{path}` |

## Roles & Permissions Model
{Aggregated across the whole application: each role, what it can do, any restrictions.}

## Data Model Overview
{The main business entities and how they relate, in plain English.}

## Integrations
{Every external system: databases, queues, identity, payment, email, file transfer, partner APIs, scheduled jobs. What each is used for, with citations.}

## Non-Functional Requirements
{Performance, security, scalability, audit and error-handling patterns actually observed in the code, not assumed.}

## Release / Versioning Scope
{What is on by default versus optional, plugin or disabled, where the code or config shows it.}

## Out of scope   (checked: backticked paths here count as covered for the coverage check)
{Code deliberately not estimated, one bullet each with the reason, e.g. "- `legacy/reports-v1/`: not reached from any menu, route or job (verified)". "None." if nothing is excluded.}

## Not included in the estimate
QA sign-off, production deployment and data migration are not estimated; they are covered by the approximate go-live allowance in the estimate summary.

## Confidence & Open Questions
- {Statement or question}. Confidence: {NN}%
```

## Detailed PRD: `prd-NN-<slug>.md`

One file per use case or feature area. `NN` is two digits and matches the id (`prd-03-billing.md` holds `PRD-03`). `<slug>` is lowercase words joined by `-`. Cross-cutting work (sign-in and roles, shared screens and navigation, platform and CI setup, integration clients) gets its own detailed PRD when no single feature area owns it.

```markdown
# PRD-NN: {Use case or feature area}   (checked)

## Description   (checked)
{What this area does today and what the migrated version must do, in plain English. Source: `{path}`}

## Business Rules & Logic   (checked)
1. {Decision, calculation or validation the system actually makes, in plain English.} `{path}`

## Roles & Permissions   (checked)
- {Which roles can access or perform this, and any restrictions.} `{path}`

## Key Data Involved   (checked)
- {Business entities and relationships this area reads or writes.} `{path}`

## Notable Constraints   (checked)
- {Validation rules, limits, error handling actually observed in the code, never assumed.} `{path}`

## Integrations
- {External system this area uses and for what, or "None."}

## Source coverage   (checked: backticked folder or file paths, relative to the repo root)
- `{path/to/module}`: {what is in it}

## Stories   (checked: every "### PRD-NN-SMM: <title>" heading under here is one story)

### PRD-NN-S01: {Short story title}
As a {role}, I want {capability} so that {outcome}.

**Acceptance criteria**
- {Testable criterion}

**Source:** `{path}`

### PRD-NN-S02: {...}

## Dependencies
- {Other PRDs this depends on, e.g. "PRD-01 (sign-in and roles) must land first", or "None."}

## Confidence & Open Questions   (checked)
- {Statement or question}. Confidence: {NN}%
```

## Writing stories

Kriti-PLAN (story breakdown and sprint planning) is not built yet, so these rules are this skill's. Keep them identical for every client so estimates are comparable.

- **One story = one user-visible or system-visible capability that one engineer can build and test in a few days.** Each covers its own development and unit/integration testing.
- **Derive stories from the PRD sections**: each distinct business rule group, permission behaviour, screen or endpoint group, scheduled job, report or export, and integration client in the PRD maps to at least one story. Split a story that spans several screens, several endpoints with different rules, or a UI plus a batch job. Merge stories that are only a field or a label.
- **Cover what the code does, not what it could do.** Each story cites the code it re-implements (`**Source:**`). No stories for new features the client did not ask for.
- **Include the unglamorous work** the migration needs: authentication and roles, shared layout and navigation, configuration and secrets, logging and audit, error handling, each integration client, each scheduled job, each report or export, API contracts used by other systems, and the CI pipeline and automated test harness for the new codebase.
- **No stories** for QA sign-off, production deployment or data migration. They are outside the estimate and covered by the go-live allowance.
- Number stories `S01`, `S02`, ... within each PRD with no gaps. Never write a story heading in any other form: it would not be counted.
