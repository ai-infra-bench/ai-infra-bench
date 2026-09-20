# Investigating upstream history before building a task

Use this procedure when creating a task that repairs or extends an existing repository. Complete the investigation before accepting an Oracle and freezing the instruction and verifier. Scaffolding or environment preparation can proceed while research is incomplete, but do not treat the task as validated.

## Establish the starting point

Record the repository, exact Base commit, proposed Oracle source, and initial observable requirements. Describe the relevant inputs, supported modes, resource preconditions, lifecycle, and behavior that must remain intact. Start from the developer's problem; do not derive correctness from the supplied patch or its tests.

If there is no source PR, search from the affected feature and symptoms. For a task with no relevant upstream implementation or history, a brief explanation is sufficient; do not invent a PR provenance requirement.

## Search beyond the original PR

Read the source PR or issue, its discussion and review comments, and linked reports. Search the repository for the same symptoms, affected components, changed symbols, and fixes that cite the original change. Use both symptom-based and code-based searches: reports may describe the same defect without mentioning the original PR or using the same terminology.

Include open and closed issues, merged PRs, open PRs, and closed-but-unmerged PRs. Follow relevant replacement, revert, regression, and follow-up links. A closed PR may have been superseded or abandoned without the bug being fixed; an open PR may contain the only known reproducer. Do not filter the search to merged changes or rely solely on automatically linked issues.

Inspect file or symbol history when discussion does not establish what changed. For claims about whether a bug still exists, fetch the current upstream state and pin the inspected commit. Check the actual implementation and relevant tests; an issue's status or a proposed fix does not establish that the fix landed. Distinguish the date a problem was reported from when the affected code was introduced.

Record the search date, useful queries or history commands, links, PR merge status, and inspected commits. Follow concrete leads until the relevant findings have an explained disposition. Do not attempt to enumerate the repository's entire bug history. If search access fails or results are truncated, state the limitation; “no report found” is not “no bug exists.”

## Decide what belongs in the task

For each material finding, answer these questions:

- Does it violate an explicit requirement or a reasonable consequence of the proposed task contract?
- Can it occur with the frozen Base's interfaces and supported inputs, including after applying the proposed Oracle?
- Does the proposed Oracle handle it, and what evidence supports that conclusion?

Include defects that satisfy the first two conditions. Exclude defects that require later-added features, unsupported modes, or unrelated behavior, and explain that boundary. A bug reported after the cutoff may still belong if its triggering conditions already existed at Base; its later report date alone is not grounds for exclusion.

If a finding would materially expand the scope, present that change before adopting it. Once the task is frozen, record an accepted scope expansion as a new version rather than silently adding requirements after an evaluated agent passes. Do not add Oracle-specific helpers, representations, or protocols to the instruction merely to accommodate tests.

## Turn applicable findings into behavioral checks

Apply the [fixture reachability requirements](../../ai-infra-bench-task-review/references/review-rubric.md#8-verify-fixture-reachability) when adapting upstream cases. A merged fix, upstream unit test, or failing internal probe does not by itself establish that the triggering state is reachable in the task’s supported product workflow.

Construct a legal reproducer from the failure mechanism and task contract. Exercise the component and lifecycle that determine the behavior, including important transitions or combinations that isolated happy-path cases miss. Upstream tests can inform the scenario, but inspect their assumptions before adapting them to Base.

Assert observable inputs, outputs, state changes, or execution ordering appropriate to the requirement. Avoid binding the test to the upstream fix's private helpers or internal representation. Confirm that a failing implementation reaches the intended path and fails for the defect, not for missing dependencies, invalid fixtures, or a report-format mismatch.

Challenge the proposed Oracle with these checks. Repair applicable defects before accepting it, and retain the old implementation as a regression counterexample when it demonstrates the problem. Apply the same checks to alternative solutions; the historical Oracle has no exemption. Base must fail the task's target behavior, but it need not fail every added regression check: some checks protect behavior that the proposed patch could break.

For example, a prefix-cache fix may pass an initial reuse check yet lose information when multiple media inputs share an unfinished block and later decoding fills it. If that combination is supported at Base and covered by the contract, verify reuse through that lifecycle. Neither an upstream merge nor a passing existing verifier settles the case.

Distinguish code inspection, a focused reproducer, and a full task-verifier run. Record exact revisions and results for each; a passing extracted-function probe does not establish that the service or final scoring entrypoint works. If a relevant contradiction remains unresolved, the Oracle and task are not ready for acceptance.

## Preserve evidence without exposing the answer

Keep a compact curator-facing record, using an existing construction report when available:

| Finding and source | Base and scope applicability | Oracle evidence | Disposition and coverage |
| --- | --- | --- | --- |
| Linked issue, PR, or code finding; status and inspected revision | Trigger, supported conditions, and requirement affected | Inspection or reproduction command, revision, and result | Included test, justified exclusion, or unresolved next step |

Include the search date and limitations, plus the final Base and Oracle revisions. Map each included finding to a verifier case and a stated or reasonably implied requirement. Conversely, check the task's remaining requirements for coverage: an upstream search does not replace bidirectional instruction/verifier alignment or independent review.

Keep later patches, diagnostic answers, and private reproducers outside the agent's image and accessible workspace. Apply the task's cutoff and visibility rules to repository history, build contexts, and copied artifacts as well as the instruction. Express any accepted requirement as a natural developer request about behavior, without revealing the root cause or prescribing the reference fix.

Store verbose logs and reproduction artifacts in an evidence archive when needed; link them from the compact record rather than adding unrelated logs to the task. At handoff, explicitly identify unresolved findings and unverified claims. Research informs task construction; it does not prove the absence of unknown bugs.
