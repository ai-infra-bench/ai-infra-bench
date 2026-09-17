"""Narrow production-method regressions; NOT full vLLM/Harbor validation.

Usage: python test_behavior_methods.py --oracle SOURCE --base SOURCE
Uses real torch tensors, extracted unchanged production method bodies, and
minimal surrounding request/runner/geometry fixtures. No model/GPU execution.
"""
from __future__ import annotations
import argparse
import ast
from collections import OrderedDict
from dataclasses import dataclass
from functools import cached_property
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import torch


def node(root, path, cls, method=None):
    tree = ast.parse((root / path).read_text())
    result = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    return next(n for n in result.body if getattr(n, 'name', None) == method) if method else result


def compile_node(n, namespace):
    tree = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), n], type_ignores=[])
    exec(compile(ast.fix_missing_locations(tree), '<production-method>', 'exec'), namespace)


def run(oracle, base):
    tests = Path(__file__).resolve().parents[1] / 'tests'
    spec = importlib.util.spec_from_file_location('verifier', tests / 'verify_encoder_cache.py')
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    check = next(n for n in ast.parse(verifier.WORKER_CODE).body if getattr(n, 'name', None) == 'check_cache_lifecycle')
    def mask(n, indices):
        result = torch.zeros(n, dtype=torch.bool)
        result[indices] = True
        return result
    class Request:
        def __init__(self, rid, masks):
            self.request_id = rid
            self.mm_features = [SimpleNamespace(identifier=f'{rid}-{i}', mm_position=SimpleNamespace(is_embed=m)) for i, m in enumerate(masks)]
        def get_num_encoder_embeds(self, i):
            return int(self.mm_features[i].mm_position.is_embed.sum())
    result = {'scope': __doc__, 'torch': torch.__version__, 'cache': [], 'gather': [], 'profile': []}
    for rename in (False, True):
        n = node(oracle, 'vllm/v1/core/encoder_cache_manager.py', 'EncoderCacheManager')
        if rename:
            for item in ast.walk(n):
                if isinstance(item, ast.Attribute):
                    item.attr = {'cached': 'entries', 'freed': 'evicted'}.get(item.attr, item.attr)
        ns = {'OrderedDict': OrderedDict, 'SparseRequest': Request, 'sparse_mask': mask}
        compile_node(n, ns)
        compile_node(check, ns)
        actual = ns['check_cache_lifecycle']()
        assert actual == {'eviction': True, 'free_slots': 4}, actual
        result['cache'].append({'candidate': 'renamed' if rename else 'oracle', 'result': actual})
    ns = {'dataclass': dataclass, 'cached_property': cached_property, 'torch': torch}
    compile_node(node(oracle, 'vllm/multimodal/inputs.py', 'PlaceholderRange'), ns)
    pos = ns['PlaceholderRange'](0, 5, mask(5, [1, 3, 4]))
    for omit in (False, True):
        n = node(oracle, 'vllm/v1/worker/gpu_model_runner.py', 'GPUModelRunner', '_gather_mm_embeddings')
        if omit:
            for item in ast.walk(n):
                if isinstance(item, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'num_computed_tokens' for t in item.targets):
                    item.value = ast.Attribute(value=ast.Name(id='req_state', ctx=ast.Load()), attr='num_computed_tokens', ctx=ast.Load())
        ns = {'torch': torch}
        compile_node(n, ns)
        buf = torch.zeros(5, dtype=torch.bool)
        runner = SimpleNamespace(input_batch=SimpleNamespace(req_ids=['r']), requests={'r': SimpleNamespace(num_computed_tokens=0, mm_features=[SimpleNamespace(mm_position=pos, identifier='image')])}, is_mm_embed=SimpleNamespace(cpu=buf, copy_to_gpu=lambda size: buf[:size]), encoder_cache={'image': torch.tensor([[10.], [20.], [30.]])}, is_multimodal_pruning_enabled=False, uses_mrope=False)
        output = SimpleNamespace(total_num_scheduled_tokens=1, num_scheduled_tokens={'r': 1})
        payload, flags = ns['_gather_mm_embeddings'](runner, output, 1)
        observed = {'rows': [t.tolist() for t in payload], 'mask': flags.tolist()}
        matches = observed == {'rows': [[[10.]]], 'mask': [True]}
        assert matches == (not omit), observed
        result['gather'].append({'candidate': 'omit-shift' if omit else 'oracle', 'accepted': matches, 'observed': observed})
    for root in (oracle, base):
        ns = {}
        compile_node(node(root, 'vllm/model_executor/models/qwen3_vl.py', 'Qwen3VLProcessingInfo', 'get_max_video_tokens'), ns)
        counts = []
        for rows in (16, 48):
            info = SimpleNamespace(get_image_size_with_most_features=lambda: (112, 112), get_num_video_tokens=lambda **kw: rows, get_num_frames_with_most_features=lambda *a: 2)
            counts.append(ns['get_max_video_tokens'](info, 4096, {'video': 4}))
        matches = counts == [16, 48]
        assert matches == (root == oracle), counts
        result['profile'].append({'candidate': 'oracle' if root == oracle else 'restored-prompt-profile', 'accepted': matches, 'counts': counts})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--oracle', type=Path, required=True)
    parser.add_argument('--base', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.oracle, args.base), indent=2))
