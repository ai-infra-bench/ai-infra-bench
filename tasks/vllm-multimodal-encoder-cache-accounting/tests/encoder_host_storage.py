"""Observe live Python/NumPy allocations across real encoder lifecycles.

Torch backing storage is observed separately. Tracemalloc measures outstanding
allocations rather than RSS, so allocator arenas are not mistaken for retained
objects. We compare the same prompt-span change at two embedding widths: legal
per-position metadata can grow with span, but embedding-value expansion also
grows with width. No candidate attribute, container or conversion API is read.
"""
from contextlib import contextmanager
import tracemalloc


@contextmanager
def hidden_width(width):
    # This changes only the registered task model/fixture geometry. Scenarios
    # are sequential and every width gets fresh Runtime/runner/request state.
    global WIDTH
    previous = WIDTH
    WIDTH = width
    try:
        yield
    finally:
        WIDTH = previous


@contextmanager
def trace_host_allocations():
    owner = not tracemalloc.is_tracing()
    if owner:
        tracemalloc.start()
    gc.collect()
    baseline = tracemalloc.get_traced_memory()[0]
    try:
        yield lambda: max(0, tracemalloc.get_traced_memory()[0] - baseline)
    finally:
        if owner:
            tracemalloc.stop()


def forget_test_history(pair):
    """Release only task-owned workload/observation records after completion."""
    pair.workloads.clear()
    pair.consumed.clear()
    pair.delivered.clear()
    pair.draft_delivered.clear()
    pair.trace.clear()
    pair.model.encodings.clear()
    pair.model.inputs.clear()


def host_residency(runtime, span):
    indices = [i * (span - 1) // 7 for i in range(8)]
    spec = specification(span, indices)
    workload = request_workload('host-span', span, [spec])
    pair = None
    try:
        with trace_host_allocations() as live_bytes:
            pair = runtime.pair(spec, chunk=1)
            pair.add(workload)
            pair.step()
            gc.collect()
            return live_bytes()
    finally:
        if pair:
            pair.close()


def host_lifecycle(runtime):
    profile = specification(19, [0, 2, 5, 7, 10, 12, 15, 17])
    pair = None
    resident = []
    try:
        with trace_host_allocations() as live_bytes:
            pair = runtime.pair(profile, chunk=4)
            for index in range(32):
                item = dict(profile, rows=specification(
                    19, [0, 2, 5, 7, 10, 12, 15, 17], value=503 + 31 * index)['rows'])
                pair.add(request_workload(f'host-turnover-{index}', 21, [item], token=31))
                pair.finish()
                forget_test_history(pair)
                gc.collect()
                resident.append(live_bytes())
        warm = max(resident[:4])
        allowance = 65536 + warm // 10
        assert all(value <= warm + allowance for value in resident[4:]), (
            'host payload grows after request completion', resident)
        return resident
    finally:
        if pair:
            pair.close()


def check_host_storage():
    sizes = []
    resident = None
    for width in (16, 256):
        with hidden_width(width), Runtime() as runtime:
            # Warm ordinary constructor/import/operator caches before tracing.
            warm = runtime.pair(specification(16, list(range(8))), chunk=4)
            warm.add(request_workload('warm', 16, [specification(16, list(range(8)))]))
            warm.finish()
            warm.close()
            del warm
            gc.collect()
            sizes.append([host_residency(runtime, span) for span in (32, 4096)])
            if width == 256:
                resident = host_lifecycle(runtime)
    small_growth = sizes[0][1] - sizes[0][0]
    wide_growth = sizes[1][1] - sizes[1][0]
    allowance = 65536 + abs(small_growth) // 4
    assert wide_growth <= small_growth + allowance, (
        'host payload grows with prompt span and embedding width', sizes)
    return {'widths': [16, 256], 'spans': [32, 4096], 'retained_bytes': sizes,
            'completed_requests': len(resident), 'resident_bytes': resident}
