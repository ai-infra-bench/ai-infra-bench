"""Public-output checks for sparse routing across large expert sets.

Fixtures send tokens to the first, middle and final experts, with unequal
counts and empty ranges between them. Validation permits any within-expert
ordering whose forward/inverse maps and payload agree. No kernel helpers,
launch dimensions or intermediate buffers are observed.
"""

import hashlib
import struct

EXPERT_COUNTS = (1023, 1024, 1025, 2049)
TOKENS, TOPK, HIDDEN, ALIGN = 7, 2, 128, 128
ROW_BYTES = HIDDEN * 2  # FP16 storage


def routes_for(experts):
    return [
        0, experts - 1,
        experts - 2, experts // 2,
        experts // 4, experts - 1,
        experts // 2, experts - 2,
        experts - 1, 3 * experts // 4,
        3 * experts // 4, 0,
        experts - 2, experts - 1,
    ]


def payload_bytes():
    return struct.pack(f"<{TOKENS * HIDDEN}e", *range(TOKENS * HIDDEN))


def capacity(experts, aligned):
    slots = TOKENS * TOPK
    if not aligned:
        return slots
    return (slots + experts * (ALIGN - 1) + ALIGN - 1) // ALIGN * ALIGN


def case_key(experts, aligned):
    return f"high-experts={experts}:{'aligned' if aligned else 'unaligned'}"


def reference(experts, aligned):
    groups = {}
    for source, expert in enumerate(routes_for(experts)):
        groups.setdefault(expert, []).append(source)
    offsets = [0]
    for expert in range(experts):
        count = len(groups.get(expert, ()))
        width = (count + ALIGN - 1) // ALIGN * ALIGN if aligned else count
        offsets.append(offsets[-1] + width)
    mids = []
    if aligned:
        for expert in sorted(groups):
            mids.extend([expert] * (offsets[expert + 1] - offsets[expert]))
        mids.extend([-1] * (capacity(experts, aligned) - len(mids)))
    return groups, offsets, mids


def _digest(experts, aligned, offsets, destinations, forward, payload, mids):
    parts = [case_key(experts, aligned).encode(),
             struct.pack(f"<{len(offsets)}q", *offsets)]
    for values in (destinations, forward, mids):
        parts.append(struct.pack(f"<{len(values)}i", *values))
    parts.append(payload)
    return hashlib.sha256(b"|".join(parts)).hexdigest()


def expected_digest(experts, aligned):
    groups, offsets, mids = reference(experts, aligned)
    destinations = [offsets[e] + j for e in sorted(groups)
                    for j in range(len(groups[e]))]
    sources = list(range(TOKENS * TOPK))
    raw = payload_bytes()
    payload = b"".join(raw[(s // TOPK) * ROW_BYTES:(s // TOPK + 1) * ROW_BYTES]
                       for s in sources)
    return _digest(experts, aligned, offsets, destinations, sources, payload, mids)


def validate_outputs(experts, aligned, payload, offsets, inverse, forward, mids):
    def require(condition, message):
        if not condition:
            raise ValueError(f"{case_key(experts, aligned)}: {message}")

    slots = TOKENS * TOPK
    cap = capacity(experts, aligned)
    groups, wanted_offsets, wanted_mids = reference(experts, aligned)
    require(len(payload) == cap * ROW_BYTES, "payload size")
    require(len(inverse) == slots and len(forward) == cap and len(mids) == cap,
            "mapping sizes")
    require(offsets == wanted_offsets, "expert offsets")
    destinations = []
    for expert in sorted(groups):
        observed = sorted(inverse[source] for source in groups[expert])
        require(observed == list(range(offsets[expert],
                                       offsets[expert] + len(groups[expert]))),
                "inverse must fill each expert's payload rows")
        destinations.extend(observed)
    actual_forward = [forward[inverse[source]] for source in range(slots)]
    require(actual_forward == list(range(slots)), "forward/inverse round trip")
    raw = payload_bytes()
    actual_payload = b"".join(payload[row * ROW_BYTES:(row + 1) * ROW_BYTES]
                              for row in inverse)
    wanted_payload = b"".join(raw[(s // TOPK) * ROW_BYTES:(s // TOPK + 1) * ROW_BYTES]
                              for s in range(slots))
    require(actual_payload == wanted_payload, "payload bytes")
    occupied = set(destinations)
    require(all(value == slots for row, value in enumerate(forward)
                if row not in occupied), "padding forward sentinel")
    if aligned:
        require(mids == wanted_mids, "aligned expert ranges and tail")
    return _digest(experts, aligned, offsets, destinations, actual_forward,
                   actual_payload, mids if aligned else [])
