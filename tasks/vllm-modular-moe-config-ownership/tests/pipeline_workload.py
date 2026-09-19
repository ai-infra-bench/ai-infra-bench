"""Fresh layer-owned communication inputs, generated before importing vLLM."""
import random


def parallel(dp, tp, dp_rank, tp_rank, use_ep):
    size = dp * tp
    rank = dp_rank * tp + tp_rank
    return dict(tp_size=1 if use_ep else size, tp_rank=0 if use_ep else rank,
                pcp_size=1, pcp_rank=0, dp_size=dp, dp_rank=dp_rank,
                ep_size=size if use_ep else 1, ep_rank=rank if use_ep else 0,
                use_ep=use_ep, all2all_backend='allgather_reducescatter')


def make_pipeline_workload(seed, *, hidden=128, sizes=(3, 5)):
    rng = random.Random(seed)
    cases = []
    # Canonical flattened MoE TP/EP layouts, including nonzero ranks.
    for dp, tp, dp_rank, tp_rank, ep, explicit in [
        (2, 1, 1, 0, True, False),
        (2, 2, 1, 1, True, True),
        (1, 1, 0, 0, False, True),
        (2, 1, 1, 0, False, True),
        (1, 2, 0, 1, True, True),
        (1, 2, 0, 1, False, False),
    ]:
        owner = parallel(dp, tp, dp_rank, tp_rank, ep)
        stale = parallel(1, 1, 0, 0, False) if dp > 1 or tp > 1 else parallel(2, 1, 1, 0, True)
        rows = list(sizes) if dp > 1 else [sizes[0]]
        inputs = []
        for n in rows:
            inputs.append({
                'x': [[rng.randrange(-32, 33) / 8 for _ in range(hidden)] for _ in range(n)],
                'ids': [rng.sample(range(8), 2) for _ in range(n)],
                'weights': [[0.25, 0.75] for _ in range(n)],
            })
        cases.append({'owner': owner, 'stale': stale, 'explicit': explicit,
                      'sizes': rows, 'hidden': hidden, 'intermediate': 128,
                      'global_experts': 8, 'ranks': inputs})
    return cases
