# Approved remediation

| Finding | Change | Actual validation |
| --- | --- | --- |
| Inferred Chinese/Japanese scope omitted | Replace one instruction sentence; bump task to 0.0.2 | Final frozen instruction used by 14 Harbor runs |
| Oracle treats unspecified language as always spaced | Infer CJK script boundaries in shared joiner; update independent wrapper alternative | Both 48/48 regression + 1/1 pipeline; independent challenge 8/8 each |
| Attempt 8 over-suppresses spaces near quotes | Add 8 English quote-boundary regressions and preserve attempt 8 as negative control | Attempt 8 reward 0; isolated quote heuristic reward 0 |
| Required pipeline can exit 0 before checks execute | Require exact completed JUnit inventory for both suites | SystemExit(0) and os._exit(0) reach the old import boundary, exit 0, reward 0 |
| Old image / 22-case evidence | Preserve it as history and regenerate final executable hashes, image and 48+1 case records | Final strict artifact audit and recorded Harbor results |
| Agent budget exceeds the project policy | Reduce `[agent].timeout_sec` from 64800 to 36000 | Repository validation, strict artifact audit and final Harbor Oracle validation |

No historical model rewards were changed. The image and CPU/memory budget were
preserved. ASR edits are local; commit and push are not part of this authorization.
