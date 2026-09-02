from __future__ import annotations

import multiprocessing as mp
import pickle

from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace
from transformers import PreTrainedTokenizerFast

from vllm.tokenizers.hf import ThreadSafeHFTokenizerMixin, maybe_make_thread_pool


def make_tokenizer():
    backend = Tokenizer(WordLevel({"[UNK]": 0, "hello": 1, "world": 2}, unk_token="[UNK]"))
    backend.pre_tokenizer = Whitespace()
    return PreTrainedTokenizerFast(tokenizer_object=backend, unk_token="[UNK]")


def child(tokenizer, queue):
    queue.put(None if tokenizer is None else tokenizer.encode("hello world"))


def run():
    tokenizer = make_tokenizer()
    maybe_make_thread_pool(tokenizer, copies=2)
    restored = pickle.loads(pickle.dumps(tokenizer))
    context = mp.get_context("spawn")
    queue = context.Queue()
    process = context.Process(target=child, args=(tokenizer, queue))
    process.start()
    process.join(timeout=30)
    return {
        "wrapped_thread_safe": isinstance(tokenizer, ThreadSafeHFTokenizerMixin),
        "pickle_is_none": restored is None,
        "pickle_ids": None if restored is None else restored.encode("hello world"),
        "spawn_ids": queue.get(timeout=5) if process.exitcode == 0 else None,
        "spawn_exit_code": process.exitcode,
    }
