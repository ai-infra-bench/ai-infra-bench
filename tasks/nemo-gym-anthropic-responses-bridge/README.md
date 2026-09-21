# NeMo Gym Responses–Messages bridge

Author: 李岱霖. The initial public release is `1.0.0`; `v0.0.10` identifies
the previously reviewed development snapshot.

This task asks for a reusable bidirectional converter between OpenAI Responses
and Anthropic Messages, plus a default Messages route backed by Gym's existing
Responses implementation. The motivation is collecting coding-agent rollouts
with different harness protocols against the same RL infrastructure.

The solver receives `instruction.md` and
[environment/bridge-contract.md](environment/bridge-contract.md) (installed at
`/opt/nemo-gym/docs/bridge-contract.md`). The public contract defines the supported
subset, including tool history, request and response conversion, Messages SSE,
errors and usage. It does not require provider credentials or model weights.

The source is [NVIDIA NeMo Gym](https://github.com/NVIDIA-NeMo/Gym), pinned to
`797db2912ced96991ae4944a3fffc9d9c445ece0`. Dependencies are recorded under
`environment/lock/`; execution is offline. The agent and verifier use separate
containers. Harbor transfers the solved `/workspace/Gym` checkout to the verifier,
while the standard collection hook retains a patch and untracked-file archive
for review. Collection failures must remain execution failures.

`tests/test.sh` evaluates 27 behavior groups. Reward 1 requires every group to
pass; this is not a claim of complete support for either provider's entire API.
`validation/ci-cases.json` declares Base, Oracle and controls through the common
CI runner. Control patches apply directly to the pinned Base, as their manifest explicitly
records. Raw trajectories and run records belong outside this task directory.

The v0.0.10 cross-review and three GPT-6 attempts were evaluated before public
packaging. Packaging retains their statement, contract and behavior scorer;
current Harbor integration is checked separately before delivery.
