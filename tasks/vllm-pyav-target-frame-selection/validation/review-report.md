# Review report: vllm-pyav-target-frame-selection v0.0.2

## Retention decision

Retain the task after verifier hardening. The scenario is authentic and the requested public behavior is solvable on the pinned vLLM base. The original red display was not evidence of eight model failures: all eight historical `gpt-5.6-sol` high-effort trials recorded reward 1 with no trial exception. The substantive issue ran in the opposite direction—the old verifier accepted two incomplete fixes.

## Semantic boundary

For every existing PyAV-capable public video loader, sampling targets are positions relative to the beginning of the stream. PyAV seeks use absolute stream timestamps, so an implementation must account for `stream.start_time` when it is present. A zero or absent start time remains valid. Correct implementations may seek independently per target or decode sequentially, and may organize helpers and state freely, provided they return the requested frames in order, preserve stable public metadata, work without OpenCV, and do not share decoder state across calls.

The verifier does not require model inference. Its E2E boundary is `VIDEO_LOADER_REGISTRY.load(...).load_bytes` using both the pinned public Sintel asset and generated real H.264 streams.

## Root cause and historical classification

The v0.0.1 generated H.264 fixtures all began at PTS 0. That made `seek(int(seconds / time_base))` appear correct, although PyAV's seek target is on the stream's absolute timeline. On a nonzero-start stream this returns earlier frames while metadata can still look correct.

Replaying the eight historical patches under v0.0.2 yields 6/8:

| Trial suffix | Old reward | v0.0.2 reward | Classification |
|---|---:|---:|---|
| `63g2MyH` | 1 | 0 | incomplete zero-origin implementation |
| `6PDfmAY` | 1 | 1 | valid start-time-aware implementation |
| `UnDxh5H` | 1 | 0 | incomplete zero-origin implementation |
| `f78TWv3` | 1 | 1 | valid start-time-aware implementation |
| `ivruRrg` | 1 | 1 | valid start-time-aware implementation |
| `MNLfHZn` | 1 | 1 | valid start-time-aware implementation |
| `ELqY4UP` | 1 | 1 | valid start-time-aware implementation |
| `UzfCeLx` | 1 | 1 | valid start-time-aware implementation |

Therefore the task was not too hard, and the red UI annotation should not be interpreted as an agent failure. The old 8/8 result overstated model success because verifier coverage was incomplete. The corrected estimate for those same patches is 6/8.

## Behavior-to-test coverage

| Contract behavior | Coverage |
|---|---|
| Correct temporal frames on normal timelines | Pinned Sintel parity plus four numbered H.264 profiles |
| Correct relative positions on shifted timelines | Nonzero-start H.264 through uniform, dynamic, and Nemotron loaders |
| Sampling combinations | `num_frames`, `fps`, `max_duration`, short clips, all-frame requests |
| Public interface and metadata | Registry `load_bytes`, frame identity/order/shape/dtype and stable metadata |
| PyAV independence | Every PyAV-capable loader runs with OpenCV made unimportable |
| Reentrancy | Four concurrent public loader calls |
| Verifier integrity | Exact 23-test JUnit set, no skips, stale-output cleanup, two early-exit controls |

## Executed results

- Direct Docker matrix: 21/21 cases matched their expected rewards, including eight historical patches.
- Formal Harbor matrix: 13/13 cases matched; Base and ten adversarial controls received 0, while the updated Oracle and an independent correct alternative received 1.
- Final Oracle: 23/23 pytest cases passed, real-video E2E passed, reward 1, and no Harbor exception.
- Independent held-out challenge: both accepted implementations selected the same 15 target frames from a 97-frame, 25 fps, long-GOP/B-frame H.264 stream starting at PTS 437.

Detailed hashes and path-addressable run records are in `validation/e2e-evidence.json`.
