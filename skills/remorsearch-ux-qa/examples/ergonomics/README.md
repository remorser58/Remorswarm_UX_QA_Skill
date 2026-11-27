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
