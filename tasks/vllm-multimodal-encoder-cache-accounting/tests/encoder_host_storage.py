"""Observe live Python/NumPy allocations across real encoder lifecycles.

Torch backing storage is observed separately. Tracemalloc measures outstanding
allocations rather than RSS. Spatial runs compare prompt spans at two widths;
lifecycle runs pair widths and row counts while keeping request shape, order
and encoder capacity fixed. Unattributed background growth is diagnostic. No
candidate attribute, container or conversion API is read.
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
        yield lambda: tracemalloc.get_traced_memory()[0] - baseline
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


def host_lifecycle(runtime, row_count):
    # Keep the same eight-row capacity in all cells. Only the actual output
    # geometry changes; four-row items may occupy two cache entries instead.
    indices = [0, 2, 5, 7, 10, 12, 15, 17]
    profile = specification(19, indices)
    selected = indices if row_count == 8 else indices[::2]
    pair = None
    resident = []
    try:
        with trace_host_allocations() as live_bytes:
            pair = runtime.pair(profile, chunk=4)
            for index in range(HOST_CHECKPOINTS[-1]):
                item = specification(19, selected, value=503 + 31 * index)
                pair.add(request_workload(f'host-turnover-{index}', 21, [item], token=31))
                pair.finish()
                forget_test_history(pair)
                if index + 1 in HOST_CHECKPOINTS:
                    gc.collect()
                    resident.append(live_bytes())
        return resident
    finally:
        if pair:
            pair.close()


def check_host_storage():
    sizes = []
    lifecycle = []
    for width in HOST_WIDTHS:
        with hidden_width(width), Runtime() as runtime:
            # Warm ordinary constructor/import/operator caches before tracing.
            warm = runtime.pair(specification(16, list(range(8))), chunk=4)
            warm.add(request_workload('warm', 16, [specification(16, list(range(8)))]))
            warm.finish()
            warm.close()
            del warm
            gc.collect()
            sizes.append([host_residency(runtime, span) for span in (32, 4096)])
            lifecycle.append([host_lifecycle(runtime, rows) for rows in HOST_ROWS])
    observed = {'widths': list(HOST_WIDTHS), 'spans': [32, 4096],
                'retained_bytes': sizes, 'row_counts': list(HOST_ROWS),
                'checkpoints': list(HOST_CHECKPOINTS),
                'completed_requests': HOST_CHECKPOINTS[-1],
                'lifecycle_bytes': lifecycle}
    failure = host_storage_failure(observed)
    assert failure is None, failure
    return observed
