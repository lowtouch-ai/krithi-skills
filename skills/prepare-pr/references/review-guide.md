# Review guide

The goal is a short list of real, verified problems in **this change**, each with a concrete way it fails. A long list of possible problems is worse than no review: it buries the real ones and wastes the developer's time.

## Method

1. **Understand before judging.** For each changed hunk, read the whole function and its callers and callees, the tests that cover it, and any config or schema it depends on. Know what the code is supposed to do (the requirements from step 0).
2. **Generate candidates** across the five areas below. Be thorough here.
3. **Verify each candidate** as a skeptic trying to disprove it:
   - Is the code path reachable with real inputs? Trace it.
   - Does something else already handle it (a guard upstream, framework validation, a type that rules it out, a test that proves it fine)?
   - Can you write the failure scenario: *with input/state X, line Y does Z, and the result is W instead of V*?
   - If you can run it cheaply (a unit test, a one-line script), do.
4. **Keep only confirmed findings.** Drop a candidate that you cannot tie to a concrete failure, that is pre-existing code this change did not touch (unless the change makes it worse or newly reachable), that is a matter of taste, or that a configured linter or formatter would catch anyway.
5. **Rank by severity**, then by confidence.

## Checklist

### Correctness
- Logic errors: inverted or wrong conditions, off-by-one, wrong operator, wrong variable, missing `return`/`break`, fall-through.
- Edge cases: empty, null/None/undefined, zero, negative, very large, Unicode, duplicate, missing keys, time zones and DST, concurrent calls.
- Error handling: exceptions swallowed or logged and ignored, errors turned into success values, missing cleanup (`finally`, context managers, `defer`), partial writes left behind, retries without limits.
- State and concurrency: race conditions, shared mutable state, stale caches, non-idempotent retries, async calls not awaited, ordering assumptions.
- Contracts: callers not updated after a signature or return type changed, broken backwards compatibility in a public API, schema or migration mismatches, serialization changes.
- Resource handling: unclosed files, connections or handles; leaks in loops.

### Security
- Injection: SQL, shell, template, LDAP, XPath, header or log injection from user-controlled input; unsafe `eval`/deserialization.
- Access control: missing authentication or authorization checks on new endpoints or actions, IDOR (object IDs from the request used without an ownership check), privilege escalation.
- Secrets: credentials, tokens or keys in code, config, tests, fixtures or logs.
- Data exposure: sensitive data in logs, errors, responses or URLs; overly broad API responses.
- Input handling: path traversal, unvalidated redirects, SSRF on user-supplied URLs, file upload type and size checks, XSS (unescaped output, `dangerouslySetInnerHTML`, `v-html`, `|safe`).
- Crypto and sessions: weak algorithms, home-made crypto, predictable randomness for tokens, missing CSRF protection, insecure cookie flags, disabled TLS verification.
- Dependencies: new packages that are unmaintained, typo-squatted or unpinned where the project pins.

### Performance
- N+1 queries, queries or I/O inside loops, missing pagination or limits on unbounded data.
- Quadratic (or worse) algorithms on data that can grow; repeated work that could be computed once.
- Blocking calls on async or UI threads; missing timeouts on network calls.
- Loading whole files or tables into memory when streaming is needed.
- Only report performance problems that matter at the data sizes this code will plausibly see.

### Code quality and maintainability
- Duplication of logic that already exists in the codebase (name the existing helper).
- Dead code, leftover debug output, commented-out blocks, stray TODOs added by this change.
- Names that mislead, functions doing several unrelated things, magic numbers with no explanation.
- Inconsistency with the patterns the surrounding code uses for the same job (errors, logging, config, data access).
- Comments that no longer match the code.
- Tests: changed behaviour with no test, tests that assert nothing meaningful, tests depending on order, time or network.

### Requirements
- Every stated requirement: met, partly met or not met, with the code location.
- Behaviour the change adds that nobody asked for (scope creep), and anything in the requirements' non-goals that was done anyway.
- Acceptance criteria that the tests do not actually exercise.

## Severity

| Severity | Meaning | Examples |
|---|---|---|
| Critical | Data loss, security breach, or the main feature broken for normal use | SQL injection on a public endpoint, migration that drops a column with data, crash on the main path |
| High | Wrong results or a crash in a realistic case; a requirement not met | Off-by-one dropping the last record, unhandled None on a common input, missing auth check on an admin action |
| Medium | Fails in edge cases, or a real maintainability or performance cost | Missing timeout on an external call, N+1 query on a list page, duplicated business rule likely to drift |
| Low | Minor issues worth fixing while here | Misleading name, stale comment, leftover debug log |

## Finding format

```
[High] src/billing/invoice.py:142, total excludes the last line item
Failure: an invoice with 3 items sums only items[0:2], because range(len(items) - 1) stops one short. A 3-item invoice of 10/20/30 totals 30 instead of 60.
Fix: iterate over items directly (for item in items).
```

One finding per problem. If the same mistake appears in several places, give one finding and list the locations.
