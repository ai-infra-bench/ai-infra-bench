# Validation and regrading

The four integrated Pi tasks (Messaging, Plan Mode, Context Management and Agent Trace) use their declared public behavior through the normal Harbor verifier. They do not require submission-specific binding profiles. Plan Mode’s visible interaction contract and driver are described in [interaction checks](pi-plan-mode-ui-bindings.md).

## Declared cases

`tasks/<task>/validation/ci-cases.json` lists complete and incremental controls, patch hashes, application order and expected rewards. The shared runner validates the source task, checks its actual image, materializes a selected case and checks the Harbor result. Run from the repository root with an existing local image and an unused output directory:

```bash
TASK_NAME=pi-plan-mode TARGET_PLATFORM=linux/amd64 \
  AI_INFRA_LOCAL_IMAGE="$PI_VALIDATION_IMAGE" \
  AI_INFRA_CASE_FILTER=oracle PUBLISH_IMAGE=false \
  HARBOR_JOBS_DIR="$PI_VALIDATION_OUTPUT" \
  bash .github/scripts/run_task_validation.sh
```

Set `PI_VALIDATION_IMAGE` to the immutable image ID verified against the task’s manifest and `PI_VALIDATION_OUTPUT` to a new directory outside the source tree. Omit `AI_INFRA_CASE_FILTER` to run the full declared matrix. A filtered run cannot publish images. Public CPU validation uses four CPUs; the formal task declares eight CPUs and 16 GiB. Context automatically adds the checked-in Docker `network_mode: none` overlay.

## Retained submissions

Materialize the retained submission against its recorded Base in a disposable task copy, keeping the exact patch, image, verifier inputs and application order. Run the normal Harbor entrypoint with that prepared copy. Do not edit a historical answer to make it pass, infer a new score from a different verifier, or coerce missing rewards and infrastructure errors into zero. Keep the original result alongside any new regrading result.

The root verifier owns the scoring observations and result files. Inspect the actual scenario summaries, native requests or JUnit reports as well as reward; a successful process exit alone does not prove all behavior ran. Supported substitutions and grading trust limits remain specific to each task.

## Build inputs and evidence

The task’s Dockerfile, lock, optional build configuration and image manifest identify its environment. Static validation checks these inputs without refreshing stale evidence. Rebuild changed environment inputs using the task’s supported builder or the shared CI build route, record the actual image ID, and revalidate affected behavior. Preserve named dependency-cutoff exceptions; matching compiled source does not date generated catalog data.

Keep prepared copies, exact source identities, Harbor results, resource and cleanup receipts, and full requested workspace archives outside the task directory. Source validation and a patch-application check supplement real behavioral validation; neither establishes a passing task by itself.
