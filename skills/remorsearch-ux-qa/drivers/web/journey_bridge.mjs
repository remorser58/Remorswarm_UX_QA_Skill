#!/usr/bin/env node
// Bounded owned static-page journeys. No user browser, URL fetch or adapter code.
// The parent freezes the reviewed source/persona/criteria, owns dispatch recovery,
// and admits the native driver evidence through the existing swarm receipt gates.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { WebSession } from './session.mjs';
import { resolveDevice } from './devices.mjs';
import { normalizeAction, normalizeScenario, isTaskSelector } from './validate.mjs';
import { loadPlaywright } from './playwright_loader.mjs';

const ORIGIN = 'https://remorsearch.invalid';
const INPUT_LIMIT = 256 * 1024;
const FILE_LIMIT = 2 * 1024 * 1024;
const TOTAL_FILE_LIMIT = 16 * 1024 * 1024;
const EVIDENCE_LIMIT = 64 * 1024 * 1024;
const HASH = /^[a-f0-9]{64}$/;
const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$/;
const MIME = Object.freeze({ '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.woff': 'font/woff', '.woff2': 'font/woff2' });
const CSP = "default-src 'self' data: blob:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'none'; frame-src 'none'; object-src 'none'; worker-src 'none'; base-uri 'none'; form-action 'none'";

function reject(code = 'input_invalid') { const error = new Error(code); error.bridgeCode = code; throw error; }
function object(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function keys(value, required, optional = []) {
  if (!object(value) || required.some(k => !Object.hasOwn(value, k)) ||
      Object.keys(value).some(k => !required.includes(k) && !optional.includes(k))) reject();
}
function digest(bytes) { return crypto.createHash('sha256').update(bytes).digest('hex'); }
function relative(name) {
  if (typeof name !== 'string' || name.length > 512 || !/^[A-Za-z0-9][A-Za-z0-9._/-]*$/.test(name) ||
      name.split('/').some(part => !part || part === '.' || part === '..' || part.startsWith('.'))) reject();
  if (!Object.hasOwn(MIME, path.posix.extname(name))) reject();
  return name;
}
function absolute(name) {
  if (typeof name !== 'string' || name.length > 4096 || !path.isAbsolute(name) || path.normalize(name) !== name || /[\x00-\x1f]/.test(name)) reject();
  return name;
}
function inside(child, parent) { return child === parent || child.startsWith(parent + path.sep); }
function resourceName(url) {
  if (typeof url !== 'string' || !url.startsWith(ORIGIN + '/')) return null;
  const name = url.slice(ORIGIN.length + 1);
  try { return relative(name); } catch { return null; }
}

/** Pure validation. A scenario is data; it never contains an execution program. */
export function validateRequest(raw) {
  keys(raw, ['schema_version', 'binding', 'source', 'files', 'output', 'scenario', 'device_id', 'timeout_seconds']);
  if (raw.schema_version !== 'ux-journey-browser-request.v1') reject();
  const b = raw.binding;
  keys(b, ['task_id', 'attempt', 'operation_id', 'build_sha256', 'persona_id', 'revision', 'profile_sha256', 'prd_sha256']);
  for (const k of ['task_id', 'operation_id', 'persona_id']) if (typeof b[k] !== 'string' || !ID.test(b[k])) reject();
  for (const k of ['build_sha256', 'profile_sha256', 'prd_sha256']) if (typeof b[k] !== 'string' || !HASH.test(b[k])) reject();
  for (const k of ['attempt', 'revision']) if (!Number.isSafeInteger(b[k]) || b[k] < 1) reject();
  absolute(raw.source); absolute(raw.output);
  if (inside(raw.output, raw.source) || inside(raw.source, raw.output)) reject();
  if (!object(raw.files) || Object.keys(raw.files).length < 1 || Object.keys(raw.files).length > 64) reject();
  for (const [name, hash] of Object.entries(raw.files)) { relative(name); if (typeof hash !== 'string' || !HASH.test(hash)) reject(); }
  if (!Number.isInteger(raw.timeout_seconds) || raw.timeout_seconds < 1 || raw.timeout_seconds > 30) reject();
  const doc = structuredClone(raw.scenario);
  keys(doc, ['schema_version', 'scenario_id', 'surface', 'task_goal_ko', 'device_ids', 'steps', 'success'], ['targets']);
  keys(doc.surface, ['kind', 'url', 'build_id']);
  const first = resourceName(doc.surface.url);
  if (doc.surface.kind !== 'web' || doc.surface.build_id !== b.build_sha256 || first === null ||
      !Object.hasOwn(raw.files, first) || !first.endsWith('.html')) reject();
  if (typeof doc.scenario_id !== 'string' || !ID.test(doc.scenario_id) || typeof doc.task_goal_ko !== 'string' ||
      !doc.task_goal_ko.trim() || doc.task_goal_ko.length > 4000) reject();
  if (!Array.isArray(doc.device_ids) || doc.device_ids.length !== 1 || doc.device_ids[0] !== raw.device_id) reject();
  if (!Array.isArray(doc.steps) || doc.steps.length < 1 || doc.steps.length > 16) reject();
  for (const action of doc.steps) {
    if (!['type', 'click', 'tap', 'press', 'scroll', 'wait', 'snapshot'].includes(action?.action)) reject();
    normalizeAction(action, { strict: true });
    // Bound authored typing by action work, not a hidden per-character delay.
    if (action.action === 'type' && action.delay_ms === undefined) action.delay_ms = 0;
    if (['type', 'click', 'tap'].includes(action.action) && !isTaskSelector(action.target)) reject();
    for (const key of ['ms', 'hold_ms', 'duration_ms', 'delay_ms', 'settle_ms', 'feedback_timeout_ms', 'timeout_ms']) {
      if (action[key] !== undefined && (action[key] > 1000 || (key === 'delay_ms' && action[key] !== 0))) reject();
    }
  }
  keys(doc.success, ['task_checks']);
  if (!Array.isArray(doc.success.task_checks) || !doc.success.task_checks.length) reject();
  for (const check of doc.success.task_checks) {
    if (!Number.isInteger(check?.after_step) || check.after_step < 1 || check.after_step > doc.steps.length) reject();
  }
  const { scenario, warnings } = normalizeScenario(doc, { requireSteps: true });
  if (warnings.length || scenario.success_unevaluable.length) reject();
  const deviceRequest = { id: raw.device_id };
  const device = resolveDevice(deviceRequest).snapshotDevice;
  if (device.viewport_css[0] * device.viewport_css[1] * device.dpr ** 2 > 16_000_000) reject();
  return { scenario, deviceRequest, runId: 'R-' + b.operation_id };
}

/** Null means abort, never continue/fetch. Query strings and URL aliases are refused. */
export function routeReply(files, url, method) {
  const name = resourceName(url);
  if (name === null || !['GET', 'HEAD'].includes(method) || !files.has(name)) return null;
  const entry = files.get(name);
  return { status: 200, contentType: entry.contentType, body: method === 'HEAD' ? Buffer.alloc(0) : entry.body,
    headers: { 'content-security-policy': CSP, 'x-content-type-options': 'nosniff', 'cache-control': 'no-store' } };
}

function noLinks(file) {
  let cursor = path.parse(file).root;
  for (const part of file.slice(cursor.length).split(path.sep).filter(Boolean)) {
    cursor = path.join(cursor, part);
    if (fs.lstatSync(cursor).isSymbolicLink()) reject('source_unavailable');
  }
}

function readReviewedFiles(source, manifest) {
  noLinks(source);
  if (!fs.statSync(source).isDirectory() || fs.realpathSync(source) !== source) reject('source_unavailable');
  const result = new Map();
  let total = 0;
  for (const [name, expected] of Object.entries(manifest)) {
    const file = path.join(source, name); noLinks(file);
    const fd = fs.openSync(file, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW);
    try {
      const stat = fs.fstatSync(fd);
      if (!stat.isFile() || stat.size > FILE_LIMIT || total + stat.size > TOTAL_FILE_LIMIT) reject('source_unavailable');
      const bytes = fs.readFileSync(fd);
      if (bytes.length > FILE_LIMIT || digest(bytes) !== expected || fs.realpathSync(file) !== file) reject('source_changed');
      total += bytes.length;
      if (total > TOTAL_FILE_LIMIT) reject('source_unavailable');
      result.set(name, { body: bytes, contentType: MIME[path.posix.extname(name)] });
    } finally { fs.closeSync(fd); }
  }
  return result;
}

/** Runs before page code in every owned document, including child frames/popups.
 * Routing/CSP do not cover every RTC transport (for example TCP TURN). Disable
 * these capabilities instead of claiming that an HTTP interception is a firewall.
 * Keep this function self-contained: Playwright serializes it into each document.
 */
export function disableUnroutedTransports() {
  const names = [...new Set([
    'RTCPeerConnection', 'webkitRTCPeerConnection', 'mozRTCPeerConnection',
    'RTCIceTransport', 'RTCDtlsTransport', 'RTCSctpTransport', 'RTCQuicTransport',
    'RTCDataChannel', 'RTCRtpSender', 'RTCRtpReceiver', 'RTCRtpTransceiver', 'WebTransport',
    ...Object.getOwnPropertyNames(globalThis).filter(name => /^RTC[A-Z]|^(?:webkit|moz)RTCPeerConnection$|^WebTransport$/.test(name)),
  ])];
  for (const name of names) {
    Object.defineProperty(globalThis, name, { value: undefined, writable: false, configurable: false, enumerable: false });
  }
  Object.defineProperty(globalThis, '__remorsearchOwnedNetworkGuard', {
    value: Object.freeze({ installed: true, disabled: Object.freeze(names) }),
    writable: false, configurable: false, enumerable: false,
  });
}

function transportGuardInstalled() {
  const guard = Object.getOwnPropertyDescriptor(globalThis, '__remorsearchOwnedNetworkGuard');
  return !!guard && guard.configurable === false && guard.writable === false && guard.value.installed === true &&
    Object.isFrozen(guard.value) && Object.isFrozen(guard.value.disabled) &&
    guard.value.disabled.every(name => {
      const descriptor = Object.getOwnPropertyDescriptor(globalThis, name);
      return !!descriptor && descriptor.configurable === false && descriptor.writable === false && descriptor.value === undefined;
    });
}

class OwnedSession extends WebSession {
  constructor(options, files) { super(options); this.reviewedFiles = files; }
  async onRoute(route) {
    const request = route.request();
    const reply = routeReply(this.reviewedFiles, request.url(), request.method());
    if (reply) await route.fulfill(reply).catch(() => {});
    else { this.blockedCount++; await route.abort('blockedbyclient').catch(() => {}); }
  }
  async onWebSocket(socket) {
    this.blockedCount++;
    await socket.close({ code: 1008, reason: 'No network in reviewed static journeys' }).catch(() => {});
  }
}

function within(promise, ms) {
  let timer;
  return Promise.race([promise, new Promise((_, rejectTimeout) => {
    timer = setTimeout(() => rejectTimeout(Object.assign(new Error('timeout'), { bridgeCode: 'timeout' })), ms);
  })]).finally(() => clearTimeout(timer));
}

function evidenceSize(root) {
  let total = 0;
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    if (!entry.isFile() || entry.isSymbolicLink()) reject('evidence_invalid');
    total += fs.statSync(path.join(root, entry.name)).size;
    if (total > EVIDENCE_LIMIT) reject('evidence_limit');
  }
}

/** Probe only the already installed runtime. Never launch or install a browser. */
function packageRoot(start, expectedName) {
  let directory = fs.realpathSync(start);
  if (!fs.statSync(directory).isDirectory()) directory = path.dirname(directory);
  for (;;) {
    const metadata = path.join(directory, 'package.json');
    if (fs.existsSync(metadata)) {
      const doc = JSON.parse(fs.readFileSync(metadata, 'utf8'));
      if (doc.name === expectedName) {
        if (doc.version !== '1.56.1') reject('runtime_unavailable');
        return directory;
      }
    }
    const parent = path.dirname(directory);
    if (directory === parent) reject('runtime_unavailable');
    directory = parent;
  }
}

function runtime({ discovery = false } = {}) {
  if (process.versions.node.split('.')[0] !== '22' || process.env.REMORSEARCH_BROWSER_WS !== undefined ||
      process.env.NODE_OPTIONS !== undefined) reject('runtime_unavailable');
  let loaded;
  try {
    const pinned = process.env.REMORSEARCH_JOURNEY_PLAYWRIGHT;
    if (pinned !== undefined) {
      absolute(pinned);
      if (fs.realpathSync(pinned) !== pinned || packageRoot(pinned, 'playwright') !== pinned) reject('runtime_unavailable');
      const entry = path.join(pinned, 'index.js');
      if (fs.realpathSync(entry) !== entry || !fs.statSync(entry).isFile()) reject('runtime_unavailable');
      const requirePinned = createRequire(path.join(pinned, 'package.json'));
      const pinnedCore = process.env.REMORSEARCH_JOURNEY_PLAYWRIGHT_CORE;
      if (typeof pinnedCore !== 'string' || fs.realpathSync(pinnedCore) !== pinnedCore ||
          packageRoot(requirePinned.resolve('playwright-core'), 'playwright-core') !== pinnedCore) reject('runtime_unavailable');
      loaded = { pw: requirePinned(entry), info: { version: '1.56.1', path: pinned, resolved_by: 'frozen journey package root' } };
    } else {
      // Discovery is for the first preflight only. The parent persists the
      // returned canonical root and pins it on every subsequent invocation.
      if (!discovery) reject('runtime_unavailable');
      loaded = loadPlaywright();
    }
  } catch { reject('runtime_unavailable'); }
  if (loaded.info.version !== '1.56.1') reject('runtime_unavailable');
  let playwrightPath, corePath;
  try {
    playwrightPath = packageRoot(loaded.info.path, 'playwright');
    const requireFromPlaywright = createRequire(path.join(playwrightPath, 'package.json'));
    corePath = packageRoot(requireFromPlaywright.resolve('playwright-core'), 'playwright-core');
  } catch { reject('runtime_unavailable'); }
  const executable = loaded.pw.chromium.executablePath();
  if (!discovery && process.env.REMORSEARCH_JOURNEY_CHROMIUM !== executable) reject('runtime_unavailable');
  try {
    if (!fs.statSync(executable).isFile()) reject('runtime_unavailable');
    fs.accessSync(executable, fs.constants.X_OK);
  } catch { reject('runtime_unavailable'); }
  return { ...loaded, executable, playwrightPath, corePath };
}

/** Actual execution. No browser is started until every input and runtime is checked. */
export async function executeRequest(request) {
  const result = { schema_version: 'ux-journey-browser-result.v1', binding: null, problem: null, cleanup_confirmed: true, run: null };
  let ownedBrowser = null, launched = false, launchSettled = true, launchPromise = null, closePromise = null;
  let session = null, timer = null, aborted = null, interrupt = null, flow = null;
  let browserCloseAcknowledged = false;
  const onStop = code => { if (!aborted) { aborted = code; interrupt?.(); } };
  const onTerm = () => onStop('cancelled');
  const closeOwned = async () => {
    if (!ownedBrowser) return !launched && launchSettled;
    if (!closePromise) closePromise = (async () => {
      await ownedBrowser.close({ reason: 'Owned reviewed journey finished' });
      browserCloseAcknowledged = !ownedBrowser.isConnected();
      return browserCloseAcknowledged;
    })();
    return closePromise;
  };
  try {
    const accepted = validateRequest(request);
    result.binding = structuredClone(request.binding);
    const { pw, info, executable } = runtime();
    const cwd = fs.realpathSync(process.cwd());
    noLinks(path.dirname(request.output));
    if (path.dirname(request.output) !== cwd || fs.statSync(cwd).mode & 0o077 || fs.existsSync(request.output)) reject('output_unavailable');
    const files = readReviewedFiles(request.source, request.files);
    fs.mkdirSync(request.output, { mode: 0o700 });
    process.umask(0o077);
    const stopSignal = new Promise(resolve => { interrupt = resolve; });
    process.once('SIGTERM', onTerm); process.once('SIGINT', onTerm);
    timer = setTimeout(() => onStop('timeout'), request.timeout_seconds * 1000);
    const wrappedPw = { devices: pw.devices, chromium: { launch: async () => {
      launched = true; launchSettled = false;
      launchPromise = pw.chromium.launch({ headless: true, executablePath: executable, timeout: Math.min(10000, request.timeout_seconds * 1000),
        handleSIGINT: false, handleSIGTERM: false, handleSIGHUP: false,
        env: { PATH: '/usr/bin:/bin', HOME: cwd, TMPDIR: cwd, LANG: 'C', LC_ALL: 'C' },
        args: ['--disable-background-networking', '--disable-component-update', '--disable-quic',
          '--host-resolver-rules=MAP * ~NOTFOUND', '--force-webrtc-ip-handling-policy=disable_non_proxied_udp'] });
      try { ownedBrowser = await launchPromise; } finally { launchSettled = true; }
      if (aborted) { await closeOwned(); reject(aborted); }
      return new Proxy(ownedBrowser, { get(target, property) {
        if (property === 'close') return closeOwned;
        if (property === 'newContext') return async options => {
          const context = await target.newContext(options);
          await context.addInitScript(disableUnroutedTransports);
          let firstPage = null;
          context.on('page', page => {
            page.on('download', download => {
              session?.block('unexpected download blocked');
              void download.cancel().catch(() => {});
            });
            if (!firstPage) firstPage = page;
            else {
              session?.block('unexpected popup blocked');
              void page.close().catch(() => {});
            }
          });
          return new Proxy(context, { get(ownedContext, key) {
            if (key === 'newPage') return async () => {
              const page = await ownedContext.newPage();
              if (!(await page.evaluate(transportGuardInstalled))) reject('transport_guard_unavailable');
              return page;
            };
            const value = Reflect.get(ownedContext, key, ownedContext);
            return typeof value === 'function' ? value.bind(ownedContext) : value;
          } });
        };
        const value = Reflect.get(target, property, target);
        return typeof value === 'function' ? value.bind(target) : value;
      } });
    } } };
    session = new OwnedSession({ pw: wrappedPw, pwInfo: info, scenario: accepted.scenario,
      deviceRequest: accepted.deviceRequest, profileId: request.binding.persona_id, runId: accepted.runId,
      runDir: request.output, mode: 'scripted', warnings: [], options: {
        headed: false, flashSampleMs: 0, feedbackTimeoutMs: 100, settleMs: 50,
        autoScroll: true, focusWalk: false, reflow: false, visualFeedback: false, allowOrigins: [],
        locale: 'ko-KR', timezoneId: 'Asia/Seoul', buildId: request.binding.build_sha256,
        buildIdSource: 'frozen reviewed workspace', agent: 'deterministic reviewed journey bridge',
        agentInfo: { model_family: 'none', model: 'scripted task execution', input_channel: 'screenshot+a11y', persona_arm: 'neutral' },
      } }, files);
    flow = (async () => {
      await session.start();
      if (aborted) reject(aborted);
      for (const action of accepted.scenario.steps) {
        if (aborted) reject(aborted);
        if (session.blockReasons.length || session.crashed) break;
        const { step } = await session.act(action);
        evidenceSize(request.output);
        if (aborted) reject(aborted);
        if (step.result !== 'ok') break;
      }
    })();
    // Capture rejection now: a cancellation race may win before flow settles.
    const flowResult = flow.then(() => null, error => error);
    const error = await Promise.race([flowResult, stopSignal.then(() => ({ bridgeCode: aborted }))]);
    if (aborted || error) {
      result.problem = aborted || error.bridgeCode || 'browser_execution_failed';
      if (!launchSettled) await within(launchPromise.catch(() => {}), 3000).catch(() => {});
      await within(closeOwned(), 3000).catch(() => {});
      await within(flowResult, 1000).catch(() => {});
    }
    const finished = await within(session.finish(result.problem ? { reason: result.problem } : {}), 3000);
    if (aborted) result.problem = aborted;
    evidenceSize(request.output);
    const runFile = path.join(request.output, 'run.json');
    if (finished.runPath !== runFile || !fs.lstatSync(runFile).isFile()) reject('evidence_invalid');
    const bytes = fs.readFileSync(runFile);
    if (!bytes.length || bytes.length > 8 * 1024 * 1024) reject('evidence_invalid');
    result.run = { path: 'run.json', sha256: digest(bytes) };
  } catch (error) {
    result.problem = aborted || error.bridgeCode || (launched ? 'browser_execution_failed' : 'input_invalid');
  } finally {
    if (aborted) result.problem = aborted;
    clearTimeout(timer); process.removeListener('SIGTERM', onTerm); process.removeListener('SIGINT', onTerm);
    if (!launchSettled && launchPromise) await within(launchPromise.catch(() => {}), 3000).catch(() => {});
    if (ownedBrowser) await within(closeOwned(), 3000).catch(() => {});
    result.cleanup_confirmed = launched ? !!ownedBrowser && browserCloseAcknowledged : launchSettled;
    if (!result.cleanup_confirmed) result.problem = 'cleanup_uncertain';
  }
  return result;
}

async function main() {
  if (process.argv.length === 3 && process.argv[2] === '--probe') {
    try {
      const { info, executable, playwrightPath, corePath } = runtime({ discovery: true });
      process.stdout.write(JSON.stringify({ schema_version: 'ux-journey-browser-runtime.v1',
        node_version: process.versions.node, playwright_version: info.version, chromium_executable: executable,
        playwright_path: playwrightPath, playwright_core_path: corePath }) + '\n');
    } catch {
      process.stdout.write(JSON.stringify({ schema_version: 'ux-journey-browser-runtime.v1', problem: 'runtime_unavailable' }) + '\n');
      process.exitCode = 2;
    }
    return;
  }
  const validationOnly = process.argv.length === 3 && process.argv[2] === '--validate';
  let length = 0; const chunks = [];
  try {
    for await (const chunk of process.stdin) {
      length += chunk.length; if (length > INPUT_LIMIT) reject(); chunks.push(chunk);
    }
    if (!length || (!validationOnly && process.argv.length !== 2)) reject();
    const request = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    if (validationOnly) {
      validateRequest(request);
      readReviewedFiles(request.source, request.files);
      process.stdout.write(JSON.stringify({ schema_version: 'ux-journey-browser-validation.v1', valid: true }) + '\n');
      return;
    }
    const result = await executeRequest(request);
    process.stdout.write(JSON.stringify(result) + '\n');
    process.exitCode = result.problem ? 4 : 0;
  } catch {
    if (validationOnly) {
      process.stdout.write(JSON.stringify({ schema_version: 'ux-journey-browser-validation.v1', valid: false }) + '\n');
      process.exitCode = 2;
      return;
    }
    process.stdout.write(JSON.stringify({ schema_version: 'ux-journey-browser-result.v1', binding: null,
      problem: 'input_invalid', cleanup_confirmed: true, run: null }) + '\n');
    process.exitCode = 2;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main().then(() => process.exit(process.exitCode || 0));
}
