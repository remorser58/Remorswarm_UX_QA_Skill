// Opt-in, local preflight: Python owns canonical JSON and profile/model resolution.
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { UsageError, sha256 } from './util.mjs';

export function bindingDeviceMatches(binding, device) {
  const pinned = binding?.device;
  return !!pinned && !!device && ['id', 'orientation', 'dpr', 'input', 'form_factor'].every(k => pinned[k] === device[k])
    && Array.isArray(pinned.viewport_css) && pinned.viewport_css.length === 2
    && pinned.viewport_css.every((value, axis) => value === device.viewport_css?.[axis]);
}

export function prepareProfileBinding(bytes, profile, device) {
  const script = fileURLToPath(new URL('../../scripts/ergo_qa.py', import.meta.url));
  const result = spawnSync('python3', ['-I', '-B', script, 'profile-binding'],
    { input: bytes, encoding: 'utf8', timeout: 10000, maxBuffer: 65536 });
  if (result.error || result.status !== 0) {
    throw new UsageError('--bind-profile requires a valid full profile and working package Python 3.10+ preflight');
  }
  let output;
  try { output = JSON.parse(result.stdout); } catch { throw new UsageError('invalid profile binding preflight output'); }
  const binding = output?.binding;
  const hashes = ['profile_file_sha256', 'profile_sha256', 'condition_sha256', 'model_revision_sha256'];
  if (output?.profile_id !== profile.profile_id || binding?.schema_version !== 'ergo-profile-binding.v1'
      || !hashes.every(k => typeof binding[k] === 'string' && /^[0-9a-f]{64}$/.test(binding[k]))
      || binding.profile_file_sha256 !== sha256(bytes)
      || !bindingDeviceMatches(binding, device)) {
    throw new UsageError('--bind-profile profile bytes or catalog device/orientation do not match recorder configuration');
  }
  return binding;
}
