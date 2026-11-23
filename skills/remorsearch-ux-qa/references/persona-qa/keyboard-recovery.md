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

## Same focused control across a sticky breakpoint

Use an existing, authorized synthetic flow with an author-created sticky footer
and a control it can cover. In one browser at a time, start from the same task
state at a wide and a narrow CSS viewport. Use the same Tab or Shift+Tab path to
the same logical control. Record browser/build, CSS viewport, scroll container
and offset, whether the footer is sticky, and the actual focused control. If
the control has no matched counterpart, record that rather than comparing
different controls as if only viewport width changed. If focus lands on the
wrong control or is lost, record that separately from occlusion.

At keyboard focus arrival, capture the rendered control and footer together;
record any intervening automatic scroll and the settled result before another
input. Distinguish complete, partial and no coverage of the control itself.
Record [indicator visibility](https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html)
and contrast separately. Do not infer coverage from intersecting rectangles
or focus from pixels alone. Then try ordinary user scrolling without changing
focus: record whether the same control becomes visible and usable, or whether
focus actually moved. Later recovery does not erase a covered focus stop.
Hiding only after incidental scroll is a separate observation, not by itself
a focus-arrival failure.

[WCAG 2.2 SC 2.4.11 (AA)](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html)
addresses a component entirely hidden by author-created content on receipt of
keyboard focus; see [F110](https://www.w3.org/WAI/WCAG22/Techniques/failures/F110).
Partial coverage alone is not a 2.4.11 failure; assess
[2.4.12 (AAA)](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-enhanced.html)
and actual usability separately. The user-opened-content note is not an exemption
for an always-present authored footer. [C43](https://www.w3.org/WAI/WCAG22/Techniques/css/C43)
shows a responsive reference, not a mandated fix. Report
[KWCAG 2.2 6.1.2 focus order and indication](https://www.rra.go.kr/ko/reference/kcsList_view.do?nb_seq=5247&nb_type=6)
separately, not as an equivalent occlusion result. Mark unobserved rendering,
browser software keyboard, device safe area and assistive technology as
`not_run`; a CSS viewport check is not a compliance or product verdict.

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
