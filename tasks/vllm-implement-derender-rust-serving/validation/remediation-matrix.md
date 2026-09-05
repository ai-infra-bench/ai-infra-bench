# Qualification findings

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
