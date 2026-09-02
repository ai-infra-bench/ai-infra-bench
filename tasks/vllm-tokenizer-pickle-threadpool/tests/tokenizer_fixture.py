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


def overlapping_encodes(tokenizer) -> list[list[int]]:
    original = PreTrainedTokenizerFast.encode
    state_lock = threading.Lock()
    first_entered = threading.Event()
    release_first = threading.Event()
    active_instances: set[int] = set()

    def guarded_encode(instance, *args, **kwargs):
        identity = id(instance)
        with state_lock:
            if identity in active_instances:
                release_first.set()
                raise RuntimeError("one tokenizer instance handled overlapping calls")
            active_instances.add(identity)
            is_first = not first_entered.is_set()
            if is_first:
                first_entered.set()
            else:
                release_first.set()
        try:
            if is_first and not release_first.wait(timeout=5):
                raise TimeoutError("second encode call did not overlap the first")
            return original(instance, *args, **kwargs)
        finally:
            with state_lock:
                active_instances.discard(identity)

    PreTrainedTokenizerFast.encode = guarded_encode
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(tokenizer.encode, "hello world"),
                executor.submit(tokenizer.encode, "杭州 weather"),
            ]
            return [future.result(timeout=10) for future in futures]
    finally:
        PreTrainedTokenizerFast.encode = original
