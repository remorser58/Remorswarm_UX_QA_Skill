# Local Workshop Planner, PE-1

This is a synthetic local application, not a real-user study. It supports planning a small craft workshop without accounts, real people, network services, payments, or uploads. All listed names, values and token prices are invented. Evaluate transitions and decisions, not visual taste. It intentionally has no persistence across page navigation or reload; each case URL starts fresh. Within a case, controls are synchronous.

## Users and goals
Organizers may revise a plan, pause to deal with another task, change their minds while importing a list, or compare room alternatives in a different order. They must retain control over what gets confirmed. The public case IDs represent separate synthetic starting datasets, not defect categories.

## Obligations
- D1: Title and seat-limit edits must be reflected in review and confirmation. Use seat limits from 1 to 30 and nonempty synthetic titles; other validation is out of scope.
- D2: Pause then resume within the same page must preserve every draft field. Review then back must also preserve edits. Pausing does not confirm a plan.
- I1: Import accepts one material name per line. Preview displays nonempty trimmed names and must not modify current materials.
- I2: Back without applying must leave current materials unchanged and preserve the input for revision/retry. Apply appends exactly the previewed materials once, clears input, and returns to the material list. Duplicate input names are allowed and not automatically deduplicated.
- C1: Room selection is an identity choice, not a row position. Sorting must preserve the chosen room, its visible selected state, and the identity carried into review and confirmation.
- C2: Review then back must preserve selection and ordering; choosing a different room must replace the previous selection. Name order is Cedar, Maple, Willow. Cost order is Maple (12), Cedar (18), Willow (24); room capacity is information only, not a filter.

## Public cases
| ID | Starting workflow | Initial data |
|---|---|---|
| K4M | Draft | Paper shapes, 12 seats |
| P8R | Compare | Ink patterns, 10 seats; no room selected |
| T2V | Import | Clay tokens, 9 seats; Starter kit |
| B7N | Draft | Ribbon forms, 14 seats |
| D5Q | Import | Wood mosaics, 11 seats; Starter kit |
| H9S | Compare | Thread grids, 8 seats; no room selected |

All obligations apply to the corresponding workflow in every case. No case is promised to be broken or correct. Report observable PRD conflicts, including exact case, steps, expected and actual result, evidence and task impact. Nonexecution is not a pass. Do not inspect application JavaScript, server implementation, private oracle, browser storage, page runtime variables or network internals until findings are frozen. DOM-visible text, semantic controls and screenshots are allowed. Source files are public build inputs only for the coordinator, not evaluation evidence.
