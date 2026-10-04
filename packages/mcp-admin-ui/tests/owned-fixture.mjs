// Standalone LOCAL MOCK only; retain Playwright's configured context/options.
import { test as base, expect } from '@playwright/test';
import { startOwnedUI, guardedUIRequest, installUIContextGuard } from '../../../tests/owned_ui.mjs';

export const test = base.extend({
  ownedUI: [async ({ playwright }, use) => {
    const fixture = await startOwnedUI({ request: playwright.request });
    try { await use(fixture); } finally { await fixture.stop(); }
  }, { scope: 'worker' }],
  baseURL: async ({ ownedUI }, use) => use(ownedUI.baseURL),
  serviceWorkers: 'block',
  context: async ({ context, ownedUI }, use) => {
    const close = await installUIContextGuard(context, ownedUI);
    try { await use(context); } finally { await close(); }
  },
  request: async ({ request, ownedUI }, use) => use(guardedUIRequest(request, ownedUI)),
});
export { expect };
