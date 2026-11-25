// Owned, single-file diagnostic tool transport. No user browser or live target.
// Callers supply decisions: offline fixture or the separately reviewed live host.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import readline from 'node:readline';
import { createRequire } from 'node:module';
import { disableUnroutedTransports } from '../../drivers/web/journey_bridge.mjs';

const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const origin = 'http://remorsearch-agent.invalid/';
let browser, context, page, sourceHash, count = 0;
const checked = name => {
  if (!path.isAbsolute(name) || fs.realpathSync(name) !== name) throw new Error('path');
  for (let p = name; p !== path.dirname(p); p = path.dirname(p))
    if (fs.lstatSync(p).isSymbolicLink()) throw new Error('link');
  return name;
};
const stop = async () => {
  if (browser) {
    await browser.close();
    return { stopped: !browser.isConnected() };
  }
  return { stopped: true };
};
async function start(input) {
  if (browser || process.versions.node.split('.')[0] !== '22' || process.env.NODE_OPTIONS)
    throw new Error('runtime');
  const source = checked(input.source);
  const bytes = fs.readFileSync(source);
  if (bytes.length > 1024 * 1024 || hash(bytes) !== input.sha256) throw new Error('source');
  sourceHash = input.sha256;
  const root = checked(process.env.REMORSEARCH_AGENT_PLAYWRIGHT);
  const require = createRequire(path.join(root, 'package.json'));
  if (require(path.join(root, 'package.json')).version !== '1.56.1') throw new Error('version');
  const pw = require(path.join(root, 'index.js'));
  const cwd = checked(process.cwd());
  if (fs.statSync(cwd).mode & 0o077) throw new Error('private');
  browser = await pw.chromium.launch({ headless: true, timeout: 10000,
    handleSIGINT: false, handleSIGTERM: false, handleSIGHUP: false,
    env: { PATH: '/usr/bin:/bin', HOME: cwd, TMPDIR: cwd, LANG: 'C' },
    args: ['--disable-background-networking', '--disable-component-update',
      '--disable-quic', '--host-resolver-rules=MAP * ~NOTFOUND',
      '--force-webrtc-ip-handling-policy=disable_non_proxied_udp'] });
  context = await browser.newContext({ viewport: { width: 1024, height: 768 },
    serviceWorkers: 'block', acceptDownloads: false });
  await context.addInitScript(disableUnroutedTransports);
  await context.route('**/*', route => route.request().url() === origin &&
      route.request().method() === 'GET' ?
    route.fulfill({ status: 200, contentType: 'text/html', body: bytes,
      headers: { 'content-security-policy': "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; form-action 'none'; frame-src 'none'; base-uri 'none'" } }) :
    route.abort('blockedbyclient'));
  await context.routeWebSocket('**/*', ws => ws.close());
  context.on('page', created => {
    created.on('download', download => { void download.cancel(); });
    if (page && created !== page) void created.close();
  });
  page = await context.newPage();
  await page.goto(origin, { waitUntil: 'load', timeout: 10000 });
  return { started: true, source_sha256: sourceHash, node: process.versions.node, playwright: '1.56.1' };
}
async function act(input) {
  if (!page || page.url() !== origin || count >= 24) throw new Error('scope');
  if (input.name === 'enter') {
    if (typeof input.value !== 'string' || !/^Owned [A-Za-z0-9 .,!?'-]{1,80}$/.test(input.value))
      throw new Error('owned_data');
    await page.locator('#note').fill(input.value, { timeout: 1000 });
  } else if (input.name === 'reject') {
    if (!['#reject-control', '#reject-broken'].includes(input.target)) throw new Error('target');
    await page.locator(input.target).click({ timeout: 1000 });
  } else if (input.name === 'save') {
    await page.locator('#save').click({ timeout: 1000 });
  } else if (input.name !== 'inspect') throw new Error('tool');
  const name = 'actual-browser-' + (++count) + '.png';
  const png = await page.screenshot({ path: name, timeout: 3000 });
  fs.chmodSync(name, 0o600);
  return { note: await page.locator('#note').inputValue(),
    saved: await page.locator('#saved').textContent(),
    feedback: await page.locator('#feedback').textContent(),
    capture: { path: name, sha256: hash(png) }, source_sha256: sourceHash };
}
process.umask(0o077);
for await (const line of readline.createInterface({ input: process.stdin })) {
  if (line.length > 16384) break;
  let message;
  try {
    message = JSON.parse(line);
    const result = message.kind === 'start' ? await start(message.payload) :
      message.kind === 'close' ? await stop() : await act(message.payload);
    process.stdout.write(JSON.stringify({ id: message.id, result }) + '\n');
    if (message.kind === 'close') break;
  } catch {
    process.stdout.write(JSON.stringify({ id: message?.id, error: 'owned_browser_failed' }) + '\n');
    break;
  }
}
await stop().catch(() => {});
