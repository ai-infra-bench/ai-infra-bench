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
establish a candidate failure. Existing controls exercise renamed selectors
and a public custom SelectList, without claiming support for every terminal UI.

A `plan_submit` tool result can display the plan. The verifier renders the actual
`ToolExecutionComponent` with `setExpanded(true)`, corresponding to a user's tool
expansion action. Registered custom renderers still determine visible text:
hidden result fields do not satisfy the display assertion. Approved execution
context is checked independently of display.

Adapting interaction does not change assertions for stale approval, exact
execution, Stay, Refine, restrictions or persistence. The reviewed Plan Mode
v0.0.11 campaign also checked a verbose expanded-result positive control and a
custom renderer that hides the plan as a negative control.
