"""Small EP contract cases and stdlib-only output validation.

Routing fixtures are shared, but expected observations are derived without
candidate code. Canonicalization permits different ordering within an expert.
Unused payload bytes and unaligned m_indices are deliberately not constrained.
"""

import hashlib
import struct

PARTITION_CASES = ("mixed", "all-local", "all-remote")
TOKENS, TOPK, HIDDEN, EXPERTS, LOCAL_EXPERTS, ALIGN = 7, 2, 256, 17, 5, 128
EXPERT_MAP = (-1, 3, -1, -1, 0, -1, -1, -1, -1, 4, -1, -1, -1, 1, -1, -1, 2)


def routes_for(name):
    if name == "mixed":
        return [(5 * t + 3 * k) % EXPERTS for t in range(TOKENS) for k in range(TOPK)]
    if name == "all-local":
        return [4, 13] * TOKENS
    if name == "all-remote":
        return [0, 2] * TOKENS
    raise ValueError(f"unknown partition case: {name}")


def payload_bytes():
    # Every row contains all 256 encodings, including negative values and NaNs.
    return bytes((37 * t + col) % 256 for t in range(TOKENS) for col in range(HIDDEN))


def case_key(name, aligned):
    return f"partition={name}:{'aligned' if aligned else 'unaligned'}"


def reference(name, aligned):
    groups = [[] for _ in range(LOCAL_EXPERTS)]
    remote = []
    for source, expert in enumerate(routes_for(name)):
        local = EXPERT_MAP[expert]
        (remote if local == -1 else groups[local]).append(source)
    offsets = [0]
    for group in groups:
        width = ((len(group) + ALIGN - 1) // ALIGN) * ALIGN if aligned else len(group)
        offsets.append(offsets[-1] + width)
    return groups, remote, offsets


def capacity(aligned):
    routes = TOKENS * TOPK
    return ((routes + EXPERTS * (ALIGN - 1) + ALIGN - 1) // ALIGN * ALIGN
            if aligned else routes)


def _digest(name, aligned, offsets, destinations, forward, payload, remote, mids):
    parts = [case_key(name, aligned).encode(), struct.pack(f"<{len(offsets)}q", *offsets)]
    for values in (destinations, forward, remote, mids):
        parts.append(struct.pack(f"<{len(values)}i", *values))
    parts.append(payload)
    return hashlib.sha256(b"|".join(parts)).hexdigest()


def expected_partition_digest(name, aligned):
    groups, remote, offsets = reference(name, aligned)
    local_sources = [source for source, expert in enumerate(routes_for(name))
                     if EXPERT_MAP[expert] != -1]
    destinations = [offsets[e] + j for e, group in enumerate(groups) for j in range(len(group))]
    raw_count = len(local_sources)
    skipped = ([offsets[-1]] * len(remote) if aligned
               else list(range(raw_count, TOKENS * TOPK)))
    data = payload_bytes()
    payload = b"".join(data[(source // TOPK) * HIDDEN:(source // TOPK + 1) * HIDDEN]
                       for source in local_sources)
    mids = []
    if aligned:
        mids = [e for e in range(LOCAL_EXPERTS) for _ in range(offsets[e + 1] - offsets[e])]
        mids += [-1] * (capacity(aligned) - len(mids))
    return _digest(name, aligned, offsets, destinations, local_sources, payload, skipped, mids)


def validate_partition_outputs(name, aligned, payload, offsets, inverse, forward, mids):
    """Check actual native outputs and hash a tie-order-independent observation."""
    def require(condition, message):
        if not condition:
            raise ValueError(f"{case_key(name, aligned)}: {message}")

    groups, remote, wanted_offsets = reference(name, aligned)
    cap = capacity(aligned)
    require(len(payload) == cap * HIDDEN, "payload size")
    require(len(inverse) == TOKENS * TOPK and len(forward) == cap and len(mids) == cap,
            "mapping sizes")
    require(offsets == wanted_offsets, "expert offsets")
    destinations = []
    for expert, group in enumerate(groups):
        observed = sorted(inverse[source] for source in group)
        require(observed == list(range(offsets[expert], offsets[expert] + len(group))),
                "local inverse must bijectively fill its expert's payload region")
        destinations.extend(observed)
    local_sources = sorted(source for group in groups for source in group)
    actual_forward = [forward[inverse[source]] for source in local_sources]
    require(actual_forward == local_sources, "forward/inverse round trip")
    data = payload_bytes()
    actual_payload = b"".join(payload[inverse[source] * HIDDEN:(inverse[source] + 1) * HIDDEN]
                              for source in local_sources)
    wanted_payload = b"".join(data[(source // TOPK) * HIDDEN:(source // TOPK + 1) * HIDDEN]
                              for source in local_sources)
    require(actual_payload == wanted_payload, "local payload bytes")
    skipped = sorted(inverse[source] for source in remote)
    wanted_skipped = ([offsets[-1]] * len(remote) if aligned
                      else list(range(len(local_sources), TOKENS * TOPK)))
    require(skipped == wanted_skipped, "nonlocal inverse destinations")
    # The caller initializes this sentinel; nonlocal routes must not copy rows.
    occupied = set(destinations)
    require(all(value == TOKENS * TOPK for row, value in enumerate(forward) if row not in occupied),
            "nonlocal/padding forward sentinel")
    if aligned:
        wanted_mids = [e for e in range(LOCAL_EXPERTS)
                       for _ in range(offsets[e + 1] - offsets[e])]
        wanted_mids += [-1] * (cap - len(wanted_mids))
        require(mids == wanted_mids, "aligned expert ranges and tail")
    return _digest(name, aligned, offsets, destinations, actual_forward, actual_payload,
                   skipped, mids if aligned else [])
