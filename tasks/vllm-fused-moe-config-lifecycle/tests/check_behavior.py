"""Independent numerical oracle, outside the process importing candidate vLLM."""
def check_numerics(cases, expected_count, workload):
    import torch
    from workload import PHASES, phase_order
    assert len(cases) == expected_count
    for index, case in enumerate(cases):
        prescribed = workload['numerics'][PHASES.index(case['phase'])]
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
                if int(expert) not in case['owned_experts']:
                    continue
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

EXPECTED_STAGES = ['configured_construction_no_warning', 'profile_lifecycle_no_warning',
                   'forward_lifecycle_no_warning', 'genuine_missing_config_warns',
                   'active_layer_owner_wins', 'numerical_path_unchanged', 'explicit_layer_overrides']

def check(raw, workload):
    from workload import PHASES, phase_order
    overrides = raw['layer_overrides']
    assert [r['engine_dp'] for r in overrides] == [1, 2]
    for owner in overrides:
        assert not owner['construction_warned'], 'explicitly configured layer construction warned'
        assert [c['lifecycle'] for c in owner['cases']] == ['profile', 'forward', 'profile_again']
        for case in owner['cases']:
            assert not case['warned'] and case['peak_bytes'] > 0
            assert case['owned_experts'] == list(range(len(workload['numerics'][0]['w1'])))
        check_numerics(owner['cases'], 3, workload)
    for ordinary, overridden in zip(overrides[0]['cases'], overrides[1]['cases']):
        assert ordinary['peak_bytes'] == overridden['peak_bytes'], (
            'ordinary layer workspace follows engine config instead of explicit layer sizes',
            ordinary['lifecycle'], ordinary['peak_bytes'], overridden['peak_bytes'])
    expected_owners = [('dp_ep',0), ('dp_ep',1), ('ordinary',0)]
    expected_constructors = [(kind,rank,state) for kind,rank in expected_owners for state in ('gap','conflict')]
    assert [(x['kind'],x['rank'],x['construction']) for x in raw['constructors']] == expected_constructors
    assert all(x['warned'] is False for x in raw['constructors']), 'configured construction warned'
    expected = [(kind,rank,state,phase) for kind,rank,state in expected_constructors for phase in phase_order(state)]
    assert [(x['kind'],x['rank'],x['construction'],x['phase']) for x in raw['numerics']] == expected, 'incomplete lifecycle'
    prescribed = workload['numerics'][0]
    hidden = len(prescribed['x'][0])
    projected = len(prescribed['w1'][0])
    topk = len(prescribed['ids'][0])
    experts = len(prescribed['w1'])
    worst = 16384 * topk * max(projected, hidden) * 2
    for case in raw['numerics']:
        assert case['warned'] is False, f"{case['kind']}/{case['rank']}/{case['phase']} emitted a missing-config warning"
        dp = 2 if case['kind'] == 'dp_ep' else 1
        rank = case['rank']
        owned = list(range(rank * (experts//dp), (rank+1) * (experts//dp)))
        assert case['owned_experts'] == owned
        expected_map = [owned.index(i) if i in owned else -1 for i in range(experts)] if dp > 1 else None
        assert case['expert_map'] == expected_map
        tokens = len(prescribed['x'])
        assert case['token_counts'] == [tokens//dp + int(i < tokens % dp) for i in range(dp)]
        assert case['workspace_bytes'] > 0
    # Compare the same ordinary implementation across cold ambient states;
    # a legal shared arena may be larger than one logical workspace.
    ordinary = [case for case in raw['numerics'] if case['kind'] == 'ordinary']
    initial = [case for case in ordinary if case['phase'] == 'profile_' + case['construction']]
    assert len(initial) == 2
    assert all(case['workspace_bytes'] < worst for case in initial), 'cold ordinary layer reserved DP+EP worst-case workspace'
    assert initial[0]['live_workspace_bytes'] == initial[1]['live_workspace_bytes'], 'ordinary cold reservation depends on ambient configuration'
    for case in ordinary:
        assert case['live_workspace_bytes'] <= initial[0]['live_workspace_bytes'], 'ordinary workspace grew under a context transition'
    capacities = raw['capacities']
    assert [(x['kind'],x['rank'],x['construction']) for x in capacities] == [x for x in expected_constructors if x[0] == 'dp_ep']
    for case in capacities:
        assert not case['warned'] and case['rows'] == 16384
        assert case['phase'] == 'profile_' + case['construction']
        assert case['required_workspace_peak_bytes'] > 16384 * hidden * 2, 'large forward did not expose workspace use'
        assert case['profile_workspace_capacity_bytes'] >= case['required_workspace_peak_bytes'], 'profiling under-reserved the workspace required by large forward'
        assert case['owned_experts'] == list(range(case['rank'] * (experts//2), (case['rank']+1) * (experts//2)))
        for bound in ('output_min','output_max'):
            check_numerics([dict(case, output=case[bound])], 1, workload)
    interleaved = raw['interleaved']
    assert [case['label'] for case in interleaved] == ['a_profile','b_profile','a_forward','b_forward','a_profile_again']
    for case, dp in zip(interleaved, [1,2,1,2,1]):
        assert not case['warned'], 'interleaved lifecycle warned'
        assert case['owned_experts'] == list(range(experts//dp))
        assert case['token_counts'] == [len(prescribed['x'])//dp] * dp
    check_numerics(interleaved, 5, workload)
    assert raw['missing_warnings'] is True, 'genuine missing-config warning was suppressed'
    check_numerics(raw['numerics'], len(expected), workload)
    return EXPECTED_STAGES
