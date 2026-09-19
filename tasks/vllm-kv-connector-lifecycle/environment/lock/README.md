# Environment lock

The source is `vllm-project/vllm` at `f80aa53c9dc2273a19a6855092069db7e1306fff`, with root tree `2af517bd7880077a9fed9a39dc0e8b1e244a48b1` and cutoff `2026-05-09T21:46:52Z`.

The Dockerfile fetches the exact commit, deepens the clone until all reachable history is present, and checks out branch `main`. It removes remotes, tags, remote refs, reflogs and fetch metadata, then checks that the repository is not shallow and has no unreachable objects. The final checkout uses the real upstream commit, not a synthetic archive commit.

The runtime is pinned to `vllm/vllm-openai:v0.20.1@sha256:9eff9734a30b6713a8566217d36f8277630fd2d31cec7f0a0292835901a23aa4`. The source cutoff falls between v0.20.1 and v0.20.2. No task-layer Python dependency resolution runs; the installed runtime comes from the pinned image. Build tools installed with apt do not determine constructor dispatch.

All candidate Python code comes from the exact source checkout. `native-paths.txt` lists the ten generated/native files copied from the pinned runtime: nine shared libraries and `_version.py`. The build rejects missing files, symlinks and non-ELF shared libraries, and checks that the resulting working tree is clean. Generated/native files are ignored by upstream Git rules.

The constructor and lifecycle workload uses CPU only. It needs no model, tokenizer, GPU, dataset or network access. Normal build networking fetches apt packages and upstream Git history; runtime networking is disabled. `task.toml` retains a 10-hour agent budget.

Only `environment/` is sent as the image build context. The task statement, solution, verifier, controls and evidence are never copied into the agent image. Harbor supplies the verifier later in the agent's container. The current image identity is recorded in `environment/image-manifest.json`; actual audit results belong with the CI or Harbor run records. Earlier build notes are historical evidence only.
