# Remediation matrix

The behavior contract is frozen as follows: a multi-node Ray compiled-DAG
execution that carries vLLM logprob results must continue serving subsequent
results while preserving request metadata, token IDs, logprob values, sampled
ranks, and cumulative-token boundaries. The internal representation may be
NumPy arrays or Python lists, and the fix may occur at any layer that satisfies
that behavior.

| ID | Severity | Finding and evidence | Contract impact | User approved? | Planned change | Validation | Status |
|---|---|---|---|---|---|---|---|
| R1 | blocking | The verifier constructs `LogprobsLists` from NumPy arrays and requires detachment at `FutureWrapper.result()`, so it rejects restoring the pre-4228be Python-list representation even though the issue reporter confirmed that reverting 4228be fixes the service failure. | Rewards one implementation boundary and an undisclosed internal representation instead of the service behavior. | yes | Generate the E2E payload through the real `LogprobsTensors.tolists()` production conversion, compare values representation-neutrally, remove unit assertions about memory sharing and dtype, exercise downstream logprob processing, and add a revert-to-lists positive control. | Base timed out in five of five rounds; Oracle and the restore-list alternative scored 1; every incomplete control scored 0. | fixed |
| R2 | blocking | Evidence records instruction SHA-256 `9cf40e...`, while the current instruction is `318282...`; its Harbor checksum identifies the previous task revision. | Publication evidence does not identify the current task. | yes | Regenerate all changed artifact hashes and actual run records, then run final Harbor Oracle against the final task checksum. | Final Harbor job `fb4352f8-d209-4781-a94a-5a85705c495f` used task checksum `79040c336fcdc15318623380bb8ad604bd9ecd9367c7ca399a088b788bf76466`, completed one trial with reward 1, and had zero errored trials. | fixed |
| R3 | blocking | Logprob-bearing E2E outputs leave `sampled_token_ids` empty, while only the `logprobs=None` control checks generated tokens. | A patch can keep logprobs and later channel reads correct while corrupting the completion result that the instruction explicitly requires preserving. | yes | Populate generated token IDs for every logprob case, require them to match the selected token represented by the first logprob entry, cover them in repeated functional cases, and add a control that fixes the channel but clears generated tokens. | Base failed at the channel boundary in five of five rounds; Oracle and all four correct alternatives preserved generated tokens and scored 1; the corrupt-result control scored 0. | fixed |
