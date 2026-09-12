#!/usr/bin/env python3
"""Focused production behavior contract for Mamba one-token FULL-CG rows."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import torch

sys.path.insert(0, "/workspace/repo")

from vllm.config.compilation import CUDAGraphMode
from vllm.v1.attention.backend import CommonAttentionMetadata
from vllm.v1.attention.backends.mamba_attn import (
    BaseMambaAttentionMetadata,
    BaseMambaAttentionMetadataBuilder,
)
from vllm.v1.kv_cache_interface import MambaSpec


class ConcreteMambaBuilder(
    BaseMambaAttentionMetadataBuilder[BaseMambaAttentionMetadata]
):
    metadata_cls = BaseMambaAttentionMetadata


def make_config(num_speculative_tokens: int = 0) -> SimpleNamespace:
    speculative_config = (
        SimpleNamespace(
            num_speculative_tokens=num_speculative_tokens,
            parallel_drafting=False,
        )
        if num_speculative_tokens
        else None
    )
    return SimpleNamespace(
        cache_config=SimpleNamespace(block_size=16, mamba_cache_mode="all"),
        compilation_config=SimpleNamespace(
            cudagraph_mode=CUDAGraphMode.FULL,
            max_cudagraph_capture_size=None,
        ),
        speculative_config=speculative_config,
        num_speculative_tokens=num_speculative_tokens,
        parallel_config=SimpleNamespace(decode_context_parallel_size=1),
        scheduler_config=SimpleNamespace(max_num_seqs=4),
        model_config=SimpleNamespace(max_model_len=64),
    )


def make_common_metadata(
    *,
    seq_len: int,
    is_prefilling: bool,
    device: torch.device,
    query_len: int = 1,
) -> CommonAttentionMetadata:
    return make_batch_metadata(
        [(seq_len, query_len, is_prefilling)], device=device
    )


def make_batch_metadata(
    rows: list[tuple[int, int, bool]], *, device: torch.device
) -> CommonAttentionMetadata:
    seq_len_values = [row[0] for row in rows]
    query_len_values = [row[1] for row in rows]
    query_offsets = [0]
    for query_len in query_len_values:
        query_offsets.append(query_offsets[-1] + query_len)
    query_start_loc_cpu = torch.tensor(query_offsets, dtype=torch.int32)
    query_start_loc = query_start_loc_cpu.to(device)
    seq_lens_cpu = torch.tensor(seq_len_values, dtype=torch.int32)
    seq_lens = seq_lens_cpu.to(device)
    num_computed_tokens_cpu = seq_lens_cpu - torch.tensor(
        query_len_values, dtype=torch.int32
    )
    metadata = CommonAttentionMetadata(
        query_start_loc=query_start_loc,
        query_start_loc_cpu=query_start_loc_cpu,
        seq_lens=seq_lens,
        seq_lens_cpu_upper_bound=seq_lens_cpu,
        _seq_lens_cpu=seq_lens_cpu,
        _num_computed_tokens_cpu=num_computed_tokens_cpu,
        num_reqs=len(rows),
        num_actual_tokens=query_offsets[-1],
        max_query_len=max(query_len_values),
        max_seq_len=max(seq_len_values),
        block_table_tensor=torch.zeros(
            (len(rows), 1), dtype=torch.int32, device=device
        ),
        slot_mapping=torch.zeros(
            (query_offsets[-1],), dtype=torch.int64, device=device
        ),
        causal=True,
    )
    return metadata.replace(
        is_prefilling=torch.tensor([row[2] for row in rows], dtype=torch.bool)
    )


def make_builder(
    device: torch.device, num_speculative_tokens: int = 0
) -> ConcreteMambaBuilder:
    spec = MambaSpec(
        block_size=16,
        shapes=((1,), (1,)),
        dtypes=(torch.float32,),
    )
    return ConcreteMambaBuilder(
        spec, ["layer0"], make_config(num_speculative_tokens), device
    )


def replay_recurrent_graph(
    metadata: BaseMambaAttentionMetadata,
    *,
    device: torch.device,
    expected_first: float,
    expected_replay: float,
) -> None:
    """Consume the production classification in an actual CUDA graph.

    The tiny recurrence substitutes for model weights and the Mamba kernel, but
    preserves the behavior that matters here: a decode row consumes persistent
    state while a first-token prefill starts a new state.  Capturing and
    replaying the device operation prevents a metadata-only repair from passing
    without producing the corresponding FULL-CG state behavior.
    """

    prior = torch.tensor([3.0], device=device)
    token = torch.tensor([2.0], device=device)
    output = torch.empty_like(token)
    graph = torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        if metadata.num_decodes == 1 and metadata.num_prefills == 0:
            output.copy_(prior + token)
        elif metadata.num_decodes == 0 and metadata.num_prefills == 1:
            output.copy_(token)
        else:
            raise AssertionError(
                "single-row metadata has an invalid decode/prefill split"
            )

    graph.replay()
    torch.cuda.synchronize()
    if output.item() != expected_first:
        raise AssertionError(
            f"captured recurrent result is wrong: {output.item()}!={expected_first}"
        )

    prior.fill_(11.0)
    token.fill_(5.0)
    graph.replay()
    torch.cuda.synchronize()
    if output.item() != expected_replay:
        raise AssertionError(
            f"replayed recurrent result is wrong: {output.item()}!={expected_replay}"
        )


def main() -> int:
    if not torch.cuda.is_available():
        print("FAIL: CUDA is unavailable", file=sys.stderr)
        return 2

    device = torch.device("cuda")

    # Environment control: an ordinary decode row must traverse the production
    # FULL-CG metadata path and keep CUDA-backed persistent decode state.
    control = make_builder(device).build_for_cudagraph_capture(
        make_common_metadata(seq_len=10, is_prefilling=False, device=device)
    )
    if not (
        control.num_decodes == 1
        and control.num_prefills == 0
        and control.state_indices_tensor_d is not None
        and control.state_indices_tensor_d.is_cuda
    ):
        print(f"FAIL: control decode metadata is invalid: {control}", file=sys.stderr)
        return 2

    # Bug contract: D-side recomputation of N from existing h(N-1) is still
    # scheduler-labelled prefill, but a uniform single-token FULL-CG batch must
    # build decode/update metadata.
    previous_sync_mode = torch.cuda.get_sync_debug_mode()
    prior_state_input = make_common_metadata(
        seq_len=10, is_prefilling=True, device=device
    )
    prior_state_builder = make_builder(device)
    speculative_builder = make_builder(device, 1)
    speculative_input = make_common_metadata(
        seq_len=10,
        query_len=2,
        is_prefilling=True,
        device=device,
    )
    mixed_builder = make_builder(device)
    mixed_input = make_batch_metadata(
        [(10, 1, True), (1, 1, True)], device=device
    )
    torch.cuda.set_sync_debug_mode("error")
    try:
        prior_state = prior_state_builder.build_for_cudagraph_capture(
            prior_state_input
        )

        # A wider speculative prefill is not the one-token NIXL recomputation
        # case and must remain prefill-shaped.
        speculative_prefill = speculative_builder.build(0, speculative_input)

        # Exercise the split used by a real batch: the prior-state one-token
        # row becomes decode while a genuine first-token row remains prefill.
        mixed = mixed_builder.build(0, mixed_input)
    finally:
        torch.cuda.set_sync_debug_mode(previous_sync_mode)

    # Guardrail: the very first prompt token has no prior Mamba state and must
    # remain a prefill.
    first_token = make_builder(device).build(
        0, make_common_metadata(seq_len=1, is_prefilling=True, device=device)
    )
    torch.cuda.synchronize()

    print(
        "observed "
        f"prior_state=(decodes={prior_state.num_decodes},prefills={prior_state.num_prefills}) "
        f"first_token=(decodes={first_token.num_decodes},prefills={first_token.num_prefills})"
    )
    if prior_state.num_decodes != 1 or prior_state.num_prefills != 0:
        print(
            "FAIL: a one-token Mamba row with prior state stayed prefill while "
            "the production FULL-CG metadata path is decode-shaped",
            file=sys.stderr,
        )
        return 1
    replay_recurrent_graph(
        prior_state,
        device=device,
        expected_first=5.0,
        expected_replay=16.0,
    )
    if first_token.num_decodes != 0 or first_token.num_prefills != 1:
        print("FAIL: a true first-token prompt was reclassified", file=sys.stderr)
        return 3
    replay_recurrent_graph(
        first_token,
        device=device,
        expected_first=2.0,
        expected_replay=5.0,
    )
    if (
        speculative_prefill.num_decodes != 0
        or speculative_prefill.num_prefills != 1
    ):
        print("FAIL: a multi-token speculative prefill was reclassified", file=sys.stderr)
        return 4
    if mixed.num_decodes != 1 or mixed.num_prefills != 1:
        print(
            "FAIL: mixed prior-state and first-token rows were not split correctly",
            file=sys.stderr,
        )
        return 5

    props = torch.cuda.get_device_properties(0)
    print(
        "PASS: production Mamba FULL-CG metadata classifies prior-state "
        "single-token rows as decode and preserves first-token prefill"
    )
    print(
        f"gpu={props.name} capability={props.major}.{props.minor} uuid={props.uuid}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
