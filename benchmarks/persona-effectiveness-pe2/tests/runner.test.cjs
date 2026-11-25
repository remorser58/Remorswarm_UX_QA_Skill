'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { startServer, readiness } = require('../run.cjs');
const runner = path.resolve(__dirname, '../run.cjs');
const run = env => spawnSync(process.execPath, [runner], { env: { ...process.env, ...env }, encoding: 'utf8', timeout: 10000 });
test('ephemeral loopback server readiness requires no browser/UI action', async () => {
  const server = await startServer();
  try { assert.equal(server.address().address, '127.0.0.1'); assert.ok(server.address().port > 0); await readiness(server.address().port); }
  finally { await new Promise(r => server.close(r)); }
});
test('missing dependency is logged and cleanly fails without launching browser', () => {
  const parent = fs.mkdtempSync(path.join(os.tmpdir(), 'pe-runner-test-'));
  try {
    const out = path.join(parent, 'new');
    const result = run({ EVIDENCE_DIR: out, PLAYWRIGHT_MODULE: path.join(parent, 'missing-module') });
    assert.equal(result.status, 1); assert.equal(result.error, undefined);
    const events = fs.readFileSync(path.join(out, 'lifecycle.jsonl'), 'utf8').trim().split('\n').map(JSON.parse);
    assert.deepEqual(events.map(x => x.event), ['launcher_start', 'launcher_error', 'shutdown_begin', 'shutdown_complete']);
    assert.ok(events.every((e, i) => e.wall_time && (i === 0 || e.monotonic_ms >= events[i - 1].monotonic_ms)));
  } finally { fs.rmSync(parent, { recursive: true }); }
});
test('existing evidence including an empty directory is never overwritten', () => {
  const parent = fs.mkdtempSync(path.join(os.tmpdir(), 'pe-runner-test-'));
  try {
    const empty = run({ EVIDENCE_DIR: parent }); assert.equal(empty.status, 1); assert.deepEqual(fs.readdirSync(parent), []);
    const marker = path.join(parent, 'lifecycle.jsonl'); fs.writeFileSync(marker, 'preserve');
    const existing = run({ EVIDENCE_DIR: parent }); assert.equal(existing.status, 1); assert.equal(fs.readFileSync(marker, 'utf8'), 'preserve');
  } finally { fs.rmSync(parent, { recursive: true }); }
});
test('evidence path is mandatory', () => { const result = run({ EVIDENCE_DIR: '' }); assert.equal(result.status, 1); assert.match(result.stderr, /Set EVIDENCE_DIR/); });
test('injected launch error closes the owned server and records child failure', async () => {
  const parent = fs.mkdtempSync(path.join(os.tmpdir(), 'pe-runner-test-'));
  try {
    const modulePath = path.join(parent, 'launch-error.cjs');
    fs.writeFileSync(modulePath, "exports.chromium={launch:async()=>{throw Error('test-only launch failure')}};");
    const out = path.join(parent, 'new');
    const result = run({ EVIDENCE_DIR: out, PLAYWRIGHT_MODULE: modulePath });
    assert.equal(result.status, 1); assert.equal(result.error, undefined);
    const events = fs.readFileSync(path.join(out, 'lifecycle.jsonl'), 'utf8').trim().split('\n').map(JSON.parse);
    assert.ok(events.some(x => x.event === 'harness_exit' && x.code === 1));
    assert.equal(events.at(-1).event, 'shutdown_complete');
    assert.ok(!events.some(x => x.event === 'command_forwarded'));
    await assert.rejects(readiness(events.find(x => x.event === 'server_listening').port));
  } finally { fs.rmSync(parent, { recursive: true }); }
});
