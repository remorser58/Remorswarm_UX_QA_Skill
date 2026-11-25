"""Owned synthetic web sample and authored hypotheses, never participant evidence.

The retention defect is deliberately known: one invalid-input path clears a
draft. Both paths can subsequently save, so later recovery must not erase the
earlier failed checkpoint. No production product or account is involved.
"""
from pathlib import Path
import sys

SKILL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL))
from uxpersonas.library import Library
from uxresearch.canonical import byte_digest, canonical
from uxresearch.storage import atomic, safe_path

FILES = ["PRD.md", "index.html", "browser-adapter.json"]
PRD = (
    "Keep the entered note when invalid input is rejected. "
    "After correcting the input, save the exact corrected note.\n"
)
PAGE = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Owned synthetic note sample</title>
<style>
body { margin: 48px; max-width: 720px; font: 18px system-ui, sans-serif; }
label, input, button, p { display: block; margin: 16px 0; }
input, button { padding: 12px; font: inherit; }
input { width: 420px; }
button { min-height: 44px; }
</style>
<main>
<h1>Owned synthetic note sample</h1>
<p>This diagnostic contains an intentionally defective error path.</p>
<label for="note">Note</label>
<input id="note" type="text" autocomplete="off">
<button id="reject-broken" type="button">Reject invalid input: defective path</button>
<button id="reject-control" type="button">Reject invalid input: control path</button>
<p id="feedback" role="status">Ready</p>
<button id="save" type="button">Save corrected note</button>
<p>Saved note:</p>
<p id="saved">No note saved</p>
</main>
<script>
const note = document.getElementById('note');
const feedback = document.getElementById('feedback');
document.getElementById('reject-broken').addEventListener('click', () => {
  note.value = '';
  feedback.textContent = 'Invalid input rejected. Correct the note and try again.';
});
document.getElementById('reject-control').addEventListener('click', () => {
  feedback.textContent = 'Invalid input rejected. Correct the note and try again.';
});
document.getElementById('save').addEventListener('click', () => {
  document.getElementById('saved').textContent = note.value;
  feedback.textContent = 'Corrected note saved';
});
</script>
</html>
"""


def build(root):
    """Create a new disposable target, Library and plan; never write old results."""
    root = safe_path(root)
    root.mkdir(mode=0o700)
    source, library = root / "source", root / "existing-personas"
    source.mkdir(mode=0o700)
    atomic(source / "PRD.md", PRD.encode())
    atomic(source / "index.html", PAGE.encode())
    tasks, profiles, journeys = [], [], []
    for name, button, context in (
        ("RETURN", "#reject-broken", "Resume an entered note after an error."),
        ("EXPLORE", "#reject-control", "Check the ordinary correction path before continuing."),
    ):
        goal = "Keep the draft through rejection and save the corrected note"
        profiles.append(dict(
            persona_id="PER-" + name, label=context, goals=[goal],
            behaviors=["Check entered values before continuing after an error."],
            contexts=[context, "Owned synthetic browser fixture"],
            assumptions=["Authored PRD hypothesis, not observed participant behavior"],
            unknowns=["No real user preference or effect evidence"],
            requirement_ids=["R-STATE"], claim_ids=[]))
        task = dict(
            id="T-" + name, persona_id="PER-" + name, requirement_ids=["R-STATE"],
            goal=goal, starting_state="Fresh isolated page with an empty note and no saved note",
            actions=["Enter the owned note", "Reject invalid input using " + button,
                     "Enter the corrected owned note", "Save the corrected note"],
            decisions=["Check the draft at the error checkpoint before correcting it.",
                       "Compare the saved result with the corrected input."],
            success_criteria=["The entered note remains present after invalid input is rejected."],
            recovery_criteria=["The corrected note is saved exactly after retry."],
            data_namespace=name, resource_id=name, side_effects="read_only",
            stop_conditions=["Stop outside the owned synthetic page or on uncertain browser cleanup."],
            requirement_coverage=[dict(requirement_id="R-STATE", obligations=[
                dict(id="O-RETAIN", description="Retain the entered note at the rejection checkpoint.",
                     criterion_refs=[dict(kind="success", index=0)], exclusion_reason=None),
                dict(id="O-RECOVER", description="Save the exact corrected note after retry.",
                     criterion_refs=[dict(kind="recovery", index=0)], exclusion_reason=None)])])
        tasks.append(task)
        steps = [
            dict(action="type", target="#note", text="Owned draft"),
            dict(action="tap", target=button),
            dict(action="type", target="#note", text="Owned corrected note", clear=True),
            dict(action="tap", target="#save"),
        ]
        checks = [
            dict(id="draft-after-error", selector="#note", property="value",
                 from_step=1, after_step=2, severity="P1",
                 consequence="Losing a draft forces the user to enter it again."),
            dict(id="saved-after-retry", selector="#saved", property="text",
                 from_step=3, after_step=4, severity="P1",
                 consequence="The saved result must match the corrected input."),
        ]
        scenario = dict(
            schema_version="ergo-scenario.v1", scenario_id="SC-browser-" + name.lower(),
            surface=dict(kind="web", url="https://remorsearch.invalid/index.html"),
            task_goal_ko=goal, device_ids=["desktop-1920"], steps=steps,
            success=dict(task_checks=checks))
        journeys.append(dict(task_id=task["id"], scenario=scenario, device_id="desktop-1920",
                             criteria=[dict(kind="success", index=0, check_id="draft-after-error"),
                                       dict(kind="recovery", index=0, check_id="saved-after-retry")]))
    with Library(library) as store:
        imported = store.import_profiles(dict(
            schema_version="ux-persona-library-input.v1", product_id="owned-product",
            mode="prd_hypothesis",
            context=dict(prd_path=str(source / "PRD.md"),
                         prd_sha256=byte_digest((source / "PRD.md").read_bytes()),
                         requirements=[dict(id="R-STATE", source_anchor="Owned browser PRD",
                                            excerpt=PRD.strip())]),
            personas=profiles))
    adapter = dict(schema_version="ux-journey-browser-adapter.v1", journeys=journeys)
    atomic(source / "browser-adapter.json", canonical(adapter))
    plan = dict(schema_version="ux-journey-browser-plan.v1", product_id="owned-product",
                runner="browser-adapter.json", timeout_seconds=30, tasks=tasks)
    plan_path = root / "reviewed-plan.json"
    atomic(plan_path, canonical(plan))
    return dict(source=source, work=root / "work", library=library, tasks=tasks,
                plan=plan, plan_path=plan_path, adapter=adapter, imported=imported)
