# PE2 independent adjudication

## Verdict

**Completed, valid bounded synthetic detection/false-alarm comparison: descriptive tie.** M and N each independently reported and evidenced all three seeded defects, with no unsupported unique defect claims, duplicate defects, or false alarms among the three observed clean controls. This is not whole-PRD equivalence, an efficiency advantage, a persona-only causal effect, or evidence about real users.

| Measure | M | N |
|---|---:|---:|
| Unique seeded defects | 3/3 | 3/3 |
| Clean-control false-alarm cases | 0/3 | 0/3 |
| Cases executed | 6/6 | 6/6 |
| Attempted / successful / failed / unknown actions | 60 / 59 / 1 / 0 | 37 / 36 / 1 / 0 |
| First action to last action end, ms | 455477.674750 | 321799.955208 |
| First action to final evidence end, ms | 455511.974250 | 321832.001792 |

Both limits hold. Both first gotos succeeded. Each sole failure was action 11, a bounded timeout seeking the removal control after faulty cancellation removed the episode. No missing or uncertain operations. Logs have continuous sequences/counts, a single first-action origin, valid start/end/evidence order, and matching raw/stdout content. Both runners reached input EOF and shutdown with exit code 0. M failure: 01:16:25.657–01:16:28.160 UTC; N: 01:17:40.480–01:17:42.983 UTC, November 11, 2026. First/last action timestamps are in the JSON companion.

## Evidence and integrity

All four frozen report hashes match the supplied freeze. The commitment record equals its version in pre-dispatch commit `37b9e89`. The private key hash matches the precommitted `d0f2c62f41f43a067e5351dd6945e29baf580c50f868b92816cef6f59bed19f6`; public manifest plus all seven entries, oracle trace manifest plus all 66 entries, and seven frozen skill/protocol/input entries match. This is local consistency evidence, not external authenticity proof.

Review used frozen findings, actual action logs, visible DOM form states, selected original PNGs, public PRD/plan, committed oracle and implementation. No new UI execution or target edits. Explicitly visually inspected M PNGs 005,009,010,018,025,030,035,036 and N 005,009,010,015,022,027,032,033. These show valid saves, preserved clean cancellation and step-free retry, removal after faulty cancellation, stale validation with corrected input visibly entered, and Avoid-stairs outage followed by Shortest-path/stairs output. Complete action sequences, not images alone, establish the triggering actions.

- J2N: both 8–11 show confirmation opening then Cancel removes Morning Birds, leaving River Sounds and count one. Missing later control is a consequence, not a second defect.
- R5B: M 21–27 and N 18–24 show invalid submission then valid correction/resubmission retains obsolete error and no saved note. Continued valid edits also fail; same defect.
- D3W: M 33–38 and N 30–37 show Avoid stairs retained during initial simulated outage but reset on retry. Later ordinary Avoid-stairs preview resets too. Source uses the same preference-reset branch, so this is the seeded fault's further manifestation, not an unseeded additional defect.
- Clean controls: V7Q M/N 1–7; H8C M15–20/N12–17; L9F M28–32/N25–29 establish representative recovery, later edit and confirmation/cancellation behaviors. No observed unseeded defect invalidates this scored scope. This is not exhaustive certification that the application has none.

## Treatment workflow

Three synthetic profiles were imported, reimported unchanged at revision 1, and retrieved. Six claim/starter/accepted-record sets match task/worker/lease/build/profile bindings. All starter outcomes were inconclusive rather than ready-made passes. Independently hash-verified 31 receipt artifact references. Recorded outcomes are three passed and three failed. The final state has empty history lists: bindings/artifacts corroborate use, but these files alone do not independently timestamp claim-before-action ordering. No secrets are reproduced here.

Receipt acceptance is not whole-obligation validation. In particular, N's D3W explicit Shortest-path result was correct only for that narrow already-selected state; the later actual change to Avoid stairs failed. Do not upgrade this to a broad change-preference pass. Declared coverage totals or duplicated PRD paragraph references are not independently earned whole-paragraph passes.

## Coverage and methodological limits

- One worker per condition and six authored synthetic cases; no population, causal persona-only, statistical, production, or real-user inference.
- Different bounded paths: M exercised additional invalid classes and endpoints; N did not. Smaller N action/time totals are not equal-coverage efficiency.
- Plan does not explicitly map plant initial defaults or walk initial defaults; valid endpoints not specifically required/excluded. Initial visible defaults were nonetheless present in execution.
- Duplicated P1/P2, Q1/Q2, R1/R2 source paragraphs are not independent whole-paragraph coverage.
- N J2N confirmed removal after cancellation was not run; absence of control directly observed. M checked confirm after reload, not successful recovery from faulty cancellation.
- N D3W explicit Shortest-path check occurred when already selected; narrowly correct route is not evidence of successful broader preference change. Later Avoid-stairs change failed.
- R5B invalid-class checks after validation latch cannot isolate each validator. Neither condition establishes valid-first R5B saving.
- Preparation before first UI is untimed and nonzero; no model-token, cost or complete effort metric.
- Harness gates at action start, not hard interruption of in-flight actions; all observed completions/evidence were within limit. Free observations are not time-gated; no extra observations occurred here.
- Local digest commitment establishes checked consistency, not external authenticity. Reviewer is unblinded; strategy apparent in prose.

M used its remaining budget for additional input classes and endpoint checks; N used representative 0, 5 and 9. Report the measured durations/actions descriptively, never as equal-coverage speed or cost savings. All planned clean controls were observed, but the explicit exclusions above remain. No further trial actions, edits to evidence, or post-hoc plan repairs were made during this review.
