# Environment rebuild

The r3 image is built from the same digest-pinned v0.21.0 native donor and the exact Base commit. Its build context is `environment/` only. The rebuilt manifest excludes PR identifiers, target-source mappings, Oracle mount paths and task-specific diagnosis. Those fields never enter a build layer.

Build command: `docker build --network host -t ai-infra-bench/vllm-mamba-full-cg-decoding:base-737bfa3a43ce-r3 environment`. Host networking is used only to fetch pinned build inputs; agent and verifier execution use network none. Runtime needs one A100, four CPUs and 24 GiB RAM. The local Harbor adapter binds exactly one GPU and enforces network none for both containers; it does not modify candidate code or scoring.

The source checkout retains Base history, has no remote, tags, remote refs, reflogs, fetch metadata or unreachable future objects, and imports Python/Triton and native wrappers from the expected checkout. Runtime Python dependencies are inherited from the pinned donor. The image identity and artifact hashes are recorded in `environment/image-manifest.json` and `validation/e2e-evidence.json`.

Later upstream reports inform additional tests only when their behavior belongs to this contract and can occur at the frozen Base. Oracle compatibility is not a reason to omit such a test. This revision reproduced a mixed fresh/stateful request defect and updated the reference patch accordingly. It does not claim to reproduce a later multi-GPU hybrid-model accuracy report.

The current image was built by CI from the HTTPS-source recipe and audited locally. Both Ubuntu sources use HTTPS; package versions and signature checks remain unchanged and no retry logic was added. The local validation adapter mirrors the exact image source into a separate data-disk directory for each agent/verifier phase and restores its agent ownership. It also isolates compiler caches and uses executable temporary storage. This avoids the full host root disk without changing submitted code, reference code, artifact transfer or scoring.
