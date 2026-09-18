"""Independent public-boundary check outside the grading inventory."""

from pathlib import Path
from unittest.mock import patch

from transformers import OPTConfig, PretrainedConfig

from vllm.config import ModelConfig


def main() -> None:
    root = Path("/tmp/independent-config-refresh-model")
    root.mkdir(exist_ok=True)
    OPTConfig(
        vocab_size=64,
        hidden_size=128,
        ffn_dim=256,
        num_hidden_layers=1,
        num_attention_heads=4,
        max_position_embeddings=128,
        word_embed_proj_dim=128,
    ).save_pretrained(root)

    original = PretrainedConfig._dict_from_json_file
    calls = 0

    def transient_partial_read(path):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError(f"transient partial read of {path}")
        return original(path)

    with patch.object(
        PretrainedConfig,
        "_dict_from_json_file",
        side_effect=transient_partial_read,
    ):
        config = ModelConfig(
            model=str(root),
            trust_remote_code=False,
            dtype="float32",
            seed=0,
            skip_tokenizer_init=True,
        )

    assert calls >= 2
    assert config.hf_config.model_type == "opt"
    print({"transient_partial_read_recovered": True, "read_attempts": calls})


if __name__ == "__main__":
    main()
