# Independent INT8 quantization challenge

This curator-only check is outside the agent image and independent of the grading observer. It executes the public Python dispatch and rebuilt native `_C.per_token_group_quant_int8` entrypoint on actual CUDA tensors. Independently chosen cases cover native dispatch, numerical equivalence, FP32 precision boundaries, empty outputs and subsequent CUDA health.

Configured native ranges include positive lower bounds `(0, 11)`, `(5, 29)` and `(11, 93)` across FP16, BF16 and FP32, using shape `(2, 192)`, group size 96 and a separate signed input pattern. The native API receives these bounds directly; the existing Python convenience wrapper is not required to acquire new bounds keyword arguments. This supplements the default-range public-dispatch check and previous custom-range cases.

Run `python3 validation/challenge/challenge_int8_quant.py` in the pinned GPU image with the selected source and its matching rebuilt native library. The challenge emits structured results plus `CHALLENGE_INT8_QUANT=PASS|FAIL`. Oracle and the native-kernel, compatible-alias and renamed-private-helper alternatives should pass. Base, reciprocal-overflow, empty-launch and positive-lower-bound rejection controls should fail. Actual outcomes, native/source hashes and fresh-container commands are recorded in e2e-evidence.json.
