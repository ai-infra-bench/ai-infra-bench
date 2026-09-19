"""CPU diagnostic only: real constructor/factory, substituted device and apply."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys
import torch
sys.path[:0] = ['/workspace/repo', '/tests']
import verify_profile_warning as formal
import vllm.model_executor.layers.fused_moe.unquantized_fused_moe_method as quant_module
from vllm.model_executor.layers.fused_moe.fused_moe import TritonExperts
from vllm.model_executor.layers.fused_moe.layer import FusedMoE
from vllm.model_executor.layers.fused_moe.fused_moe_modular_method import FusedMoEModularMethod
spec=importlib.util.spec_from_file_location('challenge','/challenge/challenge_profile_lifecycle.py')
challenge=importlib.util.module_from_spec(spec);spec.loader.exec_module(challenge)
class CPUDeviceBoundary:
    def __getattr__(self,name):return getattr(torch,name)
    def device(self,*args,**kwargs):return torch.device('cpu')
    def arange(self,*args,**kwargs):
        kwargs['device']='cpu'
        return torch.arange(*args,**kwargs)
original_make=FusedMoEModularMethod.make
captured=[]
def inspect_make(layer,*args,**kwargs):
    assert isinstance(layer,FusedMoE), type(layer)
    assert layer.dp_size == layer.moe_parallel_config.dp_size
    assert layer.use_ep == layer.moe_parallel_config.use_ep
    result=original_make(layer,*args,**kwargs)
    captured.append((layer,result))
    return result
results=[]
with patch.object(quant_module,'TritonExperts',TritonExperts,create=True), patch.object(FusedMoEModularMethod,'make',side_effect=inspect_make):
    for module,dp,rank,experts,hidden,intermediate in [(formal,1,0,4,64,128),(formal,2,0,4,64,128),(formal,2,1,4,64,128),(challenge,4,0,8,96,160),(challenge,4,3,8,96,160)]:
        config=module.make_config(parallel_config=module.ParallelConfig(data_parallel_size=dp,data_parallel_rank=rank,enable_expert_parallel=dp>1))
        other=module.make_config(parallel_config=module.ParallelConfig(data_parallel_size=2 if dp==1 else 1,enable_expert_parallel=dp==1))
        for ambient in (None,other):
            module.clear_current_config()
            with patch.object(module,'torch',CPUDeviceBoundary()):
                forward=module.make_kernel_through_factory(config,ambient=ambient)
            layer,method=captured[-1]
            expected=list(range(rank*(experts//dp),(rank+1)*(experts//dp)))
            assert forward.owned_experts==expected,(forward.owned_experts,expected)
            assert layer.dp_size==dp and layer.ep_rank==rank and layer.use_ep==(dp>1)
            assert layer.quant_method is method
            initial_weights=(id(layer.w13_weight),id(layer.w2_weight))
            w1=torch.arange(experts*2*intermediate*hidden,dtype=torch.float32).reshape(experts,2*intermediate,hidden).to(torch.float16)
            w2=torch.randn(experts,hidden,intermediate,dtype=torch.float16)
            x=torch.zeros(4,hidden,dtype=torch.float16);weights=torch.ones(4,2);ids=torch.zeros(4,2,dtype=torch.long)
            with patch.object(method,'apply',return_value=x) as apply:
                assert forward(x,w1,w2,weights,ids,activation='silu',global_num_experts=experts) is x
                assert apply.call_count==1
            assert (id(layer.w13_weight),id(layer.w2_weight))==initial_weights
            assert torch.equal(layer.w13_weight,w1[expected]) and torch.equal(layer.w2_weight,w2[expected])
            results.append({'entry':module.__name__,'dp':dp,'rank':rank,'conflict':ambient is not None,'owned':expected})
import json
print('CPU_REAL_LAYER_FACTORY_DIAGNOSTIC='+json.dumps(results),flush=True)
