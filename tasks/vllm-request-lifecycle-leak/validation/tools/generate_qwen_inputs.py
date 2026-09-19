"""Curator-only input provenance probe; run at Base with the pinned processor files."""
import argparse
import json
from pathlib import Path
from PIL import Image
from vllm.config import ModelConfig
from vllm.multimodal import MULTIMODAL_REGISTRY

parser=argparse.ArgumentParser()
parser.add_argument('--model', required=True)
parser.add_argument('--output', required=True)
args=parser.parse_args()
config=ModelConfig(args.model,max_model_len=256,limit_mm_per_prompt={'image':2},mm_processor_cache_gb=0,mm_processor_kwargs={'min_pixels':3136,'max_pixels':3136})
processor=MULTIMODAL_REGISTRY.create_processor(config)
marker='<|vision_start|><|image_pad|><|vision_end|>'
records={}
def capture(name,prompt,colors):
    out=processor.apply(prompt,mm_items=processor.info.parse_mm_data({'image':[Image.new('RGB',(56,56),c) for c in colors]}),hf_processor_mm_kwargs={})
    ranges=out['mm_placeholders']['image']
    layout=[[p.offset,p.length,h] for p,h in zip(ranges,out['mm_hashes']['image'])]
    record={'prompt':prompt,'colors':colors,'tokens':out['prompt_token_ids'],'layout':layout}
    assert all(record['tokens'][o:o+n]==[151655]*n for o,n,_ in layout)
    # Fresh requests can include previously generated text as token input.
    # Verify this public processor path preserves both the suffix and media.
    raw = processor.info.get_tokenizer().encode(prompt, add_special_tokens=False)
    suffix = [101, 151645]
    replay = processor.apply(raw + suffix,
        mm_items=processor.info.parse_mm_data({'image': [Image.new('RGB', (56, 56), c) for c in colors]}),
        hf_processor_mm_kwargs={})
    assert replay['prompt_token_ids'] == record['tokens'] + suffix
    assert [[p.offset, p.length, h] for p, h in zip(
        replay['mm_placeholders']['image'], replay['mm_hashes']['image'])] == layout
    records[name]=record
    print(name,len(record['tokens']),[(o,n) for o,n,_ in layout],flush=True)
    return record
single=capture('single',marker+' x'*2,['red'])
assert len(single['tokens'])==8 and single['layout'][0][:2]==[1,4]
capture('single-changed',marker+' x'*2,['green'])
for b in (16,32):
    for stage in ('partial','boundary'):
        gap=2 if stage=='partial' else b-10
        suffix=b-14 if stage=='partial' else 0
        prompt=' x'*(b-1)+marker+' y'*gap+marker+' z'*suffix
        # For b=32 partial, two images still share the same unfinished block.
        base=capture(f'{stage}-{b}',prompt,['red','blue'])
        assert len(base['tokens'])==(2*b-1 if stage=='partial' else 2*b+1)
        if stage=='boundary': assert sum(base['layout'][-1][:2])==2*b
        for idx in (0,1):
            colors=['red','blue'];colors[idx]='green'
            changed=capture(f'{stage}-{b}-changed-{idx}',prompt,colors)
            assert changed['tokens']==base['tokens']
        repeated=capture(f'{stage}-{b}-repeated',prompt,['red','red'])
        moved_prompt=' x'*(b-1)+marker+' y'*(gap+1)+marker+' z'*suffix
        moved=capture(f'{stage}-{b}-moved',moved_prompt,['red','blue'])
        assert moved['layout'][1][0]==base['layout'][1][0]+1
        assert moved['tokens']!=base['tokens']
Path(args.output).write_text(json.dumps(records,indent=2)+'\n')
