import { defineConfig } from '@playwright/test';
import { rejectPortOverride } from '../../tests/owned_ui.mjs';
rejectPortOverride();
export default defineConfig({
  testDir: './tests/browser', fullyParallel: false, workers: 1, retries: 0,
  reporter: 'list', timeout: 30000,
  use: { browserName: 'chromium', headless: true, trace: 'off', screenshot: 'off', video: 'off', serviceWorkers: 'block' },
  // No URL-based webServer preflight: tests/owned-fixture retains the child.
});
