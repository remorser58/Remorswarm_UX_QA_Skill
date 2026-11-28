# Score a synthetic icon toggle

The two PNGs and their snapshot metadata are constructed, not collected. They show a plus button changing to a minus after a click. Both states deliberately leave the button’s accessible name empty and provide no tooltip or focus hint for the icon. The supplied desktop profile is simulated. No website, browser, download, API key or real user data is needed.

Unzip the release archive and change into its `remorsearch-ux-qa` directory. With Python 3.10+ and a writable parent directory, run:

```sh
sample=examples/ergonomics
result=../ergonomics-result
python3 scripts/remorsearch.py ergonomics swarm --runs "$sample/run" --profiles "$sample/profiles.json" --out "$result" --title "Synthetic icon toggle"
python3 scripts/remorsearch.py ergonomics bench --key "$sample/answer-key.json" --findings "$result/findings.json" --profiles "$sample/profiles.json" --out "$result/score.json"
cat "$result/report.md"
```

Use a new result directory so nothing is overwritten. Look for `SM-01` (no accessible name) and `UI-01` (no visual explanation) on `#toggle` in the report. The score should show two seeded defects, `recall_strict: 1.0` and `severity_agreement: 1.0`. That is two matched defects on one constructed control, not a detector accuracy estimate or a real accessibility audit. The answer key is read only by the scoring command.

In a source checkout, run from `skills/remorsearch-ux-qa` and use `python3 scripts/ergo_qa.py` in place of `python3 scripts/remorsearch.py ergonomics`.

## Optional: explain the report with a storyboard

**Illustration only.** This storyboard redraws one event from the synthetic example. It is neither a screenshot nor test evidence. Open the [three-panel storyboard](toggle-storyboard.svg) as a still, or read it here:

1. **Before:** the synthetic `#toggle` button shows plus. See [the fixture’s before image](run/S-synthetic-before.png).
2. **After the fixture’s click:** it shows minus. See [the fixture’s after image](run/S-synthetic-after.png).
3. **What to check in `report.md`:** `SM-01` (no accessible name) and `UI-01` (no visual explanation) refer to the same control. The changed icon is not a fix for either finding. This fixture did not test a screen reader.

To make one for another report, start **after** QA. Pick one already documented task and name who needs the explanation, the role of the control, and the state to check. Sketch three to five beats in a compact crop: what was shown, what changed or did not, and where to verify it in the report. Keep the key control in the same place across beats and leave unrelated detail out. Label every detachable frame **Illustration only**. Link the actual observation by run, step, or finding ID rather than inserting an invented result. Keep the observed capture, any inference, and any PRD expectation separately labeled. A missing observation stays **not checked**. Neither a synthetic role nor a mockup is real-user evidence, and neither belongs in the QA evidence bundle.

Review the final state first as a standalone still, then compare every beat at its intended size and at a narrow width. Check that state, label, and caption remain legible and do not overlap or get cropped. Keep a text equivalent. If you add motion later, keep the same still available with reduced motion, provide a way to pause or stop, and sample frames at the action, any overlap, the hold, and the reset. Check for clipped content, unexplained jumps, and readable timing. Use a still if you cannot verify the motion.

Adapted from Benji Taylor’s [Stageshow overview](https://benji.org/stageshow) and [Stageshow workflow](https://github.com/benjitaylor/skills/blob/main/stageshow/SKILL.md). This example uses no Stageshow code or runtime.
