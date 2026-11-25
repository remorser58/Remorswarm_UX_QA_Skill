#!/usr/bin/env python3
"""Check and safely apply versioned GitHub Release updates for remorsearch-ux-qa."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

DEFAULT_REPO = "remorser58/Remorswarm_UX_QA_Skill"
RELEASE_MANIFEST_SCHEMA = "remorswarm-release-manifest.v1"
BUNDLE_MANIFEST_NAME = "manifest.remorsearch.json"
PRESERVED_RUNTIME_DIRS = (
    "drivers/web/node_modules",
    ".ux-loop",
    ".ux-research",
    ".ergo-bench",
    ".ergo-runs",
)
IGNORED_WALK_DIRS = frozenset({"__pycache__", "node_modules", ".ux-loop", ".ux-research", ".ergo-bench", ".ergo-runs"})
IGNORED_WALK_FILES = frozenset({".DS_Store"})
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def default_manifest_url(repo: str) -> str:
    return f"https://github.com/{repo}/releases/latest/download/release-manifest.json"


def validate_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.username or parsed.password:
        raise ValueError("URL credentials are not permitted")
    if parsed.scheme == "https" and parsed.hostname:
        return url
    if parsed.scheme == "http" and parsed.hostname in LOOPBACK_HOSTS:
        return url
    raise ValueError(f"Unsupported or insecure update URL: {url}")


def parse_version(raw: str) -> tuple[int, int, int]:
    cleaned = raw.strip().lstrip("vV")
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", cleaned)
    if not match:
        return (0, 0, 0)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def read_local_version(skill_dir: Path) -> str:
    version_file = skill_dir / "VERSION"
    if version_file.is_file():
        text = version_file.read_text(encoding="utf-8").strip()
        if text:
            return text
    manifest_file = skill_dir / BUNDLE_MANIFEST_NAME
    if manifest_file.is_file():
        try:
            data = json.loads(manifest_file.read_text(encoding="utf-8"))
            ver = data.get("engine", {}).get("version")
            if isinstance(ver, str) and ver.strip():
                return ver.strip()
        except (OSError, ValueError):
            pass
    return "0.0.0-legacy"


def cache_path() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")).expanduser()
    return base / "remorsearch-ux-qa" / "update-check.json"


def fetch_bytes(url: str, *, timeout: int = 15, max_bytes: int = 64 * 1024 * 1024) -> bytes:
    validate_url(url)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "remorsearch-ux-qa-updater/1.1 (+https://github.com/remorser58/Remorswarm_UX_QA_Skill)"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"Downloaded asset exceeded maximum size ({max_bytes} bytes)")
    return data


def fetch_manifest(manifest_url: str, *, timeout: int = 15) -> dict:
    raw = fetch_bytes(manifest_url, timeout=timeout, max_bytes=1024 * 1024)
    manifest = json.loads(raw.decode("utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != RELEASE_MANIFEST_SCHEMA:
        raise ValueError("Unsupported release manifest schema")
    if not isinstance(manifest.get("version"), str) or not manifest["version"].strip():
        raise ValueError("Release manifest missing version")
    assets = manifest.get("assets")
    if not isinstance(assets, dict) or "remorsearch-ux-qa" not in assets:
        raise ValueError("Release manifest missing remorsearch-ux-qa asset")
    return manifest


def detect_local_modifications(skill_dir: Path) -> list[str]:
    """Compare installed files against manifest.remorsearch.json if present."""
    manifest_path = skill_dir / BUNDLE_MANIFEST_NAME
    if not manifest_path.is_file():
        return []
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = data.get("files")
    if not isinstance(expected, dict):
        return ["malformed manifest"]
    problems: list[str] = []
    seen: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(skill_dir, followlinks=False):
        parent = Path(dirpath)
        rel_dir = parent.relative_to(skill_dir)
        kept = []
        for name in sorted(dirnames):
            rel_posix = (rel_dir / name).as_posix() if rel_dir.parts else name
            if name in IGNORED_WALK_DIRS or rel_posix in PRESERVED_RUNTIME_DIRS:
                continue
            kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            if name in IGNORED_WALK_FILES:
                continue
            path = parent / name
            rel = path.relative_to(skill_dir).as_posix()
            seen.add(rel)
            if rel == BUNDLE_MANIFEST_NAME:
                continue
            receipt = expected.get(rel)
            if receipt is None:
                problems.append(f"added:{rel}")
                continue
            if path.is_symlink() or not path.is_file():
                problems.append(f"changed:{rel}")
                continue
            raw = path.read_bytes()
            if len(raw) != receipt.get("bytes") or hashlib.sha256(raw).hexdigest() != receipt.get("sha256"):
                problems.append(f"modified:{rel}")
    for missing in sorted(set(expected) - seen):
        problems.append(f"missing:{missing}")
    return problems


def safe_extract_zip(archive_path: Path, stage_root: Path, expected_top: str) -> Path:
    resolved_stage = stage_root.resolve()
    with zipfile.ZipFile(archive_path) as zipped:
        for info in zipped.infolist():
            name = info.filename
            if "\\" in name or name.startswith("/"):
                raise ValueError(f"Unsafe archive entry: {name}")
            posix = PurePosixPath(name)
            if posix.is_absolute() or ".." in posix.parts or not posix.parts:
                raise ValueError(f"Unsafe archive path traversal: {name}")
            if posix.parts[0] != expected_top:
                raise ValueError(f"Unexpected top-level archive folder: {name}")
            if stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
                raise ValueError(f"Symlink entry refused in archive: {name}")
            dest = (resolved_stage / name).resolve()
            if not dest.is_relative_to(resolved_stage):
                raise ValueError(f"Extracted path escapes stage root: {name}")
            if info.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(info, "r") as src, dest.open("wb") as out:
                    shutil.copyfileobj(src, out)
                mode = 0o755 if ((info.external_attr >> 16) & 0o111) else 0o644
                dest.chmod(mode)
    extracted = stage_root / expected_top
    if not (extracted / "SKILL.md").is_file():
        raise ValueError(f"Archive missing {expected_top}/SKILL.md")
    return extracted


def verify_extracted_bundle(extracted: Path) -> None:
    """Verify extracted skill integrity if manifest.remorsearch.json exists."""
    problems = detect_local_modifications(extracted)
    if problems:
        raise ValueError("Extracted bundle failed integrity verification: " + "; ".join(problems[:5]))


def preserve_runtime_dirs(existing_target: Path, staged_target: Path) -> list[str]:
    preserved: list[str] = []
    if not existing_target.is_dir():
        return preserved
    for rel in PRESERVED_RUNTIME_DIRS:
        src = existing_target / rel
        if src.exists():
            dst = staged_target / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True)
            preserved.append(rel)
    return preserved


def atomic_swap_directory(staged: Path, target: Path, *, keep_backup: bool) -> str | None:
    target = target.resolve()
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    backup_path: Path | None = None
    if target.exists() or target.is_symlink():
        stamp = time.strftime("%Y%m%d-%H%M%S")
        candidate = parent / f"{target.name}.backup-{stamp}"
        counter = 1
        while candidate.exists():
            candidate = parent / f"{target.name}.backup-{stamp}-{counter}"
            counter += 1
        target.rename(candidate)
        backup_path = candidate
    try:
        staged.rename(target)
    except Exception:
        if backup_path is not None and backup_path.exists() and not target.exists():
            backup_path.rename(target)
        raise
    if backup_path is not None and not keep_backup:
        shutil.rmtree(backup_path)
        return None
    return str(backup_path) if backup_path is not None else None


def resolve_asset_url(
    manifest_url: str,
    filename: str,
    *,
    repo: str | None = None,
    tag: str | None = None,
    explicit_manifest_url: bool = False,
) -> str:
    if not filename or "/" in filename or "\\" in filename or filename in {".", ".."}:
        raise ValueError(f"Unsafe asset filename: {filename}")
    if not explicit_manifest_url and repo and tag:
        return validate_url(f"https://github.com/{repo}/releases/download/{tag}/{filename}")
    return validate_url(urllib.parse.urljoin(manifest_url, filename))


def download_and_verify(url: str, expected_sha256: str, expected_bytes: int, dest: Path, *, timeout: int) -> None:
    data = fetch_bytes(url, timeout=timeout)
    if len(data) != expected_bytes:
        raise ValueError(f"Asset byte count mismatch for {dest.name}: got {len(data)}, expected {expected_bytes}")
    actual_sha = hashlib.sha256(data).hexdigest()
    if actual_sha != expected_sha256:
        raise ValueError(f"Asset SHA-256 mismatch for {dest.name}: got {actual_sha}, expected {expected_sha256}")
    dest.write_bytes(data)


def cmd_check(args: argparse.Namespace) -> int:
    skill_dir = Path(args.target).expanduser().resolve()
    current = read_local_version(skill_dir)
    manifest_url = args.manifest_url or default_manifest_url(args.repo)
    if args.cached and os.environ.get("REMORSEARCH_NO_UPDATE_CHECK") == "1":
        print(json.dumps({
            "status": "disabled",
            "current_version": current,
            "update_available": False,
        }, indent=2))
        return 0
    cpath = cache_path()
    now = time.time()
    if args.cached and cpath.is_file():
        try:
            cached = json.loads(cpath.read_text(encoding="utf-8"))
            if (
                cached.get("manifest_url") == manifest_url
                and now - float(cached.get("checked_at", 0)) < args.ttl_hours * 3600
                and isinstance(cached.get("latest_version"), str)
            ):
                available = parse_version(cached["latest_version"]) > parse_version(current)
                print(json.dumps({
                    "status": "cached",
                    "current_version": current,
                    "latest_version": cached["latest_version"],
                    "tag": cached.get("tag", f"v{cached['latest_version']}"),
                    "update_available": available,
                    "repository": args.repo,
                    "manifest_url": manifest_url,
                }, indent=2))
                return 0
        except (OSError, ValueError, TypeError):
            pass
    try:
        manifest = fetch_manifest(manifest_url, timeout=args.timeout)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        if args.cached:
            print(json.dumps({
                "status": "offline",
                "current_version": current,
                "update_available": False,
                "error": str(exc),
            }, indent=2))
            return 0
        print(json.dumps({"status": "error", "current_version": current, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    latest = manifest["version"]
    tag = manifest.get("tag") or f"v{latest}"
    available = parse_version(latest) > parse_version(current)
    result = {
        "status": "checked",
        "current_version": current,
        "latest_version": latest,
        "tag": tag,
        "update_available": available,
        "repository": manifest.get("repository", args.repo),
        "release_url": f"https://github.com/{args.repo}/releases/tag/{tag}",
        "manifest_url": manifest_url,
    }
    if args.cached:
        try:
            cpath.parent.mkdir(parents=True, exist_ok=True)
            cpath.write_text(json.dumps({
                "checked_at": now,
                "manifest_url": manifest_url,
                "latest_version": latest,
                "tag": tag,
            }, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass
    print(json.dumps(result, indent=2))
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    target = Path(args.target).expanduser().resolve()
    current = read_local_version(target)
    manifest_url = args.manifest_url or default_manifest_url(args.repo)
    try:
        manifest = fetch_manifest(manifest_url, timeout=args.timeout)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(json.dumps({"updated": False, "error": str(exc)}), file=sys.stderr)
        return 2

    latest = manifest["version"]
    tag = manifest.get("tag") or f"v{latest}"
    modifications = detect_local_modifications(target) if target.exists() else []
    if modifications and not args.force:
        print(json.dumps({
            "updated": False,
            "reason": "local_modifications_detected",
            "current_version": current,
            "latest_version": latest,
            "modified_files": modifications,
        }, indent=2))
        return 3

    if parse_version(latest) <= parse_version(current) and not args.force:
        print(json.dumps({
            "updated": False,
            "reason": "already_up_to_date",
            "current_version": current,
            "latest_version": latest,
            "tag": tag,
        }, indent=2))
        return 0

    if args.dry_run:
        print(json.dumps({
            "updated": False,
            "dry_run": True,
            "from_version": current,
            "to_version": latest,
            "tag": tag,
            "target": str(target),
            "with_design_system": args.with_design_system,
        }, indent=2))
        return 0

    primary_asset = manifest["assets"]["remorsearch-ux-qa"]
    design_asset = manifest["assets"].get("react-design-system") if args.with_design_system else None
    if args.with_design_system and not design_asset:
        print(json.dumps({"updated": False, "error": "react-design-system asset missing from manifest"}), file=sys.stderr)
        return 2

    explicit_manifest = bool(args.manifest_url)
    target.parent.mkdir(parents=True, exist_ok=True)
    stage_dir = Path(tempfile.mkdtemp(prefix=".remorsearch-update-", dir=target.parent))
    try:
        zip_path = stage_dir / primary_asset["filename"]
        download_and_verify(
            resolve_asset_url(
                manifest_url,
                primary_asset["filename"],
                repo=args.repo,
                tag=tag,
                explicit_manifest_url=explicit_manifest,
            ),
            primary_asset["sha256"],
            int(primary_asset["bytes"]),
            zip_path,
            timeout=args.timeout,
        )
        extract_dir = stage_dir / "extracted"
        extract_dir.mkdir()
        staged_skill = safe_extract_zip(zip_path, extract_dir, "remorsearch-ux-qa")
        verify_extracted_bundle(staged_skill)
        preserved = preserve_runtime_dirs(target, staged_skill)
        backup_path = atomic_swap_directory(staged_skill, target, keep_backup=not args.no_backup)

        design_updated = False
        design_backup = None
        if design_asset is not None:
            ds_zip = stage_dir / design_asset["filename"]
            download_and_verify(
                resolve_asset_url(
                    manifest_url,
                    design_asset["filename"],
                    repo=args.repo,
                    tag=tag,
                    explicit_manifest_url=explicit_manifest,
                ),
                design_asset["sha256"],
                int(design_asset["bytes"]),
                ds_zip,
                timeout=args.timeout,
            )
            ds_extract = stage_dir / "extracted-ds"
            ds_extract.mkdir()
            staged_ds = safe_extract_zip(ds_zip, ds_extract, "react-design-system")
            ds_target = target.parent / "react-design-system"
            design_backup = atomic_swap_directory(staged_ds, ds_target, keep_backup=not args.no_backup)
            design_updated = True
    except (OSError, ValueError, urllib.error.URLError, zipfile.BadZipFile) as exc:
        print(json.dumps({"updated": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    finally:
        if stage_dir.exists():
            shutil.rmtree(stage_dir, ignore_errors=True)

    print(json.dumps({
        "updated": True,
        "from_version": current,
        "to_version": latest,
        "tag": tag,
        "target": str(target),
        "backup_path": backup_path,
        "preserved_runtime_dirs": preserved,
        "design_system_updated": design_updated,
        "design_system_backup_path": design_backup,
    }, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    default_target = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="subcommand", required=True)

    for name in ("check", "apply"):
        p = sub.add_parser(name)
        p.add_argument("--target", type=Path, default=default_target, help="Installed remorsearch-ux-qa folder")
        p.add_argument("--repo", default=DEFAULT_REPO, help="GitHub OWNER/REPO")
        p.add_argument("--manifest-url", help="Override release-manifest.json URL (HTTPS or loopback HTTP)")
        p.add_argument("--timeout", type=int, default=15 if name == "check" else 30)
        if name == "check":
            p.add_argument("--cached", action="store_true", help="Use TTL cache and never fail when offline")
            p.add_argument("--ttl-hours", type=float, default=24.0)
        else:
            p.add_argument("--with-design-system", action="store_true", help="Also install/update sibling react-design-system")
            p.add_argument("--force", action="store_true", help="Overwrite local edits or reinstall same version")
            p.add_argument("--dry-run", action="store_true", help="Preview update without modifying files")
            p.add_argument("--no-backup", action="store_true", help="Remove timestamped backup after verified swap")
    return parser


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 10):
        print("Python 3.10 or newer is required", file=sys.stderr)
        return 2
    args = build_parser().parse_args(argv)
    if args.subcommand == "check":
        return cmd_check(args)
    return cmd_apply(args)


if __name__ == "__main__":
    raise SystemExit(main())
