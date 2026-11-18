// Reusable Playwright fixtures added by validate-pr. Commit this file with the tests; it stays useful for
// regression runs without validate-pr.
//
//   import { test, expect, requireEnv } from './fixtures/validate-fixtures';
//
// - Browser console errors, uncaught page errors, failed requests and HTTP 5xx responses are collected for every
//   test and attached to the report as "console-errors" (validate-pr copies them into its evidence folder).
// - checkpoint('name') attaches a full-page screenshot at an important validation point.
// - requireEnv('E2E_USER', 'E2E_PASSWORD') reads credentials from the environment and skips the test with a clear
//   reason when they are missing. Never hard-code credentials in tests.
import { test as base, expect } from '@playwright/test';

type ValidateFixtures = {
  consoleErrors: string[];
  checkpoint: (name: string) => Promise<void>;
};

export const test = base.extend<ValidateFixtures>({
  consoleErrors: [
    async ({ page }, use, testInfo) => {
      const errors: string[] = [];
      page.on('console', (m) => {
        if (m.type() === 'error') errors.push(`console.error: ${m.text()} (${m.location().url}:${m.location().lineNumber})`);
      });
      page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
      page.on('requestfailed', (r) => errors.push(`requestfailed: ${r.method()} ${r.url()} ${r.failure()?.errorText ?? ''}`));
      page.on('response', (r) => {
        if (r.status() >= 500) errors.push(`http ${r.status()}: ${r.request().method()} ${r.url()}`);
      });
      await use(errors);
      if (errors.length) {
        await testInfo.attach('console-errors', { body: JSON.stringify(errors, null, 2), contentType: 'application/json' });
      }
    },
    { auto: true },
  ],
  checkpoint: async ({ page }, use, testInfo) => {
    await use(async (name: string) => {
      const safe = name.replace(/[^A-Za-z0-9]+/g, '-');
      await testInfo.attach(`checkpoint-${safe}`, { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' });
    });
  },
});

/** Read required environment variables; skip the test (reported as skipped, with the reason) if any is missing. */
export function requireEnv(...names: string[]): Record<string, string> {
  const missing = names.filter((n) => !process.env[n]);
  test.skip(missing.length > 0, `needs environment variables: ${missing.join(', ')}`);
  return Object.fromEntries(names.map((n) => [n, process.env[n] as string]));
}

export { expect };
