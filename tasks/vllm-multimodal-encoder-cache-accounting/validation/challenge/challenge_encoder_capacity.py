"""Independent curator challenge for real encoder-capacity consumers.

Uses a separate input geometry and no verifier observer/checker. Only real
capacity consumers are observed; unused registry accessors are not called.
"""
import json
from types import SimpleNamespace
import torch
from vllm.config import SchedulerConfig
from vllm.multimodal.inputs import PlaceholderRange
from vllm.multimodal.registry import MultiModalRegistry
from vllm.multimodal.profiling import MultiModalProfiler
from vllm.v1.core.encoder_cache_manager import compute_encoder_budget
from vllm.v1.worker.utils import MultiModalBudget
import vllm.v1.worker.utils as worker_utils

rows=[]
for length,indices in [(137,[3,9,23,37,52,66,81,104,129]),(53,[4,13,27,39,48]),(11,None),(17,[]),(0,[])]:
 mask=None if indices is None else torch.zeros(length,dtype=torch.bool)
 if indices:mask[indices]=True
 expected=length if indices is None else len(indices)
 position=PlaceholderRange(offset=0,length=length,is_embed=mask)
 processor=SimpleNamespace(info=SimpleNamespace(get_mm_max_tokens_per_item=lambda **kw:None),allowed_mm_limits={'image':4})
 registry=object.__new__(MultiModalRegistry)
 registry.create_processor=lambda *args,**kw:processor
 registry.supports_multimodal_inputs=lambda *args:True
 model=SimpleNamespace(is_multimodal_model=True,max_model_len=256)
 config=SchedulerConfig(max_model_len=256,is_encoder_decoder=False,max_num_batched_tokens=2,max_num_seqs=1,enable_chunked_prefill=True,is_multimodal_model=True,disable_chunked_mm_input=False)
 expected_budget=max(2,expected)
 old_dummy=MultiModalProfiler._get_dummy_mm_inputs
 old_cache=worker_utils.processor_only_cache_from_config
 try:
  MultiModalProfiler._get_dummy_mm_inputs=lambda *args,**kw:{'mm_placeholders':{'image':[position]}}
  worker_utils.processor_only_cache_from_config=lambda *args,**kw:None
  scheduler_budget=compute_encoder_budget(model,config,registry)
  runner_budget=MultiModalBudget(model,config,registry)
  result={'length':length,'expected_rows':expected,'expected_capacity':expected_budget,'scheduler_budget':list(scheduler_budget),'runner_budget':runner_budget.get_encoder_budget()}
  result['pass']=scheduler_budget==(expected_budget,expected_budget) and result['runner_budget']==expected_budget
  rows.append(result)
 finally:
  MultiModalProfiler._get_dummy_mm_inputs=old_dummy
  worker_utils.processor_only_cache_from_config=old_cache
# Independent direct-estimate cases: different geometry and batch floor from
# the grader. Keep the production video estimate and downstream consumers.
from vllm.model_executor.models.qwen3_vl import Qwen3VLProcessingInfo
for actual_rows in (32, 80):
 info=object.__new__(Qwen3VLProcessingInfo)
 info.get_image_size_with_most_features=lambda: ((actual_rows // 2) * 7,112)
 info.get_max_image_tokens=lambda: actual_rows // 2
 info.get_num_frames_with_most_features=lambda *args,**kw: 4
 info.get_num_video_tokens=lambda *args,**kw: actual_rows
 processor=SimpleNamespace(info=info,allowed_mm_limits={'video':2})
 registry=object.__new__(MultiModalRegistry)
 registry.create_processor=lambda *args,**kw: processor
 registry.supports_multimodal_inputs=lambda *args: True
 old_cache=worker_utils.processor_only_cache_from_config
 old_dummy=MultiModalProfiler._get_dummy_mm_inputs
 frame_mask=[False]*7+[True]*(actual_rows//4)+[False]
 mask=torch.tensor(frame_mask*4,dtype=torch.bool)
 position=PlaceholderRange(0,len(mask),mask)
 try:
  MultiModalProfiler._get_dummy_mm_inputs=lambda *args,**kw:{'mm_placeholders':{'video':[position]}}
  worker_utils.processor_only_cache_from_config=lambda *args,**kw: None
  scheduler_budget=compute_encoder_budget(model,config,registry)
  runner_budget=MultiModalBudget(model,config,registry).get_encoder_budget()
  rows.append({'path':'direct-video-estimate','expected_rows':actual_rows,
      'scheduler_budget':list(scheduler_budget),'runner_budget':runner_budget,
      'pass':scheduler_budget==(actual_rows,actual_rows) and runner_budget==actual_rows})
 finally:
  worker_utils.processor_only_cache_from_config=old_cache
  MultiModalProfiler._get_dummy_mm_inputs=old_dummy
print(json.dumps({'cases':rows,'pass':all(r['pass'] for r in rows)},indent=2))
raise SystemExit(0 if all(r['pass'] for r in rows) else 1)
