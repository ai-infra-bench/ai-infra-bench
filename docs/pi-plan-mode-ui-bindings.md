# Reviewing Plan Mode interaction bindings

Plan Mode specifies review behavior, not exact labels or a particular Pi UI
primitive. Reviewers can supply `tests/ui-actions.json` in the trusted verifier
input. Never load this file from the candidate workspace.

For `ctx.ui.select`, map `select.execute`, `select.stay` and `select.refine` to
exact visible labels. For `ctx.ui.custom`, each `custom.<action>` supplies a
visible `label` and raw terminal `keys`; the host uses Pi's actual TUI, theme and
keybinding manager. Choose bindings from visible controls and documented keys
before inspecting outcomes. Trying choices until one produces the expected
state could accept a mislabeled button.

Retain the bindings, their review basis, candidate snapshot and verifier hashes
before replay. An unmatched action requires integration review; it does not
establish a candidate failure. The harness supports selectors and a public custom SelectList, without claiming
support for every terminal UI.

A `plan_submit` tool result can display the plan. The verifier renders the actual
`ToolExecutionComponent` with `setExpanded(true)`, corresponding to a user's tool
expansion action. Registered custom renderers still determine visible text:
hidden result fields do not satisfy the display assertion. Approved execution
context is checked independently of display.

Adapting interaction does not change assertions for stale approval, exact
execution, Stay, Refine, restrictions or persistence. The reviewed Plan Mode
v0.0.11 campaign also checked a verbose expanded-result positive control and a
custom renderer that hides the plan as a negative control.

The checked-in `validation/tools/ui-reference.json` and `ui-renamed.json` are
explicit curator bindings. `renamed-visible-actions` uses Run approved steps,
Keep planning, and Revise draft and carries a separate binding from the reference.
There is no label-guessing fallback. Use the
[reviewed replay entrypoint](pi-reviewed-replay.md) to bind those inputs to the
materialized candidate and verifier before scoring. A binding file alone is
insufficient: missing or stale profiles remain unscored.
