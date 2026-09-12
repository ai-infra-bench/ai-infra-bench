# Current environment build

Task 1.2.3 adds the pinned tblib 3.1.0 wheel required by the normal upstream
pytest conftest. It does not add curator tests or solution material to the
agent image. The Base source, official native overlay and runtime versions
remain unchanged. Build checks collect the normal cache-manager test module
as the agent user; a separate offline run executes its nine tests.

The real build used the legacy Docker builder with cache enabled and a local
git-history mirror. Exact Base/tree/history assertions ran in the Dockerfile.
This is not described as a no-cache build. The mirror changes transport only;
the content checks determine source provenance.

Current image: `sha256:aad47363477b6b2092e8d3ba616da14fc35a11af170bc19f8d26de7ef00bb107`.
Tag: `vllm-encoder-local:tblib-20260909T062308Z`.
Authoritative metadata: `environment/image-manifest.json`.
Full build command/log, image audits, self-test and final Harbor evidence:
`validation/e2e-evidence.json` and its portable raw-evidence archive.

The source/native import checks establish the declared CPU accounting boundary;
this task does not change native code or claim full-model GPU validation.
Historical build reports remain in `validation/history/`.
