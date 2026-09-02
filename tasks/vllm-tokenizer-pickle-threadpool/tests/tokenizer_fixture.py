from __future__ import annotations

import multiprocessing as mp
import pickle

import cloudpickle
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace
from transformers import PreTrainedTokenizerFast

from vllm.tokenizers.hf import ThreadSafeHFTokenizerMixin, maybe_make_thread_pool


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


def is_thread_safe(tokenizer) -> bool:
    return isinstance(tokenizer, ThreadSafeHFTokenizerMixin)
