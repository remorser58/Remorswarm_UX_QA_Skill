import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { normalizeScenario } from './validate.mjs';

export async function runTemporalSelftest({ base, tmp, runDriver, check }) {
  const scenario = {
    schema_version: 'ergo-scenario.v1', scenario_id: 'SC-temporal-keyboard',
    surface: { kind: 'web', url: `${base}/temporal_keyboard.html` }, task_goal_ko: 'Check request feedback and keyboard recovery.',
    device_ids: ['desktop-1920'], targets: {}, hotspots: [],
    steps: [
      { action: 'click', target: '#save' }, { action: 'wait', ms: 1000 },
      { action: 'click', target: '#open' }, { action: 'press', key: 'Escape' },
      { action: 'click', target: '#validate' }, { action: 'click', target: '#details' },
      { action: 'click', target: '#many' },
    ],
    timing_windows: [{ id: 'notice', selector: '#notice', kind: 'transient_text', measure: 'visible_duration', recovery: { selector: '#receipt', after_step: 2 } }],
    focus_walks: [
      { id: 'confirmation', state: 'confirmation', after_step: 2, selector: '#receipt', fixture: true },
      { id: 'modal', state: 'modal', after_step: 3, selector: '#review', return_selector: '#open', fixture: true },
      { id: 'error', state: 'validation_error', after_step: 5, selector: '#error', fixture: true },
      { id: 'detail', state: 'detail', after_step: 6, selector: '#detail', fixture: true },
    ],
    success: { selector_visible: '#detail' },
  };
  const input = path.join(tmp, 'temporal-keyboard.json');
  fs.writeFileSync(input, JSON.stringify(scenario));
  const result = await runDriver(['run', '--scenario', input, '--device', 'desktop-1920', '--out', path.join(tmp, 'temporal'),
    '--run-id', 'R-temporal', '--no-focus-walk', '--no-reflow', '--settle-ms', '40', '--feedback-timeout-ms', '100'], { timeoutMs: 180000 });
  check('temporal: recorded task completes independently of probes', result.code === 0, result.err || result.out);
  if (result.code !== 0) return;
  const directory = path.join(tmp, 'temporal', 'R-temporal');
  const run = JSON.parse(fs.readFileSync(path.join(directory, 'run.json')));
  const notice = run.temporal_candidates.find((c) => c.selector === '#notice');
  check('temporal: automatic status candidate appears and disappears inside the window',
    notice?.status === 'disappeared' && notice.visible_ms > 0 && notice.declared_window_id === 'notice', notice);
  const plain = run.temporal_candidates.find((c) => c.selector === '#plain');
  check('temporal: undeclared text candidate provides a timing replay declaration without claiming persistence beyond observation',
    plain?.status === 'open_at_observation_end' && plain.visible_ms === null && plain.declared_window_id === null
    && plain.timing_window.selector === '#plain', plain);
  const window = run.timing_windows[0];
  check('temporal: same visible receipt text establishes recovery with capture provenance',
    window.visible_ms > 0 && window.recovery.status === 'available' && window.recovery.snapshot_id, window);
  check('keyboard: all four intermediate states replay in separate recorded runs',
    run.probe_replays.length === 4 && run.probe_replays.every((p) => p.status === 'observed'
      && p.source_snapshot_id && p.run_id !== run.run_id && fs.existsSync(path.join(directory, p.run_path))), run.probe_replays);
  const modal = run.probe_replays.find((p) => p.id === 'modal');
  check('keyboard: normal modal loop supports reverse navigation and Escape returns focus',
    modal?.walks?.some((w) => w.direction === 'Tab' && w.ended === 'cycle')
    && modal.walks.some((w) => w.direction === 'Shift+Tab') && modal.escape.returned === true
    && modal.escape.state_still_visible === false, modal);
  check('temporal: page sampling cap is explicit rather than a clean observation', run.temporal_sampling_truncated === true);
  check('keyboard: probe does not replace task steps or task captures', run.steps.length === 7
    && run.snapshots.every((s) => !s.snapshot_id.includes('-focus-')));
  const analyzed = spawnSync(process.env.ERGOQA_PYTHON || 'python3', ['-c', [
    'import json, sys',
    'from ergoqa.analyze import analyze_run',
    'from ergoqa.profiles import sample_profiles',
    'profiles = sample_profiles(1, seed=7, device_ids=["desktop-1920"], orientation="landscape")',
    'result = analyze_run(sys.argv[1], profiles, cross_profile=True, gaze_enabled=False)',
    'hits = [o for o in result["observations"] if o["check_id"] == "SM-05" and o.get("extra", {}).get("probe_kind") == "intermediate_focus"]',
    'assert hits, result',
    'assert all(o["run_id"] != result["run_id"] and o["extra"]["source_run_id"] == result["run_id"] for o in hits)',
    'assert result["temporal_candidates"]',
    'print("probe capture provenance verified")',
  ].join('\n'), directory], { encoding: 'utf8',
    env: { ...process.env, PYTHONPATH: fileURLToPath(new URL('../..', import.meta.url)) } });
  check('keyboard: analyzer promotes measured focus gaps with independent probe provenance', analyzed.status === 0, analyzed.stderr || analyzed.stdout);
  for (const mutation of [
    (s) => { s.focus_walks[0].fixture = false; },
    (s) => { s.focus_walks[0].after_step = 100; },
    (s) => { s.timing_windows[0].recovery.selector = 'input[value="private"]'; },
    (s) => { s.timing_windows[0].exception = { kind: 'essential', basis: '' }; },
  ]) {
    const invalid = structuredClone(scenario);
    mutation(invalid);
    let rejected = false;
    try { normalizeScenario(invalid, { requireSteps: true }); } catch { rejected = true; }
    check('temporal: invalid probe/recovery declarations fail closed', rejected);
  }
}
