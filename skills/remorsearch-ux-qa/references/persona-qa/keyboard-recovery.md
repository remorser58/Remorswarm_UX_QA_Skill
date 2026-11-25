# Keyboard recovery after asynchronous state changes

Use this focused task recipe for dialogs, imports and forms whose active
controls become disabled, disappear or are replaced during work. It supplements
the product task, not a separate screenshot audit. Record build, PRD obligations,
start state and expected behavior before execution. If task assignment happened
after an exploratory run, report that run separately; do not invent a prior claim.

## Exercise the transition

1. Start in an isolated approved state. Use actual Tab/Shift+Tab and Enter/Space
   to reach and invoke the task. Record the focused role/name and visible state.
2. Provide a safe invalid input through the invoked control. Observe the busy
   phase, including whether the focused initiating control becomes disabled.
3. When the error appears, record active focus and whether it is inside the
   still-open dialog. Check subsequent Tab and Shift+Tab destinations. Do not
   programmatically focus a control to hide the product's recovery behavior.
4. Retry using valid approved data and actual keyboard invocation. Compare
   storage/results with expected values; an error must not replace prior valid
   state. Record whether reselecting the same input is possible where applicable.
5. Verify close/Escape and focus return. If the opener was removed on success,
   inspect the next meaningful action and declared navigation behavior. BODY
   focus alone does not establish severity; document task impact and the next
   keyboard destinations.

Keep a still-open dialog's focus containment separate from closing it and
restoring focus. A successful retry does not erase a failure in the error state.
Never substitute a pointer-only test for keyboard recovery.

## Cancellation during processing

Start with a nonempty approved synthetic record. While loading/processing,
check whether close, Escape and any promised cancel control are available.
Record cancellation acceptance separately from dismissal and later commits.
If cancellation cannot be invoked, mark late-result-after-cancel checks not_run,
not another failure. Compare prior stored bytes before/after incomplete work.
A bounded delayed local response can expose a transient phase; document exactly
what was delayed, preserve served product bytes and do not report natural timing
or worker execution that the delay prevented. Release owned delays and close
the test browser/server, including on failure.

## Evidence and limits

Record each action, resulting UI state, focused element, outcome and time.
Screenshots cannot establish focus isolation on their own. Include actual
runtime/build hashes and distinguish an existing built artifact from a fresh
source build. Preserve failed harness attempts separately from product findings.

Record keyboard reachability and visible focus separately. After recording where
focus landed on recovery, use Tab or Shift+Tab to compare the same control with
focus on it and off it. Keep the build, viewport, scroll position, theme and
error state the same in both captures; include the control and its surroundings
so a clipped indicator is visible. Identify what changes at the control, not
elsewhere on the screen. A matching focused role/name proves the destination,
not a visible cue. If the state cannot be held comparable, keep the observed
destination and report cue visibility as unverified.

For visible labels, handle rendered nonbreaking spaces deliberately without
altering the product text or accepting a different control.

If a browser filechooser was opened by Enter but automation supplied the files,
that proves application-level invocation, not native OS picker keyboard use.
State screen reader, real-device, native UI and other excluded checks explicitly.
Keep setup errors, unavailable controls and unvisited states as not_run/blocked.

For every outcome, separate:
- PRD-linked obligation and its actual result.
- Technical focus/recovery observation, expected behavior and impact.
- Synthetic persona assumptions and unmeasured real-user effects.

Changes still require product-edit authority and the project's design/intent
checks. A verified defect in a QA target does not authorize changing that target.

## Korean input: distinguish composition from the intended action

For a Korean search, form or composer, use a disposable record and a supported
OS input method on the target device (e.g. macOS Safari with a Korean keyboard
or iPhone Safari with the Korean software keyboard). Record OS, browser/app
build, keyboard layout and physical/software input. Use a phrase with a final
syllable and an edit or candidate-selection step, such as `한글 검색`. Exercise
the platform's actual confirm/cancel controls and only use Enter or Escape
where those keys apply. Do not assume every Korean input path exposes a separate
inline composition session.

- While composing or confirming text, verify no unintended submit, send, save,
  clear, or dismiss. Distinguish intentional live search updates from a final
  search or committed action. Where composition cancellation exists, verify
  its effect separately from clearing the field or dismissing the UI. Preserve already confirmed text unless the user explicitly clears it.
- Verify the complete committed value, including the last syllable. Then
  explicitly invoke the product action once and confirm that the full value
  arrived at the expected result or disposable stored record exactly once.
- Record observable text and action counts; event traces are diagnostic, not
  the pass criterion. A complete-string test, paste, Playwright
  [insertText](https://playwright.dev/docs/api/class-keyboard#keyboard-insert-text)
  or dispatched composition events may test downstream handling or a targeted
  regression, but do not establish that the OS keyboard path was tested.
  Mark native input not run if the target device or keyboard is unavailable.

[React Aria's SearchField report](https://github.com/adobe/react-spectrum/issues/10249)
and its [merged fix](https://github.com/adobe/react-spectrum/pull/10200) document
an unintended Enter/Escape interaction. [WebKit's Korean input report](https://bugs.webkit.org/show_bug.cgi?id=274700)
describes paths without inline composition events; a [separate WebKit change](https://bugs.webkit.org/show_bug.cgi?id=317127)
disabled a key-event order correction after regression reports. These justify
checking the actual keyboard and build, not assuming that every current browser
is affected or prescribing a universal event-handler fix.
