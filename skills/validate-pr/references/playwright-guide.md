# Writing the Playwright tests

Tests become part of the application's permanent suite. Write them as a careful engineer on the team would, so they still pass, and still mean something, months later.

## 1. Follow the repository first

Use `inspect_repo.py` → `playwright`:

| Found | Do |
|---|---|
| `configs` | Use that config and its `testDir`. Do not add a second config. |
| `existing_specs` | Put new specs beside them, same naming (`*.spec.ts` vs `*.e2e.ts`), same `describe` style, same import of `test`. |
| `helpers_and_fixtures`, `page_objects` | Reuse them (login helpers, page objects, seeded users). Extend an existing page object rather than writing a parallel one. |
| `runner: python` | Write pytest-playwright tests (`test_*.py`, `page` fixture, `expect` from `playwright.sync_api`). |
| `proposed_layout` (no convention) | Use it: Node → `playwright.config.ts` (from `templates/playwright.config.ts`) + `tests/e2e/`; Python → `tests/e2e/` with pytest-playwright; other stacks → self-contained `e2e/` with its own `package.json`. Adding `@playwright/test` (or `pytest-playwright`) as a dev dependency is a config change the reviewer sees in the patch. |

### Fit the repository's own rules (check before choosing the layout)

- **Monorepos:** put tests in the app folder the PR changes (`inspect_repo.py` → `app_root`), not at the repository root.
- **Dependency rules:** if `AGENTS.md`/README restrict dependency or lockfile changes (for example "never run npm install on the host", lockfiles generated in Docker), do not add `@playwright/test` to the app's `package.json`. Use a self-contained package in `<app_root>/e2e/` with its own `package.json`, lockfile, `.gitignore` (`node_modules/`, `test-results/`, `playwright-report/`) and config.
- **Type-check and test scope:** if the app's lint/type-check (`tsc --noEmit` with `include: ["**/*.ts"]`) would compile `.ts` specs that cannot resolve `@playwright/test`, write the specs, fixtures and config as `.mjs` (`templates/validate-fixtures.mjs`) or put them where `exclude` already covers them; never edit `tsconfig.json` just to fit the tests in. Check that the existing test command (`node --test`, `jest`, `vitest`, `pytest`) does not pick the e2e specs up (name them `*.spec.*` under `e2e/`), and run it once to prove it.
- After adding the files, run the repository's own lint and test commands; a test change that breaks them is a test-automation defect.

Fixtures: copy `templates/validate-fixtures.ts` (or `.mjs`) to the fixtures folder (`tests/e2e/fixtures/validate-fixtures.ts` or the existing fixtures folder) and import `test`, `expect` from it, so console errors and checkpoints are captured. If the repository already has an extended `test`, merge the `consoleErrors` and `checkpoint` fixtures into it instead. Python: merge `templates/conftest_validate.py` into `tests/e2e/conftest.py`.

## 2. Test shape

```ts
import { test, expect } from './fixtures/validate-fixtures';

test.describe('Cart quantity (PR #42)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/cart');
  });

  test('TC-02 rejects a quantity of 0 and keeps the previous value', async ({ page, checkpoint, consoleErrors }) => {
    const qty = page.getByRole('spinbutton', { name: 'Quantity' });
    await qty.fill('0');
    await qty.press('Enter');
    await expect(page.getByRole('alert')).toHaveText('Quantity must be at least 1');
    await expect(qty).toHaveValue('1');
    await checkpoint('quantity-zero-error');
    expect(consoleErrors, 'no browser errors').toEqual([]);
  });
});
```

- Title starts with the TC ID from the plan, then the behaviour in plain words.
- One behaviour per test. Independent tests: each sets up its own state (no reliance on test order).
- End important tests with `checkpoint('<point>')` for the evidence screenshot. Assert `consoleErrors` is empty where the page should be error-free.
- Use relative URLs (`page.goto('/cart')`); the base URL comes from the config, so the same test runs locally, in CI and under validate-pr.

## 3. Locators (most to least preferred)

1. `getByRole(role, { name })`: also proves the control is accessible.
2. `getByLabel`, `getByPlaceholder`, `getByText` for static, user-visible text.
3. `getByTestId` when the repository already uses `data-testid`. Adding a `data-testid` means changing application code: do **not** add one; use a role/text locator or record that the element is hard to target.
4. Never: CSS chains tied to layout (`div > div:nth-child(3)`), generated class names (`.css-1x2y3z`, `.sc-bdfBwQ`), XPath, element indexes (`.nth(2)`) unless the order is the behaviour being tested.

## 4. Waiting

- Rely on auto-waiting locators and web-first assertions: `await expect(locator).toBeVisible()`, `toHaveText`, `toHaveURL`, `toHaveCount`.
- Wait for the thing the user waits for: `await page.waitForResponse(r => r.url().includes('/api/cart') && r.ok())` around the action that triggers it, or the visible result.
- Never `page.waitForTimeout(...)` or `sleep`. Never `networkidle` as a correctness signal.

## 5. Data and credentials

- No credentials in tests. Read them with `requireEnv('E2E_USER', 'E2E_PASSWORD')` (Python: `require_env`), which skips with a clear reason when missing. Document the variable names in the plan's *Test data and environment*.
- Create the data a test needs through the UI or the app's API in `beforeEach`; use unique values (`Date.now()`) so reruns do not collide. Clean up when the app supports it.
- Do not call production or third-party services. If the app calls one, use `page.route()` to stub it in the test and say so in the plan.

## 6. Accessibility checks

- Keyboard: complete the workflow with `page.keyboard.press('Tab')`/`Enter`/`Space` only; assert `toBeFocused()` on the expected control.
- Names and roles: every interactive element found by `getByRole` with its visible name.
- Errors announced: assert `role=alert` or an `aria-live` region contains the message.
- axe: when `@axe-core/playwright` is installed (or the reviewer approves adding it as a dev dependency):
  ```ts
  import AxeBuilder from '@axe-core/playwright';
  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).include('main').analyze();
  expect(results.violations.map(v => `${v.id}: ${v.nodes.length}`)).toEqual([]);
  ```
  Scope the scan to the changed region when the rest of the page has known, unrelated issues, and note it in the plan.

## 7. Before running

- Type-check or at least list the tests: `npx playwright test --list -c <config>` (catches syntax and import errors as test-automation issues before they look like app failures).
- Run a new spec once on its own before the full run, and fix the test (not the app) if it fails for test reasons.

## 8. What not to do

- Do not change application code, add test IDs, or loosen app validation to make a test pass.
- Do not use `test.only`, `test.fixme` or `test.skip` to hide failures; a skip needs a stated reason (missing env var).
- Do not weaken an assertion after it fails. If the behaviour is wrong, it is a defect; if the expectation was wrong, fix the plan first, then the test, and record why.
- Do not commit generated output: `test-results/`, `playwright-report/`, traces, screenshots. Add them to `.gitignore` if the repository does not ignore them.
