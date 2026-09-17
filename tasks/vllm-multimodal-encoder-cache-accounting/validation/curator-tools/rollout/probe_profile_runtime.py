"""Diagnostic: same maximal media output, live versus profiled cache storage.

Not a scored test. Both encoder-cache writers and profile_run remain production
code. Replace only media preprocessing/inference and downstream decoder work.
Cache layout is unrestricted: observe unique backing tensor storage bytes.
"""
import json
from collections.abc import Mapping
from types import SimpleNamespace
import torch
from vllm.config import SchedulerConfig
from vllm.multimodal.inputs import MultiModalFeatureSpec, PlaceholderRange
from vllm.multimodal.profiling import MultiModalProfiler
from vllm.multimodal.registry import MultiModalRegistry
from vllm.v1.worker.gpu_model_runner import GPUModelRunner
from vllm.v1.worker.utils import MultiModalBudget
import vllm.v1.worker.gpu_model_runner as runner_module
import vllm.v1.worker.utils as worker_utils


def storage_bytes(value):
    storages={}
    def visit(item):
        if isinstance(item,torch.Tensor):
            storage=item.untyped_storage()
            storages[storage.data_ptr()]=storage.nbytes()
        elif isinstance(item,Mapping):
            for child in item.values():visit(child)
        elif isinstance(item,(tuple,list)):
            for child in item:visit(child)
    visit(value)
    return sum(storages.values())


def observe(length,indices,width):
    mask=torch.zeros(length,dtype=torch.bool);mask[indices]=True
    position=PlaceholderRange(3,length,mask)
    payload=torch.arange(len(indices)*width,dtype=torch.float32).reshape(-1,width)
    processor=SimpleNamespace(info=SimpleNamespace(get_mm_max_tokens_per_item=lambda **kw:None),allowed_mm_limits={'image':1})
    registry=object.__new__(MultiModalRegistry)
    registry.create_processor=lambda *args,**kw:processor
    registry.supports_multimodal_inputs=lambda *args:True
    model_config=SimpleNamespace(is_multimodal_model=True,max_model_len=256,
                                 multimodal_config=SimpleNamespace(skip_mm_profiling=False))
    config=SchedulerConfig(max_model_len=256,is_encoder_decoder=False,
        max_num_batched_tokens=1,max_num_seqs=1,enable_chunked_prefill=True,
        is_multimodal_model=True,disable_chunked_mm_input=False)
    old_dummy=MultiModalProfiler._get_dummy_mm_inputs
    old_cache=worker_utils.processor_only_cache_from_config
    old_group=runner_module.group_mm_kwargs_by_modality
    old_pp=runner_module.get_pp_group
    try:
        MultiModalProfiler._get_dummy_mm_inputs=lambda *args,**kw:{'mm_placeholders':{'image':[position]}}
        worker_utils.processor_only_cache_from_config=lambda *args,**kw:None
        budget=MultiModalBudget(model_config,config,registry)
        runner=object.__new__(GPUModelRunner)
        runner.supports_mm_inputs=True;runner.model_config=model_config
        runner.mm_budget=budget;runner.max_num_tokens=1
        runner.device=torch.device('cpu');runner.pin_memory=False
        runner.encoder_cache={};runner.maybe_save_ec_to_connector=lambda *args:None
        feature=MultiModalFeatureSpec(data=SimpleNamespace(modality='image',rows=payload),
            modality='image',identifier='profile-consistency',mm_position=position)
        runner.requests={'req':SimpleNamespace(mm_features=[feature])}
        runner.model=SimpleNamespace(embed_multimodal=lambda rows:[r.clone() for r in rows])
        runner_module.group_mm_kwargs_by_modality=lambda items,**kw:[
            ('image',len(items),{'rows':[item.rows for item in items]})]
        GPUModelRunner._execute_mm_encoder(runner,SimpleNamespace(scheduled_encoder_inputs={'req':[0]}))
        live=storage_bytes(runner.encoder_cache)
        runner.encoder_cache.clear()
        produced=[];profiled=[]
        def dummy_batch(modality,count):
            assert modality=='image'
            produced.append(count)
            return {'rows':[payload.clone() for _ in range(count)]}
        def decoder(*args,**kwargs):
            profiled.append(storage_bytes(runner.encoder_cache))
            return torch.zeros((1,width)),torch.zeros((1,width))
        runner._get_mm_dummy_batch=dummy_batch
        runner._dummy_run=decoder;runner._sync_device=lambda:None
        runner_module.get_pp_group=lambda:SimpleNamespace(is_last_rank=False)
        GPUModelRunner.profile_run(runner)
        assert len(produced)==len(profiled)==1 and produced[0]>0
        return dict(length=length,encoder_rows=len(indices),width=width,
            live_cache_bytes_per_item=live,profile_items=produced[0],
            profiled_cache_bytes=profiled[0],
            same_storage_for_same_maximal_output=profiled[0]==live*produced[0])
    finally:
        MultiModalProfiler._get_dummy_mm_inputs=old_dummy
        worker_utils.processor_only_cache_from_config=old_cache
        runner_module.group_mm_kwargs_by_modality=old_group
        runner_module.get_pp_group=old_pp


if __name__=='__main__':
    cases=[observe(37,[3,12,19,30],3),observe(61,[2,9,18,31,48,59],5)]
    print(json.dumps({'diagnostic_only':True,'cases':cases},indent=2))
    raise SystemExit(0 if all(c['same_storage_for_same_maximal_output'] for c in cases) else 1)
