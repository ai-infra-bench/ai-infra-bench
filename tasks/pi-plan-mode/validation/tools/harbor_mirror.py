#!/usr/bin/env python3
"""Author-only Harbor launcher for a devbox unable to reach Docker Hub.

Run with Harbor's own Python. The only provider override changes its kernel
probe image registry to a mirror of the identical digest; no capability,
network enforcement, task configuration or grading behavior is overridden.
Set BUILDX_BUILDER to the existing mirror-enabled builder for sidecar builds.
"""
from harbor.environments.docker.docker import DockerEnvironment
from harbor.cli.main import app

PROBE_DIGEST = "sha256:5b10f432ef3da1b8d4c7eb6c487f2f5a8f096bc91145e68878dd4a5019afde11"
expected = f"alpine:3.23.4@{PROBE_DIGEST}"
if DockerEnvironment._EGRESS_CONTROL_KERNEL_PROBE_IMAGE != expected:
    raise RuntimeError("Harbor probe changed; review this adapter before use")
DockerEnvironment._EGRESS_CONTROL_KERNEL_PROBE_IMAGE = f"docker.m.daocloud.io/library/alpine:3.23.4@{PROBE_DIGEST}"

if __name__ == "__main__":
    app()
