# Pi Messaging automated validation

Run the ordinary Harbor Base, Oracle and declared control cases for
`pi-subagent-live-messaging`. The instruction defines the public `subagent`,
`team_members` and `team_send` interfaces. No candidate profile, source-review
approval or per-submission preparation is part of scoring. Extra tool-result
fields and the choice of RPC, sockets, native IPC or file mailboxes remain free.

The previous free-interface task and reviewed-replay workflow remain in Git at
`a0ec3bc54768dce1d019b6b8d469be70a791bffa`. Historical submissions belong to their
original contract; the new public interfaces do not apply retroactively. Other
tasks with an explicit `reviewed_replay` catalog retain their own workflow.

## Behavior and timing

The suite runs the candidate's actual Pi CLI, core and separate worker processes.
A test-owned copy of Pi's Faux provider supplies model responses; an ordinary
external tool supplies controlled work. Communication and agent-loop behavior
remain in the candidate implementation.

Tests retain actual instance IDs and associate tool arguments and results by
actor and call ID. They use discovered teammate addresses rather than replacing
wrong addresses with fixture values. Disabled cases exercise legacy parallel
inputs, an omitted switch and explicit `false`. Registered but disabled tools
may reject requests explicitly; registration alone is not a failure.

Pi's native tool-completion event records each send outcome before the entire
tool batch reaches history. Ordinary work releases independently of send
completion, so capacity backpressure can progress without a teammate reply.
Accepted messages with an established boundary are due in the next model call;
a missed obligation cannot be extended by observing a later boundary. A message
already delivered during a handoff is counted once. FIFO compares the actual
order of accepted sends and their positions in recipient inputs. Reports expose
which strict boundaries and FIFO pairs were exercised rather than treating an
empty conditional check as proof of coverage.

All model inputs use one reader for complete bodies, sender attribution,
ordering and duplicates. It understands supported plain-text and lossless JSON
representations, nested sender/body containers and explicit adjacent headers.
A roster, sibling message or quoted text cannot supply a missing sender.
Missing bodies, missing identities and definite wrong identities fail behavior.
A complete body with an external identity claim that the reader cannot safely
associate produces `scoring_error`; fix the shared reader and rerun affected
cases. There are no candidate-specific format exemptions or external LLM judges.

## Execution and resource observations

A root-owned grader is the sole reward writer. Candidate processes run as UID
60000 and cannot modify the trusted harness or reward files. External Node
Inspector observations track the actual parent and workers and require executed
Pi sessions; importing Pi or fabricating observer messages is insufficient.
The observer binds each model request to the content seen inside the trusted
provider in that native process. The provider bundle's source manifest and
rebuild tool are included under `validation/`.
Correct CLI wrappers and delegated prompt methods have positive controls.
This catches the declared report-forgery controls; it is not a proof against all
malicious programs that run unrelated Pi sessions as camouflage.

Cancellation observes real process identities, including discovered helpers,
before test teardown. For file communication, pinned `strace` records actual
writes, recipient reads and consumption. Only established queue relationships
qualify retained files as communication resources; an ordinary log containing
message text is not enough. The queued-cancellation case first delivers a
warmup message, then cancels with another message pending, and finally reuses
the same task IDs and scratch environment to detect stale delivery.

The transport-fault case discovers an eligible recipient-only file queue and
removes its write permission, then checks the actual broadcast and recipient
inputs. A traced write denial establishes the fault; another recipient's new
delivery establishes that the fault was isolated. Recovery and complete delivery
are valid outcomes. A fault that could not be established is reported as a
coverage diagnostic, not a candidate failure. Queue pressure separately checks
partial rejection and false acceptance for bounded IPC implementations.

Resource classification is deliberately conservative. Unrecognized persistent
file layouts are diagnostic, and precise TCP/native-IPC transport fault
injection is not claimed. Socket/IPC observations and process termination do not
prove every possible transport-failure path. These are suite coverage limits,
not a requirement to review each submission manually. The historical
`validation/tools/review_resources.py` is a curator diagnostic for old reviewed
profiles; it is not called by the automatic grader and is not an acceptance gate.

## Qualification and records

Use the controls in `validation/ci-cases.json` to check both false rejection and
false acceptance: alternate storage and message representations, backpressure,
explicit tool errors, disabled tools, wrong IDs/senders, dropped or repeated
messages, retained mailboxes, early exits and forged parent/worker observations.
Size probes near 64 KiB permit explicit rejection or complete delivery; they do
not require that capacity or prove arbitrary documented limits.

Keep actual outcomes, exercised coverage, source hashes, image identity and
Harbor records outside the task. Component probes, local CLI runs and formal
Harbor trials establish different boundaries. A scorer infrastructure error
leaves no reward; neither a successful process exit nor old passing results
establish completion of the current checks.
