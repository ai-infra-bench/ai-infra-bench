"""Representation-independent comparisons of controlled host-allocation runs.

Allocation totals alone are diagnostic. The lifecycle comparison first removes
each run's initial occupancy, then separates request/width-only bookkeeping from
growth that also follows the number of encoder rows. No candidate fields,
containers, conversion APIs or allocation addresses participate in the rule.
"""

HOST_WIDTHS = (16, 256)
HOST_ROWS = (4, 8)
HOST_CHECKPOINTS = (4, 16, 32)
HOST_NOISE_BYTES = 65536


def host_storage_diagnostics(observed):
    fields = {'widths', 'spans', 'retained_bytes', 'row_counts',
              'checkpoints', 'completed_requests', 'lifecycle_bytes'}
    if not isinstance(observed, dict) or set(observed) != fields:
        raise ValueError('invalid host-storage report fields')
    if (observed['widths'] != list(HOST_WIDTHS)
            or observed['row_counts'] != list(HOST_ROWS)
            or observed['checkpoints'] != list(HOST_CHECKPOINTS)
            or observed['spans'] != [32, 4096]
            or type(observed['completed_requests']) is not int
            or observed['completed_requests'] != HOST_CHECKPOINTS[-1]):
        raise ValueError('incomplete host-storage workload')
    spatial = observed['retained_bytes']
    lifecycle = observed['lifecycle_bytes']
    if (not isinstance(spatial, list) or len(spatial) != 2
            or any(not isinstance(row, list) or len(row) != 2 for row in spatial)
            or not isinstance(lifecycle, list) or len(lifecycle) != 2
            or any(not isinstance(width, list) or len(width) != 2 for width in lifecycle)
            or any(not isinstance(curve, list) or len(curve) != 3
                   for width in lifecycle for curve in width)):
        raise ValueError('incomplete host-storage observations')
    values = [value for row in spatial for value in row]
    values += [value for width in lifecycle for curve in width for value in curve]
    # Intervals can be negative if pre-existing allocations are reclaimed. Do
    # not clamp them: the per-run subtraction must retain that information.
    if any(type(value) is not int for value in values):
        raise ValueError('host allocation changes must be integer bytes')
    growth = [[[value - curve[0] for value in curve] for curve in width]
              for width in lifecycle]
    width_effect = [[growth[1][row][step] - growth[0][row][step]
                     for step in range(3)] for row in range(2)]
    interaction = [width_effect[1][step] - width_effect[0][step]
                   for step in range(3)]
    return {
        'span_growth_bytes': [row[1] - row[0] for row in spatial],
        'width_growth_by_row_count_bytes': width_effect,
        'row_width_interaction_bytes': interaction,
    }


def host_storage_failure(observed):
    signals = host_storage_diagnostics(observed)
    small, wide = signals['span_growth_bytes']
    if wide > small + HOST_NOISE_BYTES + abs(small) // 4:
        return 'host payload grows with prompt span and embedding width: ' + repr(signals)
    _, middle, last = signals['row_width_interaction_bytes']
    # Require both payload dimensions and a continuing late increase. Growth
    # explained only by requests or width is recorded, without failing reward.
    # This fixed noise allowance cannot be enlarged by a startup allocation.
    if last > HOST_NOISE_BYTES and last - middle > HOST_NOISE_BYTES // 2:
        return 'host payload accumulation follows encoder rows and width: ' + repr(signals)
    return None
