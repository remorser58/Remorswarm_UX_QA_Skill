"""Validate authored links to the shipped NVIDIA pack without supplying reach inputs."""
from __future__ import annotations

from typing import Any

from uxpersonas.product_controls import seed_catalog
from uxresearch.canonical import digest, normalize

from .profiles import profile_index
from .snapshot import validate_profile


SCHEMA = "ergo-seed-bindings.v1"
RECEIPT_SCHEMA = "ergo-seed-binding-receipt.v1"
DATASET = "nvidia/Nemotron-Personas-Korea"
REVISION = "ada0f5b53a38bb5a30cce09358adde883c1ab63a"
# Same canonical JSON digest domain as seed-input, not the saved file or API response bytes.
PACK_SHA256 = "677aba0ac8324b2006aad33a079b37c054a1fbabe905b83305917e6d00df31c1"


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"{field} must be a nonempty identifier")
    return value


def bind(doc: Any, profiles: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a stable receipt, not a profile set or approval to evaluate reach."""
    doc = normalize(doc)
    expected = {
        "schema_version": SCHEMA,
        "dataset": DATASET,
        "dataset_revision": REVISION,
        "seed_pack_sha256": PACK_SHA256,
    }
    if not isinstance(doc, dict) or set(doc) != set(expected) | {"bindings"}:
        raise ValueError("expected schema_version, dataset, dataset_revision, seed_pack_sha256 and bindings")
    for key, value in expected.items():
        if doc[key] != value:
            raise ValueError(f"{key} does not match the supported canonical seed pack")

    pack = seed_catalog()
    if digest(pack) != PACK_SHA256:
        raise ValueError("installed Korean seed pack integrity mismatch")
    seeds = {row["id"] for row in pack["records"]}
    rows = doc["bindings"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= len(seeds):
        raise ValueError(f"expected 1..{len(seeds)} explicitly authored bindings")

    indexed = profile_index(normalize(profiles))
    used_seeds: set[str] = set()
    used_profiles: set[str] = set()
    bindings = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"seed_id", "profile_id"}:
            raise ValueError("binding fields must be exactly seed_id and profile_id")
        seed_id = _identifier(row["seed_id"], "seed_id")
        profile_id = _identifier(row["profile_id"], "profile_id")
        if seed_id not in seeds:
            raise ValueError("unknown seed_id in binding")
        if profile_id not in indexed:
            raise ValueError("unknown profile_id in binding")
        if seed_id in used_seeds:
            raise ValueError("duplicate seed_id in bindings")
        if profile_id in used_profiles:
            raise ValueError("duplicate profile_id in bindings")

        profile = indexed[profile_id]
        errors = validate_profile(profile)
        if errors:
            raise ValueError("invalid bound ergo-profile.v1: " + "; ".join(errors))
        ref = profile.get("persona_ref")
        if ref is not None and ref != {"dataset": DATASET, "revision": REVISION, "record_id": seed_id}:
            raise ValueError("conflicting persona_ref on bound profile")

        used_seeds.add(seed_id)
        used_profiles.add(profile_id)
        bindings.append({"seed_id": seed_id, "profile_id": profile_id, "profile_sha256": digest(profile)})

    return {
        **expected,
        "schema_version": RECEIPT_SCHEMA,
        "binding_basis": "authored",
        "reach_input_status": "unknown",
        "analysis_performed": False,
        "bindings": sorted(bindings, key=lambda row: row["seed_id"]),
    }
