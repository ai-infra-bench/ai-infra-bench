#!/usr/bin/env python3
"""Preloaded behavioral suite. Imports candidate code only after privilege drop."""
from __future__ import annotations


def run_suite(cases, emit):
    # Imports and helpers stay inside the authenticated suite. The parent loads
    # this code before the child imports any candidate-controlled module.
    from pathlib import Path
    import sys
    from unittest.mock import patch
    from contextlib import ExitStack, nullcontext
    import torch

    sys.path.insert(0, "/workspace/repo")
    import vllm
    from vllm.model_executor.models.interfaces import SupportsMultiModal
    from vllm.model_executor.models.utils import _merge_multimodal_embeddings as merge

    if Path("/workspace/repo").resolve() not in Path(vllm.__file__).resolve().parents:
        raise AssertionError("candidate source is not active")
    if not torch.cuda.is_available():
        raise AssertionError("CUDA is required")
    print(f"candidate_source={vllm.__file__}; gpu={torch.cuda.get_device_name(0)}", flush=True)

    class RejectCudaSync:
        def __enter__(self):
            self.previous = torch.cuda.get_sync_debug_mode()
            torch.cuda.set_sync_debug_mode("error")
            self.guards = ExitStack()
            self.guards.enter_context(patch.object(torch.cuda, "set_sync_debug_mode",
                side_effect=AssertionError("candidate disabled synchronization checks")))
            # PyTorch sync-debug does not intercept these explicit waits.
            for owner, name in ((torch.cuda, "synchronize"),
                                (torch.cuda.Stream, "synchronize"),
                                (torch.cuda.Event, "synchronize"),
                                (torch._C, "_cuda_synchronize")):
                self.guards.enter_context(patch.object(owner, name,
                    side_effect=AssertionError("CPU-mask merge explicitly waited for CUDA")))
        def __exit__(self, *args):
            self.guards.close()
            torch.cuda.set_sync_debug_mode(self.previous)

    def check_merge(spec):
        dtype = getattr(torch, spec["dtype"])
        n, h = (8192, 512) if spec["form"] == "nested" else (1024, 64)
        cpu_mask = (torch.arange(n) % (3 if spec["form"] == "nested" else 2)) == 1
        selected = int(cpu_mask.sum())
        mask = cpu_mask.to(spec["device"])
        # Every row differs. Constant segments cannot detect within-segment swaps.
        values_cpu = (torch.arange(selected * h).reshape(selected, h) % 113).float()
        values = values_cpu.cuda()
        mm = [values[:selected // 2], [values[selected // 2:]]] if spec["form"] == "nested" else values.reshape(1, selected, h)
        inputs = torch.full((n, h), -3., dtype=dtype, device="cuda")
        expected = torch.full((n, h), -3., dtype=dtype)
        expected[cpu_mask] = values_cpu.to(dtype)
        ratios = []
        for _ in range(2):
            inputs.fill_(-3.)
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()
            before = torch.cuda.memory_allocated()
            if spec["device"] == "cpu":
                with RejectCudaSync():
                    returned = merge(inputs, mm, mask)
            else:
                returned = merge(inputs, mm, mask)
            if returned is not inputs or returned.dtype != dtype:
                raise AssertionError("merge must retain dtype and return the input object")
            torch.cuda.synchronize()
            ratio = (torch.cuda.max_memory_allocated() - before) / (inputs.numel() * inputs.element_size())
            if ratio >= 4.0:
                raise AssertionError(f"temporary allocation is excessive: {spec['device']} {ratio:.3f}")
            if not torch.equal(inputs.cpu(), expected):
                raise AssertionError("embedding order, values, or non-placeholder rows changed")
            ratios.append(ratio)
        return {"passed": True, "peak_ratios": ratios}

    def check_counts(spec):
        actual, expected = spec["actual"], spec["expected"]
        inputs = torch.zeros((9, 16), dtype=torch.bfloat16, device="cuda")
        mask = (torch.arange(9) < expected).to(spec["device"])
        mm = [torch.ones((actual, 16), dtype=torch.float32, device="cuda")]
        try:
            merge(inputs, mm, mask)
        except ValueError as exc:
            message = str(exc)
            if str(actual) not in message or str(expected) not in message:
                raise AssertionError(f"cardinality error must identify both counts: {message}") from exc
        else:
            raise AssertionError(f"cardinality mismatch {actual}!={expected} accepted")
        return {"passed": True}

    def check_empty(spec):
        inputs = torch.randn((7, 13), dtype=torch.float16, device="cuda")
        before = inputs.clone()
        mask = torch.zeros(7, dtype=torch.bool, device=spec["device"])
        returned = merge(inputs, [], mask)
        if returned is not inputs or not torch.equal(inputs, before):
            raise AssertionError("empty merge is not an identity operation")
        return {"passed": True}

    def check_interface(spec):
        class LanguageModel:
            def embed_input_ids(self, ids):
                # Actual embedding lookup checks the OOV preparation branch.
                weight = torch.arange(128, dtype=torch.float16, device="cuda").reshape(16, 8)
                return torch.nn.functional.embedding(ids, weight)
        class ModelHarness:
            _embed_text_input_ids = SupportsMultiModal._embed_text_input_ids
            def get_language_model(self):
                return LanguageModel()
        mask = torch.zeros(12, dtype=torch.bool)
        mask[[1, 4, 9]] = True
        ids_cpu = torch.arange(12, dtype=torch.long)
        if spec["oov"]:
            ids_cpu[mask] = 100
        ids = ids_cpu.cuda()
        replacements = torch.arange(24, dtype=torch.float32, device="cuda").reshape(3, 8)
        model = ModelHarness()
        SupportsMultiModal.configure_mm_token_handling(
            model, vocab_size=16, mm_token_ids=[100 if spec["oov"] else 1])
        # Qwen3-VL uses in-vocabulary placeholders. Preserve the existing OOV
        # preparation path with its normal device-local mask; requiring CPU
        # masks here would silently extend the requested merge repair.
        device_mask = mask.to(spec["device"])
        with RejectCudaSync() if spec["device"] == "cpu" else nullcontext():
            output = SupportsMultiModal.embed_input_ids(model, ids, replacements, is_multimodal=device_mask)
        torch.cuda.synchronize()
        expected = torch.arange(128, dtype=torch.float16).reshape(16, 8)[torch.arange(12)]
        expected[mask] = torch.arange(24, dtype=torch.float16).reshape(3, 8)
        if not torch.equal(output.cpu(), expected):
            raise AssertionError("model interface changed text or multimodal embeddings")
        return {"passed": True}

    checks = {"merge": check_merge, "counts": check_counts,
              "empty": check_empty, "interface": check_interface}
    for spec in cases:
        result = checks[spec["kind"]](spec)
        # Native authentication accepts only this original code object as caller.
        emit(spec["name"], result)
        print(f"PASS: {spec['name']}: {result}", flush=True)
