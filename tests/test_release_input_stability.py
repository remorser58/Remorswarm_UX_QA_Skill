"""Source stability covers repository checks, not only the installed payload."""
import hashlib
import contextlib
import io
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('release_stability_checker', ROOT / 'scripts/check_release.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class ReleaseInputStabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'source'
        self.root.mkdir()
        self.write('README.md', 'English source')
        self.write('README.ko.md', 'Korean source')
        self.write('tests/test_fixture.py', 'fixture input')
        self.write('skills/remorsearch-ux-qa/SKILL.md', 'skill input')

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def snapshot(self):
        return checker.snapshot_validation_inputs(self.root)

    def test_unchanged_without_git_and_relative_digests_only(self):
        before = self.snapshot()
        self.assertFalse((self.root / '.git').exists())
        self.assertEqual(before['errors'], [])
        self.assertEqual(before['files']['README.md'], hashlib.sha256(b'English source').hexdigest())
        self.assertTrue(checker.validation_inputs_check(before, self.snapshot())['passed'])
        self.assertNotIn(str(self.root), json.dumps(before))
        self.assertNotIn('English source', json.dumps(before))

    def test_readme_modified_after_tests_is_not_ready(self):
        before = self.snapshot()
        self.write('README.md', 'Added untested paragraph')
        check = checker.validation_inputs_check(before, self.snapshot())
        self.assertFalse(check['passed'])
        self.assertEqual(check['changed'], ['README.md'])
        self.assertIn('rerun all checks', check['reason'])
        self.assertFalse(all(row['passed'] for row in [{'passed': True}, check]))

    def test_readme_creation_and_deletion_detected(self):
        (self.root / 'README.ko.md').unlink()
        before = self.snapshot()
        self.write('README.ko.md', 'New translation')
        after = self.snapshot()
        self.assertEqual(checker.validation_inputs_check(before, after)['added'], ['README.ko.md'])
        (self.root / 'README.md').unlink()
        self.assertEqual(checker.validation_inputs_check(after, self.snapshot())['removed'], ['README.md'])

    def test_scripts_tests_skill_and_fixture_changes_detected(self):
        for path in ('scripts/helper.py', 'tests/new_test.py', 'examples/fixture.json',
                     'benchmarks/local/app.js', 'docs/release.md',
                     'integrations/insane-search/scripts/remorsearch.py',
                     'skills/remorsearch-ux-qa/drivers/web/fixture.html'):
            before = self.snapshot()
            self.write(path, 'new checked input')
            with self.subTest(path=path):
                self.assertEqual(checker.validation_inputs_check(before, self.snapshot())['added'], [path])

    def test_generated_and_private_inputs_ignored(self):
        before = self.snapshot()
        for path in ('dist/result.json', '.git/config', '.ux-loop/run.json',
                     'tests/__pycache__/test.pyc', 'scripts/dist/report.json',
                     'skills/remorsearch-ux-qa/drivers/web/node_modules/package/index.js',
                     'docs/.private/note.md', 'tests/secrets/private.json',
                     'scripts/credentials.json', 'scripts/token.key', 'scripts/.env',
                     'personal/unrelated.txt'):
            self.write(path, 'must not be hashed')
        after = self.snapshot()
        self.assertEqual(before, after)

    @unittest.skipUnless(hasattr(__import__('os'), 'symlink'), 'symlinks unavailable')
    def test_external_file_link_rejected_without_reading_target(self):
        outside = Path(self.temp.name) / 'private-value.txt'
        outside.write_text('outside secret')
        (self.root / 'tests/external.txt').symlink_to(outside)
        result = self.snapshot()
        self.assertNotIn('tests/external.txt', result['files'])
        self.assertEqual(result['errors'], [{'path': 'tests/external.txt', 'reason': 'Symlink input is not followed'}])
        self.assertNotIn(str(outside), json.dumps(result))
        self.assertNotIn('outside secret', json.dumps(result))
        self.assertFalse(checker.validation_inputs_check(result, result)['passed'])

    @unittest.skipUnless(hasattr(__import__('os'), 'symlink'), 'symlinks unavailable')
    def test_directory_and_parent_links_not_followed(self):
        outside = Path(self.temp.name) / 'private-directory'
        outside.mkdir()
        (outside / 'secret.txt').write_text('outside secret')
        (self.root / 'docs').symlink_to(outside, target_is_directory=True)
        (self.root / 'integrations').symlink_to(outside, target_is_directory=True)
        result = self.snapshot()
        self.assertTrue(any(row['path'] == 'docs' for row in result['errors']))
        self.assertTrue(any(row['path'] == 'integrations/insane-search' for row in result['errors']))
        self.assertFalse(any('secret.txt' in path for path in result['files']))
        self.assertFalse(checker.validation_inputs_check(result, result)['passed'])

    def test_main_snapshots_before_checks_and_records_late_change(self):
        output = self.root / 'dist/check'
        calls = []
        def fake_run(command, **kwargs):
            calls.append(command)
            if len(calls) == 1:
                self.write('README.md', 'Changed while unit tests run')
            return SimpleNamespace(returncode=1)
        with patch.object(checker, 'ROOT', self.root), patch.object(checker.subprocess, 'run', fake_run), contextlib.redirect_stdout(io.StringIO()):
            code = checker.main(['--output', str(output), '--skip-web'])
        report = json.loads((output / 'validation.json').read_text())
        stable = next(row for row in report['checks'] if row['name'] == 'validation-inputs-stable')
        self.assertEqual(code, 1)
        self.assertFalse(report['ready'])
        self.assertEqual(stable['changed'], ['README.md'])
        before = report['validation_inputs']['before']['files']['README.md']
        after = report['validation_inputs']['after']['files']['README.md']
        self.assertNotEqual(before, after)
        self.assertNotIn(str(self.root), json.dumps(report['validation_inputs']))

    def test_exact_output_exclusion_keeps_sibling_changes_visible(self):
        output = self.root / 'docs/my-check'
        output.mkdir(parents=True)
        before = checker.snapshot_validation_inputs(self.root, exclude_output=output)
        self.write('docs/my-check/logs/unit.log', 'generated log')
        self.write('docs/my-check/extracted/source.py', 'generated extraction')
        after = checker.snapshot_validation_inputs(self.root, exclude_output=output)
        self.assertTrue(checker.validation_inputs_check(before, after)['passed'])
        self.assertEqual(after['excluded_output'], 'docs/my-check')
        self.write('docs/unrelated.md', 'new source')
        self.write('README.md', 'changed source')
        self.write('docs/my-check-sibling/input.md', 'not excluded')
        changed = checker.validation_inputs_check(after, checker.snapshot_validation_inputs(self.root, exclude_output=output))
        self.assertFalse(changed['passed'])
        self.assertEqual(changed['changed'], ['README.md'])
        self.assertEqual(changed['added'], ['docs/my-check-sibling/input.md', 'docs/unrelated.md'])

    def test_main_allowed_output_inside_docs_does_not_fingerprint_itself(self):
        output = self.root / 'docs/my-check'
        def fake_run(command, **kwargs):
            self.write('docs/my-check/generated.txt', 'new generated output')
            return SimpleNamespace(returncode=1)
        with patch.object(checker, 'ROOT', self.root), patch.object(checker.subprocess, 'run', fake_run), contextlib.redirect_stdout(io.StringIO()):
            checker.main(['--output', str(output), '--skip-web'])
        report = json.loads((output / 'validation.json').read_text())
        stable = next(row for row in report['checks'] if row['name'] == 'validation-inputs-stable')
        self.assertTrue(stable['passed'])
        self.assertEqual(report['validation_inputs']['after']['excluded_output'], 'docs/my-check')
        self.assertNotIn(str(self.root), json.dumps(report['validation_inputs']))
        self.assertFalse(report['ready'])  # Other failed checks remain failures.

    def test_oversized_source_fails_closed_without_hashing(self):
        path = self.root / 'tests/oversized.bin'
        with path.open('wb') as stream:
            stream.truncate(64 * 1024 * 1024 + 1)
        result = self.snapshot()
        self.assertNotIn('tests/oversized.bin', result['files'])
        self.assertEqual(result['errors'], [{'path': 'tests/oversized.bin', 'reason': 'Source snapshot size limit exceeded'}])
        self.assertFalse(checker.validation_inputs_check(result, result)['passed'])

    def test_external_output_path_not_disclosed_or_broadly_excluded(self):
        outside = Path(self.temp.name) / 'outside-private-output'
        result = checker.snapshot_validation_inputs(self.root, exclude_output=outside)
        self.assertIsNone(result['excluded_output'])
        self.assertIn('README.md', result['files'])
        self.assertNotIn(str(outside), json.dumps(result))

    def test_missing_source_root_reports_safe_failure(self):
        result = checker.snapshot_validation_inputs(self.root / 'missing')
        self.assertEqual(result['files'], {})
        self.assertEqual(result['errors'][0]['path'], '.')
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertFalse(checker.validation_inputs_check(result, result)['passed'])


if __name__ == '__main__':
    unittest.main()
