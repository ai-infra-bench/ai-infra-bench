# vLLM Model Runner V2 selection

Add configuration-based defaults for Model Runner V2 while preserving explicit environment overrides and selecting the correct runner during worker startup. The statement does not require a particular environment accessor representation or internal worker field.

The environment uses the exact Base SHA, a digest-pinned pre-cutoff runtime, one A100 and offline execution. See `environment/lock/README.md` for the source and native binding. The agent budget is ten hours. A writable `.venv` provides pytest and pre-commit, inherits the pinned runtime, and has the Base hook environments cached for offline Python development.

The verifier drives real `ModelConfig`, `VllmConfig`, `Worker.init_device` and V1/V2 runner constructors with small local model configurations. It covers automatic defaults, compatible explicit overrides, incompatible configurations, explanatory startup failure and repeated automatic startup. Elastic EP orchestration is the only substituted startup component; weights and generation are outside this selection task.

The root supervisor performs a candidate-independent CUDA preflight and grades authenticated per-case observations. The trusted suite is loaded before candidate imports. A verifier-only native checkpoint emitter authenticates events from that suite's code object; ordinary stdout is diagnostic and cannot grant reward. These checks cover the retained report-forgery and early-exit controls. They are not a sandbox against arbitrary native memory modification or arbitrary mutation of Python test execution.

Cases with the same startup override reuse one observation process; unset, 0 and 1 each start in a separate process, with fresh configuration and worker objects plus distributed cleanup for each case. Candidate implementations and controls are run in separate containers. Stage timings and case diagnostics are retained in `/logs/verifier`.

Build with `docker build -t <image> tasks/vllm-runner-v2-selection/environment`, supplying the build network/proxy settings appropriate to the host. Only `environment/` is a build input. Set the resulting image identity in the manifest and task configuration before formal validation.

Validation status and exact executable hashes are recorded under `validation/`. Historical results do not certify the changed verifier. Local script validation and a formal Harbor trial are reported separately.
