// Proposed by validate-pr for a repository with no Playwright configuration. Adjust testDir, the start command and
// the port to the application; keep credentials out of this file (use environment variables).
import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.BASE_URL ?? 'http://127.0.0.1:3000';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  // Starts the app when BASE_URL is not given (local runs and CI). validate-pr starts the app itself and disables this.
  webServer: process.env.BASE_URL
    ? undefined
    : { command: 'npm run start', url: baseURL, reuseExistingServer: !process.env.CI, timeout: 120_000 },
});
