"""CPU execution boundary for the real scheduler and GPUModelRunner.

Only media/model arithmetic and CUDA runtime primitives are substituted. Real
constructors, request admission, schedule(), execute_model(), input preparation,
batching, encoder-cache writes/reads, and the model's embedding merge run.
The decoder has no attention layers: decoder KV arithmetic is outside this task.
This module is compiled by the trusted parent and executed after privilege drop.
"""
import gc
import os
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import vllm  # Candidate import is a deliberate, reachable completion boundary.
import torch
from transformers import LlamaConfig, LlavaConfig, Qwen3VLConfig
from vllm.config import (
    CacheConfig, CompilationConfig, DeviceConfig, ModelConfig, ParallelConfig,
    SchedulerConfig, SpeculativeConfig, VllmConfig, set_current_vllm_config,
)
from vllm.distributed import (
    destroy_distributed_environment, destroy_model_parallel,
    init_distributed_environment, initialize_model_parallel,
)
from vllm.model_executor.models import ModelRegistry
from vllm.model_executor.models.interfaces import SupportsMultiModal
from vllm.multimodal.inputs import (
    MultiModalBatchedField, MultiModalFeatureSpec, MultiModalFieldElem,
    MultiModalKwargsItem, MultiModalKwargsItems, PlaceholderRange,
)
from vllm.multimodal.profiling import ProcessorInputs
from vllm.multimodal.processing import PromptUpdateDetails
from vllm.multimodal.registry import MultiModalRegistry
from vllm.multimodal import MULTIMODAL_REGISTRY
from vllm.sampling_params import SamplingParams
from vllm.v1.core.sched.scheduler import Scheduler
from vllm.v1.kv_cache_interface import KVCacheConfig
from vllm.v1.outputs import ModelRunnerOutput
from vllm.v1.sample.metadata import SamplingMetadata
from vllm.v1.sample.logits_processor import LogitsProcessors
from vllm.v1.request import Request
from vllm.v1.structured_output import StructuredOutputManager
from vllm.v1.worker.gpu_model_runner import GPUModelRunner
from vllm.platforms import current_platform
import vllm.v1.worker.gpu_model_runner as runner_module
import vllm.v1.worker.utils as worker_utils


WIDTH = 16
MEDIA_TOKEN = 250


def media_item(spec):
    """A legal processor result: token positions, mask and encoder rows agree."""
    indices = spec['indices']
    mask = None
    if indices is not None:
        tokens = [MEDIA_TOKEN if i in indices else 17 for i in range(spec['length'])]
        update = PromptUpdateDetails.select_token_id(tokens, MEDIA_TOKEN)
        mask = update.is_embed(None, update.full)
    payload = torch.tensor(spec['rows'], dtype=torch.float32).reshape(-1, WIDTH)
    data = MultiModalKwargsItem.from_elems([
        MultiModalFieldElem(spec.get('modality', 'image'), 'rows', payload,
                            MultiModalBatchedField())])
    return PlaceholderRange(spec.get('offset', 0), spec['length'], mask), data


class MediaProcessor:
    """Controlled external processor/encoder geometry, with real MM containers."""
    def __init__(self, spec):
        self.spec = spec
        self.info = self
        self.dummy_inputs = self
        self.modality = spec.get('modality', 'image')
        self.allowed_mm_limits = {self.modality: 8}

    def get_mm_max_tokens_per_item(self, **kwargs):
        return None

    def get_supported_mm_limits(self):
        return self.allowed_mm_limits

    def get_dummy_processor_inputs(self, seq_len, mm_counts, mm_options=None):
        return ProcessorInputs(prompt=[MEDIA_TOKEN], mm_data={self.modality: [self.spec]})

    def apply(self, prompt, mm_data, **kwargs):
        position, data = media_item(self.spec)
        selected = set(range(position.length) if self.spec['indices'] is None
                       else self.spec['indices'])
        tokens = [MEDIA_TOKEN if i in selected else 17 for i in range(position.length)]
        return {'type': 'multimodal', 'prompt_token_ids': tokens,
                'mm_kwargs': MultiModalKwargsItems({self.modality: [data]}),
                'mm_hashes': {self.modality: ['profile-item']},
                'mm_placeholders': {self.modality: [position]}}


class ModelInputObserved(Exception):
    """Stop after the real caller has delivered the actual decoder input."""


class EmptyWeightProfile:
    """The controlled neural model owns no learned parameter storage."""
    consumed_memory = 0
    initial_memory = 0
    final_memory = 0

    def __init__(self, *args, **kwargs):
        pass

    def current_memory_usage(self):
        return 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TextArithmetic:
    def embed_input_ids(self, ids):
        return ids.to(torch.float32).unsqueeze(1).repeat(1, WIDTH)


class ObservedModel(torch.nn.Module, SupportsMultiModal):
    def __init__(self, vllm_config=None, prefix=''):
        super().__init__()
        self.inputs = []
        self.encodings = []
        self.on_encode = None
        self.on_forward = None

    def get_language_model(self):
        return TextArithmetic()

    def embed_multimodal(self, rows, **kwargs):
        result = [value.clone() for value in rows]
        self.encodings.extend(value.tolist() for value in result)
        if self.on_encode:
            self.on_encode(result)
        return result

    def forward(self, input_ids, positions, inputs_embeds=None, **kwargs):
        if inputs_embeds is None:
            inputs_embeds = self.get_language_model().embed_input_ids(input_ids)
        self.inputs.append({'positions': positions.tolist(), 'rows': inputs_embeds.tolist()})
        if self.on_forward:
            self.on_forward()
        raise ModelInputObserved()

    def compute_logits(self, hidden_states):
        return hidden_states


class ObservedDraft:
    """Draft neural arithmetic boundary; runner chooses and gathers its window."""
    def __init__(self, config, device, runner):
        self.runner = runner
        self.inputs = []

    def validate_same_kv_cache_group(self, config):
        # The controlled draft arithmetic has no attention layers.
        if config.kv_cache_groups:
            raise ValueError('the decoder substitute expects no attention layers')

    def load_model(self, model):
        self.model = model

    def prepare_next_token_ids_cpu(self, samples, requests, batch, scheduled):
        self.req_ids = list(batch.req_ids)
        self.counts = [scheduled[rid] for rid in self.req_ids]
        return torch.tensor([
            requests[rid].prompt_token_ids[end]
            if (end := requests[rid].num_computed_tokens + scheduled[rid])
            < len(requests[rid].prompt_token_ids) else samples[i][-1]
            for i, rid in enumerate(self.req_ids)], dtype=torch.int32)

    def propose(self, *, target_token_ids, target_positions, next_token_ids,
                mm_embed_inputs, **kwargs):
        tokens = []
        cursor = 0
        for i, count in enumerate(self.counts):
            tokens.extend(target_token_ids[cursor + 1:cursor + count].tolist())
            tokens.append(int(next_token_ids[i]))
            cursor += count
        embeds, flags = mm_embed_inputs
        actual = self.runner.get_model().embed_input_ids(
            torch.tensor(tokens, dtype=torch.int32),
            multimodal_embeddings=embeds, is_multimodal=flags)
        self.inputs.append({'positions': (target_positions + 1).tolist(),
                            'rows': actual.tolist()})
        return [[17] for _ in self.req_ids]


def _cpu_factory(original):
    def call(*args, **kwargs):
        if str(kwargs.get('device', '')).startswith('cuda'):
            kwargs['device'] = 'cpu'
        if 'pin_memory' in kwargs:
            kwargs['pin_memory'] = False
        return original(*args, **kwargs)
    return call


class Runtime:
    """One initialized process; every scenario gets new runner/request state."""
    def __enter__(self):
        self.stack = ExitStack()
        self.tmp = Path(self.stack.enter_context(TemporaryDirectory(prefix='encoder-runtime-')))
        self.stack.enter_context(patch.dict(os.environ, {
            'VLLM_CACHE_ROOT': str(self.tmp / 'cache'), 'GLOO_SOCKET_IFNAME': 'lo'}))
        torch.set_num_threads(1)
        self.processor = None
        MULTIMODAL_REGISTRY.register_processor(
            lambda *a, **k: self.processor,
            info=lambda ctx: self.processor,
            dummy_inputs=lambda info: self.processor)(ObservedModel)
        ModelRegistry.register_model('EncoderVerifierModel', ObservedModel)
        ModelRegistry.register_model('EagleEncoderVerifierModel', ObservedModel)
        hf = LlavaConfig(
            text_config={'model_type': 'llama', 'hidden_size': WIDTH,
                         'intermediate_size': 32, 'num_hidden_layers': 1,
                         'num_attention_heads': 2, 'num_key_value_heads': 2,
                         'max_position_embeddings': 8192, 'vocab_size': 256},
            vision_config={'hidden_size': WIDTH, 'intermediate_size': 32,
                           'num_hidden_layers': 1, 'num_attention_heads': 2,
                           'image_size': 14, 'patch_size': 14},
            image_token_index=MEDIA_TOKEN)
        hf.architectures = ['EncoderVerifierModel']
        hf.dtype = torch.float32
        hf.to_json_file(self.tmp / 'config.json')
        self.draft_path = self.tmp / 'draft'
        self.draft_path.mkdir()
        draft_hf = LlamaConfig(hidden_size=WIDTH, intermediate_size=32,
            num_hidden_layers=1, num_attention_heads=2, num_key_value_heads=2,
            max_position_embeddings=8192, vocab_size=256)
        draft_hf.architectures = ['EncoderVerifierModel']
        draft_hf.dtype = torch.float32
        draft_hf.to_json_file(self.draft_path / 'config.json')
        self.model_config = ModelConfig(
            model=str(self.tmp), tokenizer=str(self.tmp), skip_tokenizer_init=True,
            dtype='float32', max_model_len=8192, enforce_eager=True,
            disable_cascade_attn=True)
        video_path = self.tmp / 'video'
        video_path.mkdir()
        video_hf = Qwen3VLConfig(
            text_config={'hidden_size': WIDTH, 'intermediate_size': 32,
                         'num_hidden_layers': 1, 'num_attention_heads': 2,
                         'num_key_value_heads': 2, 'max_position_embeddings': 8192,
                         'vocab_size': 256},
            vision_config={'hidden_size': WIDTH, 'intermediate_size': 32,
                           'depth': 1, 'num_heads': 2, 'out_hidden_size': WIDTH,
                           'patch_size': 14, 'spatial_merge_size': 2,
                           'temporal_patch_size': 1})
        video_hf.architectures = ['EncoderVerifierModel']
        video_hf.dtype = torch.float32
        video_hf.to_json_file(video_path / 'config.json')
        self.video_config = ModelConfig(
            model=str(video_path), tokenizer=str(video_path), skip_tokenizer_init=True,
            dtype='float32', max_model_len=8192, enforce_eager=True,
            disable_cascade_attn=True)
        for name in ('tensor', 'empty', 'zeros', 'ones', 'arange', 'full'):
            self.stack.enter_context(patch.object(torch, name, _cpu_factory(getattr(torch, name))))
        self.stack.enter_context(patch.object(torch.cuda, 'Stream', lambda *a, **k: torch.Stream(device='cpu')))
        self.stack.enter_context(patch.object(torch.cuda, 'get_device_properties', lambda *a: SimpleNamespace(multi_processor_count=1)))
        self.stack.enter_context(patch.object(torch.cuda, 'synchronize', lambda *a, **k: None))
        self.stack.enter_context(patch.object(torch, 'Event', lambda *a, **k: None))
        # The controlled neural model has no learned weights. Device bookkeeping
        # during loading is zero; encoder/profile storage is measured separately.
        self.stack.enter_context(patch.object(type(current_platform),
            'get_current_memory_usage', classmethod(lambda cls, *a, **k: 0)))
        self.stack.enter_context(patch.object(runner_module, 'DeviceMemoryProfiler', EmptyWeightProfile))
        self.stack.enter_context(patch.object(runner_module, 'EagleProposer', ObservedDraft))
        # Only the external media factory and its optional preprocessing cache
        # are controlled. Profiler and registry production methods remain real.
        self.stack.enter_context(patch.object(worker_utils, 'processor_only_cache_from_config', lambda *a, **k: None))
        initial = self.config(8, 4)
        self.stack.enter_context(set_current_vllm_config(initial))
        init_distributed_environment(world_size=1, rank=0, local_rank=0,
            distributed_init_method='file://' + str(self.tmp / 'gloo'), backend='gloo')
        initialize_model_parallel(1, 1, backend='gloo')
        return self

    def config(self, chunk, max_seqs, *, per_request=0, eagle=False):
        parallel = ParallelConfig()
        spec = None
        if eagle:
            spec = SpeculativeConfig(
                method='eagle', model=str(self.draft_path), num_speculative_tokens=1,
                disable_padded_drafter_batch=True,
                target_model_config=self.model_config, target_parallel_config=parallel)
        return VllmConfig(
            model_config=self.model_config, parallel_config=parallel,
            speculative_config=spec,
            scheduler_config=SchedulerConfig(
                max_model_len=8192, max_num_batched_tokens=chunk,
                max_num_seqs=max_seqs, long_prefill_token_threshold=per_request,
                enable_chunked_prefill=True, is_multimodal_model=True,
                is_encoder_decoder=False, disable_chunked_mm_input=False),
            cache_config=CacheConfig(block_size=16, enable_prefix_caching=False),
            device_config=DeviceConfig(device='cpu'),
            compilation_config=CompilationConfig(mode=0, cudagraph_mode='NONE'))

    def pair(self, profile_spec, chunk=4, max_seqs=1, *, per_request=0, eagle=False,
             processor=None):
        self.processor = processor if processor is not None else MediaProcessor(profile_spec)
        config = self.config(chunk, max_seqs, per_request=per_request, eagle=eagle)
        context = set_current_vllm_config(config)
        context.__enter__()
        try:
            model = ObservedModel()
            runner = GPUModelRunner(config, torch.device('cpu'))
            loader = SimpleNamespace(load_model=lambda **kwargs: model)
            with patch.object(runner_module, 'get_model_loader', lambda config: loader):
                runner.load_model()
            model = runner.get_model()
            kv = KVCacheConfig(num_blocks=512, kv_cache_tensors=[], kv_cache_groups=[])
            runner.initialize_kv_cache(kv)
            config.cache_config.num_gpu_blocks = 512
            scheduler = Scheduler(config, kv, StructuredOutputManager(config),
                                  block_size=16, mm_registry=MultiModalRegistry())
            return EnginePair(scheduler, runner, model, context, eagle)
        except BaseException:
            context.__exit__(None, None, None)
            raise

    def __exit__(self, *exc):
        destroy_model_parallel()
        destroy_distributed_environment()
        self.stack.close()


class EnginePair:
    def __init__(self, scheduler, runner, model, context, eagle):
        self.scheduler, self.runner, self.model = scheduler, runner, model
        self.context, self.eagle = context, eagle
        self.workloads = {}
        self.delivered = {}
        self.draft_delivered = {}
        self.trace = []

    def add(self, workload):
        rid = workload['id']
        features = []
        for i, spec in enumerate(workload['features']):
            assert 0 <= spec['offset'] <= spec['offset'] + spec['length'] <= len(workload['tokens'])
            chosen = range(spec['length']) if spec['indices'] is None else spec['indices']
            assert len(spec['rows']) == len(chosen)
            assert all(workload['tokens'][spec['offset'] + p] == MEDIA_TOKEN for p in chosen)
            position, data = media_item(spec)
            features.append(MultiModalFeatureSpec(data=data, modality='image',
                identifier=spec.get('identifier', f'{rid}-media-{i}'), mm_position=position))
        request = Request(request_id=rid, prompt_token_ids=workload['tokens'],
            sampling_params=SamplingParams(max_tokens=1, temperature=0),
            pooling_params=None, eos_token_id=None, mm_features=features)
        self.workloads[rid] = workload
        self.delivered[rid] = {'positions': [], 'rows': []}
        self.draft_delivered[rid] = {'positions': [], 'rows': []}
        self.scheduler.add_request(request)
        return request

    def _expected_chunk(self, rid, start, count, shift=0):
        workload = self.workloads[rid]
        rows = {spec['offset'] + p: row for spec in workload['features']
                for p, row in zip(range(spec['length']) if spec['indices'] is None
                                  else spec['indices'], spec['rows'])}
        positions = list(range(start + shift, start + shift + count))
        values = [rows[p] if p in rows else
                  [workload['tokens'][p] if p < len(workload['tokens']) else 17] * WIDTH
                  for p in positions]
        return {'positions': positions, 'rows': values}

    def _match_input(self, actual, starts, counts, shift=0):
        # The candidate may reorder requests. Match complete distinct request
        # chunks by their values and positions rather than prescribing row order.
        remaining = set(counts)
        cursor = 0
        order = []
        while remaining:
            found = None
            for rid in sorted(remaining):
                count = counts[rid]
                wanted = self._expected_chunk(rid, starts[rid], count, shift)
                seen = {key: actual[key][cursor:cursor + count] for key in wanted}
                if seen == wanted:
                    found = rid
                    destination = self.draft_delivered if shift else self.delivered
                    for key in wanted:
                        destination[rid][key].extend(seen[key])
                    break
            if found is None:
                raise AssertionError(f'actual model input mismatch: shift={shift}, '
                    f'starts={starts}, counts={counts}, observed={actual}')
            remaining.remove(found)
            order.append(found)
            cursor += counts[found]
        assert cursor == len(actual['rows']) == len(actual['positions'])
        return order

    def step(self):
        starts = {rid: req.num_computed_tokens for rid, req in self.scheduler.requests.items()}
        before = len(self.model.encodings)
        output = self.scheduler.schedule()
        counts = dict(output.num_scheduled_tokens)
        if not counts:
            raise AssertionError('runnable prompt made no progress')
        try:
            self.runner.execute_model(output)
        except ModelInputObserved:
            pass
        else:
            raise AssertionError('execute_model did not reach the model input boundary')
        order = self._match_input(self.model.inputs.pop(), starts, counts)
        emitted_by_id = {
            rid: [17] if starts[rid] + counts[rid] >= len(self.workloads[rid]['tokens'])
            else [] for rid in counts}
        emitted = [emitted_by_id[rid] for rid in order]
        if self.eagle:
            total = output.total_num_scheduled_tokens
            # The decoder substitute emits greedy output without penalties or
            # logprobs. Build its public sampling record instead of inspecting a
            # named runner input buffer or sampler bookkeeping container.
            sampling = SamplingMetadata(
                temperature=None, all_greedy=True, all_random=False,
                top_p=None, top_k=None, generators={}, max_num_logprobs=None,
                no_penalties=True, prompt_token_ids=None,
                frequency_penalties=torch.zeros(len(counts)),
                presence_penalties=torch.zeros(len(counts)),
                repetition_penalties=torch.ones(len(counts)),
                output_token_ids=[[] for _ in counts], allowed_token_ids_mask=None,
                bad_words_token_ids={}, logitsprocs=LogitsProcessors([]))
            self.runner.propose_draft_token_ids(
                output, emitted, sampling,
                torch.zeros(total, WIDTH), torch.zeros(len(counts), WIDTH),
                None, None, SimpleNamespace(num_actual_tokens=total))
            self._match_input(self.runner.drafter.inputs.pop(), starts, counts, 1)
        model_output = ModelRunnerOutput(req_ids=order,
            req_id_to_index={rid: i for i, rid in enumerate(order)},
            sampled_token_ids=emitted, logprobs=None,
            prompt_logprobs_dict={}, pooler_output=[])
        self.scheduler.update_from_output(output, model_output)
        record = {'counts': counts, 'starts': starts,
                  'encoded': self.model.encodings[before:]}
        self.trace.append(record)
        return record

    def finish(self):
        limit = sum(len(w['tokens']) for w in self.workloads.values()) + 8
        for _ in range(limit):
            if self.scheduler.get_num_unfinished_requests() == 0:
                break
            self.step()
        else:
            raise AssertionError('requests did not finish')
        # Deliver completion/eviction notifications through the public runner.
        final = self.scheduler.schedule()
        self.runner.execute_model(final)
        return self.delivered

    def close(self):
        self.context.__exit__(None, None, None)
