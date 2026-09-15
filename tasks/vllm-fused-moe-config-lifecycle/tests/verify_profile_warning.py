"""Behavioral GPU probe for modular-MoE config ownership and profiling."""

import contextlib
import io
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import torch
from workload import load_workload, PHASES, phase_order

import vllm.config.vllm as vllm_config_module
from vllm.config import ParallelConfig, SchedulerConfig, VllmConfig, set_current_vllm_config
from vllm.forward_context import set_forward_context
from vllm.model_executor.layers.fused_moe.config import FusedMoEQuantConfig
from vllm.model_executor.layers.fused_moe.fused_moe import TritonExperts
import vllm.model_executor.layers.fused_moe.fused_moe_modular_method as method_module
from vllm.model_executor.layers.fused_moe.modular_kernel import (
    FusedMoEModularKernel,
)
from vllm.model_executor.layers.fused_moe.prepare_finalize import (
    MoEPrepareAndFinalizeNoEP,
)

WARNING = "Current vLLM config is not set."


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


def make_kernel_through_factory(config, ambient=None, *, experts=4, topk=2, hidden=64):
    """Build through the production layer factory, not a private constructor API."""

    original_method = method_module.FusedMoEModularMethod
    quant = FusedMoEQuantConfig.make(None)

    # Construct the production quant method with its real configuration. Model
    # weight loading is outside this profile slice; the forward receives tensors.
    from vllm.model_executor.layers.fused_moe.config import (
        FusedMoEConfig, FusedMoEParallelConfig,
    )
    from vllm.model_executor.layers.fused_moe.unquantized_fused_moe_method import (
        UnquantizedFusedMoEMethod,
    )
    parallel = config.parallel_config
    dp = parallel.data_parallel_size
    rank = parallel.data_parallel_rank
    ep = parallel.enable_expert_parallel and dp > 1
    owner = FusedMoEParallelConfig(
        tp_size=1 if ep else dp, tp_rank=0, pcp_size=1, pcp_rank=0,
        dp_size=dp, dp_rank=rank, ep_size=dp if ep else 1, ep_rank=rank if ep else 0,
        use_ep=ep, all2all_backend=parallel.all2all_backend,
    )
    from vllm.model_executor.layers.fused_moe.layer import determine_expert_map
    local_count, expert_map, _ = determine_expert_map(owner.ep_size, owner.ep_rank, experts)
    owned = torch.arange(experts) if expert_map is None else torch.where(expert_map >= 0)[0]
    # This is the same local weight ownership and global-to-local map that the
    # production FusedMoE constructor derives. No replicated EP weight fixture.
    owned_cuda = owned.to(device='cuda')
    map_cuda = expert_map.to(device='cuda') if expert_map is not None else None
    moe = FusedMoEConfig(
        num_experts=experts, experts_per_token=topk,
        hidden_dim=hidden, num_local_experts=local_count,
        moe_parallel_config=owner, in_dtype=torch.float16,
    )
    # CustomOp dispatch initialization requires the normal model-init context.
    # It ends before the production factory/kernel lifecycle under test.
    with set_current_vllm_config(config):
        old_quant = UnquantizedFusedMoEMethod(moe)
    old_quant.moe_quant_config = quant
    layer = SimpleNamespace(
        vllm_config=config, moe_config=moe, moe_parallel_config=owner,
        quant_method=old_quant, shared_experts_stream=None,
    )
    context = (
        set_current_vllm_config(ambient)
        if ambient is not None
        else contextlib.nullcontext()
    )
    with context:
        method = original_method.make(
            layer, old_quant, MoEPrepareAndFinalizeNoEP(), None,
        )
    def forward(x, w1, w2, weights, ids, *, activation, global_num_experts):
        # We supply deterministic router outputs and loaded weights; the real
        # modular method owns dispatch and all access to its internal storage.
        layer.w13_weight = w1.index_select(0, owned_cuda).contiguous()
        layer.w2_weight = w2.index_select(0, owned_cuda).contiguous()
        layer.zero_expert_num, layer.zero_expert_type = 0, None
        layer.select_experts = lambda *args, **kwargs: (weights, ids, None)
        router_logits = torch.zeros((len(x), global_num_experts), device=x.device, dtype=x.dtype)
        return method.apply(
            layer, x, router_logits, top_k=ids.shape[1], renormalize=False,
            activation=activation, global_num_experts=global_num_experts, expert_map=map_cuda,
        )
    forward.owned_experts = owned.tolist()
    forward.expert_map = None if expert_map is None else expert_map.tolist()
    return forward


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



def serialize_moe(inputs, output):
    x, w1, w2, weights, ids = inputs
    return {"x": x.float().cpu().tolist(), "w1": w1.float().cpu().tolist(),
            "w2": w2.float().cpu().tolist(), "weights": weights.float().cpu().tolist(),
            "ids": ids.cpu().tolist(), "output": output.float().cpu().tolist(),
            "dtype": str(x.dtype), "device": output.device.type}


def execute_phase(kernel, config, case, *, profile, observation=None, repeat=1):
    dtype = torch.float16
    x, w1, w2, weights = [torch.tensor(case[k], device='cuda', dtype=dtype)
                          for k in ('x', 'w1', 'w2', 'weights')]
    ids = torch.tensor(case['ids'], device='cuda', dtype=torch.long)
    if repeat != 1:
        x = x.repeat(repeat, 1)
        weights = weights.repeat(repeat, 1)
        ids = ids.repeat(repeat, 1)
    recorded_x = x.clone()
    dp = config.parallel_config.data_parallel_size
    # At this boundary x is the rank-ordered activation buffer after allgather.
    # Split/cat derives valid per-engine token counts without simulating the
    # behavior under test: configuration binding and real local expert execution.
    engine_inputs = torch.tensor_split(x, dp)
    token_counts = torch.tensor([len(part) for part in engine_inputs], dtype=torch.int32)
    assert torch.equal(torch.cat(engine_inputs), x)
    local_tokens = int(token_counts[config.parallel_config.data_parallel_rank])
    assert local_tokens <= config.scheduler_config.max_num_batched_tokens
    context_args = {} if profile else {'num_tokens': local_tokens, 'num_tokens_across_dp': token_counts}
    observation = observation or WorkspaceObservation()
    with set_forward_context(None if profile else {}, config, **context_args), observation.record((x,w1,w2,weights,ids)):
        out = kernel(x, w1, w2, weights, ids, activation='silu', global_num_experts=len(w1))
    torch.cuda.synchronize()
    assert out.is_cuda and out.shape == x.shape and torch.isfinite(out).all()
    assert observation.storages, 'real CUDA path was not reached'
    if repeat == 1:
        result = serialize_moe((recorded_x,w1,w2,weights,ids), out)
    else:
        # All repeated rows are checked: retain min and max over each equal-input
        # row class, rather than serializing a large repeated JSON tensor.
        grouped = out.reshape(repeat, len(case['x']), out.shape[-1]).float()
        result = {'output_min': grouped.amin(dim=0).cpu().tolist(),
                  'output_max': grouped.amax(dim=0).cpu().tolist(),
                  'rows': len(out), 'dtype': str(out.dtype), 'device': out.device.type}
    result.update(workspace_bytes=max(entry['bytes'] for entry in observation.storages.values()),
                  live_workspace_bytes=sum(entry['bytes'] for entry in observation.live().values()),
                  owned_experts=kernel.owned_experts, expert_map=kernel.expert_map,
                  token_counts=token_counts.tolist())
    return result


def capacity_probe(kernel, config, case, reserved, phase):
    demand = WorkspaceObservation()
    rows = 16384
    assert rows % len(case['x']) == 0
    large = execute_phase(kernel, config, case, profile=False,
                          observation=demand, repeat=rows // len(case['x']))
    # The caller-owned result is allocated per call, not a reusable workspace.
    # For this backend/geometry, both major routing intermediates are larger
    # than that result. Ignore output-sized and small routing/weight temporaries;
    # match actual workspace storage use without naming candidate buffers.
    boundary = rows * len(case['x'][0]) * 2
    profile_peak = reserved.peak_workspace_bytes(boundary)
    required_peak = demand.peak_workspace_bytes(boundary, used=True)
    large.update(profile_workspace_capacity_bytes=profile_peak,
                 required_workspace_peak_bytes=required_peak,
                 phase=phase, x=case['x'], w1=case['w1'], w2=case['w2'],
                 weights=case['weights'], ids=case['ids'])
    return large


def execute_owner(selected):
    assert torch.cuda.is_available()
    workload = load_workload()
    logger = logging.getLogger('vllm.config.vllm')
    capture = Capture()
    logger.addHandler(capture)
    logger.setLevel(logging.WARNING)
    results, constructors, capacities = [], [], []
    for kind, dp, ep, ranks in [('dp_ep',2,True,(0,1)), ('ordinary',1,False,(0,))]:
        for rank in ranks:
            config = make_config(parallel_config=ParallelConfig(
                data_parallel_size=dp, data_parallel_rank=rank, enable_expert_parallel=ep))
            other = make_config(parallel_config=ParallelConfig(
                data_parallel_size=1 if ep else 2, enable_expert_parallel=not ep))
            for construction in ('gap', 'conflict'):
                if (kind,rank,construction) != selected:
                    continue
                clear_current_config()
                capture.buffer = io.StringIO()
                kernel = make_kernel_through_factory(config, ambient=other if construction == 'conflict' else None)
                constructors.append({'kind':kind, 'rank':rank, 'construction':construction, 'warned':WARNING in capture.text})
                # Reuse this exact production factory result through all transitions.
                for phase in phase_order(construction):
                    index = PHASES.index(phase)
                    clear_current_config()
                    capture.buffer = io.StringIO()
                    ambient = config if phase.endswith('matching') else other if phase.endswith('conflict') else None
                    context = set_current_vllm_config(ambient) if ambient is not None else contextlib.nullcontext()
                    with context:
                        observation = WorkspaceObservation()
                        result = execute_phase(kernel, config, workload['numerics'][index],
                                               profile=phase.startswith('profile'), observation=observation)
                        if kind == 'dp_ep' and phase == 'profile_' + construction:
                            # Check the very first cold profile before a later
                            # matching context can populate a missed reservation.
                            capacity = capacity_probe(kernel, config, workload['numerics'][index], observation, phase)
                            capacity.update(kind=kind, rank=rank, construction=construction, warned=WARNING in capture.text)
                            capacities.append(capacity)
                    result.update(kind=kind, rank=rank, construction=construction, phase=phase, warned=WARNING in capture.text)
                    results.append(result)
                    print(json.dumps({'kind':kind,'rank':rank,'construction':construction,'phase':phase,'warned':result['warned'],
                                      'workspace_bytes':result['workspace_bytes'],'owned_experts':result['owned_experts']}), flush=True)
    clear_current_config()
    capture.buffer = io.StringIO()
    vllm_config_module.get_current_vllm_config()
    raw = {'constructors':constructors, 'numerics':results, 'missing_warnings':WARNING in capture.text, 'capacities':capacities}
    with open(os.environ['AIB_OBSERVATIONS'], 'w') as stream:
        json.dump(raw, stream)
    print('PROFILE_WARNING_OBSERVATIONS_COMPLETE')


def execute_interleaved():
    case = load_workload()['numerics'][0]
    ordinary = make_config(parallel_config=ParallelConfig(data_parallel_size=1))
    dp = make_config(parallel_config=ParallelConfig(data_parallel_size=2, enable_expert_parallel=True))
    capture = Capture()
    logger = logging.getLogger('vllm.config.vllm')
    logger.addHandler(capture)
    logger.setLevel(logging.WARNING)
    clear_current_config()
    a = make_kernel_through_factory(ordinary, ambient=dp)
    b = make_kernel_through_factory(dp, ambient=ordinary)
    assert WARNING not in capture.text, 'interleaved layer construction warned'
    results = []
    for label, kernel, config, ambient, profile, kind in [
        ('a_profile', a, ordinary, dp, True, 'ordinary'),
        ('b_profile', b, dp, ordinary, True, 'dp_ep'),
        ('a_forward', a, ordinary, dp, False, 'ordinary'),
        ('b_forward', b, dp, ordinary, False, 'dp_ep'),
        ('a_profile_again', a, ordinary, dp, True, 'ordinary'),
    ]:
        clear_current_config()
        capture.buffer = io.StringIO()
        with set_current_vllm_config(ambient):
            result = execute_phase(kernel, config, case, profile=profile)
        result.update(label=label, kind=kind, rank=0, phase='profile_matching', warned=WARNING in capture.text)
        results.append(result)
    logger.removeHandler(capture)
    return results


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--layer-override':
        from verify_layer_overrides import execute
        execute(int(sys.argv[2]))
        return
    if len(sys.argv) > 1 and sys.argv[1] == '--owner':
        execute_owner((sys.argv[2], int(sys.argv[3]), sys.argv[4]))
        return
    # Every layer starts in a fresh process: another layer's global workspace
    # must not hide a missed cold reservation. Each child retains one factory
    # result across all profile/forward transitions, including warm reuse.
    combined = {'constructors': [], 'numerics': [], 'missing_warnings': True, 'capacities': []}
    bootstrap = "import runpy,sys; sys.path[:]=" + repr(sys.path) + "; script=sys.argv.pop(1); runpy.run_path(script,run_name='__main__')"
    with tempfile.TemporaryDirectory(prefix='moe-lifecycle-') as directory:
        combined['layer_overrides'] = []
        for engine_dp in (1, 2):
            output = Path(directory) / f'layer-override-{engine_dp}.json'
            env = dict(os.environ, AIB_OBSERVATIONS=str(output))
            subprocess.run([sys.executable, '-I', '-S', '-c', bootstrap,
                            __file__, '--layer-override', str(engine_dp)],
                           env=env, check=True, timeout=180)
            combined['layer_overrides'].append(json.loads(output.read_text()))
        for kind, rank in [('dp_ep',0), ('dp_ep',1), ('ordinary',0)]:
            for construction in ('gap','conflict'):
                output = Path(directory) / f'{kind}-{rank}-{construction}.json'
                env = dict(os.environ, AIB_OBSERVATIONS=str(output))
                subprocess.run([sys.executable, '-I', '-S', '-c', bootstrap,
                                __file__, '--owner', kind, str(rank), construction],
                               env=env, check=True, timeout=180)
                observed = json.loads(output.read_text())
                combined['constructors'].extend(observed['constructors'])
                combined['numerics'].extend(observed['numerics'])
                combined['capacities'].extend(observed['capacities'])
                combined['missing_warnings'] &= observed['missing_warnings']
    combined['interleaved'] = execute_interleaved()
    Path(os.environ['AIB_OBSERVATIONS']).write_text(json.dumps(combined))
    print('ALL_OWNER_LIFECYCLES_OBSERVED', flush=True)


if __name__ == '__main__':
    main()
