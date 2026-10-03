import { defineConfig } from '@playwright/test';
import net from 'node:net';
const socket = net.createServer();
await new Promise(resolve => socket.listen(0, '127.0.0.1', resolve));
const port = process.env.UI_PORT ?? String(socket.address().port);
await new Promise(resolve => socket.close(resolve));
process.env.UI_PORT = port;
const origin = `http://127.0.0.1:${port}`;
export default defineConfig({
  testDir: './tests/browser', fullyParallel: false, workers: 1, retries: 0,
  reporter: 'list', timeout: 30000,
  use: { baseURL: origin, browserName: 'chromium', headless: true, trace: 'off', screenshot: 'off', video: 'off' },
  webServer: { command: 'node fixtures/server.mjs', url: `${origin}/__fixture/ready`, reuseExistingServer: false, timeout: 10000 },
});
