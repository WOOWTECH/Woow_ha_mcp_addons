// Install the one reviewed native addon of the n8n image: better-sqlite3's prebuilt binary, from its pinned release asset.
//
// `npm ci --ignore-scripts` never runs better-sqlite3's install script (prebuild-install || node-gyp), so the npm tree
// stays hash-locked and no package script runs. This script is the only other way a binary reaches node_modules, and it
// takes nothing on trust: the archive must be exactly the pinned size and sha256 before it is opened; it must hold
// exactly one regular file with the pinned name, size and sha256 (no other entry, no extended header, no link, no path
// of its own choosing); the destination is fixed under the installed package (whose version must be the pinned one) and
// the file gets mode 0644, whatever the umask or the archive said. Node builtins only. Pins: packaging/inputs.json
// "native_addons", checked against the Dockerfile by packaging/validate.py.
//
//   node native_addon.mjs install --inputs packaging/inputs.json --addon better-sqlite3 --node-modules apps/n8n/node_modules
//   node native_addon.mjs install --version V --url U --sha256 H --size N --member M --member-size N --member-sha256 H --into DIR
//   (either form accepts --from-file ARCHIVE to verify a local archive instead of downloading it)
import { createHash } from 'node:crypto';
import { chmodSync, existsSync, lstatSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import https from 'node:https';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { gunzipSync } from 'node:zlib';

export const MAX_DOWNLOAD = 8 * 1024 * 1024;
export const MAX_UNPACKED = 32 * 1024 * 1024;
const BLOCK = 512;
const HEX64 = /^[0-9a-f]{64}$/;

export const sha256 = (buffer) => createHash('sha256').update(buffer).digest('hex');

function octal(field, what) {
  const text = field.toString('latin1').replace(/\0.*$/s, '').trim();
  if (!/^[0-7]+$/.test(text) || (field[0] & 0x80)) throw new Error(`tar ${what} is not an octal number`);
  return parseInt(text, 8);
}

/** The bytes of the archive's only entry, which must be a plain file named `member`; nothing else may be in it. */
export function singleEntry(tar, member) {
  if (tar.length < 2 * BLOCK) throw new Error('tar archive is too short');
  const header = tar.subarray(0, BLOCK);
  const stored = octal(header.subarray(148, 156), 'checksum');
  const sum = header.reduce((total, byte, index) => total + (index >= 148 && index < 156 ? 0x20 : byte), 0);
  if (sum !== stored) throw new Error('tar header checksum does not match');
  const name = header.subarray(0, 100).toString('latin1').replace(/\0.*$/s, '');
  const type = header[156];
  if (type !== 0x30 && type !== 0x00) throw new Error(`tar entry type ${JSON.stringify(String.fromCharCode(type))} is not a plain file`);
  if (header.subarray(345, 500).some((byte) => byte !== 0)) throw new Error('tar entry has a path prefix');
  if (name !== member) throw new Error(`tar entry is ${JSON.stringify(name)}, not the pinned ${JSON.stringify(member)}`);
  const size = octal(header.subarray(124, 136), 'size');
  const end = BLOCK + size;
  if (end > tar.length) throw new Error('tar entry is cut short');
  const padded = BLOCK + Math.ceil(size / BLOCK) * BLOCK;
  if (tar.subarray(end, padded).some((byte) => byte !== 0) || tar.subarray(padded).some((byte) => byte !== 0)) {
    throw new Error('tar archive holds more than the one pinned entry');
  }
  return tar.subarray(BLOCK, end);
}

/** The pinned member's bytes out of the archive, after every pinned size and digest has matched; throws otherwise. */
export function verifiedMember(archive, pin) {
  checkPin(pin);
  if (archive.length !== pin.size) throw new Error(`archive is ${archive.length} bytes, the pin says ${pin.size}`);
  if (sha256(archive) !== pin.sha256) throw new Error('archive sha256 is not the pinned value');
  let tar;
  try {
    tar = gunzipSync(archive, { maxOutputLength: MAX_UNPACKED });
  } catch (error) {
    throw new Error(`archive is not a gzip file within ${MAX_UNPACKED} bytes: ${error.code ?? error.message}`);
  }
  const entry = singleEntry(tar, pin.member);
  if (entry.length !== pin.memberSize) throw new Error(`${pin.member} is ${entry.length} bytes, the pin says ${pin.memberSize}`);
  if (sha256(entry) !== pin.memberSha256) throw new Error(`${pin.member} sha256 is not the pinned value`);
  return entry;
}

/** Write the member under the installed package; an existing identical file is left as it is, any other is an error. */
export function installMember(entry, pin, packageDir) {
  checkPin(pin);
  const root = path.resolve(packageDir);
  const manifest = path.join(root, 'package.json');
  if (!existsSync(manifest)) throw new Error(`${root} is not an installed package`);
  const installed = JSON.parse(readFileSync(manifest, 'utf8')).version;
  if (installed !== pin.version) throw new Error(`installed ${pin.package} is ${installed}, the pinned addon is for ${pin.version}`);
  const target = path.join(root, ...pin.member.split('/'));
  if (existsSync(target) || isLink(target)) {
    if (isLink(target)) throw new Error(`${target} is a link`);
    if (sha256(readFileSync(target)) !== pin.memberSha256) throw new Error(`${target} exists with other content`);
    chmodSync(target, 0o644);
    return target;
  }
  const directories = [];
  for (let dir = path.dirname(target); dir !== root; dir = path.dirname(dir)) directories.push(dir);  // member has no '..': ends at root
  mkdirSync(path.dirname(target), { recursive: true });
  for (const dir of directories) chmodSync(dir, 0o755);
  const temp = `${target}.tmp-${process.pid}`;
  writeFileSync(temp, entry, { mode: 0o644, flag: 'wx' });
  chmodSync(temp, 0o644);
  renameSync(temp, target);
  return target;
}

function isLink(file) {
  try { return lstatSync(file).isSymbolicLink(); } catch { return false; }
}

/** GET with https only, at most 5 redirects and a byte cap; resolves the body of a 200. `request` is injectable for tests. */
export function download(url, { request = https.get, maxBytes = MAX_DOWNLOAD, redirects = 5, timeoutMs = 60000 } = {}) {
  return new Promise((resolve, reject) => {
    const fetch = (location, left) => {
      let parsed;
      try { parsed = new URL(location); } catch { return reject(new Error('download URL is not a URL')); }
      if (parsed.protocol !== 'https:') return reject(new Error(`download over ${parsed.protocol} refused`));
      const req = request(parsed, { timeout: timeoutMs }, (res) => {
        if ([301, 302, 303, 307, 308].includes(res.statusCode)) {
          res.resume();
          if (left <= 0 || !res.headers.location) return reject(new Error('too many redirects'));
          let next;
          try { next = new URL(res.headers.location, parsed).href; } catch { return reject(new Error('redirect to a URL that is not a URL')); }
          return fetch(next, left - 1);
        }
        if (res.statusCode !== 200) { res.resume(); return reject(Object.assign(new Error(`HTTP ${res.statusCode}`), { status: res.statusCode })); }
        const chunks = [];
        let total = 0;
        res.on('data', (chunk) => {
          total += chunk.length;
          if (total > maxBytes) { res.destroy(); reject(new Error(`download is over ${maxBytes} bytes`)); } else chunks.push(chunk);
        });
        res.on('end', () => resolve(Buffer.concat(chunks)));
        res.on('error', reject);
      });
      req.on('timeout', () => req.destroy(new Error('download timed out')));
      req.on('error', reject);
    };
    fetch(url, redirects);
  });
}

/** download() with 3 attempts for a network error or a 5xx; a wrong digest is never retried (verifiedMember decides). */
export async function downloadWithRetry(url, options = {}, { attempts = 3, pause = 2000 } = {}) {
  for (let attempt = 1; ; attempt += 1) {
    try {
      return await download(url, options);
    } catch (error) {
      const retryable = error.status === undefined || error.status >= 500;
      if (attempt >= attempts || !retryable) throw error;
      await new Promise((done) => setTimeout(done, pause * attempt));
    }
  }
}

export function pinFrom(inputs, addon) {
  const entry = inputs.native_addons?.[addon];
  if (!entry) throw new Error(`no native addon ${addon} in the inputs`);
  return { package: entry.package, version: entry.version, url: entry.url, sha256: entry.sha256, size: entry.size,
           member: entry.member, memberSize: entry.member_size, memberSha256: entry.member_sha256 };
}

export function checkPin(pin) {
  const ok = pin && typeof pin.package === 'string' && /^[a-z0-9-]+$/.test(pin.package) && /^\d+\.\d+\.\d+$/.test(pin.version)
    && HEX64.test(pin.sha256) && HEX64.test(pin.memberSha256) && Number.isInteger(pin.size) && pin.size > 0
    && Number.isInteger(pin.memberSize) && pin.memberSize > 0 && /^[A-Za-z0-9_./-]+$/.test(pin.member ?? '')
    && !pin.member.startsWith('/') && !pin.member.split('/').includes('..') && typeof pin.url === 'string' && pin.url.startsWith('https://');
  if (!ok) throw new Error('native addon pin is incomplete or malformed');
  return pin;
}

export function parseArguments(argv) {
  const options = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    if (!key?.startsWith('--') || argv[index + 1] === undefined) throw new Error(`bad argument ${key}`);
    options[key.slice(2)] = argv[index + 1];
  }
  return options;
}

export async function run(argv) {
  const [command, ...rest] = argv;
  if (command !== 'install') throw new Error('usage: native_addon.mjs install [--inputs F --addon NAME --node-modules DIR | --version V --url U ...]');
  const options = parseArguments(rest);
  let pin;
  let packageDir;
  if (options.inputs) {
    pin = pinFrom(JSON.parse(readFileSync(options.inputs, 'utf8')), options.addon);
    packageDir = path.join(options['node-modules'], pin.package);
  } else {
    pin = { package: path.basename(options.into ?? ''), version: options.version, url: options.url, sha256: options.sha256,
            size: Number(options.size), member: options.member, memberSize: Number(options['member-size']), memberSha256: options['member-sha256'] };
    packageDir = options.into;
  }
  checkPin(pin);
  const archive = options['from-file'] ? readFileSync(options['from-file']) : await downloadWithRetry(pin.url);
  const target = installMember(verifiedMember(archive, pin), pin, packageDir);
  console.log(`native addon ${pin.package}@${pin.version}: ${pin.member} ${pin.memberSha256} -> ${target}`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  run(process.argv.slice(2)).catch((error) => {
    console.error(`native addon install failed: ${error.message}`);
    process.exit(1);
  });
}
