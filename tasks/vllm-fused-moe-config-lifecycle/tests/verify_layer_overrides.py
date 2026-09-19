"""Resolve explicit layer sizes through the real constructor before profiling."""
import io
import json
import logging
import os

import torch

from vllm.config import ParallelConfig, set_current_vllm_config
from vllm.forward_context import set_forward_context
from vllm.model_executor.layers.fused_moe.layer import FusedMoE
from vllm.model_executor.layers.fused_moe.fused_moe_modular_method import FusedMoEModularMethod
from vllm.model_executor.layers.fused_moe.prepare_finalize import MoEPrepareAndFinalizeNoEP
from verify_profile_warning import (
    Capture, WARNING, WorkspaceObservation, clear_current_config, make_config, serialize_moe,
)
from workload import load_workload


def execute(engine_dp):
    case = load_workload()['numerics'][0]
    config = make_config(parallel_config=ParallelConfig(
        data_parallel_size=engine_dp, enable_expert_parallel=engine_dp > 1))
    local = make_config(parallel_config=ParallelConfig(data_parallel_size=1))
    experts, hidden = len(case['w1']), len(case['x'][0])
    intermediate, topk = len(case['w1'][0]) // 2, len(case['ids'][0])
    # The public constructor derives the effective topology. No hand-built
    # layer/config relationship and no candidate-specific field adapter.
    with set_current_vllm_config(config), torch.device('cuda'):
        layer = FusedMoE(experts, topk, hidden, intermediate,
                         params_dtype=torch.float16, tp_size=1, pcp_size=1, dp_size=1,
                         prefix='explicit_local_layer')
        layer.ensure_moe_quant_config_init()
    assert layer.dp_size == 1 and not layer.use_ep and layer.expert_map is None
    x, w1, w2, weights = [torch.tensor(case[k], device='cuda', dtype=torch.float16)
                          for k in ('x', 'w1', 'w2', 'weights')]
    ids = torch.tensor(case['ids'], device='cuda', dtype=torch.long)
    with torch.no_grad():
        layer.w13_weight.copy_(w1)
        layer.w2_weight.copy_(w2)
    # Only model weights and router outputs are supplied; configuration,
    # dispatch, allocation and expert arithmetic execute in production code.
    layer.select_experts = lambda *args, **kwargs: (weights, ids, None)
    logits = torch.zeros(len(x), experts, device='cuda', dtype=x.dtype)
    capture = Capture()
    logger = logging.getLogger('vllm.config.vllm')
    logger.addHandler(capture)
    logger.setLevel(logging.WARNING)
    clear_current_config()
    method = FusedMoEModularMethod.make(layer, layer.quant_method, MoEPrepareAndFinalizeNoEP(), None)
    construction_warned = WARNING in capture.text
    records = []
    for phase in ('profile', 'forward', 'profile_again'):
        capture.buffer = io.StringIO()
        observation = WorkspaceObservation()
        profile = phase != 'forward'
        context_args = {} if profile else {'num_tokens': len(x)}
        with set_current_vllm_config(config), set_forward_context(None if profile else {}, local, **context_args):
            with observation.record((x, w1, w2, weights, ids, logits, layer.w13_weight, layer.w2_weight)):
                out = method.apply(layer, x.clone(), logits, top_k=topk, renormalize=False,
                                   activation='silu', global_num_experts=experts, expert_map=layer.expert_map)
        torch.cuda.synchronize()
        result = serialize_moe((x, w1, w2, weights, ids), out)
        result.update(engine_dp=engine_dp, lifecycle=phase, phase='profile_matching',
                      owned_experts=list(range(experts)),
                      warned=WARNING in capture.text,
                      peak_bytes=observation.peak_workspace_bytes(0))
        records.append(result)
    logger.removeHandler(capture)
    result = {'engine_dp': engine_dp, 'construction_warned': construction_warned, 'cases': records}
    with open(os.environ['AIB_OBSERVATIONS'], 'w') as stream:
        json.dump(result, stream)
    print(json.dumps({'explicit_layer_override': engine_dp,
                      'peak_bytes': [r['peak_bytes'] for r in records],
                      'warned': construction_warned or any(r['warned'] for r in records)}), flush=True)
