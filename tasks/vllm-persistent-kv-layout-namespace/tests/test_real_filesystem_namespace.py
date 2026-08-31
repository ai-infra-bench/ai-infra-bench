#!/usr/bin/env python3
"""Exercise persistent compatibility through real asynchronous filesystem I/O."""

from __future__ import annotations

import tempfile

from verifier_support import (
    DEFAULT_CASE,
    LAYOUT_CASES,
    incompatible_layout_lifecycle,
    layout_specific_parallel_miss,
    legacy_portable_read,
    portable_cross_parallel_lifecycle,
)


def main() -> int:
    try:
        with tempfile.TemporaryDirectory(prefix="persistent-layout-e2e-") as root:
            incompatible_layout_lifecycle(root, DEFAULT_CASE)
            incompatible_layout_lifecycle(root, LAYOUT_CASES[2])
            for parallel in (
                {"tp_size": 4, "rank": 3},
                {"pp_size": 3, "rank": 2},
                {"pcp_size": 2, "rank": 1},
                {"dcp_size": 4, "rank": 3},
            ):
                portable_cross_parallel_lifecycle(root, DEFAULT_CASE, parallel)
            layout_specific_parallel_miss(
                root, DEFAULT_CASE, {"tp_size": 2, "rank": 1}
            )
            legacy_portable_read(root, DEFAULT_CASE)
        print(
            {
                "entrypoint": "FileSystemTierManager",
                "incompatible_layout_misses": 2,
                "portable_cross_parallel_loads": 4,
                "layout_specific_parallel_misses": 1,
                "legacy_portable_loads": 1,
                "real_manager_restarts": True,
                "multi_key_data_roundtrips": True,
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
