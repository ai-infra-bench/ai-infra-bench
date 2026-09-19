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

EXPECTED_STAGES = ['compatibility_no_warning','active_owner_workspace_provenance','numerical_path_unchanged','flashinfer_consumer_follows_owner','lora_factory_follows_owner','functional_no_global_dependency','flashinfer_prepare_expert_finalize']
def check_stages(raw, workload):
    """Yield a stage only after its trusted behavioral assertions finish."""
    assert not any('Current vLLM config is not set' in x for x in raw['warnings'])
    yield 'compatibility_no_warning'

    # Keep the same acceptance predicates, grouped by the behavior they check.
    prescribed = workload['numerics'][0]
    hidden = len(prescribed['x'][0])
    projected = len(prescribed['w1'][0])
    topk = len(prescribed['ids'][0])
    worst_case_bytes = 16384 * topk * max(projected, hidden) * 2

    def check_workspace(dp_field, ordinary_field):
        assert raw[dp_field] >= worst_case_bytes, (dp_field, raw[dp_field], worst_case_bytes)
        assert 0 < raw[ordinary_field] < worst_case_bytes, (ordinary_field, raw[ordinary_field], worst_case_bytes)
        assert raw[dp_field] > raw[ordinary_field] > 0

    check_workspace('dp_workspace_bytes', 'ordinary_workspace_bytes')
    yield 'active_owner_workspace_provenance'

    check_numerics(raw['numerics'], 8, workload)
    yield 'numerical_path_unchanged'

    check_workspace('dp_consumer_workspace_bytes', 'ordinary_consumer_workspace_bytes')
    yield 'flashinfer_consumer_follows_owner'

    check_workspace('lora_dp_workspace_bytes', 'lora_ordinary_workspace_bytes')
    yield 'lora_factory_follows_owner'

    field = 'functional_workspace_bytes'
    assert 0 < raw[field] < worst_case_bytes, (field, raw[field], worst_case_bytes)
    assert raw[field] == raw['ordinary_workspace_bytes']
    yield 'functional_no_global_dependency'

    from pipeline_contract import check_pipeline
    check_pipeline(raw['flashinfer_pipeline'], workload['flashinfer_pipeline'])
    yield 'flashinfer_prepare_expert_finalize'


def check(raw, workload):
    """Compatibility entrypoint for callers that only need all-or-nothing checks."""
    return list(check_stages(raw, workload))
