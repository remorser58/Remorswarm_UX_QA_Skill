import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import { validateRequest, routeReply, disableUnroutedTransports } from './journey_bridge.mjs';

function request() {
  return {
    schema_version: 'ux-journey-browser-request.v1',
    binding: { task_id: 'T-retain', attempt: 1, operation_id: 'operation-one', build_sha256: 'a'.repeat(64),
      persona_id: 'P-returning', revision: 1, profile_sha256: 'b'.repeat(64), prd_sha256: 'c'.repeat(64) },
    source: '/reviewed/product', files: { 'index.html': 'd'.repeat(64) }, output: '/owned/scratch/browser',
    scenario: { schema_version: 'ergo-scenario.v1', scenario_id: 'SC-retain',
      surface: { kind: 'web', url: 'https://remorsearch.invalid/index.html', build_id: 'a'.repeat(64) },
      task_goal_ko: 'Preserve entered data after a validation error.', device_ids: ['desktop-1920'],
      steps: [{ action: 'type', target: '#request', text: 'Synthetic request' }, { action: 'click', target: '#submit' }],
      success: { task_checks: [{ id: 'retain', selector: '#request', property: 'value', from_step: 1, after_step: 2,
        severity: 'P1', consequence: 'The entered request must survive the failed submission.' }] } },
    device_id: 'desktop-1920', timeout_seconds: 15,
  };
}

test('binds fixed measured checkpoints to the reviewed scenario', () => {
  const doc = request();
  const accepted = validateRequest(doc);
  assert.equal(accepted.scenario.success.task_checks[0].after_step, 2);
  assert.equal(accepted.scenario.build_id, doc.binding.build_sha256);
  assert.equal(accepted.runId, 'R-' + 'operation-one');
  assert.deepEqual(doc, request(), 'validation must not mutate frozen input');
});

test('rejects other URLs, credentials, ports, fragments and unreviewed files', () => {
  for (const url of ['https://example.test/index.html', 'http://127.0.0.1/index.html',
    'https://me@remorsearch.invalid/index.html', 'https://remorsearch.invalid:443/index.html',
    'https://remorsearch.invalid/index.html#entry', 'https://remorsearch.invalid/missing.html']) {
    const doc = request(); doc.scenario.surface.url = url;
    assert.throws(() => validateRequest(doc));
  }
});

test('rejects path traversal, unknown static types, oversized input maps and missing bindings', () => {
  for (const name of ['../index.html', '/index.html', 'folder/../index.html', 'a\\index.html', '.hidden.html', 'adapter.py']) {
    const doc = request(); doc.files[name] = 'd'.repeat(64);
    assert.throws(() => validateRequest(doc));
  }
  const doc = request(); delete doc.binding.operation_id;
  assert.throws(() => validateRequest(doc));
  const many = request();
  for (let i = 0; i < 64; i++) many.files['extra-' + i + '.js'] = 'd'.repeat(64);
  assert.throws(() => validateRequest(many));
});

test('rejects unmeasured success, missing checkpoints and cross-build claims', () => {
  const cases = [
    d => { d.scenario.success = { selector_visible: '#done' }; },
    d => { delete d.scenario.success.task_checks[0].after_step; },
    d => { d.scenario.success.task_checks[0].after_step = 3; },
    d => { d.scenario.surface.build_id = 'e'.repeat(64); },
    d => { d.scenario.steps[0] = { action: 'type', target: '#request', text: 'Synthetic', unexpected: true }; },
    d => { d.scenario.steps[0] = { action: 'evaluate', script: 'document.body.remove()' }; },
    d => { d.timeout_seconds = 31; },
    d => { d.output = d.source + '/browser'; },
  ];
  for (const mutate of cases) { const doc = request(); mutate(doc); assert.throws(() => validateRequest(doc)); }
});

test('serves only reviewed bytes and never offers a network fallback', () => {
  const bytes = Buffer.from('<p>Owned fixture</p>');
  const files = new Map([['index.html', { body: bytes, contentType: 'text/html; charset=utf-8' }]]);
  const reply = routeReply(files, 'https://remorsearch.invalid/index.html', 'GET');
  assert.equal(reply.status, 200); assert.equal(reply.body, bytes);
  assert.match(reply.headers['content-security-policy'], /connect-src 'none'/);
  assert.equal(routeReply(files, 'https://remorsearch.invalid/index.html', 'HEAD').body.length, 0);
  for (const [url, method] of [
    ['https://example.test/index.html', 'GET'], ['https://remorsearch.invalid/index.html', 'POST'],
    ['https://remorsearch.invalid/index.html?secret=value', 'GET'], ['file:///index.html', 'GET'],
    ['https://remorsearch.invalid/missing.js', 'GET'], ['https://remorsearch.invalid/%2e%2e/index.html', 'GET'],
  ]) assert.equal(routeReply(files, url, method), null);
});

test('preflight validates exact source bytes without output or a browser runtime', () => {
  const driver = path.dirname(fileURLToPath(import.meta.url));
  const doc = request();
  doc.source = path.join(driver, 'fixtures');
  doc.files = { 'inspect.html': crypto.createHash('sha256').update(fs.readFileSync(path.join(doc.source, 'inspect.html'))).digest('hex') };
  doc.scenario.surface.url = 'https://remorsearch.invalid/inspect.html';
  doc.output = path.join(driver, 'not-created-validation-' + process.pid);
  assert.equal(fs.existsSync(doc.output), false);
  const invoke = value => spawnSync(process.execPath, [path.join(driver, 'journey_bridge.mjs'), '--validate'],
    { input: JSON.stringify(value), encoding: 'utf8', timeout: 5000 });
  const accepted = invoke(doc);
  assert.equal(accepted.status, 0, accepted.stderr);
  assert.deepEqual(JSON.parse(accepted.stdout), { schema_version: 'ux-journey-browser-validation.v1', valid: true });
  doc.files['inspect.html'] = 'f'.repeat(64);
  const refused = invoke(doc);
  assert.equal(refused.status, 2);
  assert.deepEqual(JSON.parse(refused.stdout), { schema_version: 'ux-journey-browser-validation.v1', valid: false });
  assert.equal(fs.existsSync(doc.output), false);
});

test('unrouted transport guard removes constructors and prevents restoration before page code', () => {
  const calls = [];
  const context = vm.createContext({ RTCPeerConnection: function () { calls.push('rtc'); },
    WebTransport: function () { calls.push('transport'); }, RTCFutureTransport: function () { calls.push('future'); } });
  vm.runInContext('(' + disableUnroutedTransports.toString() + ')()', context);
  for (const name of ['RTCPeerConnection', 'webkitRTCPeerConnection', 'RTCIceTransport', 'WebTransport', 'RTCFutureTransport']) {
    const descriptor = Object.getOwnPropertyDescriptor(context, name);
    assert.equal(descriptor.value, undefined);
    assert.equal(descriptor.writable, false);
    assert.equal(descriptor.configurable, false);
    assert.throws(() => Object.defineProperty(context, name, { value: function () {} }));
    assert.throws(() => vm.runInContext('new ' + name + '()', context));
  }
  assert.equal(vm.runInContext('Object.isFrozen(__remorsearchOwnedNetworkGuard.disabled)', context), true);
  assert.deepEqual(calls, [], 'the guard must never call the original transport');
});
