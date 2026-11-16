# Plan Mode interaction checks

The current task defines visible `Execute`, `Stay`, and `Refine` action identifiers, the `→` selection marker, Up/Down navigation, and Enter activation. Action order, explanations, styling, and the UI implementation remain open.

The verifier renders Pi’s actual UI and navigates these public controls through `tests/ui_review_driver.mjs`. It checks the displayed plan, the selected action, the approved snapshot, and the resulting state independently. A select widget, a custom component, delayed rendering, a refresh, and a reordered action list are represented in the declared controls. Navigation alone, Stay, Refine, and stale review windows must not execute a newer plan.

An expanded `plan_submit` tool result may display the plan. Hidden structured fields cannot replace visible text. Approved execution context is checked separately using the current session, plan identity, revision, and complete steps.

No submission-specific UI binding or reviewed replay profile is required. Use the public validation entrypoint described in [validation and regrading](pi-reviewed-replay.md).
