# Contributing

AI Infra Bench accepts task proposals, environment work, verifiers, workload analysis, and evaluation tooling from inference-system maintainers and researchers. Task contributions use [Harbor](https://github.com/harbor-framework/harbor) for reproducible agent execution and grading.

## Propose a source

A useful source is a real issue or pull request with clear AI-infrastructure value. Please include:

- canonical repository and issue/PR URL;
- why the work is representative, memorable, or technically diagnostic;
- the workload and subsystem categories;
- known model, dependency, hardware, and checkpoint requirements;
- an informal human-effort estimate, kept as free text;
- known reproduction or leakage risks.

Survey evidence belongs in `data/vllm_survey_results.jsonl`. Do not include respondent email addresses or private discussion.

## Build a Harbor task

Read the [Harbor documentation](https://harborframework.com/docs) for the execution model and task format. Copy [`templates/harbor-task`](templates/harbor-task/) to `tasks/<task-id>/`, replace every placeholder, and keep the contribution self-contained. Existing vLLM tasks use [`templates/vllm-harbor-all-in-one`](templates/vllm-harbor-all-in-one/) to generate reproducible CPU environments.

The repository includes Harbor's official [`create-task` Skill](.agents/skills/create-task/SKILL.md). Invoke `$create-task` in Codex to work through Harbor task scaffolding, environment setup, verifier selection, Oracle validation, and real-agent testing.

A task contribution should provide:

- a pre-solution repository state with no future Git objects;
- an instruction that begins from an observable user or developer problem without revealing the root cause or reference solution;
- a pinned offline environment;
- a stable base reproducer;
- implementation-independent behavior tests and a real subsystem end-to-end test;
- reference and plausible-wrong solutions for verifier QA;
- exact environment, dependency, hardware, asset, and checkpoint metadata;
- `environment/image-manifest.json` for the retained canonical image;
- `validation/e2e-evidence.json` containing the final measured results and known limitations.

A task may set `metadata.validation_mode = "verifier_only"` when no correct
implementation exists yet and the contribution is specifically intended to
benchmark that unsolved capability. Such a task may omit `solution/` and
solution patches, but must include a solvability analysis, independent positive
controls for the verifier's protocol expectations, a real target-boundary Base
run, and an explicit evidence statement that no full positive implementation
was executed. CI runs only the Base and declared validation patches for this
mode; it must not synthesize or report an Oracle result.

The evaluated agent must not receive `solution/`, task verifier files, validation artifacts, future Git objects, or dependencies and build caches that reveal work after the pinned base commit. Hidden tests may vary inputs and edge cases, but they must not introduce requirements absent from the instruction.

## Review and harden a task

After the Harbor task exists, use the repository-specific [`ai-infra-bench-task-review` Skill](.agents/skills/ai-infra-bench-task-review/SKILL.md). In Codex, invoke it as `$ai-infra-bench-task-review`. The Skill links to the full [review rubric](.agents/skills/ai-infra-bench-task-review/references/review-rubric.md) and [validation playbook](.agents/skills/ai-infra-bench-task-review/references/validation-playbook.md).

Review and hardening are separate stages:

1. Review the complete source context, instruction, environment, solution, verifier, and evidence without modifying the task.
2. Reproduce the stated problem in the base image and write a contract table connecting the instruction to every rewarded behavior.
3. Discuss instruction findings and the proposed end-to-end boundary before editing.
4. After the direction is approved, fix the instruction first, then the environment, Oracle when present, verifier, adversarial cases, and evidence.
5. Re-run the review against the final task before requesting repository review.

The verifier must judge public behavior rather than names or structures copied from the reference patch. A different correct implementation must receive full reward. A no-op, output spoof, test skip, visible-example special case, and plausible partial fix must receive zero.

## Validation gates

A task is not ready merely because the reference patch applies. Before requesting review, demonstrate:

```text
base fails repeatedly for the intended behavior
reference solution passes repeatedly
no-op and adversarial patches fail
plausible partial fixes fail
a behaviorally correct alternative implementation passes
the real subsystem end-to-end path passes
the final Harbor run passes with the retained canonical image
```

Performance tasks must also quantify measurement variance and show that the reference improvement is larger than environmental noise.

For `verifier_only` tasks, replace the unavailable reference/alternative gates
with independent protocol or fixture controls, repeated Base runs, a documented
solver reconstruction path, and a precise account of what remains unvalidated
without a full positive implementation. These controls establish that the
verifier's inputs and expectations are executable; they do not justify claiming
an Oracle pass.

Record actual commands, image identifiers, checksums, test counts, exit codes, Harbor results, and limitations in `validation/e2e-evidence.json`. Do not reuse evidence after an executable or contract-changing edit. A reconstructed fixture or deterministic model output must be identified as such and must not be presented as an original production or CI artifact.

## Open a pull request

Create a focused branch from the current `main`. Keep unrelated task, analysis, and template changes out of the commit. Before pushing:

1. run `git status --short` and inspect the complete diff;
2. confirm generated Dockerfiles match their shared template when applicable;
3. confirm the canonical image is retained and the final image contains no curator files or future information;
4. validate all cases required by the task's validation mode and Harbor results;
5. update evidence from those final runs.

The pull request description should identify the upstream issue and PR, pinned base commit, task contract, real end-to-end boundary, validation results, image state, and known limitations. Explain any reconstructed input or unavailable hardware rather than implying the original environment was reproduced.

Request review only after the task and evidence are final. Use GitHub's reviewer control or the GitHub CLI:

```bash
gh pr edit <pr-number> --add-reviewer <github-handle>
```

`main` is protected. Contributors cannot merge without approval and nobody can force-push or delete the branch. Address every blocking review finding and resolve review conversations before merge. If a review change affects the instruction contract, environment, solution, tests, or evidence identity, repeat the corresponding validation before asking for another review.

## Data contributions

Do not edit survey wording for style. Preserve respondent text under `survey`, and place curator inference under `benchmark`.

Before opening a pull request, confirm that JSONL records remain one valid JSON object per line, stable source IDs remain unique, public documentation links resolve, and no respondent identity or personal profile/comment link has been introduced.
