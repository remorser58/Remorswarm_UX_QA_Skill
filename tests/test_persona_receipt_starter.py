"""Read-only receipt drafting cannot assign, renew or certify execution."""
import contextlib
import copy
import io
import json
import unittest
from unittest.mock import patch

import test_persona_swarm as fixtures
from test_persona_library import profile_input
from uxpersonas import swarm
from uxpersonas.cli import main, parser
from uxpersonas.library import Library
from uxresearch.canonical import EngineError
from uxresearch.storage import atomic, canonical


class ReceiptStarterTests(unittest.TestCase):
    setUp = fixtures.SwarmTests.setUp
    plan = fixtures.SwarmTests.plan
    receipt = fixtures.SwarmTests.receipt

    def prepare(self):
        self.spec['tasks'][0]['success_criteria'].append('Final choice visible')
        self.plan()
        return swarm.claim(self.lib, self.run, 'worker1')

    def snapshot(self):
        return {str(p.relative_to(self.run)): (p.stat().st_mode, p.read_bytes())
                for p in self.run.rglob('*') if p.is_file()}

    def blocked(self, packet, code=None):
        before = self.snapshot()
        with self.assertRaises(EngineError) as raised:
            swarm.receipt_starter(self.lib, self.run, packet)
        self.assertEqual(before, self.snapshot())
        if code:
            self.assertEqual(raised.exception.issue['code'], code)
        return raised.exception

    def test_exact_bindings_all_criteria_and_no_execution(self):
        claim = self.prepare()
        before = self.snapshot()
        original = copy.deepcopy(claim)
        draft = swarm.receipt_starter(self.lib, self.run, claim)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(claim, original)
        self.assertEqual(draft['schema_version'], 'ux-persona-swarm-receipt-draft.v1')
        self.assertEqual(draft['lease_token'], claim['lease']['lease_token'])
        self.assertEqual(draft['worker_id'], 'worker1')
        self.assertEqual(draft['build_sha256'], claim['build']['sha256'])
        self.assertEqual(draft['persona_revision'], claim['binding']['revision'])
        self.assertEqual(draft['profile_sha256'], claim['binding']['profile_sha256'])
        self.assertEqual([(r['kind'], r['index']) for r in draft['criteria']],
                         [('success', 0), ('success', 1), ('recovery', 0)])
        self.assertTrue(all(r['status'] == 'not_run' and r['evidence_ids'] == [] for r in draft['criteria']))
        self.assertEqual(draft['steps'], [])
        self.assertEqual(draft['artifacts'], [])
        self.assertEqual(draft['outcome'], 'inconclusive')
        self.assertEqual(draft['drafting_guidance']['criteria'][1]['description'], 'Final choice visible')
        self.assertNotIn('profile', draft)
        self.assertNotIn('evidence_path', draft)

    def test_draft_cannot_be_recorded_and_does_not_change_state(self):
        claim = self.prepare()
        draft = swarm.receipt_starter(self.lib, self.run, claim)
        before = self.snapshot()
        with self.assertRaisesRegex(EngineError, 'Unknown receipt schema'):
            swarm.record(self.lib, self.run, draft)
        self.assertEqual(before, self.snapshot())
        # Merely renaming the schema also cannot record the extra draft fields.
        draft['schema_version'] = 'ux-persona-swarm-receipt.v1'
        with self.assertRaisesRegex(EngineError, 'fields must match'):
            swarm.record(self.lib, self.run, draft)
        self.assertEqual(before, self.snapshot())

    def test_expired_claim_does_not_save_expiry_or_renew(self):
        claim = self.prepare()
        with patch.object(swarm.time, 'time', return_value=claim['lease']['expires_at']):
            self.blocked(claim, 'lease_expired')
        self.assertEqual(json.loads((self.run / 'swarm-state.json').read_text())['payload']['tasks'][0]['status'], 'running')

    def test_other_expired_task_is_not_mutated(self):
        second = copy.deepcopy(self.spec['tasks'][0])
        second.update(id='T2', data_namespace='fixture2', resource_id='browser2')
        self.spec['tasks'].append(second)
        self.plan()
        with patch.object(swarm.time, 'time', return_value=1000):
            swarm.claim(self.lib, self.run, 'worker1', 'T1')
        with patch.object(swarm.time, 'time', return_value=1010):
            claim = swarm.claim(self.lib, self.run, 'worker2', 'T2')
        before = self.snapshot()
        with patch.object(swarm.time, 'time', return_value=1035):
            draft = swarm.receipt_starter(self.lib, self.run, claim)
        self.assertEqual(draft['task_id'], 'T2')
        self.assertEqual(before, self.snapshot())

    def test_stale_persona_gate_remains_required(self):
        claim = self.prepare()
        self.lib.stale = True
        self.blocked(claim, 'stale')

    def test_changed_build_remains_blocked(self):
        claim = self.prepare()
        self.build.write_text('different build')
        self.blocked(claim, 'stale_build')

    def test_claim_tamper_missing_and_wrong_attempt_rejected(self):
        claim = self.prepare()
        for field in ('task', 'binding', 'build', 'lease', 'attempt', 'operation_id'):
            candidate = copy.deepcopy(claim)
            del candidate[field]
            with self.subTest(field=field):
                self.blocked(candidate)
        for section, key, value in (('lease', 'worker_id', 'other-worker'),
                                    ('lease', 'lease_token', 'wrong-secret'),
                                    ('lease', 'expires_at', claim['lease']['expires_at'] + 500),
                                    ('task', 'goal', 'tampered goal'),
                                    ('binding', 'revision', 999)):
            candidate = copy.deepcopy(claim)
            candidate[section][key] = value
            with self.subTest(section=section, key=key):
                error = self.blocked(candidate, 'claim_mismatch')
                self.assertNotIn('wrong-secret', str(error.issue))
                self.assertNotIn(claim['lease']['lease_token'], str(error.issue))
        for attempt in (True, 2):
            candidate = copy.deepcopy(claim)
            candidate['attempt'] = attempt
            self.blocked(candidate, 'claim_mismatch')

    def test_unsuccessful_or_absent_claim_is_not_new_authority(self):
        self.prepare()
        for candidate in (None, {}, {'claimed': False}, {'claimed': 1, 'task': {'id': 'T1'}}):
            self.blocked(candidate, 'claim_mismatch')

    def test_terminal_task_does_not_reopen(self):
        claim = self.prepare()
        receipt = self.receipt(claim, outcome='inconclusive')
        swarm.record(self.lib, self.run, receipt)
        self.blocked(claim, 'lease_mismatch')

    def test_missing_run_is_not_created(self):
        claim = self.prepare()
        missing = self.root / 'absent-run'
        with self.assertRaises(EngineError):
            swarm.receipt_starter(self.lib, missing, claim)
        self.assertFalse(missing.exists())

    def test_cli_missing_library_does_not_create_it(self):
        missing = self.root / 'absent-library'
        with contextlib.redirect_stderr(io.StringIO()):
            code = main(['receipt-starter', '--library', str(missing), '--run', str(self.run),
                         '--claim', str(self.root / 'absent-claim.json')])
        self.assertEqual(code, 2)
        self.assertFalse(missing.exists())

    def test_cli_actual_library_read_only_and_private_claim(self):
        libpath = self.root / 'library'
        doc = profile_input(self.root)
        self.spec['product_id'] = doc['product_id']
        self.spec['tasks'][0].update(persona_id='PER-cautious', requirement_ids=['local-results'])
        with Library(libpath) as library:
            library.import_profiles(doc)
            swarm.create_plan(library, self.run, self.spec)
            claim = swarm.claim(library, self.run, 'worker1')
        packet = self.root / 'claim.json'
        atomic(packet, canonical(claim))
        before_run = self.snapshot()
        before_library = {p.name: p.read_bytes() for p in libpath.iterdir() if p.is_file()}
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(['receipt-starter', '--library', str(libpath), '--run', str(self.run), '--claim', str(packet)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue())['schema_version'], 'ux-persona-swarm-receipt-draft.v1')
        self.assertEqual(before_run, self.snapshot())
        self.assertEqual(before_library, {p.name: p.read_bytes() for p in libpath.iterdir() if p.is_file()})
        packet.chmod(0o644)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['receipt-starter', '--library', str(libpath), '--run', str(self.run), '--claim', str(packet)]), 2)
        self.assertEqual(before_run, self.snapshot())

    def test_cli_requires_explicit_claim(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser().parse_args(['receipt-starter', '--run', str(self.run)])


if __name__ == '__main__':
    unittest.main()
