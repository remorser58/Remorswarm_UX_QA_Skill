#!/usr/bin/env python3
"""Check and safely apply versioned GitHub Release updates for remorsearch-ux-qa."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
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
PRIMARY_BUNDLE_SCHEMA = "remorsearch-ux-qa-bundle.v1"
DESIGN_BUNDLE_SCHEMA = "react-design-system-bundle.v1"
BUNDLE_MANIFEST_NAME = "manifest.remorsearch.json"
DESIGN_MANIFEST_NAME = "manifest.react-design-system.json"
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

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
TAG_RE = re.compile(r"^v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
FILENAME_RE = re.compile(r"^[A-Za-z0-9._-]+\.zip$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SEMVER_RE = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:-(?P<pre>[0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$"
)

MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_EXTRACTED_FILE_BYTES = 32 * 1024 * 1024
MAX_EXTRACTED_TOTAL_BYTES = 128 * 1024 * 1024
MAX_EXTRACTED_ENTRIES = 2000


def validate_repo(repo: str) -> str:
    if not isinstance(repo, str) or not REPO_RE.fullmatch(repo):
        raise ValueError(f"Invalid GitHub repository slug: {repo!r}")
    return repo


def validate_tag(tag: str) -> str:
    if not isinstance(tag, str) or not TAG_RE.fullmatch(tag):
        raise ValueError(f"Invalid release tag: {tag!r}")
    return tag


def validate_filename(filename: str) -> str:
    if not isinstance(filename, str) or not FILENAME_RE.fullmatch(filename):
        raise ValueError(f"Unsafe asset filename: {filename!r}")
    return filename


def validate_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.username or parsed.password:
        raise ValueError("URL credentials are not permitted")
    if parsed.scheme == "https" and parsed.hostname:
        return url
    if parsed.scheme == "http" and parsed.hostname in LOOPBACK_HOSTS:
        return url
    raise ValueError(f"Unsupported or insecure update URL: {url}")


class _ValidatedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Enforce HTTPS/loopback URL checks across every HTTP redirect hop."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        absolute = urllib.parse.urljoin(req.full_url, newurl)
        validate_url(absolute)
        return super().redirect_request(req, fp, code, msg, headers, absolute)


def default_manifest_url(repo: str, version: str | None = None) -> str:
    clean_repo = validate_repo(repo)
    if version:
        clean_tag = validate_tag(version)
        return f"https://github.com/{clean_repo}/releases/download/{clean_tag}/release-manifest.json"
    return f"https://github.com/{clean_repo}/releases/latest/download/release-manifest.json"


def parse_version(raw: str) -> tuple[tuple[int, int, int], int, tuple[tuple[int, int | str], ...]]:
    cleaned = raw.strip().lstrip("vV")
    if cleaned == "0.0.0-legacy":
        return ((0, 0, 0), 0, ((0, 0),))
    match = SEMVER_RE.fullmatch(cleaned)
    if not match:
        raise ValueError(f"Invalid semantic version: {raw!r}")
    core = (int(match.group("major")), int(match.group("minor")), int(match.group("patch")))
    pre_raw = match.group("pre")
    if not pre_raw:
        return (core, 1, ())
    pre_parts: list[tuple[int, int | str]] = []
    for part in pre_raw.split("."):
        if part.isdigit():
            pre_parts.append((0, int(part)))
        else:
            pre_parts.append((1, part))
    return (core, 0, tuple(pre_parts))


def read_local_version(skill_dir: Path, *, manifest_name: str = BUNDLE_MANIFEST_NAME) -> str:
    version_file = skill_dir / "VERSION"
    if version_file.is_file() and not version_file.is_symlink():
        text = version_file.read_text(encoding="utf-8").strip()
        if text:
            try:
                parse_version(text)
                return text
            except ValueError:
                pass
    manifest_file = skill_dir / manifest_name
    if manifest_file.is_file() and not manifest_file.is_symlink():
        try:
            data = json.loads(manifest_file.read_text(encoding="utf-8"))
            ver = data.get("version") or (data.get("engine") or {}).get("version")
            if isinstance(ver, str) and ver.strip():
                parse_version(ver.strip())
                return ver.strip()
        except (OSError, UnicodeDecodeError, ValueError):
            pass
    return "0.0.0-legacy"


def _local_agent_version() -> str:
    ver_file = Path(__file__).resolve().parents[1] / "VERSION"
    if ver_file.is_file() and not ver_file.is_symlink():
        text = ver_file.read_text(encoding="utf-8").strip()
        if text:
            return text
    return "1.1.1"


def cache_path() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")).expanduser()
    return base / "remorsearch-ux-qa" / "update-check.json"


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    out: dict = {}
    for key, val in pairs:
        if key in out:
            raise ValueError(f"Duplicate JSON key: {key}")
        out[key] = val
    return out


def fetch_bytes(url: str, *, timeout: int = 15, max_bytes: int = MAX_DOWNLOAD_BYTES) -> bytes:
    validate_url(url)
    opener = urllib.request.build_opener(_ValidatedRedirectHandler)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"remorsearch-ux-qa-updater/{_local_agent_version()} (+https://github.com/remorser58/Remorswarm_UX_QA_Skill)"
        },
    )
    with opener.open(request, timeout=timeout) as response:
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"Downloaded asset exceeded maximum size ({max_bytes} bytes)")
    return data


def validate_manifest_data(manifest: object) -> dict:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != RELEASE_MANIFEST_SCHEMA:
        raise ValueError("Unsupported release manifest schema")
    version = manifest.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("Release manifest missing version")
    parse_version(version)
    tag = manifest.get("tag")
    if tag is not None:
        validate_tag(tag)
    assets = manifest.get("assets")
    if not isinstance(assets, dict) or "remorsearch-ux-qa" not in assets:
        raise ValueError("Release manifest missing remorsearch-ux-qa asset")
    for asset_name, entry in assets.items():
        if not isinstance(entry, dict):
            raise ValueError(f"Malformed asset entry: {asset_name}")
        validate_filename(entry.get("filename"))
        sha = entry.get("sha256")
        if not isinstance(sha, str) or not SHA256_RE.fullmatch(sha):
            raise ValueError(f"Invalid asset sha256 for {asset_name}")
        size = entry.get("bytes")
        if type(size) is not int or size <= 0 or size > MAX_DOWNLOAD_BYTES:
            raise ValueError(f"Invalid asset size for {asset_name}")
        top_dir = entry.get("top_directory")
        if not isinstance(top_dir, str) or top_dir != asset_name:
            raise ValueError(f"Invalid top_directory for {asset_name}")
    return manifest


def fetch_manifest(manifest_url: str, *, timeout: int = 15) -> dict:
    raw = fetch_bytes(manifest_url, timeout=timeout, max_bytes=MAX_MANIFEST_BYTES)
    manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    return validate_manifest_data(manifest)


def load_local_manifest(manifest_path: Path) -> dict:
    resolved = manifest_path.expanduser().resolve(strict=True)
    raw = resolved.read_bytes()
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("Local manifest exceeds size limit")
    manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    return validate_manifest_data(manifest)


def _payload_digest(files: dict) -> str:
    raw = json.dumps(files, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def detect_local_modifications(
    skill_dir: Path,
    *,
    manifest_name: str = BUNDLE_MANIFEST_NAME,
    preserved_dirs: tuple[str, ...] = PRESERVED_RUNTIME_DIRS,
) -> list[str]:
    """Compare installed files against the bundle manifest if present."""
    manifest_path = skill_dir / manifest_name
    if manifest_path.is_symlink():
        return [f"symlink:{manifest_name}"]
    if not manifest_path.is_file():
        return []
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeDecodeError, ValueError):
        return [f"malformed:{manifest_name}"]
    expected = data.get("files") if isinstance(data, dict) else None
    if not isinstance(expected, dict):
        return [f"malformed:{manifest_name}"]
    problems: list[str] = []
    seen: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(skill_dir, followlinks=False):
        parent = Path(dirpath)
        rel_dir = parent.relative_to(skill_dir)
        kept = []
        for name in sorted(dirnames):
            rel_posix = (rel_dir / name).as_posix() if rel_dir.parts else name
            if (parent / name).is_symlink():
                problems.append(f"symlink_dir:{rel_posix}")
                continue
            if name in IGNORED_WALK_DIRS or rel_posix in preserved_dirs:
                continue
            kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            if name in IGNORED_WALK_FILES:
                continue
            path = parent / name
            rel = path.relative_to(skill_dir).as_posix()
            seen.add(rel)
            if rel == manifest_name:
                continue
            receipt = expected.get(rel)
            if receipt is None:
                problems.append(f"added:{rel}")
                continue
            if path.is_symlink() or not path.is_file():
                problems.append(f"changed:{rel}")
                continue
            if path.stat().st_size != receipt.get("bytes"):
                problems.append(f"modified:{rel}")
                continue
            raw = path.read_bytes()
            if len(raw) != receipt.get("bytes") or hashlib.sha256(raw).hexdigest() != receipt.get("sha256"):
                problems.append(f"modified:{rel}")
    for missing in sorted(set(expected) - seen):
        problems.append(f"missing:{missing}")
    return problems


def safe_extract_zip(archive_path: Path, stage_root: Path, expected_top: str) -> Path:
    resolved_stage = stage_root.resolve()
    seen_exact: set[str] = set()
    seen_lower: set[str] = set()
    total_bytes = 0
    entry_count = 0

    with zipfile.ZipFile(archive_path) as zipped:
        for info in zipped.infolist():
            entry_count += 1
            if entry_count > MAX_EXTRACTED_ENTRIES:
                raise ValueError("Archive exceeds maximum entry count")
            name = info.filename
            if "\x00" in name or "\\" in name or name.startswith("/"):
                raise ValueError(f"Unsafe archive entry: {name}")
            if name in seen_exact:
                raise ValueError(f"Duplicate archive entry: {name}")
            seen_exact.add(name)
            folded = name.rstrip("/").casefold()
            if not info.is_dir():
                if folded in seen_lower:
                    raise ValueError(f"Case-colliding archive entry: {name}")
                seen_lower.add(folded)

            posix = PurePosixPath(name)
            if posix.is_absolute() or ".." in posix.parts or not posix.parts:
                raise ValueError(f"Unsafe archive path traversal: {name}")
            if posix.parts[0] != expected_top:
                raise ValueError(f"Unexpected top-level archive folder: {name}")
            mode_bits = info.external_attr >> 16
            ftype = stat.S_IFMT(mode_bits)
            if ftype == stat.S_IFLNK or (ftype not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise ValueError(f"Unsupported archive entry type: {name}")
            if not info.is_dir() and info.file_size > MAX_EXTRACTED_FILE_BYTES:
                raise ValueError(f"Archive member exceeds uncompressed file limit: {name}")
            total_bytes += max(0, info.file_size)
            if total_bytes > MAX_EXTRACTED_TOTAL_BYTES:
                raise ValueError("Archive exceeds total uncompressed size limit")

            dest = (resolved_stage / name).resolve()
            if not dest.is_relative_to(resolved_stage):
                raise ValueError(f"Extracted path escapes stage root: {name}")
            if info.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                copied = 0
                with zipped.open(info, "r") as src, dest.open("wb") as out:
                    while chunk := src.read(65536):
                        copied += len(chunk)
                        if copied > MAX_EXTRACTED_FILE_BYTES:
                            raise ValueError(f"Archive stream exceeds per-file limit: {name}")
                        out.write(chunk)
                mode = 0o755 if (mode_bits & 0o111) else 0o644
                dest.chmod(mode)

    extracted = stage_root / expected_top
    if not (extracted / "SKILL.md").is_file():
        raise ValueError(f"Archive missing {expected_top}/SKILL.md")
    return extracted


def verify_extracted_bundle(
    extracted: Path,
    *,
    manifest_name: str = BUNDLE_MANIFEST_NAME,
    expected_schema: str = PRIMARY_BUNDLE_SCHEMA,
) -> None:
    """Strictly verify extracted release bundle (fail-closed, zero ignored dirs/files)."""
    manifest_path = extracted / manifest_name
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError(f"Extracted archive missing required {manifest_name}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != expected_schema:
        raise ValueError(f"Unsupported bundle manifest schema in {manifest_name}")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError(f"Manifest {manifest_name} has empty file inventory")
    if manifest.get("payload_sha256") != _payload_digest(files):
        raise ValueError(f"Manifest {manifest_name} inventory digest mismatch")

    seen: set[str] = set()
    problems: list[str] = []
    for dirpath, dirnames, filenames in os.walk(extracted, followlinks=False):
        parent = Path(dirpath)
        for d in sorted(dirnames):
            child_dir = parent / d
            if child_dir.is_symlink():
                problems.append(f"symlink_dir:{child_dir.relative_to(extracted).as_posix()}")
        for name in sorted(filenames):
            path = parent / name
            rel = path.relative_to(extracted).as_posix()
            if path.is_symlink() or not path.is_file():
                problems.append(f"non_regular:{rel}")
                continue
            if rel == manifest_name:
                continue
            seen.add(rel)
            receipt = files.get(rel)
            if not isinstance(receipt, dict):
                problems.append(f"unexpected:{rel}")
                continue
            raw = path.read_bytes()
            if len(raw) != receipt.get("bytes") or hashlib.sha256(raw).hexdigest() != receipt.get("sha256"):
                problems.append(f"corrupt:{rel}")
    for missing in sorted(set(files) - seen):
        problems.append(f"missing:{missing}")
    if problems:
        raise ValueError("Extracted bundle failed integrity verification: " + "; ".join(problems[:5]))


def preserve_runtime_dirs(existing_target: Path, staged_target: Path) -> list[str]:
    preserved: list[str] = []
    if not existing_target.is_dir() or existing_target.is_symlink():
        return preserved
    for rel in PRESERVED_RUNTIME_DIRS:
        src = existing_target / rel
        if src.is_symlink() or not src.exists():
            continue
        if not src.is_dir():
            continue
        dst = staged_target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True)
        preserved.append(rel)
    return preserved


def atomic_swap_directory(staged: Path, target: Path) -> Path | None:
    """Swap staged directory into target; callers control backup cleanup after commit."""
    if target.is_symlink():
        raise ValueError(f"Refusing symlink install target: {target}")
    parent = target.parent.resolve()
    leaf = parent / target.name
    parent.mkdir(parents=True, exist_ok=True)
    backup_path: Path | None = None
    if leaf.is_symlink():
        raise ValueError(f"Refusing symlink install target: {leaf}")
    if leaf.exists():
        stamp = time.strftime("%Y%m%d-%H%M%S")
        candidate = parent / f"{leaf.name}.backup-{stamp}"
        counter = 1
        while candidate.exists() or candidate.is_symlink():
            candidate = parent / f"{leaf.name}.backup-{stamp}-{counter}"
            counter += 1
        leaf.rename(candidate)
        backup_path = candidate
    try:
        staged.rename(leaf)
    except BaseException:
        if backup_path is not None and backup_path.exists() and not leaf.exists():
            backup_path.rename(leaf)
        raise
    return backup_path


def _restore_from_backup(target: Path, backup: Path | None) -> None:
    if backup is None or not backup.exists():
        return
    if target.exists() and not target.is_symlink():
        shutil.rmtree(target, ignore_errors=True)
    if not target.exists():
        backup.rename(target)


@contextmanager
def _directory_lock(lock_path: Path):
    if lock_path.is_symlink():
        raise ValueError(f"Refusing symlink lock file: {lock_path}")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def resolve_asset_url(
    manifest_url: str,
    filename: str,
    *,
    repo: str | None = None,
    tag: str | None = None,
) -> str:
    clean_file = validate_filename(filename)
    parsed = urllib.parse.urlsplit(manifest_url)
    # Pin /releases/latest/download/ manifests to the exact manifest tag to prevent latest/download TOCTOU races.
    if (
        parsed.scheme == "https"
        and parsed.hostname == "github.com"
        and parsed.path.endswith("/releases/latest/download/release-manifest.json")
        and repo
        and tag
    ):
        clean_repo = validate_repo(repo)
        clean_tag = validate_tag(tag)
        return validate_url(f"https://github.com/{clean_repo}/releases/download/{clean_tag}/{clean_file}")
    if parsed.scheme in {"http", "https"} and parsed.hostname:
        return validate_url(urllib.parse.urljoin(manifest_url, clean_file))
    if repo and tag:
        return validate_url(f"https://github.com/{validate_repo(repo)}/releases/download/{validate_tag(tag)}/{clean_file}")
    raise ValueError("Cannot resolve remote asset URL without --repo and manifest tag")


def verify_file_digest(path: Path, expected_sha256: str, expected_bytes: int) -> None:
    if not SHA256_RE.fullmatch(expected_sha256):
        raise ValueError(f"Malformed expected SHA-256 for {path.name}")
    data = path.read_bytes()
    if len(data) != expected_bytes:
        raise ValueError(f"Asset byte count mismatch for {path.name}: got {len(data)}, expected {expected_bytes}")
    actual_sha = hashlib.sha256(data).hexdigest()
    if actual_sha != expected_sha256:
        raise ValueError(f"Asset SHA-256 mismatch for {path.name}: got {actual_sha}, expected {expected_sha256}")


def download_and_verify(url: str, expected_sha256: str, expected_bytes: int, dest: Path, *, timeout: int) -> None:
    data = fetch_bytes(url, timeout=timeout)
    if len(data) != expected_bytes:
        raise ValueError(f"Asset byte count mismatch for {dest.name}: got {len(data)}, expected {expected_bytes}")
    actual_sha = hashlib.sha256(data).hexdigest()
    if actual_sha != expected_sha256:
        raise ValueError(f"Asset SHA-256 mismatch for {dest.name}: got {actual_sha}, expected {expected_sha256}")
    dest.write_bytes(data)


def _check_safe_target(raw_target: Path) -> Path:
    if not raw_target.name or raw_target.name in {".", ".."}:
        raise ValueError(f"Invalid target skill directory: {raw_target}")
    if raw_target.is_symlink():
        raise ValueError(f"Refusing symlink install target: {raw_target}")
    parent = raw_target.expanduser().parent.resolve()
    leaf = parent / raw_target.name
    if leaf.is_symlink():
        raise ValueError(f"Refusing symlink install target: {leaf}")
    if (leaf / ".git").exists() or (parent.parent / ".git").exists():
        raise ValueError(f"Refusing to overwrite a git checkout directory: {leaf} (use git pull in a checkout)")
    return leaf


def _write_cache_atomic(cpath: Path, payload: dict) -> None:
    if cpath.is_symlink():
        return
    cpath.parent.mkdir(parents=True, exist_ok=True)
    tmp = cpath.parent / f".{cpath.name}.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, cpath)


def cmd_check(args: argparse.Namespace) -> int:
    try:
        repo = validate_repo(args.repo)
        manifest_url = args.manifest_url or default_manifest_url(repo, args.version)
        validate_url(manifest_url)
    except ValueError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    raw_target = Path(args.target).expanduser()
    if raw_target.is_symlink():
        print(json.dumps({"status": "error", "error": f"Refusing symlink target: {raw_target}"}, indent=2), file=sys.stderr)
        return 1
    skill_dir = raw_target.parent.resolve() / raw_target.name
    current = read_local_version(skill_dir)

    if args.cached and os.environ.get("REMORSEARCH_NO_UPDATE_CHECK") == "1":
        print(json.dumps({
            "status": "disabled",
            "current_version": current,
            "update_available": False,
        }, indent=2))
        return 0
    cpath = cache_path()
    now = time.time()
    if args.cached and cpath.is_file() and not cpath.is_symlink():
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
                    "repository": repo,
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
        "repository": manifest.get("repository", repo),
        "release_url": f"https://github.com/{repo}/releases/tag/{tag}",
        "manifest_url": manifest_url,
    }
    if args.cached:
        try:
            _write_cache_atomic(cpath, {
                "checked_at": now,
                "manifest_url": manifest_url,
                "latest_version": latest,
                "tag": tag,
            })
        except OSError:
            pass
    print(json.dumps(result, indent=2))
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    try:
        repo = validate_repo(args.repo)
        target = _check_safe_target(Path(args.target))
        ds_target = target.parent / "react-design-system"
        if args.with_design_system:
            if ds_target.is_symlink() or (ds_target / ".git").exists():
                raise ValueError(f"Refusing unsafe sibling skill target: {ds_target}")
        if args.local_manifest:
            manifest = load_local_manifest(Path(args.local_manifest))
            manifest_url = args.manifest_url or default_manifest_url(repo, manifest.get("tag"))
        else:
            manifest_url = args.manifest_url or default_manifest_url(repo, args.version)
            manifest = fetch_manifest(manifest_url, timeout=args.timeout)
    except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError) as exc:
        print(json.dumps({"updated": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2

    current = read_local_version(target)
    latest = manifest["version"]
    tag = manifest.get("tag") or f"v{latest}"

    primary_asset = manifest["assets"]["remorsearch-ux-qa"]
    design_asset = manifest["assets"].get("react-design-system") if args.with_design_system else None
    if args.with_design_system and not design_asset:
        print(json.dumps({"updated": False, "error": "react-design-system asset missing from manifest"}, indent=2), file=sys.stderr)
        return 2

    modifications = detect_local_modifications(target, manifest_name=BUNDLE_MANIFEST_NAME) if target.exists() else []
    if modifications and not args.force:
        print(json.dumps({
            "updated": False,
            "reason": "local_modifications_detected",
            "target": str(target),
            "current_version": current,
            "latest_version": latest,
            "modified_files": modifications,
        }, indent=2))
        return 3

    if target.exists() and not (target / BUNDLE_MANIFEST_NAME).is_file() and args.no_backup and not args.force:
        print(json.dumps({
            "updated": False,
            "reason": "unmanaged_install_requires_backup_or_force",
            "target": str(target),
        }, indent=2))
        return 3

    ds_current = read_local_version(ds_target, manifest_name=DESIGN_MANIFEST_NAME) if ds_target.exists() else None
    if args.with_design_system and ds_target.exists():
        ds_mods = detect_local_modifications(
            ds_target, manifest_name=DESIGN_MANIFEST_NAME, preserved_dirs=()
        )
        if ds_mods and not args.force:
            print(json.dumps({
                "updated": False,
                "reason": "local_modifications_detected",
                "target": str(ds_target),
                "current_version": ds_current,
                "latest_version": latest,
                "modified_files": ds_mods,
            }, indent=2))
            return 3
        if not (ds_target / DESIGN_MANIFEST_NAME).is_file() and args.no_backup and not args.force:
            print(json.dumps({
                "updated": False,
                "reason": "unmanaged_install_requires_backup_or_force",
                "target": str(ds_target),
            }, indent=2))
            return 3

    ver_latest = parse_version(latest)
    ver_current = parse_version(current)
    primary_needs_update = (
        args.force
        or (not target.exists())
        or (ver_latest > ver_current)
        or (args.allow_downgrade and ver_latest != ver_current)
    )
    design_needs_update = False
    if args.with_design_system:
        if not ds_target.exists() or args.force:
            design_needs_update = True
        else:
            ver_ds = parse_version(ds_current or "0.0.0-legacy")
            design_needs_update = (ver_latest > ver_ds) or (args.allow_downgrade and ver_latest != ver_ds)

    if not primary_needs_update and not design_needs_update:
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
            "primary_will_update": primary_needs_update,
            "with_design_system": args.with_design_system,
            "design_system_will_update": design_needs_update,
        }, indent=2))
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    lock_file = target.parent / ".remorsearch-update.lock"
    backup_path: Path | None = None
    design_backup: Path | None = None
    preserved: list[str] = []
    node_modules_reinstall_recommended = False
    design_updated = False

    with _directory_lock(lock_file):
        stage_dir = Path(tempfile.mkdtemp(prefix=".remorsearch-update-", dir=target.parent))
        try:
            staged_primary: Path | None = None
            staged_ds: Path | None = None

            if primary_needs_update:
                primary_zip = stage_dir / "primary.zip"
                if args.local_primary_zip:
                    src_zip = Path(args.local_primary_zip).expanduser().resolve(strict=True)
                    shutil.copyfile(src_zip, primary_zip)
                    verify_file_digest(primary_zip, primary_asset["sha256"], int(primary_asset["bytes"]))
                else:
                    download_and_verify(
                        resolve_asset_url(manifest_url, primary_asset["filename"], repo=repo, tag=tag),
                        primary_asset["sha256"],
                        int(primary_asset["bytes"]),
                        primary_zip,
                        timeout=args.timeout,
                    )
                extract_dir = stage_dir / "extracted"
                extract_dir.mkdir()
                staged_primary = safe_extract_zip(primary_zip, extract_dir, "remorsearch-ux-qa")
                verify_extracted_bundle(
                    staged_primary, manifest_name=BUNDLE_MANIFEST_NAME, expected_schema=PRIMARY_BUNDLE_SCHEMA
                )
                old_lock = target / "drivers/web/package-lock.json"
                new_lock = staged_primary / "drivers/web/package-lock.json"
                preserved = preserve_runtime_dirs(target, staged_primary)
                if "drivers/web/node_modules" in preserved and old_lock.is_file() and new_lock.is_file():
                    if hashlib.sha256(old_lock.read_bytes()).hexdigest() != hashlib.sha256(new_lock.read_bytes()).hexdigest():
                        node_modules_reinstall_recommended = True

            if design_needs_update and design_asset is not None:
                ds_zip = stage_dir / "design-system.zip"
                download_and_verify(
                    resolve_asset_url(manifest_url, design_asset["filename"], repo=repo, tag=tag),
                    design_asset["sha256"],
                    int(design_asset["bytes"]),
                    ds_zip,
                    timeout=args.timeout,
                )
                ds_extract = stage_dir / "extracted-ds"
                ds_extract.mkdir()
                staged_ds = safe_extract_zip(ds_zip, ds_extract, "react-design-system")
                if (staged_ds / DESIGN_MANIFEST_NAME).is_file():
                    verify_extracted_bundle(
                        staged_ds, manifest_name=DESIGN_MANIFEST_NAME, expected_schema=DESIGN_BUNDLE_SCHEMA
                    )

            # Commit swaps only after ALL requested archives are verified and staged.
            if staged_primary is not None:
                backup_path = atomic_swap_directory(staged_primary, target)
            if staged_ds is not None:
                try:
                    design_backup = atomic_swap_directory(staged_ds, ds_target)
                    design_updated = True
                except BaseException:
                    if staged_primary is not None:
                        _restore_from_backup(target, backup_path)
                    raise
        except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError, zipfile.BadZipFile) as exc:
            print(json.dumps({"updated": False, "error": str(exc)}, indent=2), file=sys.stderr)
            return 2
        finally:
            if stage_dir.exists():
                shutil.rmtree(stage_dir, ignore_errors=True)

        if args.no_backup:
            for old_backup in (backup_path, design_backup):
                if old_backup is not None and old_backup.exists():
                    shutil.rmtree(old_backup, ignore_errors=True)
            backup_out = None
            design_backup_out = None
        else:
            backup_out = str(backup_path) if backup_path is not None else None
            design_backup_out = str(design_backup) if design_backup is not None else None

    print(json.dumps({
        "updated": True,
        "from_version": current,
        "to_version": latest,
        "tag": tag,
        "target": str(target),
        "primary_updated": primary_needs_update,
        "backup_path": backup_out,
        "preserved_runtime_dirs": preserved,
        "node_modules_reinstall_recommended": node_modules_reinstall_recommended,
        "design_system_updated": design_updated,
        "design_system_backup_path": design_backup_out,
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
        p.add_argument("--version", help="Specific release tag vX.Y.Z to check or install")
        p.add_argument("--manifest-url", help="Override release-manifest.json URL (HTTPS or loopback HTTP)")
        p.add_argument("--timeout", type=int, default=15 if name == "check" else 30)
        if name == "check":
            p.add_argument("--cached", action="store_true", help="Use TTL cache and never fail when offline")
            p.add_argument("--ttl-hours", type=float, default=24.0)
        else:
            p.add_argument("--with-design-system", action="store_true", help="Also install/update sibling react-design-system")
            p.add_argument("--force", action="store_true", help="Overwrite local edits or reinstall same version")
            p.add_argument("--allow-downgrade", action="store_true", help="Permit installing an older --version tag")
            p.add_argument("--local-manifest", type=Path, help="Use an already-downloaded local release-manifest.json")
            p.add_argument("--local-primary-zip", type=Path, help="Use an already-downloaded primary release ZIP")
            p.add_argument("--dry-run", action="store_true", help="Preview update without modifying files")
            p.add_argument("--no-backup", action="store_true", help="Remove timestamped backup after verified swap")
    return parser


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 10):
        print(
            "Python 3.10 or newer is required; run 'python3 scripts/find_runtime.py' from the skill directory to locate a supported interpreter.",
            file=sys.stderr,
        )
        return 2
    args = build_parser().parse_args(argv)
    if args.subcommand == "check":
        return cmd_check(args)
    return cmd_apply(args)


if __name__ == "__main__":
    raise SystemExit(main())
