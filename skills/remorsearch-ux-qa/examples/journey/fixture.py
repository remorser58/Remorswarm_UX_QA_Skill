"""Purpose-built defective sample and authored PRD hypotheses, never real users.

The defect is known in advance: rejected input clears earlier in-memory items.
This checks whether the orchestration reports that observation honestly.
"""
from pathlib import Path
import sys

SKILL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL))
from uxpersonas.library import Library
from uxresearch.canonical import byte_digest, canonical
from uxresearch.storage import atomic, safe_path

FILES = ["PRD.md", "product.py", "adapter.py"]
RUNNER = '''import json, pathlib, runpy, sys
request = json.load(sys.stdin)
product = runpy.run_path(str(pathlib.Path(request["source"]) / "product.py"))
items = ["earlier"]
if request["task"]["id"] == "T-RETURN":
    try: product["replace"](items, "malformed")
    except ValueError: pass
    good = items == ["earlier"]
    observation = "Earlier item retained" if good else "Earlier item lost after rejected input"
else:
    product["replace"](items, ["candidate"])
    good = items == ["candidate"]
    observation = "Candidate loaded" if good else "Candidate missing"
criteria = [{"kind": "success", "index": 0, "status": "passed" if good else "failed", "observation": observation}]
criteria += [{"kind": "recovery", "index": 0, "status": "not_run", "observation": "Browser recovery was not observed"}]
print(json.dumps({"schema_version": "ux-journey-observation.v1", "binding": request["binding"],
    "reason": observation, "steps": [{"action": request["task"]["actions"][0], "observation": observation}], "criteria": criteria}))
'''


def build(root):
    """Create ONLY a new owned example. Production run never imports personas."""
    root = safe_path(root)
    root.mkdir(mode=0o700)  # Existing results are never reused or overwritten.
    source, library = root / "source", root / "existing-personas"
    source.mkdir(mode=0o700)
    atomic(source / "PRD.md", b"Load a candidate. Keep earlier items after invalid input.\n")
    atomic(source / "product.py", b'def replace(items, candidate):\n    items.clear()\n    if not isinstance(candidate, list): raise ValueError("invalid input")\n    items.extend(candidate)\n')
    atomic(source / "adapter.py", RUNNER.encode())
    tasks, profiles = [], []
    for name, goal in (("EXPLORE", "Load the candidate"), ("RETURN", "Keep earlier items after rejected input")):
        profiles.append(dict(persona_id="PER-" + name, label=goal, goals=[goal],
            behaviors=["Inspect owned sample"], contexts=["Owned synthetic fixture"],
            assumptions=["PRD hypothesis only"], unknowns=["No human behavior evidence"],
            requirement_ids=["R-STATE"], claim_ids=[]))
        tasks.append(dict(id="T-" + name, persona_id="PER-" + name, requirement_ids=["R-STATE"],
            goal=goal, starting_state="Earlier item in memory", actions=["Apply owned candidate"],
            decisions=["Compare memory with expected state"], success_criteria=[goal],
            recovery_criteria=["Browser recovery is usable"], data_namespace=name, resource_id=name,
            side_effects="read_only", stop_conditions=["Stop outside owned local fixture"],
            requirement_coverage=[dict(requirement_id="R-STATE", obligations=[
                dict(id="O-CORE", description=goal, criterion_refs=[dict(kind="success", index=0)], exclusion_reason=None),
                dict(id="O-RECOVER", description="Browser recovery", criterion_refs=[dict(kind="recovery", index=0)], exclusion_reason=None)])]))
    with Library(library) as store:
        imported = store.import_profiles(dict(schema_version="ux-persona-library-input.v1",
            product_id="owned-product", mode="prd_hypothesis",
            context=dict(prd_path=str(source / "PRD.md"), prd_sha256=byte_digest((source / "PRD.md").read_bytes()),
                requirements=[dict(id="R-STATE", source_anchor="Owned PRD", excerpt="Load a candidate. Keep earlier items after invalid input.")]),
            personas=profiles))
    plan = dict(schema_version="ux-journey-local-plan.v1", product_id="owned-product", runner="adapter.py", timeout_seconds=3, tasks=tasks)
    plan_path = root / "reviewed-plan.json"
    atomic(plan_path, canonical(plan))
    return dict(source=source, work=root / "work", library=library, tasks=tasks, plan=plan, plan_path=plan_path, imported=imported)
