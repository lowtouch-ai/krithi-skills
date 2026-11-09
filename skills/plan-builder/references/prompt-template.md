# Prompt template

The generated prompt is one Markdown file. Use these sections in this order. Fill each from the ticket, from reasoning about it, and from the repo's AGENTS.md, README.md and docs/ (never from the source code). Replace every `{...}` before saving; `check_prompt.py` fails on leftovers. State each fact once: do not repeat it across sections.

```markdown
> **PLAN MODE ONLY.** Do not create, edit, rename or delete any file, do not create branches or commits, and do not run commands that change the repository, its data or any environment. Read, search and analyze only.

# {TICKET}: {Ticket title}

## Objective
{2-4 sentences: what must change and why, including the business or user context from the ticket. Start with "Review the existing codebase and produce an implementation plan to ..."}

## Ticket details
Task type: {bug | enhancement | feature | removal | ui-accessibility | refactor}
{What the ticket says, as the ticket words it: the exact items, labels, fields, screens, endpoints, rules or values involved, numbered or bulleted. Bug: environment, steps to reproduce, observed vs expected, frequency. Feature: the user story and each requirement. Mark a statement "Not specified in the ticket" only where a reader would expect it.}

## Key terms
{The ticket's own names, labels, identifiers, error text and domain words, verbatim, one bullet each, with at most a few words of context from the ticket. Give the quoted phrases AND the distinct single-word stems (for example "fragment analysis images" and `fragment`, `plot`), because code identifiers rarely match whole phrases. Say: "Use these as starting points for searching the repository. Confirm what each means in this product from the code; do not assume."}

## Repository context
{From AGENTS.md, README.md and docs/ only, labelled "per docs" and unverified against the code. Include: "Read `AGENTS.md` first and follow it" if it exists; one line on what the product is and how it is layered; the `AGENTS.md` rules and documented build/test/lint commands that matter here; the doc paths most relevant to this ticket ("read these first"); what the docs say the Key terms mean. Keep it short, a few bullets. If there is no AGENTS.md, README or docs/, write "No AGENTS.md, README.md or docs/ found; discover the architecture and conventions from the code." Say: "Confirm all of this against the code; the documentation may be stale."}

## Supporting artifacts
{One bullet per verified artifact: `{absolute path, e.g. /home/user/.krithi/ABC-123/screenshot.png}`: what it shows / why it matters. Use the absolute paths reported by save_artifacts.py (the files live outside the repository). Say: "Read each artifact before exploring the code." If none: "No supporting artifacts were provided."}

## Expected behavior
{Outcomes after the change. First what the ticket states. Then what it clearly implies (see the next section), each labelled **Assumption**. Always include what must keep working and what must not change.}

## Implied requirements and hazards
{Reasoned from the ticket only. A short list of what a careful engineer would ask about this change, each labelled **Assumption** for Codex to verify: other routes to the same behavior (direct API or URL, saved state, jobs, exports, other screens), data or capabilities that must be preserved, shared components or consumers that may be affected, environments or users affected. Pick only what applies to this ticket; skip the rest. No filler.}

## Investigation tasks
Before proposing changes, inspect the repository and verify (do not assume). Group the questions by the layers this ticket touches, written for this ticket (not generic):
{For example, only those that apply: UI/front end; backend and data access; integrations or uploads; dependencies and impact. Start from the Key terms. Add the task-type module questions from task-type-modules.md, rewritten with the ticket's own terms.}

## Planning requirements
Use exactly these headings, in this order, in your plan. If a section has nothing to report, write "None" under it.
1. **Current architecture:** how the relevant feature works today (entry points, data flow, key files and functions).
2. **{Root cause | Design approach}:** {bug/removal: why the current behavior occurs | enhancement/feature: options considered and the recommended one}.
3. **Files to modify:** exact paths, functions, configuration entries and what changes in each; files to create; files that must not change.
4. **Recommended implementation:** the smallest safe change that fully satisfies the ticket, as ordered steps.
5. **Dependencies and impact:** shared code, other callers, consumers, data, jobs, integrations, configuration and environments affected.
6. **Risks and regression areas:** what could break, how likely, and how to mitigate.
7. **Testing strategy:** unit, integration, end-to-end and manual tests, including negative and edge cases, with real commands and test locations found in the repo.
8. **Rollout and compatibility:** migrations, feature flags, backward compatibility, rollback, if relevant.
9. **Acceptance criteria:** a checklist that proves each ticket requirement is met.
10. **Open questions:** anything ambiguous that needs an answer before implementation.

## Constraints
- **PLAN MODE ONLY: do not modify any files or implement changes yet.**
- Follow the repository's existing architecture, conventions and patterns.
- Prefer minimal, targeted changes over broad refactoring.
{Ticket-specific "do not" and "preserve" lines derived from the ticket and the hazards above: what must not be deleted, removed globally or changed, and what must keep working.}
- Do not assume; verify by inspecting the code. Label each finding **Confirmed** (seen in code or artifact) or **Assumption**.
- Reference actual file paths and function names.
- If requirements are ambiguous, list the questions instead of guessing.

## Open questions from the ticket
{Ambiguities, contradictions, unclear or typo-like terms, unreadable artifact parts, missing evidence. Or "None identified."}

## Deliverable
Provide a step-by-step implementation plan with exact file references, proposed changes, testing approach and risks. Do not begin implementation until the plan has been reviewed and approved.

> **PLAN MODE ONLY.** Do not modify any code.
```

## Writing rules

- **Prompt only, light context.** Read only AGENTS.md, README.md and docs/ (shallowly) to write the prompt; never source code. Do not explain domain concepts from your own knowledge. Plan Mode does the investigation. Key terms are the ticket's words; add their documented meaning only "per docs".
- **Reason, don't invent.** Ticket facts are stated plainly. Implications and hazards you reason out are labelled **Assumption**. Never state an invented fact as if the ticket said it.
- **Say each fact once.** Use "Confirmed (from ticket)" only where a statement could be mistaken for an assumption; do not put it on every line.
- Quote labels and names exactly as the ticket writes them. Do not name repo files, classes or functions unless the ticket or the docs do (then cite the doc).
- If a term looks like a typo or is unclear (for example an odd phrase in a comparison), keep it verbatim in Key terms and add a question under Open questions instead of correcting it. Do not build the Objective on it.
- Do not tell Codex to open URLs from the ticket (environments, Jira links); they are context only. Say so when the ticket contains one.
- **Numbers that depend on the setup** (screen sizes such as 1920 x 1080, time limits, volumes): ask under Open questions what they measure (physical screen, browser viewport, display scaling) and what the acceptance target is. Do not invent measurements.
- Drop an investigation layer or hazard that does not apply instead of leaving filler. Keep the other headings; write "Not applicable: {reason}" if needed.
- Include no secrets; refer to the artifact instead.
