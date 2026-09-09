"""Check all behavior groups, retaining each independent rejection reason."""
import statistics
import math

EXPECTED_STAGES = ['correctness', 'error_contracts', 'launch_scaling', 'performance']


def check(raw, workload):
    import torch
    stages = raw['stages']
    failures = dict(raw['failures'])

    def correctness():
        cases = stages['correctness']
        assert len(cases) == 6
        for case, prescribed in zip(cases, workload['correctness']):
            assert case['dtype'] == prescribed['dtype'] and case['shape'] == prescribed['shape']
            assert case['a'] == prescribed['a'] and case['b'] == prescribed['b'], 'operands differ from current workload'
            a, b = [torch.tensor(prescribed[k]) for k in ('a','b')]
            out, single, provided = [torch.tensor(case[k]) for k in ('batched','single','out')]
            batch, m, n, _ = prescribed['shape']
            assert list(out.shape) == list(single.shape) == list(provided.shape) == [batch,m,n]
            assert case['device'] == 'cuda' and case['out_ptr'] == case['returned_ptr']
            assert case['out_identity'] is True
            assert torch.equal(out, single) and torch.equal(out, provided)
            torch.testing.assert_close(out, torch.bmm(a, b), rtol=0.02, atol=0.02)
            input_dtype = getattr(torch, prescribed['dtype'].split('.')[-1])
            specs = [('cuda', dt, False) for dt in (torch.float16, torch.bfloat16, torch.float32)
                     if dt != input_dtype] + [('cpu', input_dtype, False), ('cuda', input_dtype, True)]
            assert len(case['out_copies']) == len(specs)
            for copied, (device, dtype, broadcast) in zip(case['out_copies'], specs):
                shape = [1,batch,m,n] if broadcast else [batch,m,n]
                assert copied['identity'] is True and copied['device'] == device
                assert copied['dtype'] == str(dtype) and copied['shape'] == shape
                expected = out.to(dtype).float()
                if broadcast: expected = expected.unsqueeze(0)
                assert torch.equal(torch.tensor(copied['values']), expected), 'out copy changed values'


    def errors():
        assert {c['case'] for c in stages['error_contracts']} == {
            'dtype_mismatch', 'shape_mismatch', 'batch_mismatch', 'device_mismatch',
            'out_shape_mismatch',
            'lhs_rank_mismatch', 'rhs_rank_mismatch'}

    def launches():
        observed = stages['launch_scaling']
        assert [x['batch'] for x in observed] == [1, 7, 29]
        counts = [len(x['kernels']) for x in observed]
        assert all(counts) and max(counts) <= min(counts) + 2, counts

    def performance():
        cases = stages['performance']
        assert len(cases) == 3
        speedups = []
        for case, shape in zip(cases, workload['performance_shapes']):
            assert case['shape'] == shape
            assert all(math.isfinite(x) and x > 0 for x in case['candidate_samples'] + case['legacy_samples'])
            assert len(case['candidate_samples']) == len(case['legacy_samples']) == 5
            candidate = statistics.median(case['candidate_samples'])
            assert candidate > 0
            speedups.append(statistics.median(case['legacy_samples']) / candidate)
        assert all(value >= limit for value, limit in zip(speedups, [2.0, 1.05, 1.05])), speedups

    for name, run in zip(EXPECTED_STAGES, [correctness, errors, launches, performance]):
        try:
            run()
        except Exception as exc:
            failures.setdefault(name, f'{type(exc).__name__}: {exc}')
    assert not failures, failures
    return EXPECTED_STAGES
