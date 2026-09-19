# Environment rebuild

The r2 image is built from the same digest-pinned v0.21.0 native donor and the exact Base commit. Its build context is `environment/` only. The rebuilt manifest excludes PR identifiers, target-source mappings, Oracle mount paths and task-specific diagnosis. Those fields never enter a build layer.

Build command: `docker build --network host -t ai-infra-bench/vllm-mamba-full-cg-decoding:base-737bfa3a43ce-r2 environment`. Host networking is used only to fetch pinned build inputs; agent and verifier execution use network none. Runtime needs one A100, four CPUs and 24 GiB RAM. The local Harbor adapter binds exactly one GPU and enforces network none for both containers; it does not modify candidate code or scoring.

The source checkout retains Base history, has no remote, tags, remote refs, reflogs, fetch metadata or unreachable future objects, and imports Python/Triton and native wrappers from the expected checkout. Runtime Python dependencies are inherited from the pinned donor. The image identity and artifact hashes are recorded in `environment/image-manifest.json` and `validation/e2e-evidence.json`.

Later upstream reports inform additional tests only when their behavior belongs to this contract and can occur at the frozen Base. Oracle compatibility is not a reason to omit such a test. This revision reproduced a mixed fresh/stateful request defect and updated the reference patch accordingly. It does not claim to reproduce a later multi-GPU hybrid-model accuracy report.
