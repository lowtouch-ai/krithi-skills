# Prompt template

The generated prompt is one Markdown file. Use these sections in this order. Fill each from the ticket; where the ticket gives nothing, write `Not specified in the ticket` (never invent). Replace every `{...}` before saving; `check_prompt.py` fails on leftovers.

```markdown
> **PLAN MODE ONLY.** Do not create, edit, rename or delete any file, do not create branches or commits, and do not run commands that change the repository, its data or any environment. Read, search and analyze only.

# {TICKET}: {Ticket title}

## Objective
{2-4 sentences: what must change and why, including business context from the ticket. Say "Review the existing codebase and produce an implementation plan to ..."}

## Ticket details
{Task type: bug | enhancement | feature | removal | ui-accessibility | refactor}
{The specifics exactly as the ticket words them: numbered/bulleted list of the items, labels, fields, screens, endpoints, rules or values involved. For a bug: observed vs expected behavior, steps to reproduce, environment, frequency. For a feature: the user story and each requirement.}

## Key terms
{Terms, labels, identifiers, error messages, screen or field names, and domain words taken verbatim from the ticket, one bullet each, with at most a few words of context from the ticket. Say: "Use these as starting points for searching the repository. Confirm what each means in this product from the code; do not assume."}

## Supporting artifacts
{One bullet per verified artifact: `{absolute path}`: what it shows / why it matters. Instruct: "Read each artifact before exploring the code." If none: "No supporting artifacts were provided."}

## Expected behavior
{Bulleted outcomes after the change, from the ticket. Include what must keep working and what must not change.}

## Investigation tasks
Before proposing changes, inspect the repository and verify (do not assume):
{Shared blocks below plus the task-type module(s) from task-type-modules.md.}

## Planning requirements
Produce a detailed plan that includes:
1. **Current architecture:** how the relevant feature works today (entry points, data flow, key files and functions).
2. **{Root cause | Design approach}:** {bug/removal/enhancement: why the current behavior occurs | feature: options considered and the recommended one}.
3. **Files to modify:** exact paths, functions, configuration entries and what changes in each; files to create; files that must not change.
4. **Recommended implementation:** the smallest safe change that fully satisfies the ticket, as ordered steps.
5. **Dependencies and impact:** shared code, other callers, consumers, data, jobs, integrations, configuration and environments affected.
6. **Risks and regression areas:** what could break, how likely, and how to mitigate.
7. **Testing strategy:** unit, integration, end-to-end and manual tests, including negative and edge cases, with real commands and test file locations found in the repo.
8. **Rollout and compatibility:** migrations, feature flags, backward compatibility, rollback, if relevant.
9. **Acceptance criteria:** a checklist that proves each ticket requirement is met.
10. **Open questions:** anything ambiguous that needs an answer before implementation.

## Constraints
- **PLAN MODE ONLY: do not modify any files or implement changes yet.**
- Follow the repository's existing architecture, conventions and patterns.
- Prefer minimal, targeted changes over broad refactoring.
{Ticket-specific constraints: what must not be removed, deleted or changed; compatibility rules.}
- Do not assume; verify by inspecting the code. Clearly label each finding **Confirmed** (seen in code or artifact) or **Assumption**.
- Reference actual file paths and function names.
- If requirements are ambiguous, list the questions instead of guessing.

## Open questions from the ticket
{Ambiguities, contradictions, unreadable artifact parts. Or "None identified."}

## Deliverable
Provide a step-by-step implementation plan with exact file references, proposed changes, testing approach and risks. Do not begin implementation until the plan has been reviewed and approved.

> **PLAN MODE ONLY.** Do not modify any code.
```

## Shared investigation blocks (use the ones that apply; rename freely)

1. **Locate the code:** find where this feature, screen, endpoint, job or behavior is implemented; list entry points and how a request or user action reaches them.
2. **How the data or options originate:** hardcoded, configuration, database, API, feature flag or generated; whether shared components or configs are reused by other features.
3. **Backend and data access:** APIs, services, queries and models involved; how the relevant values are represented internally (IDs, codes, enums, mappings); whether behavior can be reached by another route (direct API call, URL parameter, background job) even if one path is changed.
4. **Dependencies and impact:** search the whole repo for references to the affected names, labels, identifiers and configuration; identify shared logic, caches, scheduled jobs, reports and other consumers.
5. **Existing tests and tooling:** where tests live, how they are run, which already cover this area.
6. **Conventions:** how similar changes were done before (search history or neighboring code).

## Writing rules

- Describe the task in plain, precise sentences; quote labels and names exactly as the ticket writes them.
- Do not name repo files, classes or functions unless the ticket does.
- Keep every section ticket-specific; delete a shared block that does not apply instead of leaving filler.
- Remove sections that cannot apply only if the template says so; otherwise keep the heading and state "Not applicable: {reason}".
- Include no secrets; refer to the artifact instead.
- **Prompt only, no scanning.** Do not search or read the target repository to write the prompt, and do not explain domain concepts from your own knowledge. Plan Mode does the investigation. Key terms are the ticket's words, not definitions.
- If a term looks like a typo or is unclear (for example an odd phrase in a comparison), keep it verbatim in Key terms and add a question under Open questions instead of correcting it.
- Do not tell Codex to open URLs from the ticket (environments, Jira links); they are context only.
