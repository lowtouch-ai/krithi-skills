# Technical review guide

The goal is a short list of **real problems in this PR**, each tied to code and a concrete failure, plus a clear account of what was checked. A long list of possibilities buries the real issues and makes the author distrust the review. When in doubt, a candidate goes to **Needs verification**, never to Confirmed.

This method combines Claude Code's PR review approach (independent passes, then a separate validation of every candidate, high-signal only) with the checklist in `prepare-pr`'s review guide, so authors and reviewers use the same bar.

## 1. Understand before judging

- Read the requirements first (SKILL.md step 1): what the PR must do and its acceptance criteria.
- Read the whole diff (`gh pr diff <n>`), then for each changed hunk the full function, its callers and callees, the tests that cover it, and the config or schema it depends on. Read files at the PR head commit (`git show <head-sha>:<path>`, or `gh api repos/<o>/<r>/contents/<path>?ref=<sha>`), not the reviewer's working copy.
- Read the project's rules (`AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`) that apply to the changed paths. A rule violation is a finding only if you can quote the rule.

## 2. Generate candidates: five independent passes

Run each pass on its own, looking only for its area. If your environment can run sub-agents, run them in parallel and give each the PR title, description, requirements and diff; otherwise run them one after another. Be thorough here; the filter comes in step 3.

### A. Functional correctness and regressions
- Each requirement and acceptance criterion: where is it implemented? Met, partly met, not met.
- Logic errors: inverted conditions, off-by-one, wrong variable or operator, missing return/break, fall-through.
- Edge cases: empty, null/None/undefined, zero, negative, very large, Unicode, duplicates, missing keys, time zones.
- Error handling: swallowed exceptions, errors turned into success, partial writes, missing cleanup, unbounded retries.
- Regressions: callers not updated after a signature/return change, changed defaults, removed behaviour other code relies on, changed API/schema/serialization, migrations.
- State and concurrency: races, shared mutable state, stale caches, async not awaited.
- Scope: behaviour nobody asked for, or something the plan's non-goals excluded.

### B. Security
- Injection (SQL, shell, template, path, header, log) from user input; unsafe eval/deserialization.
- Missing authentication/authorization on new endpoints or actions; IDOR; privilege escalation.
- Secrets in code, config, tests, fixtures, logs; sensitive data in logs, errors, responses, URLs.
- XSS (unescaped output, `dangerouslySetInnerHTML`, `v-html`, `|safe`), SSRF, open redirects, upload checks.
- Weak crypto, predictable tokens, missing CSRF, insecure cookies, disabled TLS verification.
- New dependencies: unmaintained, typo-squatted, unpinned where the project pins.
- For a broad check, `appsec-static-audit` (if installed) can scan the head tree; treat its output as candidates.

### C. Accessibility (only when UI files changed: `file_groups.ui`)
- Images without alt text; icon-only buttons or links without an accessible name; inputs without labels.
- Keyboard: click handlers on non-focusable elements, removed focus outlines, focus traps, positive tabindex.
- Semantics: heading order, landmarks, tables for layout, ARIA referencing missing ids, `aria-hidden` on focusable content.
- Colour contrast for new colours; text sized in px that blocks zoom; information conveyed by colour only.
- `wave-a11y-scan` (if installed) can scan the changed UI files; treat its output as candidates. Automated checks do not prove accessibility; say what still needs manual keyboard/screen-reader testing.

### D. Tests and validation
- Does every changed behaviour have a test? Does every acceptance criterion have a test that would fail if it were broken?
- Tests that assert nothing meaningful, mock the thing under test, depend on order/time/network, or were weakened, skipped or deleted in this PR.
- Missing scenarios: list the specific cases (input → expected result) that are not covered.
- CI results (`ci` in the evidence) versus claims in the PR body and commits. A claim without CI or a local run is **claimed**, not verified.

### E. Maintainability and consistency
- Duplication of logic that already exists (name the existing helper and its location).
- Inconsistency with how surrounding code does the same job (errors, logging, config, data access, naming).
- Dead code, debug output, commented-out blocks, stray TODOs added by this PR; comments that no longer match.
- Non-obvious logic without a comment explaining why (Krithi `AGENTS.md` convention: adequate code comments).
- Performance that matters at realistic data sizes: N+1 queries, I/O in loops, unbounded loads, missing timeouts.

## 3. Validate every candidate (separately from finding it)

For each candidate, act as a skeptic trying to disprove it:
1. Is the code path reachable with real inputs? Trace it from an entry point.
2. Does something already handle it (an upstream guard, framework validation, a type, a test)?
3. Write the failure scenario: *with input/state X, line Y does Z, so the result is W instead of V.*
4. If it is cheap and safe, prove it: run the relevant test, or a one-line script, in the temporary worktree (SKILL.md step 3).
5. Is it introduced or made reachable by **this PR**? Pre-existing, untouched code is out of scope (mention it once under Notes if serious).

Then label it:

| Status | Meaning | Where it goes |
|---|---|---|
| **Confirmed** | Traced through the code with a concrete failure scenario, or reproduced by running it | Findings; counts toward the recommendation |
| **Likely** | Strong reasoning but a link in the chain could not be checked (runtime config, external service, code not available) | "Needs verification" section, with what would confirm it |
| **Needs verification** | Plausible concern, not traced | "Needs verification" section, phrased as a question |
| **Withdrawn** | Disproved during validation or by reviewer feedback | Dropped from the report; kept in the review history |

Never present Likely or Needs verification items as defects, and never let them lower the rating as if they were confirmed. Drop: style preferences, things a configured linter/formatter catches, pre-existing issues, and pedantic nitpicks a senior engineer would not raise.

## 4. Severity

| Severity | Meaning | Examples |
|---|---|---|
| Critical | Data loss, security breach, or the main feature broken for normal use | SQL injection on a public endpoint; migration dropping data; crash on the main path |
| High | Wrong results or a crash in a realistic case; a requirement not met; an exploitable security weakness | Off-by-one dropping the last record; missing auth check on an admin action; acceptance criterion not implemented |
| Medium | Fails in edge cases, or a real maintainability, performance or accessibility cost | Missing timeout on an external call; N+1 on a list page; unlabelled form input |
| Low | Minor, worth fixing while here | Misleading name; stale comment; leftover debug log |

## 5. Finding format

```
F3 [High · Confirmed] src/billing/invoice.py:142 — total excludes the last line item
Category: Functional correctness
Failure: an invoice with items 10/20/30 totals 30 instead of 60, because range(len(items) - 1) stops one short.
Evidence: traced Invoice.total() from POST /invoices; tests/test_invoice.py only covers 1 item.
Fix: iterate over items directly (`for item in items:`) and add a 3-item test.
```

One finding per problem; if the same mistake appears in several places, list all locations in one finding. Give every finding an id (F1, F2, ...) that stays stable across revisions, so feedback can refer to it.

When linking code in a GitHub comment, use the full head SHA: `https://github.com/<owner>/<repo>/blob/<full-sha>/<path>#L<start>-L<end>`.
