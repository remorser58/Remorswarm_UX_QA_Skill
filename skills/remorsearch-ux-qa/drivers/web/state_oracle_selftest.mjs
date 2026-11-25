// Hook: await runStateOracleSelftest({ pw, info, check, tmp });
// Uses its own loopback fixture server; no changes to the main selftest server are needed.
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { WebSession, ensureRunDir } from './session.mjs';
import { normalizeScenario } from './validate.mjs';

const FIXTURE = fs.readFileSync(fileURLToPath(new URL('./fixtures/state_oracle.html', import.meta.url)));
const basis = { kind: 'product', reference: 'Generic fixture #policy: draft preservation and one visible record per approval; fresh pages reset all fixture data.' };
const click = (target) => ({ action: 'click', target, settle_ms: 100, feedback_timeout_ms: 150 });
const type = (text) => ({ action: 'type', target: '#entry', text, clear: true, settle_ms: 0, feedback_timeout_ms: 150, redact: true });
const task = (id, selector, property, assertion, extra = {}) => ({
  id, selector, property, ...assertion, basis, severity: 'P1',
  consequence: 'The authored generic request state or visible record relation must hold.', ...extra,
});
const count = (id, assertion, extra = {}) => task(id, '.record', 'count', assertion, { container: '#history', ...extra });
const input = (step, kind, expectation, extra = {}) => ({ step, kind, expectation, basis, ...extra });

/** Public generic examples also serve as the executable scenario contract documentation.
 *
 * task_checks:
 * - value/text/checked: expected, authored type from_step, or earlier from_check equality.
 * - count: selector is relative to a unique visible container, expected is a nonnegative
 *   safe integer; from_check + delta compares visible record counts without reading storage.
 * - basis {kind:product|task, reference} is the explicit expectation source, not a paper,
 *   inferred universal preservation rule, field value or downstream-harm claim. Without it,
 *   measured comparison is a candidate question (passed:null), never a TI-01 defect.
 * - input_cases classify authored type actions, not generated domain-specific validators.
 *   Blank/boundary acceptance comes from the cited rule. documented_valid => accept,
 *   invalid => reject. Boundary requires a textual boundary description. Every case's
 *   actual expected UI outcome must also have its own task check.
 * - follow_up {fixture:true,changes,insertions:[{after_step,steps}],input_cases?}
 *   inserts normalized real UI actions into recorded source actions through this check's
 *   checkpoint. It is a separate fresh browser context, same URL/build/device, and compares
 *   the same target with the captured normal value. fixture:true is the author's assertion
 *   that fresh page/context resets all relevant state; it does NOT reset a remote backend.
 *   No browser storage or application-private state is used as an oracle. after_step:0
 *   inserts before the first source action. Follow-up input_cases use transformed indices.
 *   Replay evidence lives in state-oracle/<check-id>/run.json and linked screenshots.
 *   Cross-navigation scalar samples exist only in a private Node-memory map, are cleared
 *   after comparisons, and are never serialized as expected/actual values in evidence.
 *
 * The count examples below distinguish same-run invariants from fresh metamorphic replay.
 * New request deliberately clears its draft and is a normal-reset negative control.
 * These authored regression fixtures do not establish product recall, precision or generalization.
 */
export function stateOracleScenarios() {
  const approve = [type('ab-12'), click('#option'), click('#review'), click('#approve')];
  return {
    preserve: {
      steps: [type('!'), click('#option'), click('#review'), type('ab-12'), click('#rerender'), click('#review'), click('#back')],
      checks: [
        task('error-input', '#entry', 'value', { from_step: 1 }, { after_step: 3 }),
        task('error-option', '#option', 'checked', { expected: true }, { after_step: 3 }),
        task('render-input', '#entry', 'value', { from_step: 4 }, { after_step: 5 }),
        task('render-option', '#option', 'checked', { from_check: 'error-option' }, { after_step: 5 }),
        task('back-input', '#entry', 'value', { from_step: 4 }),
        task('back-option', '#option', 'checked', { from_check: 'render-option' }),
      ],
    },
    records: {
      steps: [{ action: 'snapshot' }, ...approve, click('#reenter'), click('#approve'),
        click('#reenter'), click('#cancel'), click('#review'), click('#approve'), click('#new')],
      checks: [
        count('before', { expected: 0 }, { after_step: 1 }),
        count('once', { from_check: 'before', delta: 1 }, { after_step: 5 }),
        count('reentry', { from_check: 'once', delta: 0 }, { after_step: 7 }),
        count('cancel', { from_check: 'reentry', delta: 0 }, { after_step: 9 }),
        count('resubmit', { from_check: 'cancel', delta: 0 }, { after_step: 11 }),
        task('new-input-reset', '#entry', 'value', { expected: '' }),
        task('new-option-reset', '#option', 'checked', { expected: false }),
      ],
    },
    metamorphic: {
      steps: approve,
      checks: [count('normal-versus-fresh', { expected: 1 }, {
        follow_up: { fixture: true, changes: ['back', 'cancel', 'reentry', 'edit_resubmit'],
          insertions: [
            { after_step: 3, steps: [click('#back'), click('#review'), click('#cancel'), click('#review')] },
            { after_step: 4, steps: [click('#reenter'), click('#approve'), click('#edit'), type('AB-12'), click('#review'), click('#approve')] },
          ],
          input_cases: [input(1, 'documented_valid', 'accept'), input(12, 'documented_valid', 'accept')],
        },
      })],
    },
    inputs: {
      steps: [type(''), click('#review'), type('a'), click('#review'), type('ab'), click('#review'), click('#back'),
        type('abcdefgh'), click('#review'), click('#back'), type('abcdefghi'), click('#review'),
        type('!!'), click('#review'), type('12'), click('#review')],
      checks: [
        task('blank-rejected', '#error', 'text', { expected: 'Use 2 through 8 letters, digits or hyphens.' }, { after_step: 2, input_cases: [input(1, 'blank', 'reject')] }),
        task('below-minimum', '#error', 'text', { expected: 'Use 2 through 8 letters, digits or hyphens.' }, { after_step: 4, input_cases: [input(3, 'boundary', 'reject', { boundary: 'One character below the documented minimum length of two.' })] }),
        task('minimum-accepted', '#reviewed', 'text', { from_step: 5 }, { after_step: 6, input_cases: [input(5, 'boundary', 'accept', { boundary: 'Exactly the documented minimum length of two.' })] }),
        task('maximum-accepted', '#reviewed', 'text', { from_step: 8 }, { after_step: 9, input_cases: [input(8, 'boundary', 'accept', { boundary: 'Exactly the documented maximum length of eight.' })] }),
        task('above-maximum', '#error', 'text', { expected: 'Use 2 through 8 letters, digits or hyphens.' }, { after_step: 12, input_cases: [input(11, 'boundary', 'reject', { boundary: 'One character above the documented maximum length of eight.' })] }),
        task('invalid-rejected', '#error', 'text', { expected: 'Use 2 through 8 letters, digits or hyphens.' }, { after_step: 14, input_cases: [input(13, 'invalid', 'reject')] }),
        task('alternative-accepted', '#reviewed', 'text', { from_step: 15 }, { input_cases: [input(15, 'documented_valid', 'accept')] }),
      ],
    },
  };
}

export async function runStateOracleSelftest({ pw, info, check, tmp }) {
  const server = http.createServer((_req, res) => { res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' }); res.end(FIXTURE); });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const url = `http://127.0.0.1:${server.address().port}/state_oracle.html`;
  let serial = 0;
  const run = async (name, spec, bug = '') => {
    const { scenario } = normalizeScenario({ schema_version: 'ergo-scenario.v1', scenario_id: `SC-state-${name}`,
      surface: { kind: 'web', url: `${url}${bug ? `?bug=${bug}` : ''}`, build_id: 'generic-state-fixture-v1' },
      steps: spec.steps, success: { task_checks: spec.checks } }, { requireSteps: true });
    const runDir = path.join(tmp, `state-oracle-${++serial}`);
    const error = ensureRunDir(runDir);
    if (error) throw new Error(error);
    const session = new WebSession({ pw, pwInfo: info, scenario, runDir, runId: `R-state-${serial}`,
      profileId: 'EP-state', deviceRequest: { id: 'desktop-1920' }, mode: 'scripted',
      options: { settleMs: 100, feedbackTimeoutMs: 150, flashSampleMs: 0, focusWalk: false, reflow: false,
        autoScroll: true, locale: 'en-US', timezoneId: 'UTC', buildId: 'generic-state-fixture-v1', buildIdSource: 'fixture' } });
    let failed = false;
    try {
      await session.start();
      for (const action of scenario.steps) {
        const { step } = await session.act(action);
        if (step.result !== 'ok') { failed = true; break; }
      }
    } catch { failed = true; }
    return session.finish(failed ? { reason: 'state oracle selftest action failed' } : {});
  };
  try {
    const specs = stateOracleScenarios();
    for (const name of ['preserve', 'records', 'inputs', 'metamorphic']) {
      const result = await run(name, specs[name]);
      check(`state oracle: clean ${name}`, result.success === true, result.run.success_detail);
    }
    for (const [name, bug, expectedId] of [
      ['preserve', 'error_loss', 'error-input'], ['preserve', 'rerender_loss', 'render-input'],
      ['preserve', 'back_loss', 'back-input'], ['records', 'duplicate', 'reentry'],
      ['records', 'cancel_mutates', 'cancel'], ['metamorphic', 'duplicate', 'normal-versus-fresh'],
    ]) {
      const result = await run(name, specs[name], bug);
      const outcome = result.run.success_detail?.criteria.find((item) => item.id === expectedId);
      check(`state oracle: detects ${bug} ${name}`, outcome?.passed === false, outcome);
      if (name === 'preserve') {
        const selectionId = bug === 'error_loss' ? 'error-option' : bug === 'rerender_loss' ? 'render-option' : 'back-option';
        const selection = result.run.success_detail?.criteria.find((item) => item.id === selectionId);
        check(`state oracle: selection loss ${bug}`, selection?.passed === false, selection);
      }
      if (name === 'metamorphic') {
        check('state oracle: fresh replay has linked independent evidence', outcome?.replay?.passed === false
          && outcome.replay.run_id !== result.run.run_id && !!outcome.replay.snapshot_id
          && fs.existsSync(path.join(path.dirname(result.runPath), outcome.replay.run_path)), outcome?.replay);
      }
    }
    const candidate = structuredClone(specs.preserve);
    for (const c of candidate.checks) delete c.basis;
    const result = await run('candidate', candidate, 'error_loss');
    const outcome = result.run.success_detail?.criteria.find((item) => item.id === 'error-input');
    check('state oracle: no expectation basis means candidate, not defect', result.success === null
      && outcome?.passed === null && outcome.comparison === 'fail' && outcome.reason === 'expectation_basis_missing', outcome);
    const blockedReplay = structuredClone(specs.metamorphic);
    blockedReplay.checks[0].follow_up.insertions = [{ after_step: 0, steps: [{ ...click('#absent-control'), timeout_ms: 100 }] }];
    delete blockedReplay.checks[0].follow_up.input_cases;
    const incomplete = await run('incomplete-replay', blockedReplay);
    const incompleteCheck = incomplete.run.success_detail?.criteria[0];
    check('state oracle: failed replay is missing evidence, not a product defect', incomplete.success === null
      && incompleteCheck?.passed === null && incompleteCheck.reason === 'replay_failed', incompleteCheck);
    const invalid = structuredClone(specs.records);
    invalid.checks[1].from_check = 'later-unknown';
    let rejected = false;
    try {
      normalizeScenario({ schema_version: 'ergo-scenario.v1', scenario_id: 'SC-invalid',
        surface: { kind: 'web', url }, steps: invalid.steps, success: { task_checks: invalid.checks } }, { requireSteps: true });
    } catch { rejected = true; }
    check('state oracle: invalid relation source rejected before browser input', rejected);
  } finally { await new Promise((resolve) => server.close(resolve)); }
}
