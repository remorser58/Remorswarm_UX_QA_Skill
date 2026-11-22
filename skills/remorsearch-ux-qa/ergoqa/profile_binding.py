"""Content consistency for authored ergonomic inputs, not measurement or authentication."""
from __future__ import annotations

import re
from pathlib import Path

from uxresearch.canonical import byte_digest, digest

from .devices import get_device, rotate
from .hf import reach
from .profiles import profile_index, resolve_thumb_input

BINDING_SCHEMA = "ergo-profile-binding.v1"
HASH_FIELDS = ("profile_file_sha256", "profile_sha256", "condition_sha256", "model_revision_sha256")
_SHA = re.compile(r"[0-9a-f]{64}")
_REACH_FILES = ("profile_binding.py", "profiles.py", "params.py", "devices.py", "analyze.py", "checks.py",
                "hf/pointing.py", "hf/reach.py")


def validate_binding(binding, device) -> bool:
    """A supplied binding is either well formed for this run configuration or invalid."""
    keys = {"schema_version", "device", "model_id", *HASH_FIELDS}
    if (not isinstance(binding, dict) or set(binding) != keys or binding["schema_version"] != BINDING_SCHEMA
            or not isinstance(binding["model_id"], str)
            or re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", binding["model_id"]) is None
            or not all(isinstance(binding[key], str) and _SHA.fullmatch(binding[key]) for key in HASH_FIELDS)):
        return False
    pinned = binding["device"]
    return (isinstance(device, dict) and isinstance(pinned, dict)
            and set(pinned) == {"id", "orientation", "viewport_css", "dpr", "input", "form_factor"}
            and all(isinstance(pinned[key], str) and pinned[key] for key in ("id", "orientation", "input", "form_factor"))
            and type(pinned["dpr"]) in (int, float) and 0 < pinned["dpr"] <= 10
            and isinstance(pinned["viewport_css"], list) and len(pinned["viewport_css"]) == 2
            and all(type(n) in (int, float) and 0 < n <= 10000 for n in pinned["viewport_css"])
            and all(pinned[key] == device.get(key) for key in pinned))


def model_revision() -> str:
    root = Path(__file__).parent
    return digest({"model_id": reach.MODEL_ID,
                   "files": {name: byte_digest((root / name).read_bytes()) for name in _REACH_FILES}})


def condition(profile):
    attrs = profile["attributes"]
    device = rotate(get_device(attrs["device_id"]), attrs["orientation"])
    emulation = {key: getattr(device, key) for key in ("id", "orientation", "dpr", "input", "form_factor")}
    emulation["viewport_css"] = list(device.viewport_css)
    # Values are deliberately not copied into the run. This digest binds the
    # resolved authored/synthetic input and catalog data, not measured grip/size.
    identity = digest({"grip": attrs["grip"], "thumb_input": resolve_thumb_input(profile),
                       "device": device.to_dict()})
    return emulation, identity


def prepare(raw: bytes):
    from .snapshot import parse_json, validate_profile

    profile = parse_json(raw.decode("utf-8"))
    errors = validate_profile(profile)
    if errors:
        raise ValueError("invalid recording profile: " + "; ".join(errors))
    profile_index([profile])
    device, condition_sha = condition(profile)
    return {"profile_id": profile["profile_id"], "binding": {
        "schema_version": BINDING_SCHEMA, "device": device, "model_id": reach.MODEL_ID,
        "profile_file_sha256": byte_digest(raw), "profile_sha256": digest(profile),
        "condition_sha256": condition_sha, "model_revision_sha256": model_revision(),
    }}


def match_status(binding, profile) -> str:
    if binding is None:
        return "legacy_unverified"
    if binding["profile_sha256"] != digest(profile):
        return "profile_digest_mismatch"
    if binding["model_id"] != reach.MODEL_ID or binding["model_revision_sha256"] != model_revision():
        return "model_revision_mismatch"
    device, condition_sha = condition(profile)
    if binding["condition_sha256"] != condition_sha or binding["device"] != device:
        return "condition_mismatch"
    return "matched"
