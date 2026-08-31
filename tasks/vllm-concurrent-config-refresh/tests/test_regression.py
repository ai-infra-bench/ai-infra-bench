import json
import subprocess
import sys

import pytest
from transformers import OPTConfig

from vllm.config import ModelConfig


def _valid_model(path):
    config = OPTConfig(
        vocab_size=64,
        hidden_size=128,
        ffn_dim=256,
        num_hidden_layers=1,
        num_attention_heads=4,
        max_position_embeddings=128,
        word_embed_proj_dim=128,
        do_layer_norm_before=True,
    )
    config.save_pretrained(path)


def _load(path):
    return ModelConfig(
        model=str(path),
        trust_remote_code=False,
        dtype="float32",
        seed=0,
        skip_tokenizer_init=True,
    )


def test_valid_local_configuration_loads(tmp_path):
    _valid_model(tmp_path)
    config = _load(tmp_path)
    assert config.hf_config.model_type == "opt"
    assert config.hf_config.architectures


@pytest.mark.parametrize("kind", ["missing", "malformed", "unsupported"])
def test_persistent_invalid_configuration_fails(tmp_path, kind):
    if kind == "malformed":
        (tmp_path / "config.json").write_text("{")
    elif kind == "unsupported":
        (tmp_path / "config.json").write_text(json.dumps({
            "model_type": "unsupported_hidden_model",
            "architectures": ["UnsupportedHiddenModel"],
        }))
    program = """
import sys
from vllm.config import ModelConfig
ModelConfig(model=sys.argv[1], trust_remote_code=False, dtype='float32',
            seed=0, skip_tokenizer_init=True)
"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", program, str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=12,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"{kind} configuration did not fail within 12 seconds")
    assert result.returncode != 0
