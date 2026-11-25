#!/usr/bin/env python3
"""Build and verify a local candidate without changing installed skills or publishing."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time
import zipfile

from build_insane_search_bundle import ARCHIVE_NAME, SKILL_NAME, SOURCE_COPY, build_payload

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/remorsearch-ux-qa"


# Explicit repository source scope; no Git dependency or personal-directory walk.
VALIDATION_ROOT_FILES = ("VERSION", "README.md", "README.ko.md", "PRD.md", "AGENTS.md", "LICENSE",
                         "COPYING", "NOTICE", "requirements.txt", "pyproject.toml")
VALIDATION_ROOT_DIRS = ("tests", "scripts", "skills/remorsearch-ux-qa",
                        "integrations/insane-search", "examples", "benchmarks", "docs")
VALIDATION_IGNORED = frozenset({"dist", "node_modules", "__pycache__", "venv", "env",
                              "secrets", "credentials", "credentials.json"})


def snapshot_validation_inputs(root, *, exclude_output=None):
    """Hash bounded source inputs without reading links, hidden state or secrets.

    Directory-relative O_NOFOLLOW opens also reject a link swapped in during the
    walk. Only relative names and digests (never contents or link targets) escape.
    """
    files, errors = {}, []
    excluded = None
    if exclude_output is not None:
        try:
            # Lexical normalization only: never follow a link to decide scope.
            relative_output = Path(os.path.abspath(exclude_output)).relative_to(Path(os.path.abspath(root)))
            if relative_output.parts:
                excluded = relative_output.as_posix()
        except ValueError:
            pass
    total = 0
    def ignored(name):
        return (name.startswith(".") or name in VALIDATION_IGNORED
                or name.endswith((".pyc", ".pyo", ".pem", ".key")))
    def error(relative, reason):
        errors.append({"path": relative, "reason": reason})
    def visit(parent_fd, name, relative):
        nonlocal total
        if ignored(name) or relative == excluded:
            return
        try:
            info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                error(relative, "Symlink input is not followed")
            elif stat.S_ISDIR(info.st_mode):
                fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
                try:
                    for child in sorted(os.listdir(fd)):
                        visit(fd, child, relative + "/" + child)
                finally:
                    os.close(fd)
            elif stat.S_ISREG(info.st_mode):
                if len(files) >= 20000 or info.st_size > 64 * 1024 * 1024 or total + info.st_size > 512 * 1024 * 1024:
                    error(relative, "Source snapshot size limit exceeded")
                    return
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd)
                try:
                    if not stat.S_ISREG(os.fstat(fd).st_mode):
                        error(relative, "Source changed to a non-regular file")
                        return
                    digest, read_size = hashlib.sha256(), 0
                    while chunk := os.read(fd, 1024 * 1024):
                        read_size += len(chunk)
                        if read_size > 64 * 1024 * 1024 or total + read_size > 512 * 1024 * 1024:
                            error(relative, "Source snapshot size limit exceeded")
                            return
                        digest.update(chunk)
                    total += read_size
                    files[relative] = digest.hexdigest()
                finally:
                    os.close(fd)
            else:
                error(relative, "Source input is not a regular file or directory")
        except OSError:
            error(relative, "Source input could not be read safely")
    try:
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        return {"files": {}, "errors": [{"path": ".", "reason": "Source root could not be read safely"}],
                "excluded_output": excluded}
    try:
        for relative in VALIDATION_ROOT_FILES + VALIDATION_ROOT_DIRS:
            parts = relative.split("/")
            parent_fd, opened = root_fd, []
            try:
                for part in parts[:-1]:
                    parent_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
                    opened.append(parent_fd)
                # Missing optional paths are represented by absence; later creation
                # is detected by the final inventory comparison.
                try:
                    os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                visit(parent_fd, parts[-1], relative)
            except FileNotFoundError:
                continue
            except OSError:
                error(relative, "Source parent could not be read safely")
            finally:
                for fd in reversed(opened):
                    os.close(fd)
    finally:
        os.close(root_fd)
    return {"files": dict(sorted(files.items())), "errors": errors,
            "excluded_output": excluded}


def validation_inputs_check(before, after):
    old, new = before["files"], after["files"]
    added = sorted(new.keys() - old.keys())
    removed = sorted(old.keys() - new.keys())
    changed = sorted(key for key in old.keys() & new.keys() if old[key] != new[key])
    passed = not (added or removed or changed or before["errors"] or after["errors"])
    return {"name": "validation-inputs-stable", "passed": passed,
            "reason": "Validation source inputs remained unchanged" if passed else
                      "Validation source inputs changed or could not be safely fingerprinted; rerun all checks",
            "added": added, "removed": removed, "changed": changed}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-skill", type=Path,
                        help="Optional maintainer input; defaults to the checked-in search toolkit")
    parser.add_argument("--output", required=True, type=Path,
                        help="New directory for the bundle, validation report and logs")
    parser.add_argument("--skip-web", action="store_true",
                        help="Run partial checks only; the report will NOT say ready")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 10):
        parser.error("Python 3.10 or later is required; macOS /usr/bin/python3 may be older")
    base = args.base_skill.expanduser().resolve() if args.base_skill else None
    output = args.output.expanduser().absolute()
    if base and not (base / "SKILL.md").is_file():
        parser.error("--base-skill must contain SKILL.md")
    if output.exists() or output.is_symlink():
        parser.error("--output must be a new directory; existing results are never overwritten")
    if base and output.resolve().is_relative_to(base):
        parser.error("--output must be outside --base-skill")
    if output.resolve().is_relative_to(SKILL.resolve()):
        parser.error("--output must be outside the engine source tree")
    output.mkdir(parents=True)
    logs = output / "logs"
    logs.mkdir()
    checks = []
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    # Driver probes invoke python3 by name; keep them on the checked interpreter
    # instead of accidentally falling back to macOS's unsupported system Python.
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")

    def check(name, command, cwd=ROOT, timeout=600):
        started = time.monotonic()
        log = logs / f"{name}.log"
        with log.open("w", encoding="utf-8") as stream:
            try:
                result = subprocess.run([str(x) for x in command], cwd=cwd, env=env,
                                        stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
                code = result.returncode
            except (OSError, subprocess.TimeoutExpired) as error:
                stream.write(f"{type(error).__name__}: {error}\n")
                code = 124 if isinstance(error, subprocess.TimeoutExpired) else 127
        record = {"name": name, "passed": code == 0, "exit_code": code,
                  "seconds": round(time.monotonic() - started, 2),
                  "log": str(log.relative_to(output))}
        checks.append(record)
        print(json.dumps(record), flush=True)
        return code == 0

    input_snapshot_before = snapshot_validation_inputs(ROOT, exclude_output=output)
    python = sys.executable
    check("unit-tests", [python, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"])
    check("release-files", [python, ROOT / "scripts/release_files.py"])
    extracted_skill = None
    base_arguments = ["--base-skill", base] if base else []
    built = check("bundle-build", [python, ROOT / "scripts/build_insane_search_bundle.py",
                                   *base_arguments, "--output", output / "bundle"])
    if built:
        check("bundle-integrity", [python, ROOT / "scripts/build_insane_search_bundle.py",
                                   "--verify", output / "bundle"])
        extracted = output / "extracted"
        try:
            with zipfile.ZipFile(output / "bundle" / ARCHIVE_NAME) as archive:
                # The archive was just built locally; still reject paths outside the destination.
                for member in archive.infolist():
                    target = (extracted / member.filename).resolve()
                    if not target.is_relative_to(extracted.resolve()):
                        raise ValueError(f"Unsafe archive path: {member.filename}")
                archive.extractall(extracted)
            if check("extracted-integrity", [python, ROOT / "scripts/build_insane_search_bundle.py",
                                             "--verify", extracted / SKILL_NAME]):
                extracted_skill = extracted / SKILL_NAME
                launcher = extracted_skill / "scripts/remorsearch.py"
                check("extracted-runtime-discovery",
                      [python, extracted_skill / "scripts/find_runtime.py"], cwd=output)
                check("extracted-research-help", [python, launcher, "research", "--help"], cwd=output)
                check("extracted-search-source", [python, launcher, "ref", SOURCE_COPY,
                                                  "phase-0-특수-엔드포인트-인덱스"], cwd=output)
                method_ok = check("extracted-search-method", [python, launcher, "ref",
                    "references/insane-search/references/public-api.md", "stack-exchange-v23"], cwd=output)
                method_body = (logs / "extracted-search-method.log").read_text(encoding="utf-8")
                checks.append({"name": "search-method-body", "passed": method_ok and
                               "curl" in method_body and "https://api.stackexchange.com/" in method_body,
                               "reason": "A linked platform method body, including its command, is readable"})
                check("extracted-smoke", [python, extracted_skill / "scripts/remorsearch.py",
                                          "smoke"], cwd=output)
                check("extracted-local-journey", [python, extracted_skill / "examples/journey/run_fixture.py",
                      "--out", output / "local-journey-result"], cwd=output)
                check("extracted-research-journey", [python, extracted_skill / "examples/journey/run_fixture.py",
                      "--research", "--out", output / "research-journey-result"], cwd=output)
                check("extracted-swarm-help", [python, launcher, "swarm", "--help"], cwd=output)
                check("extracted-scale-fixture", [python, extracted_skill / "examples/agents/scale_fixture.py",
                      "--out", output / "scale-fixture-result", "--stages", "8", "--parallel", "4"], cwd=output)
                check("extracted-swarm-status", [python, launcher, "swarm", "status", "--run",
                      output / "scale-fixture-result/stage-8/run"], cwd=output)
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            checks.append({"name": "extract", "passed": False, "error": str(error)})
    if args.skip_web:
        checks.append({"name": "web-driver", "passed": False, "skipped": True,
                       "reason": "--skip-web requested; release validation is incomplete"})
    else:
        node = shutil.which("node")
        supported = check("node-version", [node or "node", "-e",
            "console.log(process.version); if(process.versions.node.split('.')[0] !== '22') { "
            "console.error('Node.js 22 is required for the pinned Playwright driver'); process.exit(2); }"])
        if supported and extracted_skill:
            driver = extracted_skill / "drivers/web"
            try:
                # Dependencies were prepared by the developer with npm ci. Copy
                # only into the disposable extracted installation; no downloads
                # or install hooks are run by this release checker.
                shutil.copytree(SKILL / "drivers/web/node_modules", driver / "node_modules", symlinks=True)
                check("driver-dependencies", [node, "-e",
                    "const p=require('./package.json'); const v=require('./node_modules/playwright/package.json').version; "
                    "console.log('Playwright '+v); if(v!==p.dependencies.playwright) process.exit(2);"], cwd=driver)
                check("web-driver", [node, "selftest.mjs"], cwd=driver, timeout=900)
                check("browser-bridge-contract", [node, "--test", "journey_bridge.test.mjs"], cwd=driver)
                check("extracted-browser-journey", [python, extracted_skill / "examples/journey/run_browser_fixture.py",
                      "--research", "--out", output / "browser-journey-result"], cwd=output, timeout=180)
                check("post-browser-integrity", [python, extracted_skill / "scripts/remorsearch.py", "verify"])
            except OSError as error:
                checks.append({"name": "web-driver", "passed": False,
                               "error": str(error), "reason": "Prepare source driver dependencies with npm ci"})
        else:
            checks.append({"name": "web-driver", "passed": False, "skipped": True,
                           "reason": "Node.js 22 and a verified extracted candidate are required"})
    if built:
        # A build can be valid yet already stale if source edits land while the
        # slower browser tests run. Never label that candidate current/ready.
        try:
            _, current = build_payload(base)
            archived = json.loads((output / "bundle" / SKILL_NAME / "manifest.remorsearch.json").read_text())
            unchanged = current == archived
            checks.append({"name": "current-source-match", "passed": unchanged,
                           "reason": "Candidate matches current inputs" if unchanged else
                           "Inputs changed during validation; rebuild and recheck"})
        except (OSError, ValueError) as error:
            checks.append({"name": "current-source-match", "passed": False, "error": str(error)})
    input_snapshot_after = snapshot_validation_inputs(ROOT, exclude_output=output)
    checks.append(validation_inputs_check(input_snapshot_before, input_snapshot_after))
    report = {"schema_version": "remorsearch-release-check.v1",
              "ready": all(item["passed"] for item in checks),
              "validation_inputs": {"root_files": VALIDATION_ROOT_FILES, "root_directories": VALIDATION_ROOT_DIRS,
                                    "before": input_snapshot_before, "after": input_snapshot_after},
              "published": False, "python": sys.version.split()[0], "checks": checks,
              "scope": "Package integrity and local synthetic regression tests; not live research or certification"}
    (output / "validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ready": report["ready"], "published": False,
                      "report": str(output / "validation.json")}), flush=True)
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
