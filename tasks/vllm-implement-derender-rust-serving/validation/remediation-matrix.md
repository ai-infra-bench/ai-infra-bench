# Qualification findings

D1–D8 are historical construction records at PR head `2e654d4`. D9–D10 below describe the current hardening.

| ID | Gate | Finding | Resolution | Status |
| --- | --- | --- | --- | --- |
| D1 | Statement | User explicitly froze the short query. | Preserve exact instruction bytes; no explanatory or test-specific clauses added. | fixed |
| D2 | Environment | A Rust task needs an executable render CLI and offline development dependencies. | Adapt merged task Docker structure, build at exact Base, retain Cargo vendor sources and real Qwen metadata. | fixed |
| D3 | Oracle | Older proposal's decoded-event and usage types do not compile at the selected Base. | Adapt to native attributed decoded text, sampled metadata, boxed finish and current usage types. | fixed |
| D4 | Verification | Ordinary token boundaries could let a stateless implementation pass a restart example. | Stop inside a Unicode character before killing the original instance; the discard-state control now fails both restart cases. | fixed |
| D5 | Verification | State layout must not be tied to the Oracle. | Full-history/native-decoder alternative passes all 49 HTTP cases and existing API regressions. | fixed |
| D6 | Verification | Generic malformed implementations are insufficient negative controls. | Four compilable complete variants fail only their intended state, parsing, logprob or usage behavior; existing APIs pass. | fixed |
| D7 | Qualification | Restoring old file timestamps caused a reused container to execute a cached mutation. | Rebuild restored Oracle source; fresh Harbor and five final rounds pass. Retain failed attempt separately. | fixed |
| D8 | Publication | Final evidence must identify exact executables and actual trials. | Record image, hashes, Python/Base/Oracle/control/stability outcomes and completed Harbor trial; strict audit is the final gate. | fixed |

The broad vllm-text network-dependent diagnostic is an environment limitation
outside the rewarded target boundary, not a claim of full offline upstream CI.

| ID | Gate | Finding | Resolution | Status |
| --- | --- | --- | --- | --- |
| D9 | Verification, P1 | Base Rust entry point delegates to Python and receives reward 1 despite the explicit native-serving contract. | Verifier-only native runtime, retained trusted Python client, explicit forwarding control and fresh Harbor reward 0. | fixed |
| D10 | Oracle/verifier, P1 | Both qualified algorithms lose legitimate terminal U+FFFD and incomplete byte tails. | Flush both endpoint decoders at termination; add 18 semantic continuation cases, repair replay alternative and add omit-flush control. Oracle/alternative receive 1; omitted flush receives 0. | fixed |

No task statement or image change was needed. Final direct versions, two HTTP
stability rounds per qualified positive native binary, independent challenges and three
fresh Harbor results are recorded in `e2e-evidence.json`. New test assertions
were audited for fairness: completed-stream replay and fixed emission timing
on an empty nonterminal chunk are not hidden requirements.
