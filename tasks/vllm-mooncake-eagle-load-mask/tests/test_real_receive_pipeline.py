#!/usr/bin/env python3
"""Exercise real Mooncake receive threads and verify target-buffer contents."""

from __future__ import annotations

from verifier_support import (
    HYBRID_PROFILES,
    MAMBA_PROFILE,
    MIXED_PROFILE,
    NON_EAGLE_PROFILES,
    SINGLE_EAGLE_PROFILES,
    run_receive,
)


def main() -> int:
    try:
        cases = [
            run_receive(SINGLE_EAGLE_PROFILES[4]),
            run_receive(NON_EAGLE_PROFILES[1]),
            run_receive(HYBRID_PROFILES[3], tp_rank=1),
            run_receive(MIXED_PROFILE, tp_rank=2),
            run_receive(MAMBA_PROFILE),
            run_receive(HYBRID_PROFILES[1], tp_rank=1, request_count=4),
        ]
        print(
            {
                "entrypoint": "KVCacheStoreRecvingThread",
                "cases": [case.__dict__ for case in cases],
                "verified_buffer_blocks": sum(
                    case.verified_blocks for case in cases
                ),
                "concurrent_requests": 4,
                "transport": "in-memory store writing deterministic bytes to ctypes buffers",
            },
            flush=True,
        )
        return 0
    except Exception as exc:
        print(
            {
                "error": type(exc).__name__,
                "message": str(exc).splitlines()[0] if str(exc) else "no message",
            },
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
