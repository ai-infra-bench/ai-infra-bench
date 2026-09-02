# Remediation matrix

| ID | Severity | Finding and evidence | Planned change | Validation | Status |
|---|---|---|---|---|---|
| C1 | blocking | PR #38933 has no linked issue; its only user context is the reported RL batch-one workload and ~205 ms recompile overhead. | Start from that observable pause and avoid inventing serving hardware or traffic. | Public compile-count trace and source timeline align. | fixed |
| C2 | blocking | Environment and cutoff lock are not materialized. | Build the squash-parent CPU image with deterministic Dynamo instrumentation. | Lock, warm digest, Git, dependency, layer, hidden-file, and network audits pass. | fixed |
| C3 | blocking | Verifier independence and shape/error boundaries require validation. | Count real Dynamo graphs through `Sampler.gather_logprobs`, check outputs and invalid dimensions, and challenge partial symbolic fixes. | Base/Oracle five rounds, alternative 1, partial fixes 0. | fixed |
| C4 | blocking | Evidence and Harbor identifiers are missing. | Record actual hashes, limitations, compile counts, image, and final Harbor result. | Evidence audit and Harbor Oracle pass. | fixed |
| C5 | blocking | Exact-cutoff resolution failed because the base requires torch 2.11 CPU wheels uploaded on 2026-04-27, after the 2026-04-09 source cutoff. | Add package-scoped torch/torchaudio/torchvision overrides through 2026-05-01 with the base-requirement reason recorded. | Lock resolves while every unrelated package remains cutoff-bound. | fixed |
