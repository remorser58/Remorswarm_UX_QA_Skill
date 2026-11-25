#!/usr/bin/env python3
"""Build versioned deterministic release archives and manifest for GitHub Releases."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

import build_insane_search_bundle as bundle_builder
import release_files

REPO = Path(__file__).resolve().parents[1]
DESIGN_SKILL = REPO / "skills" / "react-design-system"
DEFAULT_REPO = "remorser58/Remorswarm_UX_QA_Skill"
SCHEMA_VERSION = "remorswarm-release-manifest.v1"
DESIGN_BUNDLE_SCHEMA = "react-design-system-bundle.v1"
DESIGN_MANIFEST = "manifest.react-design-system.json"
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
TAG_RE = re.compile(r"^v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _design_member_mode(relative: str) -> int:
    if relative.startswith("scripts/") and relative.endswith((".py", ".sh")):
        return 0o755
    return 0o644


def build_skill_zip(
    source_dir: Path,
    top_name: str,
    archive_path: Path,
    *,
    version: str,
    repository: str,
) -> tuple[int, str]:
    """Create a deterministic stored ZIP for a standalone skill folder with manifest."""
    if source_dir.is_symlink() or not source_dir.is_dir():
        raise ValueError(f"Skill directory missing: {source_dir}")
    if not (source_dir / "SKILL.md").is_file():
        raise ValueError(f"Skill entrypoint missing: {source_dir / 'SKILL.md'}")
    entries: list[tuple[str, bytes, int]] = []
    file_inventory: dict[str, dict[str, object]] = {}
    pruned = release_files.PRUNED_DIR_NAMES | {".git", ".hg", ".svn"}
    for dirpath, dirnames, filenames in os.walk(source_dir, followlinks=False):
        parent = Path(dirpath)
        dirnames[:] = sorted(name for name in dirnames if name not in pruned)
        for name in dirnames:
            if (parent / name).is_symlink():
                raise ValueError(f"Refusing symlink directory in release asset: {parent / name}")
        for name in sorted(filenames):
            if name in release_files.PRUNED_FILE_NAMES:
                continue
            path = parent / name
            st = path.lstat()
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
                raise ValueError(f"Refusing non-regular file in release asset: {path}")
            relative = path.relative_to(source_dir).as_posix()
            if relative == DESIGN_MANIFEST:
                raise ValueError(f"Reserved manifest path exists in source tree: {path}")
            if Path(relative).name == "SKILL.md" and relative != "SKILL.md":
                raise ValueError(f"Nested SKILL.md refused in release asset: {relative}")
            problems = release_files.denylist_problems(relative)
            if problems:
                raise ValueError("; ".join(problems))
            raw = path.read_bytes()
            entries.append((f"{top_name}/{relative}", raw, _design_member_mode(relative)))
            file_inventory[relative] = {
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }

    inv_raw = json.dumps(
        file_inventory, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    payload_sha256 = hashlib.sha256(inv_raw).hexdigest()
    bundle_manifest = {
        "schema_version": DESIGN_BUNDLE_SCHEMA,
        "skill": top_name,
        "version": version,
        "repository": repository,
        "payload_sha256": payload_sha256,
        "files": file_inventory,
    }
    manifest_bytes = (
        json.dumps(bundle_manifest, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    entries.append((f"{top_name}/{DESIGN_MANIFEST}", manifest_bytes, 0o644))
    entries.sort(key=lambda item: item[0])

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as target:
        for member_name, raw, mode in entries:
            info = zipfile.ZipInfo(member_name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_STORED
            target.writestr(info, raw)
    return len(entries), payload_sha256


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO, capture_output=True, text=True, check=True, timeout=5,
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def build_release(
    output: Path,
    *,
    tag: str | None = None,
    commit: str | None = None,
    published_at: str | None = None,
    repository: str = DEFAULT_REPO,
) -> dict:
    if not REPO_RE.fullmatch(repository):
        raise ValueError(f"Invalid GitHub repository slug: {repository!r}")
    output = output.expanduser().absolute()
    if output.exists() or output.is_symlink():
        raise ValueError(f"--output must be a new directory: {output}")
    version = (REPO / "VERSION").read_text(encoding="utf-8").strip()
    resolved_tag = tag or f"v{version}"
    if not TAG_RE.fullmatch(resolved_tag):
        raise ValueError(f"Invalid release tag: {resolved_tag!r}")
    if resolved_tag != f"v{version}":
        raise ValueError(f"Release tag {resolved_tag!r} must match VERSION v{version}")
    resolved_commit = commit if commit is not None else git_commit()
    resolved_time = published_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".remorswarm-release-", dir=output.parent))
    try:
        bundle_dir = temporary / "bundle"
        bundle_summary = bundle_builder.build(None, bundle_dir)

        primary_zip = temporary / "remorsearch-ux-qa.zip"
        shutil.copyfile(bundle_dir / bundle_builder.ARCHIVE_NAME, primary_zip)
        primary_sha, primary_bytes = sha256_file(primary_zip)

        design_zip = temporary / "react-design-system.zip"
        design_count, design_payload_sha = build_skill_zip(
            DESIGN_SKILL,
            "react-design-system",
            design_zip,
            version=version,
            repository=repository,
        )
        design_sha, design_bytes = sha256_file(design_zip)

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "repository": repository,
            "version": version,
            "tag": resolved_tag,
            "commit": resolved_commit,
            "published_at": resolved_time,
            "min_python": "3.10",
            "assets": {
                "remorsearch-ux-qa": {
                    "filename": primary_zip.name,
                    "sha256": primary_sha,
                    "bytes": primary_bytes,
                    "file_count": bundle_summary["file_count"],
                    "payload_sha256": bundle_summary["payload_sha256"],
                    "top_directory": "remorsearch-ux-qa",
                },
                "react-design-system": {
                    "filename": design_zip.name,
                    "sha256": design_sha,
                    "bytes": design_bytes,
                    "file_count": design_count,
                    "payload_sha256": design_payload_sha,
                    "top_directory": "react-design-system",
                },
            },
        }
        manifest_path = temporary / "release-manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        sums_lines = []
        for path in (primary_zip, design_zip, manifest_path):
            digest, _ = sha256_file(path)
            sums_lines.append(f"{digest}  {path.name}\n")
        (temporary / "SHA256SUMS.txt").write_text("".join(sums_lines), encoding="utf-8")

        if output.exists() or output.is_symlink():
            raise ValueError(f"--output appeared during build: {output}")
        temporary.rename(output)
        return manifest
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New directory for release artifacts")
    parser.add_argument("--tag", help="Release tag name (defaults to v<VERSION>)")
    parser.add_argument("--commit", help="Commit SHA recorded in release-manifest.json")
    parser.add_argument("--published-at", help="ISO-8601 UTC timestamp")
    parser.add_argument("--repository", default=DEFAULT_REPO)
    args = parser.parse_args(argv)
    if sys.version_info < (3, 10):
        parser.error("Python 3.10 or later is required")
    manifest = build_release(
        args.output,
        tag=args.tag,
        commit=args.commit,
        published_at=args.published_at,
        repository=args.repository,
    )
    print(json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
