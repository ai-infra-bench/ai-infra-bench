#!/usr/bin/env python3
"""Prove offline runtime, GPU selection and candidate native provenance."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import socket
import subprocess

import torch
import vllm


def main() -> None:
    root = pathlib.Path("/app").resolve()
    python_source = pathlib.Path(vllm.__file__).resolve()
    native_spec = importlib.util.find_spec("vllm._moe_C")
    assert native_spec and native_spec.origin
    native = pathlib.Path(native_spec.origin).resolve()
    assert python_source.is_relative_to(root)
    assert native.is_relative_to(root)
    torch.ops.load_library(str(native))
    assert torch.ops._moe_C.moe_permute_unpermute_supported()
    assert torch.cuda.is_available()

    sock = socket.socket()
    sock.settimeout(1.0)
    try:
        connect_ex = sock.connect_ex(("1.1.1.1", 443))
    finally:
        sock.close()

    git_tree = subprocess.check_output(
        ["git", "-C", "/app", "rev-parse", "HEAD^{tree}"], text=True
    ).strip()
    git_status = subprocess.check_output(
        ["git", "-C", "/app", "status", "--porcelain=v1", "--untracked-files=all"],
        text=True,
    )
    properties = torch.cuda.get_device_properties(0)
    print(
        json.dumps(
            {
                "candidate_native": str(native),
                "candidate_python_source": str(python_source),
                "compute_capability": list(torch.cuda.get_device_capability(0)),
                "cuda_available": True,
                "git_clean": git_status == "",
                "git_commit_count": int(
                    subprocess.check_output(
                        ["git", "-C", "/app", "rev-list", "--count", "HEAD"],
                        text=True,
                    )
                ),
                "git_remote_count": len(
                    subprocess.check_output(
                        ["git", "-C", "/app", "remote"], text=True
                    ).splitlines()
                ),
                "git_tree": git_tree,
                "gpu_name": properties.name,
                "gpu_uuid": str(properties.uuid),
                "moe_permute_supported": True,
                "network_connect_ex": connect_ex,
                "torch": torch.__version__,
                "torch_cuda": torch.version.cuda,
            },
            sort_keys=True,
        )
    )
    assert connect_ex != 0
    assert git_status == ""
    assert git_tree == "89beecb205e031cbb82e2eea9d2cd0f350135b8c"


if __name__ == "__main__":
    main()
