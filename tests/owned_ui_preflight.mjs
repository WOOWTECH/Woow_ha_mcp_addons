// Controlled regression: the only destination is this retained, self-proved decoy.
import assert from 'node:assert/strict';
import http from 'node:http';
import { readFileSync, readdirSync, readlinkSync, writeFileSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import './owned_network.cjs';
const ui = new URL('../packages/mcp-admin-ui/', import.meta.url);
let hits = 0;
const server = http.createServer((request, response) => { hits++; response.end('owned decoy'); });
let child, timer, killTimer;
const record = { owner: process.pid };
try {
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  const port = server.address().port;
  assert.notEqual(port, 3000);
  const sockets = new Set(readdirSync(`/proc/${process.pid}/fd`).flatMap(fd => {
    try { return [readlinkSync(`/proc/${process.pid}/fd/${fd}`)]; } catch { return []; }
  }));
  const row = readFileSync(`/proc/${process.pid}/net/tcp`, 'utf8').split('\n').map(line => line.trim().split(/\s+/))
    .find(cols => cols[1] === `0100007F:${port.toString(16).toUpperCase().padStart(4, '0')}` && cols[3] === '0A' && sockets.has(`socket:[${cols[9]}]`));
  assert(row, 'retained self PID/fd/listener proof before installed startup');
  Object.assign(record, { port, inode: row[9], proofBeforeStartup: true });
  child = spawn(process.execPath, [new URL('node_modules/@playwright/test/cli.js', ui).pathname, 'test', '--grep', 'MOCK health dimensions', '--output', process.env.UI_EVIDENCE_DIR + '/preflight-results'], {
    cwd: ui, env: { PATH: '/usr/bin:/bin', HOME: '/tmp', UI_PORT: String(port), PLAYWRIGHT_BROWSERS_PATH: '0', UI_EVIDENCE_DIR: process.env.UI_EVIDENCE_DIR }, stdio: ['ignore', 'pipe', 'pipe'],
  });
  record.child = child.pid;
  let output = '';
  child.stdout.on('data', bytes => { output += bytes; });
  child.stderr.on('data', bytes => { output += bytes; });
  timer = setTimeout(() => { record.deadline = true; child.kill('SIGTERM'); killTimer = setTimeout(() => child.kill('SIGKILL'), 3000); }, 15000);
  const [code, signal] = await once(child, 'close');
  Object.assign(record, { code, signal, reaped: true, hits, refused: /invalid private UI_PORT|already used/.test(output) });
  writeFileSync(process.env.UI_EVIDENCE_DIR + '/preflight-startup.log', output);
  assert.equal(code, 1);
  assert.equal(record.refused, true);
  assert.equal(hits, 0, 'unowned prelaunch readiness HTTP must never be sent');
} finally {
  clearTimeout(timer); clearTimeout(killTimer);
  if (child && child.exitCode === null && child.signalCode === null) { child.kill('SIGKILL'); await once(child, 'close'); }
  await new Promise(resolve => { server.close(resolve); server.closeAllConnections(); });
  record.closed = !server.listening;
  console.log(JSON.stringify(record));
}
