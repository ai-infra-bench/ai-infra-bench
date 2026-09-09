"""Independent numerical oracle, outside the process importing candidate vLLM."""
def check_numerics(cases, expected_count, workload):
    import torch
    assert len(cases) == expected_count
    for index, case in enumerate(cases):
        prescribed = workload['numerics'][index % len(workload['numerics'])]
        for key in ('x','w1','w2','weights','ids','dtype'):
            assert case[key] == prescribed[key], f'{key} differs from current workload'

        assert case['device'] == 'cuda'
        dtype = {'torch.float16': torch.float16, 'torch.bfloat16': torch.bfloat16}[case['dtype']]
        x, w1, w2, weights = [torch.tensor(prescribed[k], dtype=torch.float32) for k in ('x','w1','w2','weights')]
        ids = torch.tensor(prescribed['ids'], dtype=torch.long)
        actual = torch.tensor(case['output'])
        assert actual.shape == x.shape
        lower = torch.zeros_like(x)
        upper = torch.zeros_like(x)
        # Explicit routed expert computation, with the same documented tensor
        # dtypes at GEMM/activation boundaries; no candidate kernel is imported.
        for token in range(len(x)):
            for j, expert in enumerate(ids[token]):
                gate, up = (w1[expert] @ x[token]).to(dtype).float().chunk(2)
                activated = (torch.nn.functional.silu(gate).to(dtype).float() * up).to(dtype).float()
                # FP32 dot/reduction order can move a weighted contribution
                # across an FP16/BF16 rounding midpoint. Bound that arithmetic
                # uncertainty before the dtype store and expert reduction;
                # comparing only the final, possibly cancelled sum is unsound.
                products = w2[expert].double() * activated.double()[None, :]
                route_weight = weights[token, j].double()
                exact = products.sum(dim=-1) * route_weight
                u = torch.finfo(torch.float32).eps / 2
                operations = 2 * products.shape[-1] + 1
                gamma = operations * u / (1 - operations * u)
                radius = gamma * products.abs().sum(dim=-1) * route_weight.abs()
                lower[token] += (exact - radius).to(dtype).float()
                upper[token] += (exact + radius).to(dtype).float()

        low = lower.to(dtype).float()
        high = upper.to(dtype).float()
        # Keep the existing comparison coefficients. The reference is now the
        # representable interval induced by FP32 arithmetic, not one CPU BLAS
        # reduction order chosen at a low-precision rounding midpoint.
        nearest = torch.minimum(torch.maximum(actual, low), high)
        torch.testing.assert_close(actual, nearest, rtol=0.03, atol=0.5)

EXPECTED_STAGES = ['valid_profile_no_warning','lifecycle_gap_no_warning','genuine_missing_config_warns','active_layer_owner_wins','numerical_path_unchanged']
def check(raw, workload):
    # Standard Triton workspace geometry from the frozen backend: two routed
    # intermediates plus output. The task preserves the 16K routing bound.
    prescribed = workload['numerics'][0]
    hidden = len(prescribed['x'][0])
    projected = len(prescribed['w1'][0])
    topk = len(prescribed['ids'][0])
    worst_case_bytes = 16384 * topk * max(projected, hidden) * 2
    assert raw['dp_workspace_bytes'] >= worst_case_bytes
    assert 0 < raw['ordinary_workspace_bytes'] < worst_case_bytes

    assert raw['valid_warnings'] is False and raw['gap_warnings'] is False
    assert raw['missing_warnings'] is True
    assert raw['dp_workspace_bytes'] > raw['ordinary_workspace_bytes'] > 0
    check_numerics(raw['numerics'], 4, workload)
    return EXPECTED_STAGES
