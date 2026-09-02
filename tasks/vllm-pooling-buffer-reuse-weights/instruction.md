A pooling model loaded through a streaming checkpoint reader can report success while producing embeddings that do not match the same checkpoint loaded by the ordinary iterator. The mismatch occurs when the reader reuses a small host buffer; disabling buffer reuse restores the expected output.

The image contains a CPU reduction using the production pooling adapter:

```bash
python /opt/repro/pooling_stream_trace.py
```

Make pooling-model loading safe for iterators whose yielded tensor storage may be overwritten on the next iteration. Ordinary iterators, both supported checkpoint prefix forms, packed projections such as separate q/k shards loaded into qkv weights, missing output heads, and the loader's streaming memory behavior must remain correct. Do not solve this by materializing the whole checkpoint.
