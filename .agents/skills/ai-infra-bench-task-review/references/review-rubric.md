# Task Review Rubric

Use this rubric for a read-only review. First determine whether the instruction and base environment form a real, solvable task. Then review provenance, Docker isolation, the verifier, and the recorded evidence. An Oracle pass alone does not make a task valid.

## 1. Record the review scope

Read the complete local task. Do not stop at file listings, partial previews, or prior summaries:

- `task.toml`
- `instruction.md`
- every file under `environment/`, including the Dockerfile, image manifest, lock inputs, lock output, and lock manifest
- every file under `solution/`, including the solve script and Oracle patch
- every file under `tests/`, including the test runner, behavior tests, E2E scripts, and integrity checks
- every file under `validation/`, including all adversarial and alternative patches and the complete `e2e-evidence.json`
- any other task-root file that affects building, execution, or publication

Read text, configuration, scripts, and patches in full. For binary or large runtime assets, inspect at least the type, size, hash, source, and license. Open or parse the content when the review depends on it.

The solution and tests are available for review, but they do not define the task by themselves:

- the solution is one reference implementation, not the only valid implementation;
- the tests are the current scoring mechanism, not proof that every hidden requirement is fair;
- the instruction, GitHub provenance, and observable behavior jointly define the contract;
- one purpose of review is to find disagreement among the instruction, solution, and tests.

Record the current branch, worktree state, task directory, base commit, candidate ID, instance ID, canonical image tag, and image ID. Confirm whether the user authorized only review or also authorized changes.

Run `git status --short`. Existing tracked and untracked changes belong to the user. Do not clean, overwrite, or mix them into later commits.

## 2. Retrieve the complete GitHub context

Use `task.toml` and the evidence file to identify the repository, base commit, PR, and issue. Read primary GitHub data rather than search-result summaries or secondary descriptions.

Read the complete current PR context:

- title, body, state, author, creation time, and merge time;
- base SHA, head SHA, merge commit, and every commit in the PR;
- each commit message, its order, and its actual diff;
- changed files and the complete PR diff;
- linked issues, closing issues, and issues or PRs referenced in the body;
- all ordinary comments;
- all review summaries;
- all inline review comments and replies;
- timeline events such as cross-references, close/reopen events, force pushes, and replacement relationships;
- proposals that review rejected, changed, or added.

Useful entrypoints include:

```bash
gh pr view "$pr" --repo "$repo" --json \
  number,title,url,state,author,createdAt,mergedAt,body,baseRefOid,headRefOid,\
commits,comments,reviews,files,closingIssuesReferences
gh pr diff "$pr" --repo "$repo"
gh api --paginate "repos/$repo/pulls/$pr/comments"
gh api --paginate "repos/$repo/issues/$pr/timeline" \
  -H 'Accept: application/vnd.github+json'
```

Read every linked issue in full:

- the issue body in its current edited form;
- all comments;
- labels, state, close reason, and linked PRs;
- commands, configuration, logs, hardware, and reproduction conditions supplied by users;
- information maintainers requested and the user's later validation;
- related discussions referenced in the issue timeline.

Follow new URLs, issues, and PRs referenced by bodies or comments until the provenance chain closes. If there is no directly linked issue, state that explicitly. Do not substitute a superficially similar issue.

Inspect relevant Git history:

- read every PR commit in chronological order;
- inspect earlier commits affecting the relevant files and functions;
- identify the feature commit or predecessor PR that introduced the problem;
- inspect earlier proposals that the current PR replaced;
- inspect later fixes that affect task boundaries without importing those fixes into the base;
- use `git log -- <path>`, `git show <sha>`, and `git blame <base> -- <path>` when needed.

Write a timeline: how the problem arose, how it was observed, how it was narrowed, how review changed the proposal, what the final PR fixed, and what belongs to later work. Leave undocumented steps unknown.

## 3. Review the instruction in context

Use GitHub provenance, the solution, and the tests for different purposes:

- GitHub provenance establishes facts, discovery history, and public scope.
- The instruction defines what the evaluated agent receives.
- The solution shows whether one reference fix satisfies the contract.
- The tests show how the task is currently scored and whether scoring depends on the reference implementation.

Do not turn a helper, field, parameter, or code structure introduced by the solution into a required interface. Do not narrow the task to the one input currently used by tests.

### Choose the instruction's starting point

Break the GitHub timeline into stages:

- A: the normal job the user or developer originally wanted to perform;
- B: the first observable failure, wrong output, slowdown, or missing capability;
- C: an internal trace, narrowed subsystem, or numeric discrepancy found during investigation;
- D: the root cause, design conclusion, and final fix.

The instruction should normally begin at A or B so the agent must diagnose the path from surface behavior to the internal cause. If the full timeline is A → B → C → D, beginning directly at C can remove most of the diagnostic work and disclose knowledge obtained only after the original investigation.

Do not mechanically choose the earliest chronological event. The starting point must:

- have support in public sources or a verifiable local run;
- be executable in the available image, or come with sufficient authentic logs;
- avoid unavailable private customer data, private prompts, missing weights, or nonexistent hardware;
- avoid invented business stories, commands, numbers, or causal claims;
- avoid expanding a local fix into a much larger product request;
- retain enough signal to make the task solvable within its time limit.

Starting at C is acceptable when:

- the problem was originally found during code review or new subsystem development and no user symptom is known;
- A or B requires private data, unavailable hardware, or unavailable model assets, so moving earlier would require invention;
- the instruction intentionally uses a developer-debugging perspective and C is the first evidence that developer actually had;
- the early symptom cannot be aligned reliably with the current PR's fix boundary.

When the task starts at C, explain in the review why A or B is not a suitable instruction boundary. Do not choose C merely because the existing verifier is written at C.

Fine-grained verifier cases may operate at C, but the real E2E should enter through the A or B public boundary whenever feasible.

For the instruction, identify:

- who is asking: end user, operator, library developer, reviewer, or subsystem engineer;
- what operation they performed;
- what they actually observed;
- which statements are source-backed facts and which are user hypotheses;
- what behavior they want changed;
- what current behavior must remain unchanged;
- whether they request explanation, a fix, a feature, or a combination;
- whether the agent knows the workdir and available inputs.

Flag an instruction that:

- directly states the root cause, Golden solution, target field, algorithm, or Golden code structure;
- rewrites post-merge understanding as knowledge the original user already had;
- starts at C without a valid reason when the source timeline is A → B → C → D;
- invents a user, business context, number, date, or log absent from public evidence;
- presents a locally injected failure as an original production or CI log;
- asks only to investigate, review, or inspect code while the verifier requires code changes;
- says only "do not break existing behavior" while the verifier enforces specific undisclosed cases;
- requires a model, dataset, command, or service that does not exist in the image.

The instruction may include logs, requests, responses, A/B comparisons, or developer traces, but the reviewer must enter the image and verify that the claims are accurate.

## 4. Reproduce the instruction in the base image

Reading the Dockerfile is not enough. Start the canonical base image with the same CPU, memory, user, workdir, and network policy used during the Harbor agent phase.

Do not mount any of the following during this check:

- `/tests`
- `/solution`
- `validation/`
- the Oracle patch
- curator reproduction or debug scripts

Adapt the command to the task and host hardware:

```bash
docker run --rm \
  --network none \
  --cpus 8 \
  --memory 48g \
  --workdir /workspace/vllm \
  --entrypoint bash \
  "$image_tag" \
  -lc '<read-only reproduction command derived from the instruction>'
```

From the instruction and public repository code, verify:

- commands, request paths, and files mentioned by the instruction exist;
- required Python packages, system libraries, media, tokenizer metadata, configuration, and test models are available;
- the network mode permits the operation the instruction asks for;
- base exhibits the described failure instead of stopping earlier on an unrelated dependency, memory, CPU-backend, or argument error;
- the described problem actually exists and matches the instruction;
- process counts, APIs, fields, and error types in logs match the claim;
- the agent can continue diagnosis without curator-only information.

Classify reproducibility:

1. Direct reproduction: normal user behavior reliably triggers the problem in base.
2. Log-driven reproduction: the original issue is a rare race or private incident; base cannot trigger it naturally, but the instruction provides sufficient authentic logs and the verifier uses deterministic injection.
3. Reduced reproduction: model weights, GPUs, a cluster, or a private prompt are unavailable; the image keeps the relevant real subsystem and supplies deterministic input at the unavailable boundary.

The second and third categories may still be valid, but evidence must state the limitation. The verifier must not inject a stronger fault than the Golden patch is expected to handle.

Apply the same user operation to Oracle and confirm that it produces the promised result. Do not generate instruction evidence with one scenario and score an unrelated helper test.

## 5. Build and verify the contract

This is the central review. The instruction, verifier, Oracle, and E2E must describe the same observable behavior. The verifier must accept every implementation that satisfies the contract.

### 5.1 Define the role of each artifact

- GitHub provenance explains the origin, original symptom, and actual PR scope.
- The instruction defines what the agent receives and what behavior reward may require.
- Base establishes which behavior is broken and which control paths already work.
- Oracle supplies one reference implementation, not the only implementation.
- The verifier converts instruction requirements into repeatable observations.
- E2E proves that the fix resolves the instruction through a real entrypoint.
- Hidden tests vary inputs and boundaries without adding undisclosed features.

No artifact overrides all the others. In particular, the verifier must not require the helper, variable, parameter, or internal state used by Oracle.

### 5.2 Define the task-level contract

| Field | Question |
|---|---|
| Surface problem | What can a user or developer actually observe? |
| Instruction start | Which A/B/C/D stage is used, and why is it the earliest reasonable start? |
| Reproduction | How can the agent confirm the problem in the base image? |
| Desired result | Which public behavior must change? |
| Regression boundary | Which currently correct behavior must remain? |
| Negative behavior | Which invalid inputs or persistent failures must still fail? |
| Scope | Which APIs, modes, backends, languages, layouts, or hardware paths are in scope? |
| Environment | Which dependencies, metadata, media, tokenizer files, or services are required? |
| Limitations | Which models, GPUs, clusters, networks, or private assets are unavailable? |

Fill this table from the instruction, base reproduction, PR discussion, Oracle, and verifier before interpreting individual test failures.

### 5.3 Map every rewarded behavior

List every verifier behavior that can affect reward:

| ID | Instruction basis | Public observation | Base expectation | Oracle expectation | Hidden variation | Regression/negative protection | E2E entrypoint | Implementation-dependent? |
|---|---|---|---|---|---|---|---|---|

For every row, check:

- the instruction contains an explicit or reasonably implied basis;
- the test observes user-visible output, public API behavior, or stable subsystem state rather than a Golden intermediate;
- base fails because the behavior is missing;
- Oracle passes at the same public boundary;
- hidden cases vary data, scale, order, mode, or failure conditions rather than functionality;
- existing correct behavior from PR discussion and base is protected;
- a real E2E covers the same requirement;
- a correct implementation with a different structure can pass.

Check both directions:

1. Instruction → verifier: every explicit requirement has behavior coverage.
2. Verifier → instruction: every requirement capable of producing reward 0 lies within the instruction contract.

### 5.4 Check implementation independence

The following should not affect reward unless the instruction defines them as public interfaces:

- whether a Golden-added helper, class, method, or parameter exists;
- names of variables, fields, files, functions, or classes;
- whether the agent modified the same file as Golden;
- patch text, AST shape, or exact call graph;
- private maps, counters, cursors, or cache structures;
- exact internal transition timing;
- helper call counts and ordering;
- use of one particular retry, lock, namespace, buffer, reference-counting, or other algorithm.

If observable behavior and all regression boundaries are correct, renaming helpers, inlining logic, reorganizing modules, adding abstractions, or using another algorithm must not fail.

Create at least one correct alternative implementation that deliberately changes Golden's internal names or structure while satisfying the complete contract. If it does not receive full reward, fix the verifier.

Base failure must also be meaningful. If most failures are `ImportError`, `AttributeError`, missing Golden symbols, or test calls using parameters unavailable in base, the verifier is testing Golden shape rather than task behavior.

### 5.5 Check real E2E alignment

Every task needs at least one E2E through the deepest feasible real boundary. It must enter through the user or developer path in the instruction rather than a Golden helper:

- CLI tasks use the real parser and configuration conversion.
- API tasks use real HTTP or SDK requests, request schemas, and response lifecycles.
- Media tasks execute real decoding, chunking, and public loading APIs.
- Cache tasks execute real schedulers, connectors, block pools, completions, or persistence.
- Distributed tasks start the relevant nodes, workers, placement, or channels.
- GPU tasks execute the real kernel, graph, collective, memory, or serving path on GPU; CPU fallback or a mock GPU is not a complete E2E.

GPU E2E must ensure:

- tensors, model state, and target operations are actually on GPU;
- the required backend is selected without silent fallback to CPU, eager mode, another attention backend, or a dummy implementation;
- kernel tasks run the real kernel rather than only a Python wrapper or shape helper;
- CUDA Graph tasks perform real capture and replay;
- collective, TP, PP, or multi-GPU tasks establish real process groups and communication;
- multi-node issues use real multi-node placement and network paths;
- memory, offload, or DMA issues perform real allocation, transfer, events, and synchronization;
- serving issues enter through a real engine or API request.

Do not prove GPU execution by checking that a Golden function was called. Use observable output, public logs, tensor devices, backend-selection results, communication state, or profiling without binding to private Golden names.

E2E must prove:

- base fails on the target problem;
- Oracle succeeds in the same scenario;
- fixed output, state, or continued operation matches the instruction;
- explicitly preserved behavior remains correct;
- the test reaches the target subsystem rather than failing earlier on unrelated setup.

When model weights or private services are unavailable, deterministic outputs or fault injection may replace that boundary, but the real code path after the substituted boundary must run. A GPU-specific issue still requires real GPU execution. Evidence must identify every substituted layer.

E2E must not only replay the single public instruction example. Add at least one input, mode, length, ordering, or repeated scenario absent from the instruction. The public example proves alignment; hidden E2E cases prevent special-casing.

### 5.6 Check hidden-test coverage

Hidden tests should vary contract-relevant dimensions rather than merely changing constants:

- values, lengths, batch sizes, blocks, chunks, and prompt shapes;
- streaming and non-streaming;
- single and multiple processes or nodes;
- cold, warm, hit, miss, and partial-hit paths;
- eager, lazy, synchronous, asynchronous, and other stated modes;
- languages, backends, layouts, parallel configurations, and tool calls;
- valid input, transient failure, persistent failure, and malformed input;
- first run, repeated run, concurrency, restart, and recovery;
- values and combinations absent from the instruction example.

Hide inputs, not requirements. A reasonable agent should know the behavior being evaluated after reading the instruction, but should not pass by hard-coding its example.

Test data must be deterministic. Use fixed seeds and preserve failing generated data. Replace low-probability races with deterministic injection aligned to the fix boundary.

### 5.7 Check regression and negative behavior

Passing the target path is not enough. Use the instruction, PR review, and base behavior to identify controls that already work:

- ordinary requests that do not trigger the bug;
- another correct API or mode;
- single-node, cold-cache, no-speculation, or no-reset controls;
- currently supported backends, languages, layouts, or parallel settings;
- correct streaming, non-streaming, or tool-call behavior;
- requests after reset, retry, or error recovery;
- state after restart, repeated calls, and concurrency.

Preserve negative behavior:

- genuinely missing, malformed, unsupported, or persistently corrupted inputs must still fail;
- fixes must not swallow exceptions, return empty results, or succeed unconditionally;
- old data, invalid cache, or failed transfers must not be reported as success;
- fixes must not silently fall back to a forbidden backend;
- the first call cannot work while later calls leak state, resources, or references.

Regression tests must observe behavior rather than check whether the agent called a Golden guard function.

### 5.8 Decide whether the task is aligned

The task is misaligned when:

- the instruction describes a user failure but the verifier checks an internal helper;
- the verifier requires a completely unstated feature;
- multiple implementations are allowed but tests accept only Golden structure;
- Oracle passes while breaking a path the instruction says already works;
- hidden tests hide functionality rather than inputs;
- behavior tests pass but E2E never crosses the real entrypoint or target subsystem;
- E2E and hidden tests only use public instruction examples;
- regression coverage allows a patch to fix the example while breaking normal behavior;
- a correct alternative implementation fails only because names, files, parameters, or structure differ;
- base fails because tests depend on Golden symbols rather than broken product behavior.

For every gap, state which behavior test must be added, removed, or rewritten. Sections 8, 9, and 10 provide additional implementation-independence, E2E, and anti-hack checks.

## 6. Statically review the Dockerfile

Read `environment/Dockerfile` line by line. A bootable final image is not sufficient.

### Source and Git history

- Pin the base commit with a full SHA.
- Fetch only that SHA, not the PR head, branch tip, tags, or later refs.
- Remove remotes, remote refs, tags, reflogs, `FETCH_HEAD`, and `ORIG_HEAD` after checkout.
- Preserve useful parent history through the base commit.
- Avoid a shallow boundary that breaks ordinary history inspection.
- Verify during build that HEAD equals the task's base commit.

### Build context and hidden files

- The Dockerfile must build with an empty context.
- Reject `COPY .`, `ADD .`, and copies of the whole task directory.
- Tests, solution, validation, evidence, and curator logs must not enter any build stage.
- Do not copy answers in one layer and delete them later; earlier layers remain recoverable.
- Dockerfile text, labels, environment variables, and shell history must not disclose answers, secrets, credentials, or curator-only paths.

### Dependencies and runtime assets

- Pin base images by digest rather than floating tag.
- Use a complete Python lock with resolver, Python platform, and cutoff metadata.
- Enforce the task cutoff with `--exclude-newer` or equivalent.
- Document every cutoff override.
- Review system package sources as well; floating apt repositories break reproducibility.
- Pin Rust toolchains, Cargo crates, and downloaded binaries; verify hashes where possible.
- Do not install `latest`, a Git branch, or an unpinned URL.
- Pin tokenizer, configuration, and media assets by immutable revision or SHA-256.
- Record licenses and attribution.
- Do not download model tensors when metadata is sufficient.
- Verify that no other vLLM wheel is installed before the editable base checkout.

### Build cache

- Source-independent OCI layers and download caches may be shared.
- Namespace compiler output, CMake FetchContent, and other source-derived caches by full base SHA and lock digest.
- Do not import untrusted remote build caches.
- Build ordering must not allow `.so`, wheel, or generated files from later source to override the base.
- When the host already supplies TUN networking, do not bake proxy addresses or credentials into the Dockerfile.

## 7. Dynamically review the final image and future-data leakage

### Image metadata

```bash
docker image inspect "$image_tag"
docker history --no-trunc "$image_tag"
```

Check image ID, size, labels, environment, entrypoint, workdir, and history. Base, cutoff, and cache-namespace labels must match task metadata. Environment variables must not contain tokens, proxy credentials, or answer paths.

### Git objects

Run read-only checks inside the image:

```bash
git rev-parse HEAD
git branch --show-current
git remote -v
git for-each-ref --format='%(refname)' refs/remotes refs/tags
git reflog show --all
git rev-list --all --not "$base_sha"
git fsck --full --no-reflogs --unreachable --no-progress
```

Expected results:

- HEAD exactly equals base.
- There are no remotes, remote refs, tags, or reflogs.
- There are no reachable commits outside base history.
- There are no unreachable future commits, trees, or blobs.

If the PR head or a later commit SHA is known, verify that the object is absent:

```bash
git cat-file -e "$future_sha^{commit}"
```

The command must fail. Deleting refs is insufficient if future objects remain in `.git/objects` or pack files.

### Answers and verifier files

The final filesystem must not contain:

- `/solution`
- `/tests`
- task validation patches
- E2E evidence
- curator debug or reproduction directories
- Golden patches, reward files, or hidden logs

Upstream tests shipped with the vLLM source may remain. The forbidden files are Harbor-mounted task tests and curator artifacts.

If the Dockerfile contains suspicious copies or deletions, inspect image layers. Save the image into a directory created by `mktemp -d` and inspect layer tar files for solution, tests, or validation artifacts. Absence from the final filesystem does not prove absence from older layers.

### Installed packages and import paths

Inside the image, run:

```bash
python -c 'from pathlib import Path; import vllm; print(Path(vllm.__file__).resolve())'
python -m pip freeze
python -m pip show vllm
```

Confirm:

- vLLM imports from the base worktree under `/workspace/vllm`;
- no future vLLM wheel is installed alongside the worktree;
- installed versions match the lock;
- `direct_url.json`, `.dist-info`, and editable metadata do not reference other source directories;
- extra dependencies respect the cutoff or documented overrides;
- runtime assets contain no hidden patches, tests, or future implementation.

Dependencies can also leak future behavior. Check Python packages, system packages, Cargo crates, and external tools, not only vLLM Git. Review lock-generation commands, versions, release cutoffs, and override reasons.

### Cache and rebuilds

The final image must not retain source compiler caches, download directories, or temporary wheels. BuildKit cache mounts normally stay outside layers; ordinary directories do not.

Rebuild with the same Dockerfile and empty context:

- the first build may populate caches;
- the second build should hit caches;
- both final image digests should match;
- source-derived caches from other base commits must not alter output.

For stronger validation, compare a clean-cache build with a warm-cache build, including key binary hashes when useful.

### Runtime network

Use the task's declared network mode. A `no-network` task must remain reproducible and solvable offline. The agent must not use Git remotes, package indexes, or external services to retrieve the PR head or answer.

## 8. Check verifier implementation independence

Build a requirement matrix:

| Instruction requirement | Public observation | Behavior test | Hidden variation | E2E coverage |
|---|---|---|---|---|

Flag tests that:

- import a class or helper introduced only by Golden;
- call a Golden-added method or pass a Golden-added parameter;
- inspect private maps, counters, cursors, or fields;
- assert exact transition timing, call counts, or internal ordering when the instruction requires only final behavior;
- require a function, variable, class, file, or parameter name absent from the instruction;
- inspect static patch shape rather than behavior;
- make base fail mainly because a Golden symbol is missing;
- reject a behaviorally correct implementation with a different structure.

Tests may import stable public entrypoints that existed before the fix. Ensure the agent cannot see verifier source; Harbor should mount task tests only during verification.

## 9. Check the E2E boundary

Unit tests are not E2E. Use the deepest feasible real boundary:

- CLI: real parser and configuration conversion;
- serving: real HTTP or SDK request, request schema, and response lifecycle;
- video or speech: real media decoding, chunking, and public serving API;
- cache: real scheduler, connector, block pool, and completion lifecycle;
- distributed transport: real Ray nodes, placement, and channels;
- GPU kernel, CUDA Graph, collective, memory, or GPU serving: real GPU execution without CPU or mock fallback;
- persistent cache: real filesystem, asynchronous work, and process restart.

Check that E2E:

- uses a public entrypoint rather than a Golden helper;
- executes the relevant real subsystem;
- covers the primary success path and required regression path;
- fails in base because of the target bug;
- passes with Oracle;
- reaches the target boundary before any unrelated failure.

When model weights or private services are unavailable, deterministic output may replace that boundary, but the relevant real code afterward must run. GPU-specific behavior still requires real GPU execution. Evidence must identify every substituted layer.

## 10. Check anti-hack strength

Anti-hack review covers tests, images, and builds.

### Tests

- Vary values, lengths, chunks, ordering, modes, languages, layouts, errors, and repetitions.
- Do not only replay the instruction example.
- Check final state and downstream effects, not only one return value.
- Require the exact collected test count, unique cases, zero failures, zero errors, and zero skips.
- Make reward depend on unit, behavior, E2E, and integrity layers.
- Reject fixed answers, unconditional success, swallowed errors, skipped code, and fabricated reward files.

### Image

- The agent cannot see tests, solution, validation, or evidence.
- Git cannot read commits or blobs after base.
- Installed packages do not contain a future fix.
- Source-derived caches cannot reuse output from a future build.
- Image layers do not contain deleted but recoverable answers.
- Environment, labels, shell history, and runtime assets do not disclose curator information.
- `no-network` prevents external answer retrieval.

### Adversarial and positive controls

Adversarial patches should cover distinct incomplete strategies, such as:

- special-casing the instruction example;
- fixing streaming but not non-streaming, or one API but not another;
- always returning success or a fixed answer;
- swallowing an error that must remain visible;
- handling one call but leaking state across repetitions;
- falling back to a forbidden backend;
- omitting one cache group, block, worker, process, or completion direction.

Also test at least one implementation with different internal names or structure but correct behavior. It must receive full reward.

## 11. Recheck base, Oracle, and error boundaries

During review, run at least one complete base trial and one complete Oracle trial when resources permit.

For base, confirm:

- reward is 0;
- failure comes from the target behavior;
- tests do not fail merely because they import a Golden helper;
- failure is not caused by a missing dependency or unavailable required hardware;
- failure is stable rather than an accidental race.

For Oracle, confirm:

- reward is 1;
- all tests and E2E paths actually execute;
- no test is skipped;
- invalid inputs, persistent corruption, and other negative cases still fail as required;
- Oracle introduces no behavior outside the instruction contract.

Spot-check recorded repeated runs. If current output disagrees with evidence, the evidence is stale.

## 12. Review evidence

Verify evidence content rather than only JSON syntax:

- source PR or issue, base commit, and scope boundary;
- hashes for the instruction, Dockerfile, lock, Oracle, tests, and helper scripts;
- image tag, ID, size, and retained status;
- behavior-case count and actual JUnit collection;
- base and Oracle pass counts and exit codes;
- adversarial and alternative patch hashes and rewards;
- real E2E entrypoint, output, and substituted boundary;
- Harbor version, job ID, trial ID, input checksum, runtime, and errored trials;
- Git, dependency, cache, network, and hidden-file isolation gates.

Do not reuse stale numbers. Instruction-only edits change the instruction hash and task checksum. Decide whether to rerun Harbor based on whether publication evidence requires exact checksum identity.

## 13. Report before modifying

First state whether the task can remain unchanged. Then report:

- whether the instruction is authentic, solvable, and reproducible;
- provenance or scope errors;
- Dockerfile and image leakage risks;
- verifier implementation coupling;
- missing behavior coverage;
- weak or mislabeled E2E;
- Oracle defects;
- stale or inaccurate evidence;
- current base and Oracle results.

Do not modify a review-only task. After the user approves changes, read the validation playbook and implement the agreed fixes.
