Work in `/workspace/repo`.

Fix the Mamba FULL-CG accuracy regression in NIXL-style disaggregated prefill/decode serving. After recurrent state is produced or transferred, some decode outputs differ from eager execution even though requests finish successfully.

Make sure FULL-CG execution uses and updates the right recurrent state. Don't break genuine first-token prompts, eager execution, ordinary decode, or supported speculative decoding.
