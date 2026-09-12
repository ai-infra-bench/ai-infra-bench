"""Unprivileged candidate timing child; it never writes a reward.

The parent owns the input snapshot and frozen native file and validates the
complete sample record. Capturing timing functions reduces accidental or simple
rebinding interference; it is not a sandbox against arbitrary native code.
"""

import hashlib
import json
import os
from pathlib import Path
import sys

import torch


def main():
    if os.getuid() == 0:
        raise RuntimeError("candidate timing must run unprivileged")
    native, native_sha, snapshot, snapshot_sha, group = sys.argv[1:]
    for path, expected in ((native, native_sha), (snapshot, snapshot_sha)):
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise RuntimeError("timing input/artifact digest mismatch")
    event_cls = torch.cuda.Event
    elapsed = event_cls.elapsed_time
    synchronize = torch.cuda.synchronize
    empty_like, empty = torch.empty_like, torch.empty
    group = int(group)
    x = torch.load(snapshot, map_location="cuda", weights_only=True).contiguous()
    shape = list(x.shape)
    torch.ops.load_library(native)
    op = torch.ops._C.per_token_group_quant_int8

    def work():
        q = empty_like(x, dtype=torch.int8)
        scale = empty(x.shape[:-1] + (x.shape[-1] // group,),
                      device=x.device, dtype=torch.float32)
        op(x, q, scale, group, 1e-10, -128.0, 127.0)

    for _ in range(40):
        work()
    synchronize()
    samples = []
    for _ in range(5):
        start, end = event_cls(enable_timing=True), event_cls(enable_timing=True)
        start.record()
        for _ in range(400):
            work()
        end.record()
        end.synchronize()
        samples.append(elapsed(start, end) / 400)
    print("INT8_TIMING=" + json.dumps({
        "shape": shape, "group_size": group, "samples_ms": samples,
        "warmup": 40, "iterations": 400, "repeats": 5,
        "native_sha256": native_sha, "input_sha256": snapshot_sha,
        "actual_uid": os.getuid(),
    }), flush=True)


if __name__ == "__main__":
    main()
