# Task-type modules

Add the module for the classified task type to the **Investigation tasks** section, and adjust item 2 of Planning requirements. Combine two modules when the ticket mixes types. These are question lists for Codex to answer from the repo; fill in ticket specifics, never repo specifics you have not been given.

## bug
- Reproduce on paper: trace the exact steps and inputs in the ticket through the code and state where behavior diverges from expected.
- Identify the **root cause** (not just the symptom); show the line/function where it originates and why.
- Check whether the same defect exists in sibling code paths, other platforms or similar components.
- Find when and why it appeared if history makes that discoverable (recent changes to the area).
- Check logs, error handling and monitoring that should have caught it.
- Plan: smallest fix, a regression test that fails before and passes after, and checks for related paths.
- Planning item 2 is **Root cause**.

## enhancement
- Describe current behavior precisely, then the requested delta.
- Find every place the current behavior is implemented or duplicated.
- Check backward compatibility: existing users, data, API consumers, saved settings.
- Prefer extending existing patterns over new abstractions.
- Planning item 2 is **Design approach** (smallest change versus alternatives, with the trade-off).

## feature
- Find the closest existing feature and the conventions it follows (layering, naming, routing, state, validation, error handling, permissions, i18n).
- Identify integration points: data model and migrations, APIs, UI, auth/roles, configuration, jobs, external services.
- List design options with trade-offs and recommend one.
- Define the data model, interfaces and failure modes; non-functional needs (performance, security, accessibility, audit logging) the ticket implies.
- Plan phasing: what ships first, what can be flagged.
- Planning item 2 is **Design approach**.

## removal
- Distinguish removing from the **UI/entry point** versus removing the capability, data or code; follow what the ticket says and flag the difference.
- Check whether the removed item can still be reached by another route (direct API, URL or query parameters, deep links, saved state, jobs, exports); decide whether server-side validation or filtering is needed.
- Do not delete data or remove shared code unless the ticket requires it; list what other features still use the item.
- Search all references (code, config, docs, tests, fixtures, translations, caches).
- Planning item 2 is **Root cause** (why the item is still available today).

## ui-accessibility
- Identify the components, templates and styles involved, and whether they are shared.
- Map the issue to the relevant criteria (for example WCAG 2.x success criteria) and the expected fix per element: semantics, labels, names, focus order and visibility, keyboard operation, contrast, ARIA, status messages.
- Check responsive behavior, zoom/reflow, reduced motion and screen-reader announcements.
- Plan automated checks and manual checks (keyboard only, screen reader, zoom).
- Planning item 2 is **Root cause** or **Design approach**, as fits.

## refactor
- State the goal and the invariant: behavior must not change.
- Map callers and dependents; find test coverage and the gaps to close before changing code.
- Propose incremental, individually shippable steps; avoid scope creep.
- Planning item 2 is **Design approach**.

## other
Use the shared blocks only and ask the user for the missing context.
