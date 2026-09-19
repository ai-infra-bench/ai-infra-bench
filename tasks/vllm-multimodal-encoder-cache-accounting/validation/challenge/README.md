# Independent encoder-cache challenges

These curator-only checks run outside the agent image. Both enter through the same public scheduler and runner boundaries as normal execution, using independently declared input values and geometries. They do not call gather/admission helpers directly or impose a cache representation.

`challenge_encoder_cache.py` follows a 25-token request with sparse media at a nonzero offset through chunk sizes 1 and 4, with and without lookahead. It compares complete main and shifted model-input sequences with separately declared expected values. Request construction, scheduling, cache writes/reads, production embedding merge and completion remain real.

`challenge_encoder_capacity.py` observes real constructor budgets for independent sparse/dense/empty inputs. Four-frame Qwen3-VL cases calculate 32 and 80 rows through real resizing/temporal geometry and analytical estimation. A six-row storage workload spans 17, 113 and 2053 prompt positions, checking retained payload growth and profiling coverage.

Run these after applying a positive control in the pinned image. They are additional development evidence; the candidate's reward comes from `tests/test.sh`. In 1.4.0, dense payload storage is an explicit negative even when its profiling is internally consistent. Earlier historical positive results remain recorded under their original contract.
