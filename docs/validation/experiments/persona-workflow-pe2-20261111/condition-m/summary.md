# PE-2 condition M: frozen ordinary task QA

60 attempted UI actions, including one failed click; no blocked or uncertain commands. One persistent runner, no budget reset. Six cases independently inspected using only the two public benchmark documents and visible UI evidence.

## Confirmed violations
- **J2N:** Cancel removes Morning Birds and changes count from 2 to 1. A subsequent removal control is unavailable (counted timeout). Evidence: 008–011. Direct confirmed removal after reload behaves correctly (012–014).
- **R5B:** After invalid 0, corrections to valid 1 and 14 cannot save; stale validation and “No care note saved” remain. A later independently loaded sequence ending in valid 5 reproduces failure after invalid inputs. Evidence: 021–027, 050–060.
- **D3W:** Avoid stairs is preserved during the required outage, but retry changes it to Shortest path and produces Hill steps, 0.8 km, includes stairs. Reselecting Avoid stairs and previewing again repeats the wrong choice/route. Evidence: 033–038.

## Coverage and limits
- V7Q: defaults; invalid 0, empty, abc, 1.5,15; recovery to 1/5; subsequent valid 14 edit; accurate Fern confirmations and cleared errors. Tested behavior clean. Other integer/string inputs and invalid edits after an existing save untested.
- J2N: defaults, dialog preservation, cancel failure, unavailable subsequent request, direct confirmation after reload. Successful cancel-to-confirm path prevented by defect.
- H8C: all core transitions including nondefault before outage, retry, and later Shortest path preview clean. Initial default-choice outage not separately tested.
- R5B: defaults and representative invalid categories rejected; correction to 1/14/5 fails. No successful-save follow-on edit can be evaluated, and valid-first submission was not tested. Sticky validation prevents isolating later invalid-category validators.
- L9F: default queue, open/cancel/reopen/confirm all clean in tested path.
- D3W: defaults, outage, retry and subsequent preference change covered; correct Avoid stairs route never achieved; explicit subsequent Shortest path selection not separately tested.

Expected simulated first-preview outages are not defects. No root-cause hypotheses or hidden classification claims. Detailed commands, expected/observed, impact and evidence references are in findings.json; complete raw responses and captures remain in evidence/.

## Timing and cleanup
First action: 2026-11-11T01:14:59.092Z (monotonic 9540.078875 ms).
Last action end: 2026-11-11T01:22:34.570Z (monotonic 465017.753625 ms).
Final evidence end: 2026-11-11T01:22:34.604Z. Harness elapsed: 455511.974916 ms (7m35.512s).
EOF closed PTY 57791; process exit 0. Lifecycle records input_eof, harness_exit code 0 and shutdown_complete code 0 at 2026-11-11T01:22:41.968Z. No new UI work after the action cap; report frozen before any answer access.
