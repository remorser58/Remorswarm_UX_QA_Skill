'use strict';
// Owned ephemeral launcher for PE-2.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const readline = require('node:readline');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const { performance } = require('node:perf_hooks');
const ROOT = path.resolve(__dirname, '../..');

async function startServer() {
  const server = http.createServer((req, res) => {
    const route = req.url.split('?')[0];
    const file = route === '/' ? 'index.html' : route === '/app.js' ? 'app.js' : null;
    if (!file) { res.writeHead(404); res.end('Not found'); return; }
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : 'text/html');
    res.end(fs.readFileSync(path.join(__dirname, file)));
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  return server;
}
async function readiness(port) {
  await new Promise((resolve, reject) => {
    const req = http.get({ hostname: '127.0.0.1', port, path: '/', timeout: 3000 }, res => {
      let text = ''; res.setEncoding('utf8'); res.on('data', c => text += c);
      res.on('end', () => res.statusCode === 200 && text.includes('Everyday Desk') ? resolve() : reject(Error('Readiness response mismatch')));
      res.on('error', reject);
    });
    req.on('timeout', () => req.destroy(Error('Readiness timeout'))); req.on('error', reject);
  });
}
async function main() {
  if (Number(process.versions.node.split('.')[0]) !== 22) throw Error('Node.js 22 is required');
  if (!process.env.EVIDENCE_DIR) throw Error('Set EVIDENCE_DIR to a new, nonexistent directory');
  const out = path.resolve(process.env.EVIDENCE_DIR);
  // Atomic reservation: never merge with an old run, even an empty directory.
  fs.mkdirSync(out, { recursive: false });
  const t0 = performance.now();
  const log = (event, detail = {}) => fs.appendFileSync(path.join(out, 'lifecycle.jsonl'), JSON.stringify({ event, wall_time: new Date().toISOString(), monotonic_ms: performance.now() - t0, ...detail }) + '\n');
  log('launcher_start', { pid: process.pid, node: process.version, evidence: out });
  let server, child, input, stopped = false, readyTimer;
  const stop = async (reason, code) => {
    if (stopped) return; stopped = true;
    clearTimeout(readyTimer); input?.close(); process.stdin.pause();
    log('shutdown_begin', { reason, code });
    if (child && child.exitCode === null && child.signalCode === null) {
      child.kill('SIGTERM');
      const timer = setTimeout(() => { if (child.exitCode === null && child.signalCode === null) { log('child_force_stop'); child.kill('SIGKILL'); } }, 3000);
      await once(child, 'close').catch(() => {}); clearTimeout(timer);
    }
    if (server) { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
    log('shutdown_complete', { code }); process.exitCode = code;
  };
  const handlers = {};
  for (const signal of ['SIGINT', 'SIGTERM']) {
    handlers[signal] = () => { void stop(signal, signal === 'SIGINT' ? 130 : 143); };
    process.on(signal, handlers[signal]);
  }
  try {
    const moduleInput = process.env.PLAYWRIGHT_MODULE || path.join(ROOT, 'skills/remorsearch-ux-qa/drivers/web/node_modules/playwright');
    const modulePath = require.resolve(path.resolve(moduleInput));
    server = await startServer(); const port = server.address().port;
    log('server_listening', { host: '127.0.0.1', port });
    await readiness(port); log('server_ready');
    if (stopped) { server.closeAllConnections(); server.close(); return; }
    child = spawn(process.execPath, [path.join(__dirname, 'harness.cjs')], {
      cwd: ROOT, env: { ...process.env, PORT: String(port), PLAYWRIGHT_MODULE: modulePath, EVIDENCE_DIR: path.join(out, 'browser') },
      stdio: ['pipe', 'pipe', 'pipe']
    });
    log('harness_spawn', { pid: child.pid });
    let started = false;
    readyTimer = setTimeout(() => { log('harness_ready_timeout'); void stop('harness-ready-timeout', 1); }, 30000);
    child.stdin.on('error', error => log('stdin_error', { message: error.message }));
    child.stderr.on('data', chunk => { fs.appendFileSync(path.join(out, 'stderr.txt'), chunk); process.stderr.write(chunk); });
    const output = readline.createInterface({ input: child.stdout });
    output.on('line', line => {
      fs.appendFileSync(path.join(out, 'stdout.jsonl'), line + '\n'); process.stdout.write(line + '\n');
      let record; try { record = JSON.parse(line); } catch { log('non_json_output'); return; }
      log('harness_output', { action: record.action, ok: record.ok, ready: record.ready });
      if (record.ready && !started && !stopped) {
        started = true; clearTimeout(readyTimer); log('harness_ready');
        input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
        let sequence = 0;
        input.on('line', line => {
          if (stopped) return;
          log('command_forwarded', { sequence: ++sequence, raw: line });
          if (!child.stdin.write(line + '\n')) { input.pause(); child.stdin.once('drain', () => { if (!stopped) input.resume(); }); }
        });
        input.on('close', () => { if (!stopped) { log('input_eof'); child.stdin.end(); } });
      }
    });
    const [code, signal] = await once(child, 'close');
    log('harness_exit', { code, signal });
    await stop('harness-exit', code === 0 && started ? 0 : 1);
  } catch (error) {
    log('launcher_error', { message: error.message }); process.stderr.write(error.message + '\n');
    await stop('launcher-error', 1);
  } finally {
    for (const signal of Object.keys(handlers)) process.removeListener(signal, handlers[signal]);
  }
}
module.exports = { startServer, readiness };
if (require.main === module) main().catch(error => { console.error(error.message); process.exitCode = 1; });
