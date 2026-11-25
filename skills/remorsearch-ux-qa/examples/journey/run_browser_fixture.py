#!/usr/bin/env python3
"""Run the owned synthetic browser diagnostic; no actual users or live product execution."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from browser_fixture import FILES, SKILL, build
from uxresearch.canonical import byte_digest, canonical
from uxresearch.storage import atomic


def snapshot(root):
    return {str(path.relative_to(root)):
            (byte_digest(path.read_bytes()), path.stat().st_mode & 0o777, path.stat().st_mtime_ns)
            for path in root.rglob("*") if path.is_file()}


def run_fixture(root, *, research=False):
    case = build(root)
    research_root, research_baseline = None, None
    if research:
        from research_fixture import attach
        research_root, _ = attach(case, Path(root) / "owned-research", structured=True)
        research_baseline = snapshot(research_root)
    launcher = SKILL / "scripts/remorsearch.py"
    prefix = ["personas"]
    if not launcher.is_file():
        launcher, prefix = SKILL / "scripts/ux_personas.py", []
    work = case["work"]
    work.mkdir(mode=0o700)
    source_baseline, library_baseline = snapshot(case["source"]), snapshot(case["library"])
    commands = []
    # Only configured runtime locations reach the diagnostic CLI. Browser/account
    # attachment environment is not inherited.
    env = {key: os.environ[key] for key in
           ("PATH", "LANG", "LC_ALL", "REMORSEARCH_JOURNEY_NODE", "NODE_PATH",
            "PLAYWRIGHT_BROWSERS_PATH") if key in os.environ}
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    def command(name, *args, expected):
        process = subprocess.run(
            [sys.executable, str(launcher), *prefix, name, "--work", str(work),
             "--format", "json", *args], capture_output=True, text=True,
            timeout=120, env=env)
        commands.append(dict(command=name, exit_code=process.returncode,
                             expected_exit_code=expected))
        if process.returncode != expected:
            raise RuntimeError("Owned browser diagnostic command failed: " + name
                               + "; " + process.stderr)
        return json.loads(process.stdout)

    selection = [item for name in FILES for item in ("--include", name)]
    prepared = command("start", "--source", str(case["source"]), *selection, expected=0)
    assert prepared["execution_performed"] is False
    review = ["--reviewed-research-run", str(research_root)] if research_root else []
    result = command("run", "--library", str(case["library"]), "--input", str(case["plan_path"]),
                     "--allow-reviewed-local-runner", *review, expected=1)
    assert result["execution_complete"] and result["execution_performed"]
    assert result["counts"]["failed"] == 1 and result["counts"]["passed"] == 1
    assert result["counts"]["inconclusive"] == 0 and result["counts"]["pending"] == 0
    assert len(result["personas_reused"]) == 2
    assert result["ui_observed"] and not result["real_user_evidence"] and not result["product_ready"]
    assert result["evidence_audit"]["integrity"] == "consistent"
    by_task = {row["task_id"]: row for row in result["tasks"]}
    assert by_task["T-RETURN"]["status"] == "failed"
    assert by_task["T-EXPLORE"]["status"] == "passed"
    for name, row in by_task.items():
        assert row["attempts"] == 1
        observed = {(item["kind"], item["index"]): item for item in row["result"]["criteria"]}
        assert observed[("success", 0)]["status"] == ("failed" if name == "T-RETURN" else "passed")
        assert observed[("recovery", 0)]["status"] == "passed"
        assert len(row["result"]["steps"]) >= 4
        assert {artifact["kind"] for artifact in row["result"]["artifacts"]} == {"execution_log", "screenshot"}
    evidence_baseline = snapshot(work)
    assert command("run", expected=1) == result
    assert command("status", expected=0) == result
    assert evidence_baseline == snapshot(work)
    assert source_baseline == snapshot(case["source"])
    assert library_baseline == snapshot(case["library"])
    if research_root:
        assert research_baseline == snapshot(research_root)
        assert all(persona["provenance_mode"] == "gated_research"
                   and persona["research"]["export"]["scenario_ids"]
                   for persona in result["personas_reused"])
        assert not any(path.name in {"pages", ".engine", "bundle.json", "gate.json"}
                       for path in work.rglob("*"))
    summary = dict(
        schema_version="ux-journey-browser-diagnostic.v1", diagnostic_checks_passed=True,
        product_qa_passed=False, synthetic_known_defect=True, actual_browser_execution=True,
        ui_observed=True, real_user_evidence=False, target_product_executed=False,
        counts=result["counts"], report_path=result["report_path"], commands=commands,
        launcher=str(launcher.relative_to(SKILL)), personas_reused=result["personas_reused"],
        earlier_failed_checkpoint_preserved_after_recovery=True,
        readback_without_redispatch=True, original_source_unchanged=True,
        original_library_unchanged=True,
        research_contract="invented_offline_input" if research_root else None,
        actual_public_acquisition=False,
        original_research_unchanged=True if research_root else None)
    atomic(Path(root) / "diagnostic.json", canonical(summary))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path,
                        help="New directory; preserve evidence. Existing directories are refused.")
    parser.add_argument("--research", action="store_true",
                        help="Reuse invented offline research exports; not actual public research")
    args = parser.parse_args()
    if args.out:
        run_fixture(args.out, research=args.research)
    else:
        with tempfile.TemporaryDirectory(prefix="browser-journey-diagnostic-") as temporary:
            run_fixture(Path(temporary).resolve() / "case", research=args.research)
