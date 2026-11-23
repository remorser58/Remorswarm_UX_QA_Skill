# Information architecture and disclosure QA

Use this reference for information placement, navigation, warnings, prices, diagnostics, and sensitive views. Classify the information for this actor, task and state, not for a hypothetical average user. A label is helpful only if it leads to the content the user expects. Never substitute progressive disclosure for access control.

## Decide what to show

| Class | Rule | Example |
| --- | --- | --- |
| Must know before acting | Show plainly next to the decision, before commitment. Preserve meaning on narrow screens and in assistive reading order. | Total and renewal terms, who can see an item, what will be deleted, whether data was saved. Unknown values stay explicitly unknown; state what can change. |
| Useful on demand | Give a short, decision-useful summary; offer a specific disclosure label and a stable route to details. | Fee breakdown behind the total; step logs behind job status; optional explanations. Escalate a detail if it becomes important to the current failure. |
| Not needed on this path | Omit from the routine surface; keep only where needed for support or audit, under existing policy. | Internal stack traces, IDs, scheduler counters and debug context. Surface a safe support ID only when it helps recovery. |
| Must protect | Redact or remove before serving unauthorized views; gate intentional reveal. A collapsed panel, blurred text or CSS is not a security boundary. | Secrets, private message contents on a lock screen, other tenants' data. Test DOM/API, assistive output, logs and exports where in scope, using synthetic canaries. |

Resolve overlaps: protect raw details while showing a safe state or next action; do not hide consequences because the raw reason is sensitive. Set or revise the class when the role, privacy context, task stage, fault state or time changes. Never conceal an action's cost or irreversibility to improve conversion, and never disclose technical data solely because it is available.

## Convert into acceptance and replay

1. List actual PRD tasks, roles, starting states, and facts that could change a decision. Show prerequisites before the user invests work. Across screens, group by task/object where that matches user language. Keep consistent names for the same thing, and do not inflate categories based on internal teams or implementation.
2. For a findability task, write the goal in plain user language without leaking menu labels. Record predicted destination and first selection; replay from the normal entry point, follow the link, verify that the destination answers the question, and inspect back/return. A text-only tree test is for hierarchy and labels, not visual salience or accessibility.
3. For a decision task, validate the summary before activation. Include a paired fixture where hidden fees, stale status, or an uncommon condition changes which action is correct. Verify the disclosure link label, reading/focus order, values in detail vs summary, and safe return. Essential fields must not require exploring unrelated branches.
4. Replay one compact viewport and one relevant alternate input; include expanded/collapsed, expired/empty, and unauthorized or signed-out states only when the task warrants them. When validation needs a screenshot/accessibility snapshot or a resolved role, retain the existing evidence boundary. A synthetic trace shows a pathway, not real people understanding it.
5. Record facts and source scope for each case: source URL, date checked, service/platform/region/role, what the UI or official document shows, rationale explicitly stated (or not published), what we infer, counterexample and proposed replay. Never attribute an inferred rationale to the company or report this card as a completed comparative test.

## Case cards (public documentation, checked 2026-11-19)

- **GitHub Actions, failed run with repository read access.** [Workflow logs](https://docs.github.com/en/actions/how-tos/monitor-workflows/use-workflow-run-logs) documents run → job → steps; failed steps expand automatically, lines can be linked, and in-view search covers expanded steps. [The product team's rationale](https://github.blog/news-insights/product-news/a-better-logs-experience-with-github-actions/) is to help users find issues requiring action without losing the current step's context. Application: promote the failed step when action is needed, put routine logs in details, and never read a partial search as proof of absence. [Secure use](https://docs.github.com/en/actions/reference/security/secure-use) separately says transformations can defeat automatic redaction: expand/collapse is not a privacy control. Replay a mixed pass/fail fixture with a safe canary and check audience, search scope and evidence links without showing live secrets.
- **Apple, iPhone lock-screen notification preview.** [iPhone guide](https://support.apple.com/guide/iphone/iph7c3d96bab/ios) documents Always / When Unlocked / Never preview settings. [Notifications HIG](https://developer.apple.com/design/human-interface-guidelines/notifications) explains why to avoid private details when someone nearby might see the display, and why a safe generic description still helps decide whether to open. Application: separate event type from identity/content. Replay permitted settings × lock states and verify a synthetic title/body canary is present only in entitled states; don’t generalize defaults to all versions, apps or preview modes.
- **Airbnb, search and checkout.** The [price announcement](https://news.airbnb.com/total-price-display-is-now-standard-globally/) says its search total includes mandatory fees and explains that it helps budget comparisons. [Help: price breakdown](https://www.airbnb.com/help/article/125) documents the breakdown; [tax exceptions](https://www.airbnb.com/help/article/3610) are region/collection dependent. Application: show the decision value first and arithmetic on demand. Replay two equal-date/occupancy/currency fixtures whose rank flips when mandatory fees are added. Check search comparison, pre-confirmation total and breakdown; distinguish any separately collected cost.

## Research and transfer

- [Pirolli and Card, Information Foraging](https://doi.org/10.1037/0033-295X.106.4.643): proximal cues guide which path people pursue. A descriptive heading helps test destination expectations; a theory is not proof this label works for this product.
- [GOV.UK Details](https://design-system.service.gov.uk/components/details/) and [Accordion](https://design-system.service.gov.uk/components/accordion/) distinguish supplementary information from information most users need. [Check answers](https://design-system.service.gov.uk/patterns/check-answers/) provides a concrete review-and-edit path before submit. Apply the principle before choosing a component: do not copy government screens wholesale.
- [W3C cognitive accessibility pattern](https://www.w3.org/WAI/WCAG2/supplemental/patterns/o5p04-task-expectations/) advises revealing task prerequisites and steps early. This is supplementary guidance, not an additional WCAG conformance requirement. The [UK Office for Statistics Regulation's dashboard guidance](https://osr.statisticsauthority.gov.uk/guidance/regulatory-guidance-dashboards/pages/4/) puts decision-changing warnings by the data and methodology in supporting detail. In a product, test that missing/stale coverage is apparent beside the number, not merely buried in a glossary.
- Use existing product intent and access rules. For a UX change, keep decision facts and preserved styling explicit, carry before/after task and adjacent regression evidence, and use the existing Figma-first workflow where required. Record the implication of new sources or contradictions; do not add a new gate solely because a popular service uses a component.

## Evidence card: reach and dismiss help shown on hover or focus

In one reviewed owned synthetic screen, use an authored help popup with still-valid
information that covers nearby meaningful text. Pick a trigger with a harmless
known action. Use separate fresh pointer and keyboard trials on the same build,
viewport, fixture state and trigger. Record dismissal and the ordinary action separately.

- **Hoverable:** When pointer hover opens the popup, move the real pointer from
  the trigger onto the revealed content along an ordinary path. Capture whether
  it stays visible throughout the transfer. A matched negative control closes
  at the trigger edge before the pointer reaches the content.
- **Persistent:** In separate trials, dwell while the pointer still hovers the
  trigger, after transfer while it hovers the popup, and while the relevant
  keyboard focus holds, where each trigger applies. Keep the information valid.
  It should remain visible until hover or focus is removed from both the trigger
  and the additional content, the user dismisses it, or the information becomes
  invalid. A matched negative times out while the pointer is still over the popup
  and the information remains valid. Report only the interval observed.
- **Dismissible:** In separate trials, use the supported dismissal without moving
  the pointer or moving keyboard focus from the trigger, as applicable. Escape is
  an example, not the only mechanism. Verify that the covered content is visible
  again and the pointer coordinates or focused control are unchanged, with no
  ordinary trigger action or other side effect. A matched negative clears the
  obstruction only when the pointer moves away or keyboard focus advances.

The positive control retains the help during transfer and dwell, closes without
moving the pointer or focus, and leaves the trigger's ordinary action usable. Separately
activate the original trigger and check the expected harmless result; that is
a task-usability check, not an extra condition of WCAG 1.4.13.

[WCAG 2.2 SC 1.4.13](https://www.w3.org/TR/WCAG22/#content-on-hover-or-focus)
applies to additional content shown and hidden by hover or focus. Input errors
and content that neither obscures nor replaces other content are exceptions to
dismissibility only. User-agent visual presentation unmodified by the author is
excepted from the criterion (for example, a native `title` tooltip). Click-only
disclosure is outside this recipe. [SCR39](https://www.w3.org/WAI/WCAG22/Techniques/client-side-script/SCR39),
[F95](https://www.w3.org/WAI/WCAG22/Techniques/failures/F95) and
[F114](https://www.w3.org/WAI/WCAG22/Techniques/failures/F114) are examples.
Save the observed trigger, pointer endpoint, focus identity, validity and visible
before/after results by condition. An unavailable input path, state or evidence is
`not_run`, not a pass. This synthetic check does not establish touch, native
device, assistive-technology, product or WCAG conformance.
