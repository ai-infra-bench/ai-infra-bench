"""Generate an ordinary small model resource; no task tests or repair code."""
import json
from pathlib import Path

import torch
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace
from transformers import PreTrainedTokenizerFast, Qwen3Config, Qwen3ForCausalLM

torch.set_num_threads(1)
torch.manual_seed(20260217)
config = Qwen3Config.from_json_file('/tmp/tiny-qwen3-config.json')
destination = Path('/opt/models/tiny-qwen3')
destination.mkdir(parents=True)
model = Qwen3ForCausalLM(config).to(torch.float16)
model.save_pretrained(destination, safe_serialization=True)
vocab = {'<pad>': 0, '<bos>': 1, '<eos>': 2, '<unk>': 3}
vocab.update({f'token{i}': i for i in range(4, 256)})
tokenizer = Tokenizer(WordLevel(vocab, unk_token='<unk>'))
tokenizer.pre_tokenizer = Whitespace()
PreTrainedTokenizerFast(tokenizer_object=tokenizer, bos_token='<bos>',
    eos_token='<eos>', pad_token='<pad>', unk_token='<unk>',
    model_max_length=512).save_pretrained(destination)
(destination / 'README.md').write_text(
    '# Tiny random Qwen3\n\nOffline development model, not pretrained. '
    'CPU seed 20260217; two layers, hidden size 512, vocabulary 256. '
    'Tokenizer words token4 through token255 have their numbered IDs. '
    'Use for execution and consistency checks, not language quality.\n')
print(json.dumps({'parameters':sum(p.numel() for p in model.parameters()),
                  'files':sorted(p.name for p in destination.iterdir())}))
