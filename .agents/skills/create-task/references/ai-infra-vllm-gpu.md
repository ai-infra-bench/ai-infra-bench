# Constructing vLLM and GPU benchmark tasks

Use this playbook for ai-infra-bench tasks involving vLLM or other GPU
infrastructure mechanisms. It supplements the generic task-creation workflow.
The post-construction independent review remains governed by the
`ai-infra-bench-task-review` skill.

## Contents

1. [Provenance and contract](#1-record-provenance-and-define-an-independent-contract)
2. [Task contract and difficulty](#2-freeze-the-task-contract-and-difficulty)
3. [Instruction rules](#3-instruction-rules)
4. [Hardware requirements](#4-hardware-requirements-and-applicable-technical-guidance)
5. [Version and fixtures](#5-version-and-offline-fixture-compatibility)
6. [Native and image provenance](#6-native-and-image-provenance)
7. [Construction checks](#7-construction-acceptance-checks)
8. [Independent-review handoff](#8-handoff-to-independent-review)

## 1. Record provenance and define an independent contract

Before using evaluated-agent outcomes to make design decisions, record the
target repository, exact Base commit and tree, task scope, and Oracle source.
Derive the behavioral contract from a realistic user or developer scenario.

Follow [the upstream-history procedure](upstream-history.md) before accepting the Oracle and freezing the instruction and verifier. Record related reports, including unresolved and closed-but-unmerged fixes, and determine which defects can occur at Base within the proposed scope. Resolve relevant contradictory evidence through code inspection and behavioral checks; a merged patch is not automatically a correct reference implementation.

The task may adapt, combine, or extend upstream mechanisms into a realistic
independent scenario. It need not reproduce an entire PR or a named slice.
Require historical timeline and coverage fidelity only when the task explicitly
claims to reproduce a particular historical event or PR. Keep curation
provenance outside the agent-facing instruction unless needed for the public
task contract.

## 2. Freeze the task contract and difficulty

Write a contract matrix with at least:

| Field | Required decision |
| --- | --- |
| Surface behavior | What an operator or developer can observe |
| Desired behavior | Public result that must change |
| Preserved behavior | Existing modes that must not regress |
| Negative behavior | Invalid or persistent failures that must remain visible |
| Scope | Included and excluded observable behavior |
| Real E2E | Production entrypoint and deepest exercised boundary |
| Substitutions | Missing model/service boundaries replaced deterministically |
| Resources | CPU/GPU type, count, memory, disk, and network |
| Time limits | Separate build, agent, verifier, and collective timeouts |

Difficulty must come from the authentic diagnosis and implementation scope. Do
not make a task difficult by omitting a necessary public contract, dependency,
model, command, or performance protocol. Do not make it easy by stating the
root cause, Golden helper, field, file list, or algorithm.

State scope honestly in terms of observable behavior. Do not silently expand
the frozen contract after seeing an evaluated agent pass. A material scope
change requires an explicitly recorded new task or version.

## 3. Instruction rules

The instruction may disclose:

- the authentic observable symptom or developer trace;
- required public API names;
- hardware, shapes, dtypes, warmup, statistics, and frozen performance gates;
- categories of state or behavior that must be preserved.

It must not disclose:

- Golden-only private helpers, constructor keywords, attributes, or filenames;
- the root cause learned only at the final discovery stage;
- a checklist copied from the Golden diff;
- the internal algorithm selected by Golden;
- hidden test inputs or expected source structure.

Hidden tests may vary values, ordering, shape, lifecycle repetitions, topology,
and error cases. They may not introduce a behavior category that the
instruction did not disclose.

Task-specific reproduction artifacts are optional. Authors may create and
retain them when useful for construction checks or independent review. Even a
bug-fix task need not have a standalone reproducer if existing tests or
execution evidence establish the target behavior. Other task types should use
behavioral or performance checks appropriate to their goals.

If present, keep these artifacts and diagnostic materials curator-only or
verifier-only. Do not expose them through the instruction, agent filesystem,
mounts, recoverable Git objects, caches, or image layers. A `validation/`
directory name alone does not establish isolation. Normal public interfaces,
operating instructions, observable symptoms, and necessary input conditions
may still be described without supplying a task-specific diagnostic script.

A reproducer validates a particular case; it does not replace regression
coverage or validation through the actual scoring path.

## 4. Hardware requirements and applicable technical guidance

Choose hardware from the behavior being evaluated:

| Category | Requirement |
| --- | --- |
| CPU-sufficient | The target behavior does not require GPU execution. Preserve real process, service, or lifecycle behavior when it determines the result. |
| GPU-required, model-independent | Run on a GPU satisfying the required capabilities and resources; do not require an exact model without a behavioral reason. |
| Device-feature-dependent | Record the relevant architecture, capability, topology, or other device property and the devices on which the target behavior has been validated. |

The original reproduction device is evidence, not an automatic exclusivity
rule. Another device may be used when validation establishes the same target
mechanism and required behavior. Record its hardware identity and results.
Treat untested devices as unverified, not automatically supported or
unsupported. Do not reuse device-specific performance thresholds on different
hardware without validating their applicability.

CPU-only results cannot establish GPU behavior. Mentioning GPU configuration,
TP, or PP does not by itself require a real collective; executing or measuring
collective behavior does require the relevant real multi-GPU path.

Apply the following technical guidance only when the task involves that work.

### Triton and CUDA Python kernels

For Python/Triton work that executes a real GPU kernel, pin the
CUDA/PyTorch/vLLM runtime combination and prove that the tested tensors and
kernel run on the declared GPU capabilities.

### Native extensions

For `_C`, `_moe_C`, or other compiled extensions. Declare:

- the exact-source versus donor-artifact policy;
- the focused build target and command;
- CUDA architectures and compiler limits;
- source, build-input, output-library, and cold-import digests;
- the rule excluding generated `.so`, build directories, and caches from the
  agent source patch.

When candidate changes affect the native target or its build inputs, the
verifier must rebuild that target or establish equivalent provenance for the
candidate build. A source patch paired with a stale affected library is not
valid evidence.

### Multi-GPU and NCCL

Apply this subsection when the target behavior requires real multi-GPU
execution or collective communication. TP/PP configuration or device mapping
alone does not trigger these requirements. Declare the following where
applicable to the task contract:

- exact GPU count and topology;
- process count and rank mapping;
- rendezvous method;
- NCCL and subprocess timeouts;
- deterministic cleanup after success, failure, and timeout;
- the precise data-path interval in which object collectives or GPU-to-CPU
  synchronization are forbidden.

Do not flag initialization, logging, or final test assertions when the contract
only forbids synchronization on the hot data path.

## 5. Version and offline-fixture compatibility

Apply the project's cutoff and agent-visibility rules in
[the review rubric](../../ai-infra-bench-task-review/references/review-rubric.md).
Compatibility records and hashes do not establish cutoff compliance or
isolation.

Before building, construct a compatibility record for:

- vLLM base SHA and source tree;
- official/donor image digest and donor vLLM revision;
- Python, CUDA, driver requirement, PyTorch, Triton, and compiler versions;
- native extension origin;
- Oracle applicability to the base;
- tokenizer/model configuration or deterministic fixture revisions.

The verifier must be runnable under its declared network policy. If it uses a
model identifier while offline, bake the smallest required immutable metadata
or a valid local fixture into the image. Do not let Base, Oracle, or agent fail
first because a model, pytest, compiler, or package is missing.

## 6. Native and image provenance

Build from an empty context or an allow-listed context that cannot contain
tests, solution, validation patches, trajectories, credentials, or future
source. Pin all images and downloads by digest.

When borrowing native artifacts from a donor image or package, inspect retained
Python source, secondary installations, Git objects, caches, and inherited
image layers for future target-repository source or answer-revealing material.
Import precedence such as `PYTHONPATH` does not prevent the agent from reading
another copy. Build an agent environment where such material is not recoverable
and verify visibility under the actual agent settings.

General benchmark infrastructure is not required to predate cutoff unless its
behavior is part of the task; follow the rubric's semantic-dependency
distinction. For native artifacts, determine whether candidate changes affect
their sources or build inputs, including relevant headers, generated inputs,
and build settings.

- If native artifacts are unaffected, compatible donor binaries may be reused.
  Record their origin, identity, compatibility, and actual import path.
- If candidate changes affect a native target, rebuild that target from the
  candidate inputs, or establish equivalent provenance for that candidate
  build. In a fresh process, verify that the tested library is the resulting
  artifact.
- Do not require rebuilding unrelated extensions. Do not accept tests that run
  a stale library instead of the candidate's affected native implementation.

Collect the following records when applicable; do not require nonexistent build
artifacts for tasks that perform no native build:

- task/input SHA and candidate patch SHA;
- base and source tree SHA;
- Dockerfile and lock SHA;
- build command, exit code, duration, and focused target;
- CUDA/C++ source closure SHA;
- output `.so` SHA and ELF/CUDA architecture evidence;
- actual Python import path and imported-library SHA in a fresh process;
- image ID/digest and relevant installed versions.

Build failure, correctness failure, E2E failure, and performance failure are
different outcomes and must be reported separately.

## 7. Construction acceptance checks

Map every reward-affecting test to an instruction behavior. Use observable
behavior or stable subsystem state, not Golden implementation shape.

Complete these checks while constructing the task:

1. **Base negative:** reward 0 because the target behavior is wrong. Import,
   dependency, missing-model, missing-private-symbol, or build failures do not
   satisfy this control.
2. **Oracle positive:** reward 1 at the same E2E boundary, with zero unexpected
   skips.
3. **Environment smoke:** the declared compiler, package, model fixture, GPU,
   and collective requirements are available before the target behavior runs.
4. **Production-boundary smoke:** Base and Oracle exercise the production entry
   point named in the task contract rather than only a mock or private helper.
5. **Artifact provenance:** affected native targets correspond to candidate
   build inputs and are actually loaded in a fresh process; reused unaffected
   artifacts have recorded identity and verified compatibility.

For performance tasks, publish hardware, shape, dtype, warmup, repetition,
statistic, and threshold. Confirm that the Oracle has adequate margin over the
threshold rather than relying on a borderline or noisy pass.

These are construction checks, not a complete independent review. Do not add
post-construction review or evaluated-agent procedures here.

## 8. Handoff to independent review

After the construction checks pass, freeze and hand off:

- instruction and declared task scope;
- base source and image identities;
- environment and dependency locks;
- Oracle patch and applicability record;
- verifier;
- curator-only reproduction artifacts and diagnostic evidence, if any;
- Base/Oracle logs and artifact provenance;
- hardware requirements and time limits.

Hand these artifacts to the `ai-infra-bench-task-review` skill. Its procedures
and acceptance criteria are intentionally outside the scope of this creation
reference. If review later returns a construction defect, address it as a new
task version rather than silently editing the frozen candidate.
