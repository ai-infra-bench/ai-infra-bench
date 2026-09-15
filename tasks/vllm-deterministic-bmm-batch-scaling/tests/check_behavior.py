"""Check all behavior groups, retaining each independent rejection reason."""
import statistics
import math

EXPECTED_STAGES = ['correctness', 'error_contracts', 'launch_scaling', 'performance']


def check(raw, workload, artifact_dir=None):
    import torch
    def same_bits(left, right):
        return (left.shape == right.shape and left.dtype == right.dtype
                and torch.equal(left.view({2: torch.int16, 4: torch.int32}[left.element_size()]),
                                right.view({2: torch.int16, 4: torch.int32}[right.element_size()])))

    stages = raw['stages']
    failures = dict(raw['failures'])

    def correctness():
        cases = stages['correctness']
        assert len(cases) == len(workload['correctness'])
        for case, prescribed in zip(cases, workload['correctness']):
            assert case['dtype'] == prescribed['dtype'] and case['shape'] == prescribed['shape']
            assert case['a'] == prescribed['a'] and case['b'] == prescribed['b'], 'operands differ from current workload'
            batch, m, n, k = prescribed['shape']
            input_dtype = getattr(torch, prescribed['dtype'].split('.')[-1])
            a = torch.tensor(prescribed['a']).reshape(batch,m,k)
            b = torch.tensor(prescribed['b']).reshape(prescribed.get('rhs_batch', batch),k,n)[:batch]
            assert case['output_shape'] == [batch,m,n] and case['output_dtype'] == prescribed['dtype']
            out, single, provided = [torch.tensor(case[key], dtype=input_dtype).reshape(batch,m,n)
                                     for key in ('batched','single','out')]
            assert list(out.shape) == list(single.shape) == list(provided.shape) == [batch,m,n]
            assert case['device'] == 'cuda' and case['out_ptr'] == case['returned_ptr']
            assert case['out_identity'] is True
            assert same_bits(out, single) and same_bits(out, provided), "batch/single/out bit patterns differ"
            torch.testing.assert_close(out.float(), torch.bmm(a.double(), b.double()).float(), rtol=0.02, atol=0.02)
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
                assert same_bits(torch.tensor(copied['values']).reshape(shape), expected), 'out copy changed bit patterns'


    def errors():
        assert {c['case'] for c in stages['error_contracts']} == {
            'dtype_mismatch', 'shape_mismatch', 'batch_mismatch', 'device_mismatch',
            'out_shape_mismatch',
            'lhs_rank_mismatch', 'rhs_rank_mismatch', 'empty_batch', 'empty_lhs_batch'}

    def launches():
        from workload import LAUNCH_GROUPS
        observed = stages['launch_scaling']
        expected = [(dtype, shape, batch) for dtype, shape in LAUNCH_GROUPS for batch in (1,7,29)]
        assert [(x['dtype'], x['shape'], x['batch']) for x in observed] == expected
        for offset in range(0, len(expected), 3):
            counts = [len(x['kernels']) for x in observed[offset:offset+3]]
            assert all(counts) and max(counts) <= min(counts) + 2, counts

    def performance():
        from pathlib import Path
        import os
        import stat
        import numpy as np
        torch.set_num_threads(4)

        def read_result(index, name, shape):
            # Fixed filenames, bounded plain arrays; never deserialize Python
            # objects or accept a candidate-chosen path as a reference.
            path = Path(artifact_dir) / f'large-{index}-{name}.npy'
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, 'rb') as stream:
                info = os.fstat(stream.fileno())
                assert stat.S_ISREG(info.st_mode)
                assert info.st_size <= math.prod(shape) * 4 + 4096
                array = np.load(stream, allow_pickle=False, max_header_size=4096)
            assert array.dtype == np.float32 and list(array.shape) == shape
            archive = Path(workload['performance'][0]['a_path']).parent.parent / 'output-tensors'
            archive.mkdir(mode=0o755, exist_ok=True)
            np.save(archive / path.name, array, allow_pickle=False)
            return torch.from_numpy(array)

        cases = stages['performance']
        assert len(cases) == 3
        speedups = []
        for index, (case, shape) in enumerate(zip(cases, workload['performance_shapes'])):
            assert case['shape'] == shape
            batch, m, n, _ = shape
            before, single, after = [read_result(index, name, [batch, m, n])
                                     for name in ('before', 'single', 'after')]
            assert same_bits(before, single), 'large-shape batch/single mismatch'
            assert same_bits(before, after), 'large-shape result changed across timing'
            prescribed = workload['performance'][index]
            a, b = [torch.from_numpy(np.load(prescribed[key + '_path'], allow_pickle=False))
                    for key in ('a', 'b')]
            # An independent FP64 reference, bounded by a row tile, keeps the
            # original numerical tolerance without large JSON reports.
            for item in range(batch):
                rhs = b[item].double()
                for start in range(0, m, 64):
                    expected = (a[item, start:start+64].double() @ rhs).float()
                    torch.testing.assert_close(before[item, start:start+64], expected,
                                               rtol=0.02, atol=0.02)
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
