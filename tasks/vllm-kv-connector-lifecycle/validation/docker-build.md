# Current build and validation

The task uses the unchanged Dockerfile and the original digest-pinned v0.20.1 runtime. The September 19 hardening rebuild downloads and verifies that original OCI index and its linux/amd64 layers. To avoid repeated remote Git transfers, the build supplies `VLLM_REPO=git://127.0.0.1:19662/vllm.git`, a local mirror containing only Base and its reachable history. The Dockerfile still verifies the exact upstream commit and tree, retains full history and removes source remotes and fetch metadata.

The daemon and its containerd store are isolated under `/data/pr62-review-20260919/docker-isolated/`; no shared Docker images or containers are removed. The client uses Docker 29.2.1, Compose 5.5.1, Buildx 0.37.0 and Harbor 0.22.0. Tests run on CPU with no runtime network access.

Raw build, image audit, control and Harbor logs are retained under `/data/pr62-review-20260919/`. The current image manifest and `e2e-evidence.json` identify the exact image and executable snapshot. Results obtained with a v0.20.2 diagnostic donor are labeled separately and are not cutoff certification.

Earlier build notes and results are retained under `history/`. Their image IDs, source acquisition method, control implementations and success-marker verifier belong to previous snapshots and do not certify this version.
