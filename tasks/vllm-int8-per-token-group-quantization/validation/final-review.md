# 1.2.7 validation pending

A legal contiguous FP16 view with storage_offset=1 triggers a CUDA misaligned-address error in the 1.2.6 Oracle. The old verifier accepted that Oracle. A pointer-alignment guard and three offset-input regressions are prepared but not yet validated. Round-one Flash experiments retain their frozen 1.2.6 inputs. Historical full results are preserved under history/.
