"""Observe the pinned Python server without changing its requests or outputs.

Used only by the compatibility audit, never mounted during the agent phase.
The real CPU dummy-weight model runner still generates every response.
"""

from __future__ import annotations

import functools
import json
import os
from pathlib import Path

import msgspec

from vllm.v1.engine.async_llm import AsyncLLM


original_generate = AsyncLLM.generate


@functools.wraps(original_generate)
def captured_generate(self, prompt, sampling_params, request_id, *args, **kwargs):
    record = {
        "request_id": request_id,
        "prompt": msgspec.to_builtins(prompt),
        "sampling_params": msgspec.to_builtins(sampling_params),
    }
    with Path(os.environ["PYTHON_COMPAT_CAPTURE"]).open("a") as capture:
        capture.write(json.dumps(record, ensure_ascii=False) + "\n")
    return original_generate(self, prompt, sampling_params, request_id, *args, **kwargs)


AsyncLLM.generate = captured_generate


if __name__ == "__main__":
    from vllm.entrypoints.cli.main import main

    main()
