#!/usr/bin/env python3
"""Independent fresh challenge for modular-MoE profile config lifecycle.

Curator-side only: not the agent verifier, not mounted into the agent image,
not referenced by instruction.md. It enters through the same production factory
path (FusedMoEModularMethod.make -> FusedMoEModularKernel profile forward) but
with a MoE shape and a DP/EP-vs-ambient disagreement chosen independently of
tests/verify_profile_warning.py (which uses tokens/hidden/intermediate =
4/64/128 and dp_size=2).

Independent invariants re-derived here:
  1. Factory construction and a real CUDA profile forward must NOT emit the
     "Current vLLM config is not set." warning after the temporary global
     context ends, while the layer and its quant method retain valid config.
  2. Genuinely missing config must STILL warn (no blanket suppression).
  3. DP+EP profiling must retain the worst-case workspace capacity, including
     on reuse; an ordinary layer must retain its ordinary requirements under
     a conflicting ambient config. Allocation helpers and layout are free.

Expected outcomes are Oracle/alternative PASS and Base/wrong-owner FAIL.
Actual execution results are recorded separately in e2e-evidence.json.
"""
from __future__ import annotations

import contextlib
import io
import json
import logging
import sys
import subprocess
import traceback
from itertools import count
from types import SimpleNamespace
from unittest.mock import patch

import torch

import vllm.config.vllm as vllm_config_module
from vllm.config import ParallelConfig, SchedulerConfig, VllmConfig, set_current_vllm_config
from vllm.forward_context import set_forward_context
from vllm.model_executor.layers.fused_moe.layer import FusedMoE
from vllm.model_executor.layers.fused_moe.fused_moe import TritonExperts
import vllm.model_executor.layers.fused_moe.fused_moe_modular_method as method_module
from vllm.model_executor.layers.fused_moe.modular_kernel import FusedMoEModularKernel
from vllm.model_executor.layers.fused_moe.prepare_finalize import MoEPrepareAndFinalizeNoEP

WARNING = "Current vLLM config is not set."
_LAYER_IDS = count()

# Fresh MoE geometry, distinct from the verifier's 4/64/128/4/2.
TOKENS, HIDDEN, INTERMEDIATE, EXPERTS, TOPK = 6, 96, 160, 8, 3


def make_config(*, parallel_config):
    # A normal supported engine budget can produce the full routing window.
    return VllmConfig(parallel_config=parallel_config, scheduler_config=SchedulerConfig(
        max_model_len=16384, is_encoder_decoder=False, max_num_batched_tokens=16384))


class Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.buffer = io.StringIO()

    def emit(self, record):
        self.buffer.write(self.format(record) + "\n")

    @property
    def text(self):
        return self.buffer.getvalue()


def clear_current_config():
    vllm_config_module._current_vllm_config = None
    vllm_config_module.get_cached_compilation_config.cache_clear()


def make_kernel_through_factory(config, ambient=None):
    original_method = method_module.FusedMoEModularMethod
    parallel = config.parallel_config
    # Only rank discovery is substituted at this single-device transport
    # boundary. The real constructor resolves parallel sizes, public properties,
    # expert ownership, registered weights and the production quant method.
    rank_group = SimpleNamespace(
        rank_in_group=parallel.data_parallel_rank,
        world_size=parallel.data_parallel_size,
    )
    with (
        patch(
            "vllm.model_executor.layers.fused_moe.config.get_dp_group",
            return_value=rank_group,
        ),
        set_current_vllm_config(config),
        torch.device("cuda"),
    ):
        layer = FusedMoE(
            EXPERTS, TOPK, HIDDEN, INTERMEDIATE, params_dtype=torch.float16,
            tp_size=1, pcp_size=1, dp_size=parallel.data_parallel_size,
            prefix=f"profile_layer_{next(_LAYER_IDS)}",
        )
        layer.ensure_moe_quant_config_init()
    old_quant = layer.quant_method
    map_cuda = layer.expert_map
    owned_cuda = (
        torch.arange(EXPERTS, device="cuda")
        if map_cuda is None else torch.where(map_cuda >= 0)[0]
    )
    context = (set_current_vllm_config(ambient) if ambient is not None
               else contextlib.nullcontext())
    with context:
        method = original_method.make(layer, old_quant, MoEPrepareAndFinalizeNoEP(), None)
    layer.quant_method = method

    def forward(x, w1, w2, weights, ids, *, activation, global_num_experts):
        # We supply deterministic router outputs and loaded weights; the real
        # modular method owns dispatch and all access to its internal storage.
        with torch.no_grad():
            layer.w13_weight.copy_(w1.index_select(0, owned_cuda))
            layer.w2_weight.copy_(w2.index_select(0, owned_cuda))
        layer.select_experts = lambda *args, **kwargs: (weights, ids, None)
        router_logits = torch.zeros((len(x), global_num_experts), device=x.device, dtype=x.dtype)
        return method.apply(
            layer, x, router_logits, top_k=ids.shape[1], renormalize=False,
            activation=activation, global_num_experts=global_num_experts, expert_map=map_cuda,
        )
    forward.owned_experts = owned_cuda.tolist()
    return forward


def real_cuda_forward(kernel, config, workspace=None, *, profile=True, observation=None, repeat=1):
    torch.manual_seed(99001)
    device = torch.device("cuda")
    dtype = torch.float16
    x = torch.randn(TOKENS, HIDDEN, device=device, dtype=dtype)
    w1 = torch.randn(EXPERTS, 2 * INTERMEDIATE, HIDDEN, device=device, dtype=dtype)
    w2 = torch.randn(EXPERTS, HIDDEN, INTERMEDIATE, device=device, dtype=dtype)
    logits = torch.randn(TOKENS, EXPERTS, device=device, dtype=dtype)
    topk_weights, topk_ids = torch.topk(logits, TOPK, dim=-1)
    topk_weights = torch.softmax(topk_weights.float(), dim=-1).to(dtype)
    if repeat != 1:
        x = x.repeat(repeat, 1)[:16384]
        topk_weights = topk_weights.repeat(repeat, 1)[:16384]
        topk_ids = topk_ids.repeat(repeat, 1)[:16384]
    recorded_x = x.clone()
    dp = config.parallel_config.data_parallel_size
    counts = torch.tensor([len(part) for part in torch.tensor_split(x, dp)], dtype=torch.int32)
    assert int(counts.max()) <= config.scheduler_config.max_num_batched_tokens
    kwargs = {} if profile else {'num_tokens':int(counts[config.parallel_config.data_parallel_rank]), 'num_tokens_across_dp':counts}
    scope = (observation.record((x,w1,w2,topk_weights,topk_ids)) if observation is not None
             else observe_workspace_bytes(workspace, (x,w1,w2,topk_weights,topk_ids)))
    with set_forward_context(None if profile else {}, config, **kwargs), scope:
        out = kernel(x, w1, w2, topk_weights, topk_ids, activation="silu",
                     global_num_experts=EXPERTS)
    torch.cuda.synchronize()
    assert out.is_cuda and out.shape == x.shape and torch.isfinite(out).all()
    expected = torch.zeros((TOKENS,HIDDEN), device='cpu', dtype=torch.float32)
    cpu_x, cpu_w1, cpu_w2, cpu_weights = [v.cpu().float() for v in (recorded_x,w1,w2,topk_weights)]
    for token in range(TOKENS):
        for slot in range(TOPK):
            expert = int(topk_ids[token,slot])
            if expert not in kernel.owned_experts:
                continue
            gate, up = (cpu_w1[expert] @ cpu_x[token]).half().float().chunk(2)
            activation = (torch.nn.functional.silu(gate).half().float() * up).half().float()
            expected[token] += ((cpu_w2[expert] @ activation) * cpu_weights[token,slot]).half().float()
    torch.testing.assert_close(out.cpu().float(), expected.half().float().repeat(repeat,1)[:len(out)], rtol=0.03, atol=0.5)
    return float(out.float().norm().item())


@contextlib.contextmanager
def observe_workspace_bytes(observed, inputs):
    # Observe actual CUDA temporaries and views through PyTorch, independently
    # of the candidate's cache classes and allocation helper names.
    if observed is None:
        yield
        return
    from torch.utils._python_dispatch import TorchDispatchMode
    excluded = {t.untyped_storage().data_ptr() for t in inputs}
    class WorkspaceScope(TorchDispatchMode):
        def __torch_dispatch__(self, func, types, args=(), kwargs=None):
            result = func(*args, **(kwargs or {}))
            def record(value):
                if isinstance(value, torch.Tensor):
                    if value.is_cuda and value.untyped_storage().data_ptr() not in excluded:
                        observed.append(value.untyped_storage().nbytes())
                elif isinstance(value, (tuple, list)):
                    for item in value:
                        record(item)
                elif isinstance(value, dict):
                    for item in value.values():
                        record(item)
            record(result)
            return result
    with WorkspaceScope():
        yield




def measure_workspace(kernel, config):
    observed = []
    real_cuda_forward(kernel, config, workspace=observed)
    assert observed, "CUDA workspace operations were not reached"
    return max(observed)







class WorkspaceObservation:
    """Observe storage use without retaining tensors or extending allocation life."""
    def __init__(self):
        self.storages = {}
        self.snapshots = []

    def live(self):
        return {key: entry for key, entry in self.storages.items()
                if not entry['weak'].expired()}

    def peak_workspace_bytes(self, output_bytes, *, used=False):
        # Count distinct storage only while simultaneously alive. Matching the
        # two execution envelopes permits arenas, aliases and per-call storage.
        return max((sum(size for size, extent in sample
                        if size > output_bytes and (not used or extent > output_bytes))
                    for sample in self.snapshots), default=0)

    @contextlib.contextmanager
    def record(self, inputs):
        from torch.utils._python_dispatch import TorchDispatchMode
        from torch.multiprocessing.reductions import StorageWeakRef
        excluded = {t.untyped_storage()._cdata for t in inputs}
        entries = self.storages
        observation = self
        class Scope(TorchDispatchMode):
            def __torch_dispatch__(self, func, types, args=(), kwargs=None):
                result = func(*args, **(kwargs or {}))
                def record(value):
                    if isinstance(value, torch.Tensor) and value.is_cuda:
                        storage = value.untyped_storage()
                        key = storage._cdata
                        if key not in excluded:
                            if key not in entries:
                                entries[key] = {'weak': StorageWeakRef(storage),
                                                'bytes': storage.nbytes(), 'used_bytes': 0}
                            entries[key]['used_bytes'] = max(entries[key]['used_bytes'],
                                                            value.numel() * value.element_size())
                    elif isinstance(value, (tuple, list)):
                        for item in value: record(item)
                    elif isinstance(value, dict):
                        for item in value.values(): record(item)
                record(result)
                observation.snapshots.append([(entry['bytes'], entry['used_bytes'])
                                              for entry in observation.live().values()])
                return result
        with Scope():
            yield

def check_capacity_use(kernel, config):
    reservation = WorkspaceObservation()
    real_cuda_forward(kernel, config, observation=reservation)
    demand = WorkspaceObservation()
    real_cuda_forward(kernel, config, profile=False, observation=demand, repeat=(16384 + TOKENS - 1)//TOKENS)
    output_bytes = 16384 * HIDDEN * 2
    capacity = reservation.peak_workspace_bytes(output_bytes)
    required = demand.peak_workspace_bytes(output_bytes, used=True)
    assert required > output_bytes, 'no major workspace use observed'
    assert capacity >= required, ('profiling under-reserved workspace', capacity, required)
    return {'rows':16384, 'profile_capacity_bytes':capacity, 'required_bytes':required}


def cold_conflicting_capacity():
    dp = make_config(parallel_config=ParallelConfig(data_parallel_size=4, enable_expert_parallel=True))
    ordinary = make_config(parallel_config=ParallelConfig(data_parallel_size=1))
    clear_current_config()
    capture = Capture()
    logger = logging.getLogger('vllm.config.vllm')
    logger.addHandler(capture)
    logger.setLevel(logging.WARNING)
    kernel = make_kernel_through_factory(dp, ambient=ordinary)
    with set_current_vllm_config(ordinary):
        result = check_capacity_use(kernel, dp)
    assert WARNING not in capture.text, capture.text
    print(json.dumps({'cold_conflicting_capacity': result}), flush=True)


def explicit_sizes_probe(engine_dp):
    from vllm.model_executor.layers.fused_moe.layer import FusedMoE
    # A second geometry and real router execution independently exercise the
    # public layer override, outside the formal workload/serialization helpers.
    tokens, hidden, intermediate, experts, topk = 3, 128, 192, 6, 2
    engine = make_config(parallel_config=ParallelConfig(
        data_parallel_size=engine_dp, enable_expert_parallel=engine_dp > 1))
    local = make_config(parallel_config=ParallelConfig(data_parallel_size=1))
    with set_current_vllm_config(engine), torch.device('cuda'):
        layer = FusedMoE(experts, topk, hidden, intermediate, params_dtype=torch.float16,
                         tp_size=1, pcp_size=1, dp_size=1, prefix='local_override_challenge')
        layer.ensure_moe_quant_config_init()
    assert layer.dp_size == 1 and not layer.use_ep
    torch.manual_seed(67521)
    x = torch.randn(tokens, hidden, device='cuda', dtype=torch.float16)
    logits = torch.randn(tokens, experts, device='cuda', dtype=torch.float16)
    with torch.no_grad():
        layer.w13_weight.normal_(std=.04)
        layer.w2_weight.normal_(std=.04)
    capture = Capture()
    logger = logging.getLogger('vllm.config.vllm')
    logger.addHandler(capture)
    logger.setLevel(logging.WARNING)
    clear_current_config()
    method = method_module.FusedMoEModularMethod.make(
        layer, layer.quant_method, MoEPrepareAndFinalizeNoEP(), None)
    results = []
    for profile in (True, False, True):
        observation = WorkspaceObservation()
        kwargs = {} if profile else {'num_tokens': tokens}
        with set_current_vllm_config(engine), set_forward_context(None if profile else {}, local, **kwargs):
            with observation.record((x, logits, layer.w13_weight, layer.w2_weight)):
                output = method.apply(layer, x.clone(), logits, top_k=topk, renormalize=True,
                                      activation='silu', global_num_experts=experts, expert_map=layer.expert_map)
        torch.cuda.synchronize()
        assert output.is_cuda and output.shape == x.shape and torch.isfinite(output).all()
        results.append({'peak': observation.peak_workspace_bytes(0), 'output': output.float().cpu().tolist()})
    assert WARNING not in capture.text, capture.text
    print('EXPLICIT_SIZES=' + json.dumps(results), flush=True)


def check_explicit_sizes():
    bootstrap = "import runpy,sys;sys.path[:]=" + repr(sys.path) + ";runpy.run_path(sys.argv[1],run_name='__main__')"
    observed = []
    for size in (1, 3):
        child = subprocess.run([sys.executable, '-I', '-S', '-c', bootstrap,
                                __file__, '--explicit-sizes', str(size)],
                               text=True, capture_output=True, timeout=180)
        print(child.stdout, end='')
        assert child.returncode == 0, child.stderr
        rows = [line for line in child.stdout.splitlines() if line.startswith('EXPLICIT_SIZES=')]
        assert len(rows) == 1
        observed.append(json.loads(rows[0].split('=', 1)[1]))
    for ordinary, overridden in zip(*observed):
        assert ordinary['peak'] > 0 and ordinary['peak'] == overridden['peak'], 'explicit ordinary layer inherited engine workspace'
        assert ordinary['output'] == overridden['output'], 'effective ordinary output changed with engine configuration'
    return {'ordinary_peaks': [r['peak'] for r in observed[0]],
            'override_peaks': [r['peak'] for r in observed[1]]}


def main() -> None:
    assert torch.cuda.is_available(), "challenge requires CUDA"
    dp_ep = make_config(parallel_config=ParallelConfig(
        data_parallel_size=4, enable_expert_parallel=True))
    non_dp = make_config(parallel_config=ParallelConfig(
        data_parallel_size=1, enable_expert_parallel=False))

    logger = logging.getLogger("vllm.config.vllm")
    capture = Capture()
    logger.addHandler(capture)
    logger.setLevel(logging.WARNING)

    failures = {}
    stages = {}
    try:
        stages['explicit_layer_sizes'] = check_explicit_sizes()
        # A distinct process supplies genuinely cold storage without naming or
        # resetting the candidate's cache. It checks conflicting context first.
        bootstrap = "import runpy,sys;sys.path[:]=" + repr(sys.path) + ";runpy.run_path(sys.argv[1],run_name='__main__')"
        subprocess.run([sys.executable, '-I', '-S', '-c', bootstrap, __file__, '--cold-conflict'], check=True, timeout=180)
        stages['cold_conflicting_capacity'] = True
        # Observe ordinary ownership before a DP layer can populate the shared
        # backing buffers. Then check real DP allocation and warm capacity reuse.
        clear_current_config()
        non_dp_kernel = make_kernel_through_factory(non_dp, ambient=dp_ep)
        non_dp_workspace_bytes = measure_workspace(non_dp_kernel, non_dp)
        # The temporary global context has ended; the layer and its quant
        # method still retain valid config for construction and profiling.
        capture.buffer = io.StringIO()
        clear_current_config()
        kernel = make_kernel_through_factory(dp_ep)
        gap_norm = real_cuda_forward(kernel, dp_ep)
        gap_warned = WARNING in capture.text
        assert not gap_warned, f"spurious warning during lifecycle gap: {capture.text!r}"
        stages["lifecycle_gap"] = {"warned": gap_warned, "norm": gap_norm}
        transitions = []
        # The already-profiled instance must also work in ordinary forwards;
        # the DP counts are generated from the real rank-ordered token buffer.
        for label, ambient in [('gap',None), ('conflict',non_dp), ('matching',dp_ep), ('gap_again',None)]:
            clear_current_config()
            capture.buffer = io.StringIO()
            context = set_current_vllm_config(ambient) if ambient is not None else contextlib.nullcontext()
            with context:
                norm = real_cuda_forward(kernel, dp_ep, profile=False)
            assert WARNING not in capture.text, (label,capture.text)
            transitions.append({'ambient':label, 'norm':norm})
        stages['normal_forward_transitions'] = transitions
        clear_current_config()
        stages['profile_to_large_forward'] = check_capacity_use(kernel, dp_ep)
        # Return to the original ordinary layer after the other owner has run.
        with set_current_vllm_config(dp_ep):
            stages['ordinary_after_dp'] = real_cuda_forward(non_dp_kernel, non_dp, profile=False)

        # Genuine missing config must still warn.
        capture.buffer = io.StringIO()
        clear_current_config()
        assert vllm_config_module.get_current_vllm_config() is not None
        missing_warned = WARNING in capture.text
        assert missing_warned, "genuine missing-config warning was suppressed"
        stages["genuine_missing"] = {"warned": missing_warned}

        # Active-layer DP+EP resolution: disagree ambient vs layer both ways.
        clear_current_config()
        dp_kernel = make_kernel_through_factory(dp_ep, ambient=non_dp)
        dp_workspace_bytes = measure_workspace(dp_kernel, dp_ep)
        worst_case_bytes = 16384 * TOPK * max(2 * INTERMEDIATE, HIDDEN) * 2
        assert 0 < non_dp_workspace_bytes < worst_case_bytes
        stages['conflicting_owner_capacity'] = check_capacity_use(dp_kernel, dp_ep)
        stages["active_owner_workspace"] = {"dp_ep": dp_workspace_bytes, "non_dp": non_dp_workspace_bytes}
    except Exception as exc:  # noqa: BLE001 - report the failing stage
        failures["challenge"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }

    print(json.dumps({"stages": stages, "failures": failures}, indent=2, sort_keys=True))
    if failures:
        print("CHALLENGE_PROFILE_LIFECYCLE=FAIL")
        sys.exit(1)
    print("CHALLENGE_PROFILE_LIFECYCLE=PASS")


if __name__ == "__main__":
    if "--explicit-sizes" in sys.argv:
        explicit_sizes_probe(int(sys.argv[-1]))
    elif "--cold-conflict" in sys.argv:
        cold_conflicting_capacity()
    else:
        main()
