from __future__ import annotations

import json
import os

import ray


@ray.remote(num_cpus=2)
class RuntimeActor:
    def __init__(self) -> None:
        os.environ.setdefault("VLLM_LOGGING_LEVEL", "WARNING")
        os.environ.setdefault("VLLM_ENABLE_V1_MULTIPROCESSING", "0")
        os.environ.setdefault("VLLM_CPU_KVCACHE_SPACE", "1")
        from vllm import LLM

        self.runtime = LLM(
            model="/workspace/prompt-gateway/model",
            tokenizer="/workspace/prompt-gateway/model",
            load_format="dummy",
            dtype="float32",
            enforce_eager=True,
            trust_remote_code=False,
            max_model_len=128,
            max_num_seqs=8,
            max_num_batched_tokens=256,
            disable_log_stats=True,
        )

    def encode_locally(self, text: str) -> list[int]:
        return self.runtime.get_tokenizer().encode(text, add_special_tokens=False)

    def get_tokenizer(self):
        return self.runtime.get_tokenizer()


@ray.remote(num_cpus=1)
def encode_on_worker(tokenizer, text: str) -> list[int]:
    return tokenizer.encode(text, add_special_tokens=False)


def main() -> int:
    text = "Summarize this support conversation for the next agent."
    ray.init(num_cpus=4, include_dashboard=False, log_to_driver=False)
    try:
        runtime = RuntimeActor.remote()
        local_ids = ray.get(runtime.encode_locally.remote(text))
        tokenizer = ray.get(runtime.get_tokenizer.remote())
        remote_ids = ray.get(encode_on_worker.remote(tokenizer, text))
        result = {
            "entrypoint": "LLM.get_tokenizer across a real Ray actor and worker",
            "local_ids": local_ids,
            "remote_ids": remote_ids,
            "matches": remote_ids == local_ids,
        }
        print(json.dumps(result, separators=(",", ":")))
        assert local_ids
        assert remote_ids == local_ids
        return 0
    finally:
        ray.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
