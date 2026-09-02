from __future__ import annotations

import multiprocessing as mp
import pickle
import threading
from concurrent.futures import ThreadPoolExecutor

import cloudpickle
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace
from transformers import PreTrainedTokenizerFast

from vllm.tokenizers.hf import maybe_make_thread_pool


def make_tokenizer():
    backend = Tokenizer(
        WordLevel(
            {
                "[UNK]": 0,
                "[PAD]": 1,
                "hello": 2,
                "world": 3,
                "杭州": 4,
                "weather": 5,
            },
            unk_token="[UNK]",
        )
    )
    backend.pre_tokenizer = Whitespace()
    return PreTrainedTokenizerFast(
        tokenizer_object=backend,
        unk_token="[UNK]",
        pad_token="[PAD]",
    )


def pooled(copies: int = 2):
    tokenizer = make_tokenizer()
    maybe_make_thread_pool(tokenizer, copies=copies)
    return tokenizer


def pickle_roundtrip(tokenizer, protocol=None):
    kwargs = {} if protocol is None else {"protocol": protocol}
    return pickle.loads(pickle.dumps(tokenizer, **kwargs))


def cloudpickle_roundtrip(tokenizer):
    return cloudpickle.loads(cloudpickle.dumps(tokenizer))


def _child(tokenizer, queue):
    if tokenizer is None:
        queue.put({"is_none": True, "ids": None})
    else:
        queue.put({"is_none": False, "ids": tokenizer.encode("hello world")})


def spawn_roundtrip(tokenizer):
    context = mp.get_context("spawn")
    queue = context.Queue()
    process = context.Process(target=_child, args=(tokenizer, queue))
    process.start()
    process.join(timeout=30)
    assert process.exitcode == 0
    return queue.get(timeout=5)


def concurrent_encodes(tokenizer) -> list[list[int]]:
    original = PreTrainedTokenizerFast.encode
    state_lock = threading.Lock()
    callers_ready = threading.Event()
    first_entered = threading.Event()
    second_entered = threading.Event()
    release_first = threading.Event()
    active_instances: set[int] = set()
    ready_callers = 0
    total_entries = 0

    def guarded_encode(instance, *args, **kwargs):
        nonlocal total_entries
        identity = id(instance)
        with state_lock:
            if identity in active_instances:
                release_first.set()
                raise RuntimeError("one tokenizer instance handled overlapping calls")
            active_instances.add(identity)
            total_entries += 1
            if total_entries == 1:
                first_entered.set()
            elif total_entries == 2:
                second_entered.set()
        try:
            if not release_first.wait(timeout=5):
                raise TimeoutError("concurrent encode probe was not released")
            return original(instance, *args, **kwargs)
        finally:
            with state_lock:
                active_instances.discard(identity)

    def encode_after_rendezvous(prompt: str):
        nonlocal ready_callers
        with state_lock:
            ready_callers += 1
            if ready_callers == 2:
                callers_ready.set()
        if not callers_ready.wait(timeout=5):
            raise TimeoutError("concurrent encode callers did not rendezvous")
        return tokenizer.encode(prompt)

    PreTrainedTokenizerFast.encode = guarded_encode
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(encode_after_rendezvous, "hello world"),
                executor.submit(encode_after_rendezvous, "杭州 weather"),
            ]
            if not first_entered.wait(timeout=5):
                raise TimeoutError("no tokenizer encode call entered")
            # A pool may admit both calls on separate instances. A lock may
            # serialize them before this boundary. Give an unsafe raw object a
            # deterministic window to overlap, then release either safe form.
            second_entered.wait(timeout=0.5)
            release_first.set()
            return [future.result(timeout=10) for future in futures]
    finally:
        release_first.set()
        PreTrainedTokenizerFast.encode = original
