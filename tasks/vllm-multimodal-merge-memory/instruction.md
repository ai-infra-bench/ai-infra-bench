Work in `/workspace/repo`.

I am serving long, multi-image Qwen3-VL requests close to the GPU memory limit,
and some of them fail with CUDA out-of-memory errors while the multimodal
embeddings are being merged. The allocation named in the traceback is fairly
small, and eager mode fails too, so disabling CUDA graphs has not helped. In
this workload the placeholder mask is on CPU while the token and multimodal
embeddings are on CUDA.

Reduce the temporary GPU-memory pressure of this operation. When the mask is
on CPU, merging valid inputs must not wait for GPU work or copy results back
to the CPU. Masks already on CUDA must also work with bounded temporary memory;
synchronization needed to validate their cardinality is allowed.

Preserve placeholder order, output dtype, in-place behavior, supported nested
and tensor input forms, and unchanged non-placeholder embeddings. Incorrect
embedding/placeholder counts must raise a useful error rather than silently
broadcasting or dropping embeddings, for either mask device. Empty embeddings
with no placeholders should leave the input unchanged.

Fix the production path while preserving these properties across repeated calls.
