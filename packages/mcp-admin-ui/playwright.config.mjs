import { defineConfig } from '@playwright/test';
import { rejectPortOverride } from '../../tests/owned_ui.mjs';
rejectPortOverride();
export default defineConfig({
  testDir: './tests/browser', fullyParallel: false, workers: 1, retries: 0,
  reporter: 'list', timeout: 30000,
  use: { browserName: 'chromium', headless: true, trace: 'off', screenshot: 'off', video: 'off', serviceWorkers: 'block' },
  // No URL-based webServer preflight: tests/owned-fixture retains the child.
  projects: [
    // Every spec as it is: the product switched off unless a test switches profiles on itself (profiles.spec).
    { name: 'single' },
    // HM-11 (docs/multi-profile/paas-test-mapping.md): these single-profile specs must also pass switched on, unchanged.
    { name: 'profiles-on', testMatch: /\/(conditional-writes|configuration|partial-settings|write-contracts)\.spec\.mjs$/, use: { profilesOn: true } },
  ],
});
