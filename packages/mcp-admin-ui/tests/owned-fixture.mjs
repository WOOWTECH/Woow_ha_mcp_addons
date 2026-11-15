// Standalone LOCAL MOCK only; retain Playwright's configured context/options.
import { test as base, expect } from '@playwright/test';
import { startOwnedUI, guardedUIRequest, installUIContextGuard } from '../../../tests/owned_ui.mjs';

export const test = base.extend({
  // HM-11: the profiles-on project runs the same specs with the product switched on (fixtures/server.mjs defaults):
  // the default profile named explicitly on every profile-scoped request, the menu in the top bar.
  profilesOn: [false, { scope: 'worker', option: true }],
  ownedUI: [async ({ playwright, profilesOn }, use) => {
    const fixture = await startOwnedUI({ request: playwright.request });
    try {
      if (profilesOn) {
        const raw = await playwright.request.newContext({ baseURL: fixture.baseURL });
        try { await (await guardedUIRequest(raw, fixture).post('/__fixture/defaults', { data: { profiles: true } })).dispose(); }
        finally { await raw.dispose(); }
      }
      await use(fixture);
    } finally { await fixture.stop(); }
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
