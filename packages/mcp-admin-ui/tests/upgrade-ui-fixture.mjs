// Standalone browser-only contract fixture. Every request is fulfilled from
// memory/local dist; no listener, shared router, production server or network.
import { readFile } from 'node:fs/promises';
import { extname } from 'node:path';

export const sourceDigest = 'a'.repeat(64);
export const changedDigest = 'b'.repeat(64);
export const maliciousName = '<img src=x onerror="window.reportInjected=true">';
export const longName = `tool_${'long_name_'.repeat(35)}`;
const csrf = 'upgrade_test_csrf_0123456789';
const dist = new URL('../dist/', import.meta.url);
const csp = "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; connect-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'";
const headers = { 'Content-Security-Policy': csp, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' };

export function makePreview(mount = '') {
  const before = { writes_enabled: false, disabled: ['legacy_disabled'], enabled_write_tools: ['workflow:update'] };
  const common = {
    product: 'n8n', source_schema: 3, target_schema: 4, source_sha256: sourceDigest,
    changed: true, source_catalog: 'final-0.1.x-bounded', before,
    new_tools: ['workflow_create', maliciousName, longName], new_write_operations: ['workflow:delete'],
    argument_review_tools: ['workflow'], expanded_read_tools: ['workflow'], unclassified_tools: [], unverified_tools: [],
  };
  return structuredClone({
    base_path: mount, api_base: `${mount}/api`, csrf, product: 'n8n', stage: 'upgrade_review', default_policy: 'all_on',
    plans: {
      all_on: { ...common, policy: 'all_on',
        after: { writes_enabled: true, disabled: [], enabled_write_tools: ['workflow:update', 'workflow:delete', 'workflow_create'] },
        disabled_added: [], disabled_removed: ['legacy_disabled'], write_grants_added: ['workflow:delete', 'workflow_create'], write_grants_removed: [],
        effective_writes_added: ['workflow:delete', 'workflow_create', maliciousName, longName], effective_writes_removed: [],
      },
      preserve: { ...common, policy: 'preserve',
        after: { writes_enabled: false, disabled: ['legacy_disabled', 'workflow', 'workflow_create'], enabled_write_tools: ['workflow:update'] },
        disabled_added: ['workflow', 'workflow_create'], disabled_removed: [], write_grants_added: [], write_grants_removed: [],
        effective_writes_added: [], effective_writes_removed: ['workflow:update'],
      },
    },
  });
}

export async function upgradeFixture(browser, { mount = '', width = 1440, clock = false } = {}) {
  const origin = 'http://upgrade-ui.invalid';
  const context = await browser.newContext({ viewport: { width, height: 900 }, serviceWorkers: 'block' });
  const fixture = {
    context, origin, mount, preview: makePreview(mount), calls: [], requests: [], unexpected: [], errors: [], violations: [],
    accepted: false, normal: false, bootstrapCount: 0, onApply: null, onBootstrap: null,
  };
  await context.addInitScript(() => {
    globalThis.upgradeCspViolations = [];
    document.addEventListener('securitypolicyviolation', event => globalThis.upgradeCspViolations.push(event.violatedDirective));
  });
  await context.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url());
    fixture.requests.push({ path: url.pathname, method: request.method(), origin: url.origin });
    if (url.origin !== origin || url.search || !url.pathname.startsWith(`${mount}/`)) {
      fixture.unexpected.push(request.url()); await route.abort('blockedbyclient'); return;
    }
    const path = url.pathname.slice(mount.length);
    const json = (body, status = 200) => route.fulfill({ status, headers, contentType: 'application/json', body: JSON.stringify(body) });
    if (path === '/api/bootstrap' && request.method() === 'GET') {
      fixture.bootstrapCount++;
      const override = await fixture.onBootstrap?.();
      if (override?.abort) { await route.abort('connectionrefused'); return; }
      if (override) { await json(override.body, override.status); return; }
      if (fixture.normal) { await json({ base_path: mount, api_base: `${mount}/api`, product: 'n8n', csrf, tools: {}, disabled: [], enabled_write_tools: [], writes_enabled: false }); return; }
      if (fixture.accepted) { await json({ stage: 'starting' }, 503); return; }
      await json(fixture.preview); return;
    }
    if (path === '/api/upgrade/apply' && request.method() === 'POST') {
      const call = { body: request.postDataJSON(), headers: await request.allHeaders() };
      fixture.calls.push(call);
      const override = await fixture.onApply?.(call);
      if (override?.abort) { await route.abort('connectionrefused'); return; }
      if (override) { await json(override.body, override.status); return; }
      if (call.headers['x-csrf-token'] !== fixture.preview.csrf) { await json({ error: 'PRIVATE_ERROR_CANARY' }, 403); return; }
      if (call.body.expected_sha256 !== fixture.preview.plans[call.body.policy].source_sha256) { await json({ error: 'PRIVATE_ERROR_CANARY' }, 409); return; }
      fixture.accepted = true;
      await json({ saved: true, stage: 'starting' }, 202); return;
    }
    if (path === '/' && request.method() === 'GET') {
      const html = fixture.normal ? '<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"></head><body><h1>一般管理介面（測試）</h1></body></html>'
        : (await readFile(new URL('index.html', dist), 'utf8')).replace('/assets/app.js', '/assets/upgrade.js').replaceAll('__MCP_UI_BASE__', mount);
      await route.fulfill({ status: 200, headers, contentType: 'text/html', body: html }); return;
    }
    if (request.method() === 'GET' && /^\/assets\/(?:[A-Za-z0-9_-]+\/)*[A-Za-z0-9_.-]+$/.test(path)) {
      const type = { '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.woff': 'font/woff', '.ttf': 'font/ttf', '.eot': 'application/vnd.ms-fontobject' }[extname(path)];
      if (type) {
        await route.fulfill({ status: 200, headers, contentType: type, body: await readFile(new URL(path.slice(1), dist)) }); return;
      }
    }
    fixture.unexpected.push(request.url()); await route.abort('blockedbyclient');
  });
  await context.routeWebSocket('**/*', socket => { fixture.unexpected.push(socket.url()); socket.close(); });
  const page = await context.newPage();
  page.setDefaultTimeout(5000);
  page.on('pageerror', error => fixture.errors.push(error.message));
  if (clock) await page.clock.install();
  fixture.page = page;
  fixture.open = () => page.goto(`${origin}${mount}/`);
  fixture.close = () => context.close();
  return fixture;
}
