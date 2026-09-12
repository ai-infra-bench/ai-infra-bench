#!/usr/bin/env python3
"""Task-owned, independent recomputation of the expected correctness digests.

The worker's ``case_digests`` must not be believed merely because they are
well-formed and distinct: 18 randomly generated distinct digests would satisfy a
distinctness test. This helper recomputes, from the task's own deterministic
input construction and REFERENCE semantics only, the exact digest each case must
produce -- so the scorer compares against a value it derived itself.

Reference semantics used here (no candidate kernel involved):
  * inputs are seeded deterministically (``torch.manual_seed(32892 + n_token)``),
    so ``topk_ids`` is reproducible;
  * aligned offsets are ``cumsum(ceil(count/ALIGN)*ALIGN)`` per expert;
  * unaligned offsets are ``cumsum(count)`` per expert;
  * ``inverse`` is the permutation index the reference derives from the same ids.

SCOPE (deliberately conservative): the digest covers the per-expert OFFSETS plus
the shape/dtype fingerprint. Offsets are provably derivable here -- the verifier
already asserts them byte-exactly against this same cumsum formula, so an
independent recomputation is sound.

The ``inverse`` permutation is NOT included. Its exact tie-ordering is a property
of the kernel's implementation, and asserting a reference argsort against it
without GPU confirmation could fail a correct implementation. Including it is
tracked as future work; excluding it keeps this helper's expectation exact rather
than merely plausible.
"""

from __future__ import annotations

import hashlib
import json
import struct

N_EXPERT = 64
TOPK = 6
HIDDEN = 2048
ALIGN = 128
CORRECTNESS_TOKENS = (1, 32, 128, 512, 1000, 1024, 2048, 3000, 4096)


def _offsets_int64(n_token: int, aligned: bool) -> bytes:
    """Reference per-expert offsets, packed as little-endian int64 bytes.

    Pure stdlib on purpose: the trusted scorer must be able to derive this
    expectation without importing torch or numpy, i.e. without loading anything
    the candidate can influence. The task's routing ids are a closed-form
    function of the token/expert indices (no RNG draw is consumed), so this
    reproduces the same integers the verifier asserts byte-exactly, and ``<q``
    packing matches a contiguous torch int64 tensor's ``tobytes()`` layout.
    """
    counts = [0] * N_EXPERT
    for t in range(n_token):
        for r in range(TOPK):
            counts[(t * 17 + r * 7) % N_EXPERT] += 1
    if aligned:
        windows = [((c + ALIGN - 1) // ALIGN) * ALIGN for c in counts]
    else:
        windows = counts
    offsets = [0]
    acc = 0
    for w in windows:
        acc += w
        offsets.append(acc)
    return struct.pack(f"<{len(offsets)}q", *offsets)


def expected_case_digest(n_token: int, aligned: bool) -> str:
    return hashlib.sha256(
        b"|".join([
            f"{n_token}:{aligned}".encode(),
            _offsets_int64(n_token, aligned),
            f"inv_shape={n_token}x{TOPK}:int32".encode(),
        ])
    ).hexdigest()



def expected_expert_digest(experts: int, aligned: bool) -> str:
    """Independent stdlib reference for all five buffers, including padding."""
    n, h, k = 7, 128, 2
    cap = n * k + (experts * 127 if aligned else 0)
    payload = bytearray(struct.pack("<e", -33) * (cap * h))
    inverse = bytearray(struct.pack("<i", -29) * (n * k))
    forward = bytearray(struct.pack("<i", -27) * cap)
    mids = bytearray(struct.pack("<i", -25) * cap)
    offsets = [0]
    cursor = 0
    for expert in range(experts):
        positions = [j for j in range(n * k) if (j * 17 + 7) % experts == expert]
        for j, source in enumerate(positions):
            row = cursor + j
            values = range((source // k) * h, (source // k + 1) * h)
            payload[row * h * 2:(row + 1) * h * 2] = struct.pack(f"<{h}e", *values)
            struct.pack_into("<i", inverse, source * 4, row)
            struct.pack_into("<i", forward, row * 4, source)
        width = ((len(positions) + 127) // 128) * 128 if aligned else len(positions)
        if aligned:
            mids[cursor * 4:(cursor + width) * 4] = struct.pack("<i", expert) * width
        cursor += width
        offsets.append(cursor)
    key = f"experts={experts}:{'aligned' if aligned else 'unaligned'}"
    return hashlib.sha256(b"|".join([
        key.encode(), payload, struct.pack(f"<{len(offsets)}q", *offsets),
        inverse, forward, mids,
    ])).hexdigest()

def expected_digests() -> dict[str, str]:
    out = {}
    for n in CORRECTNESS_TOKENS:
        for aligned in (True, False):
            key = f"{n}:{'aligned' if aligned else 'unaligned'}"
            out[key] = expected_case_digest(n, aligned)
    for experts in (64, 1023, 1024, 1025):
        for aligned in (True, False):
            key = f"experts={experts}:{'aligned' if aligned else 'unaligned'}"
            out[key] = expected_expert_digest(experts, aligned)
    return out


REQUIRED_CASE_KEYS = tuple(
    f"{n}:{m}" for n in CORRECTNESS_TOKENS for m in ("aligned", "unaligned")
) + tuple(
    f"experts={e}:{m}" for e in (64, 1023, 1024, 1025)
    for m in ("aligned", "unaligned")
)

# Exact timing protocol the performance stage must have used.
EXPECTED_TIMING_PROTOCOL = {
    "warmup_iters": 20,
    "timed_iters": 50,
    "repeats": 5,
    "statistic": "median",
}
EXPECTED_TIME_CASE_CALLS = 9  # 7 timed batches + 2 probe points


def main() -> int:
    print(json.dumps({
        "expected_case_digests": expected_digests(),
        "required_case_keys": list(REQUIRED_CASE_KEYS),
        "expected_timing_protocol": EXPECTED_TIMING_PROTOCOL,
        "expected_check_case_calls": len(REQUIRED_CASE_KEYS),
        "expected_time_case_calls": EXPECTED_TIME_CASE_CALLS,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
