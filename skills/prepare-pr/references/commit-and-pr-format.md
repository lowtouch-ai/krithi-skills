# Commit message and PR description

Write for a reviewer who has not seen the conversation and for someone reading `git log` a year from now. Explain **why** the change was made; the diff already shows **what** each line does.

## Commit message

```
<subject: imperative, 72 characters or fewer, no trailing period>

<1 to 3 short paragraphs: the problem or goal, and why this approach.
Mention the ticket if there is one.>

- <key change 1: what and where, briefly>
- <key change 2>
- <key change 3>

Testing:
- <command>: <result, e.g. "48 passed">
- <manual check, if one was done: what and outcome>
<known gaps: "Not tested: X, because Y">

<trailers the repo already uses, e.g. Refs: ABC-123>
```

Rules:
- **Subject**: imperative ("Add", "Fix", "Remove", not "Added"/"Fixes"). Follow the repo's style. If `conventions.conventional_commits` is true, use `type(scope): subject` (`feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`). If recent subjects use another pattern (such as `area: subject` or a ticket prefix), copy it.
- **Body**: wrap at about 72 characters. Say what was wrong or missing, what changes for users or callers, and any important decision (and the alternative that was rejected, if that helps the reviewer). Skip the body only for a trivial one-line change.
- **Bullets**: 2 to 6, for the changes a reviewer should know about. Not a file-by-file list.
- **Testing**: the commands that actually ran and their real results. Never claim a test that did not run.
- **Breaking changes**: say so in the body (`BREAKING CHANGE: ...` footer with Conventional Commits).
- **No tool attribution** or co-author lines unless the repo already uses them or the developer asks.
- One commit per logical change. If the in-scope work holds two unrelated changes, offer to make two commits.

### Example

```
fix(billing): include the last line item in invoice totals

Invoices with three or more items were under-billed: the total loop
stopped one item short, so the last item was never counted. Reported
in ABC-123 for a customer with a 4-item monthly invoice.

The loop now iterates over the items directly, and the total is
computed in one helper shared by the PDF and the API response, which
had drifted apart.

- Fix the range in Invoice.total() and remove the duplicated sum in
  InvoiceSerializer
- Add tests for 0, 1 and 4 line items and for discounted items
- Update docs/billing.md: totals now include shipping lines

Testing:
- pytest tests/billing: 31 passed
- pytest (full suite): 412 passed, 2 skipped (need Redis, unchanged)
- Manually generated the PDF for the invoice in ABC-123: total matches

Refs: ABC-123
```

## Pull request

**Title**: the commit subject for a single commit; otherwise one line summarising the whole branch in the same style.

**Body** (use the repo's PR template instead when there is one, filling each of its sections with this content):

```markdown
## Summary
<2 to 4 sentences: what this PR does and why. Link the ticket.>

## Changes
- <grouped by area; what changed and why it matters to a reviewer>

## Review notes
- <issues found during the pre-PR review and how they were fixed>
- <known issues not fixed, with reasons; requirements only partly met>
- <anything the reviewer should look at closely: risky areas, design decisions, migrations>

## Documentation
- <docs updated, or "No documentation changes needed: <reason>">

## Testing
- [x] `<command>`: <result>
- [x] <manual check and outcome>
- [ ] <not tested, and why>

## Breaking changes / deployment notes
<config, env vars, migrations, feature flags, rollout order; or "None">
```

Rules:
- Every statement must be true of the pushed code. Do not list tests that were not run or fixes that were not made.
- Keep it scannable: short bullets, no repetition of the commit body word for word.
- Leave out empty sections, except Testing (write "Not run: <reason>" if nothing ran).
- Do not include secrets, customer data or internal URLs the repo does not already contain.
