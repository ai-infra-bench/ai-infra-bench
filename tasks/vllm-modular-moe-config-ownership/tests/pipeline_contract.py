"""Expected communication and kernel-boundary behavior from parent-owned inputs."""
def check_pipeline(observed, cases):
    assert len(observed) == len(cases), 'incomplete FlashInfer lifecycle coverage'
    for result, case in zip(observed, cases):
        owner = case['owner']
        distributed = owner['dp_size'] > 1
        local = case['ranks'][owner['dp_rank']]
        gathered = {key: [row for rank in case['ranks'] for row in rank[key]]
                    for key in ('weights', 'ids', 'x')}
        expected = gathered if distributed else local
        events = result['events']
        kinds = [event['kind'] for event in events]
        experts = events[1:-1] if distributed else events
        if distributed:
            assert kinds[0] == 'gather' and kinds[-1] == 'reduce_scatter', kinds
        assert experts and all(event['kind'] == 'expert' for event in experts), kinds
        # A correct implementation may split expert execution into chunks.
        for key, expected_key in [('input', 'x'), ('ids', 'ids'), ('weights', 'weights')]:
            assert [row for event in experts for row in event[key]] == expected[expected_key], 'prepare used the wrong rank data'
        for expert in experts:
            assert expert['parallel'] == {k: owner[k] for k in ('ep_size', 'ep_rank', 'tp_size', 'tp_rank')}, 'expert execution followed stale TP/EP config'
        output = [[value * (owner['dp_size'] if distributed else 1) for value in row] for row in local['x']]
        assert result['device'] == 'cuda' and result['output'] == output, 'finalize did not return the local reduced result'
        if distributed:
            gather, reduce = events[0], events[-1]
            assert gather['sizes'] == reduce['sizes'] == case['sizes']
            assert gather['sent'] == [local[k] for k in ('weights', 'ids', 'x')]
            assert gather['received'] == [gathered[k] for k in ('weights', 'ids', 'x')]
            assert reduce['input'] == gathered['x'] and reduce['output'] == output
