# Remediation scope

| Review finding | Change | Behavioral evidence |
|---|---|---|
| The statement includes workdir boilerplate and hard-wrapped prose | Natural developer request, one logical line per paragraph, explicit lifecycle and probe contract | `instruction.md` |
| Only one aggregate endpoint was fully checked | Observe health, ready and readyz before, during and after readiness | `readiness`, `probe_settings`; premature-ready control |
| Probe options could be ignored without rejection | Actual probe spacing, delayed responses, per-rank reset, exact threshold and connection failures | Ignored-options and wrong-threshold controls |
| Invalid startup could leave a nonresponsive listener | Check TCP refusal and retained/adopted process identities before teardown | Invalid-listener control |
| A dead rank could orphan its engine descendants | Oracle adopts and reaps descendants; verifier creates actual nested processes and sockets | Rank death before and after readiness; orphan control |
| Rebinding one imported callable rejected valid aliases | Preserve backend callable identities while retaining real serving entrypoints | Sequential-probe implementation with early run-server alias |
| Old image/history/result descriptions no longer matched artifacts | Separate archived evidence, exact Base/tree provenance, rebuilt image and frozen checksums | Image manifest, final evidence and review report |

The reference implementation is not exempt from any check. Historical Oracle commit metadata identifies the basis only; the current solution patch includes additional contract-driven fixes.
