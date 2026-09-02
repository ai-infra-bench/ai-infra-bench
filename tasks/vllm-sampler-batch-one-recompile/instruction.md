An RL sampling workload commonly starts with one request and then grows to larger batches. The first transition from batch size 1 to a larger batch adds roughly 205 ms on the reported host, while later calls at the same shapes are warm. Output values remain correct, and workloads that begin above batch size 1 do not show the same pause.

The image contains a deterministic CPU trace through `Sampler.gather_logprobs` that counts Torch Dynamo compilations instead of relying on wall-clock timing:

```bash
python /opt/repro/sampler_compile_trace.py
```

Make positive batch-size changes, including the 1→N boundary, reuse one compiled rank-counting graph while preserving gathered token logprobs, top-k indices, and ranks. Repeated calls and different positive batch orders must remain correct. Empty batches and mismatched batch dimensions must continue to fail rather than being silently padded or truncated.
