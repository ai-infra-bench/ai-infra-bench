# Development-host Harbor integration

Author runs use Harbor 0.23.0, Docker 29.8.0, native Linux amd64 and the retained
Pi image recorded in `environment/image-manifest.json`. Every trial requests
4 CPUs, 8192 MiB and `no-network` in the environment, agent and verifier phases.

The first matrix (`matrix-final-20260915`) did not start any trial. Harbor's
Docker capability probe attempted to download its pinned Alpine image directly
from Docker Hub, timed out, and reported `no-network unsupported`. This was an
infrastructure error, not eleven reward-zero behavior results. The same digest
from the mirror ran its original probe successfully on this host.

`harbor_mirror.py` is an author-only launcher, run with the installed Harbor
Python. It verifies the expected upstream probe reference and changes only its
registry to `docker.m.daocloud.io`, retaining the identical SHA-256 digest.
It does not override capabilities, network policy enforcement, user identities,
task settings, verifier or scoring. It is not copied into the agent image.

The next smoke attempt could not build Harbor's original egress sidecar because
DaoCloud does not mirror `gogost/gost`. Its unmodified pinned Dockerfile was
subsequently built with a separate `pi-plan-harbor-builder`, using a temporary
localhost CONNECT proxy over SSH for public Docker registry downloads. Both
BuildKit and the invoking client needed that proxy for the registry token
request. This produced Harbor's expected content-addressed sidecar tag
`harbor-prebuilt:harbor-docker-egress-control-sidecar--9af3dc172792cee8`.
Its retained image ID is
`sha256:77470b5243879242e282334311947d4486a84fd474912b21ddbc3d1dd2bc3f98`.
No installed Harbor source or Docker daemon configuration was changed.

On this development host, the launcher is:

```sh
/data00/home/xingjunqian/harbor-workspace/pi-plan-mode/harbor-mirrored
```

It invokes the installed Harbor Python and the repository's `harbor_mirror.py`.
After the required images are cached, trial execution needs neither the proxy
nor build-time internet. Original setup logs, failed attempts and actual job
artifacts remain under `/data00/home/xingjunqian/harbor-workspace/pi-plan-mode/`.
The completed acceptance matrix is identified by `e2e-evidence.json`; earlier
failed or interrupted setup attempts are not counted as successful validation.

The temporary CONNECT proxy and SSH reverse tunnel were stopped after the
sidecar build, while the acceptance matrix ran using cached images.

After validation, both task-specific BuildKit containers were stopped. Their
build caches and the retained Pi/Harbor images remain available for review.
