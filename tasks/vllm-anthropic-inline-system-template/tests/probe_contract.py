"""Verifier-owned case inventory and immutable runtime assets."""
from __future__ import annotations
from typing import Any

MODE_SPECS = {
    "official_qwen": {"family": "qwen", "source": "explicit", "model": "Qwen3.6-27B"},
    "official_qwen_default": {"family": "qwen", "source": "default", "model": "Qwen3.6-27B"},
    "restrictive_sentinel": {"family": "strict", "source": "explicit", "model": "placement-guard-model"},
    "permissive": {"family": "permissive", "source": "explicit", "model": "inline-capable-model"},
    "permissive_default": {"family": "permissive", "source": "default", "model": "inline-capable-model"},
    "permissive_context": {"family": "context", "source": "explicit", "model": "inline-context-model"},
}

ASSET_HASHES = {'config.json': '69db4eb7196bc8190813231b3018ca05d8c2e3abc7b1af19d55c157af44a9d9c', 'tokenizer.json': '5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42', 'tokenizer_config.json': '5186f0defcd7f232382c7f0aebcd2252d073bb921ab240e407b7ae8745d2b29b', 'chat_template.jinja': 'e84f32a23fdda27689f868aa4a1a5621f41133e51a48d7f3efcbea2839574259'}

def cases(mode: str) -> dict[str, dict[str, Any]]:
    family = MODE_SPECS[mode]["family"]
    if family in {"permissive", "context"}:
        return {
            "inline_position_preserved": {
                "messages": [
                    {"role": "user", "content": "PERMISSIVE_USER_1"},
                    {"role": "assistant", "content": "PERMISSIVE_ASSISTANT"},
                    {"role": "system", "content": "PERMISSIVE_INLINE_SENTINEL"},
                    {"role": "user", "content": "PERMISSIVE_USER_2"},
                ],
                "stream": True,
            }
        }
    if family == "strict":
        return {
            "all_system_content_preserved": {
                "messages": [
                    {"role": "system", "content": "LEAD_SENTINEL"},
                    {"role": "user", "content": "diagnostic user turn"},
                    {"role": "assistant", "content": "diagnostic assistant turn"},
                    {"role": "system", "content": "INLINE_SENTINEL"},
                    {"role": "user", "content": "continue"},
                ],
                "stream": True,
            }
        }
    return {
        "production_issue_shape": {
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Check the GPU status for vLLM."},
                {"role": "assistant", "content": "I will check it."},
                {"role": "user", "content": "Show the nvidia-smi output."},
                {"role": "assistant", "content": "Utilization is around 15%."},
                {"role": "user", "content": "Write a report."},
                {"role": "system", "content": "Summarize the conversation as a GPU report."},
                {"role": "user", "content": "Please summarize it."},
            ],
            "stream": True,
        },
        "inline_after_user_without_leading_system": {
            "messages": [
                {"role": "user", "content": "Earlier context"},
                {"role": "assistant", "content": "Earlier response"},
                {"role": "system", "content": "Apply the hidden task instruction."},
                {"role": "user", "content": "Continue."},
            ]
        },
        "multiple_inline_system_messages": {
            "messages": [
                {"role": "system", "content": "Global instruction."},
                {"role": "user", "content": "First question"},
                {"role": "system", "content": "First auxiliary instruction."},
                {"role": "assistant", "content": "Intermediate answer"},
                {"role": "system", "content": "Second auxiliary instruction."},
                {"role": "user", "content": "Final question"},
            ],
            "stream": True,
        },
        "top_level_and_inline_system": {
            "system": "TOP_LEVEL_SYSTEM_SENTINEL",
            "messages": [
                {"role": "user", "content": "User context"},
                {"role": "system", "content": "INLINE_SYSTEM_SENTINEL"},
                {"role": "user", "content": "Final request"},
            ]
        },
        "system_text_blocks": {
            "messages": [
                {"role": "system", "content": [{"type": "text", "text": "Leading block."}]},
                {"role": "user", "content": "Context"},
                {"role": "system", "content": [
                    {"type": "text", "text": "Inline block one."},
                    {"type": "text", "text": "Inline block two."},
                ]},
                {"role": "user", "content": "Continue"},
            ]
        },
        "empty_inline_system": {
            "messages": [
                {"role": "system", "content": "Leading instruction."},
                {"role": "user", "content": "Context"},
                {"role": "system", "content": ""},
                {"role": "user", "content": "Continue"},
            ]
        },
        "long_context_inline_system": {
            "messages": [
                {"role": "system", "content": "Global policy."},
                *[
                    {"role": "user" if index % 2 == 0 else "assistant",
                     "content": f"Historical turn {index}: " + "context " * 20}
                    for index in range(12)
                ],
                {"role": "system", "content": "Compress the history before answering."},
                {"role": "user", "content": "Give the final answer."},
            ]
        },
    }
