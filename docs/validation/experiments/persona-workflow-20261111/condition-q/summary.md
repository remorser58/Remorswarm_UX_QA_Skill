# Condition Q: frozen first-pass black-box QA

Three reproduced PRD conflicts:
- B7N / D2: seat limit 27 resets to 14 after Pause task → Resume draft; title survives. Actions 11–16.
- D5Q / I2: preview → Back without applying adds Red clay, Twine, Red clay without Apply. Retry/apply then leaves two batches. Actions 30–35. Mutation timing within preview/back is not localized.
- P8R / C1: choosing Cedar then sorting by cost selects Maple instead; review and confirmation commit Maple. Actions 36–40.

All six cases exercised. K4M draft transitions, T2V import transitions, and H9S compare transitions had no observed PRD conflicts on tested paths. P8R separate review/back and replacement-choice checks also retained state. This is bounded coverage, not a blanket pass. See findings.json for exact steps, per-obligation coverage, evidence filenames, and untested conditions.

60 attempted actions: 58 succeeded, 2 failed. First failure was refused local server navigation; same harness continued after server restoration. Second was a mismatched accessible label, corrected without resetting budget. Harness ended with EOF and exit 0.

Actual screenshot timestamps span 107.584 seconds from first successful action to last. Total elapsed is unavailable in harness output, because the initial failed action and startup/server wait lack a harness timestamp; no exact total is claimed.

Evidence: evidence/actions.jsonl and automatically generated screenshots. No source/runtime/storage/network introspection, outside conclusions, or persona packets used. Synthetic fixture findings are not real-user or population-level effectiveness evidence. No token/cost metrics available.
