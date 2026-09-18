# Rust tool entity preservation hardening, task version 0.0.2

Retain the task. The verifier now follows the instruction's compatibility
requirement: ordinary named and numeric entity spellings remain byte-for-byte
unchanged, while escaped protocol closing delimiters retain their existing Base
decoding behavior.

## Contract and semantic boundary

Raw model-format tool text -> production Rust XML-style parser in complete or
streaming mode -> OpenAI-compatible tool arguments -> real OpenCode exact edit
-> `pom.xml` contents and Maven validation.

Model generation is substituted with deterministic raw model-format output.
The real vLLM Rust HTTP route, request conversion, chat output processing,
production parser, SSE assembly, OpenCode request schemas/read/edit operations,
filesystem and Maven all execute. This substitution preserves the text,
fragmentation, ordering and lifecycle that determine entity handling.

## Compatibility behavior

The four parser families preserve ordinary named, decimal and hexadecimal
entities, unknown or incomplete entities, and double-escaped text. Only complete
escaped forms of their own protocol closing delimiters are decoded. Matching is
not limited to one entity spelling: mixed named, decimal and hexadecimal angle
brackets are accepted. MiniMax, Qwen Coder, GLM and DeepSeek DSML are covered in
both complete and streaming modes.

The Oracle uses a shared control-tag matcher parameterized by full parser tags.
The correct alternative uses a different tag-name representation and matching
algorithm. Both preserve parser-specific whitespace and typed schema conversion.

## Verification and controls

The verifier requires the complete Base Rust source suite, 68 exact behavioral
cases, a 60-case compiled Rust fragmentation matrix, and the real OpenCode E2E
story plus all eight parser/mode cells. Base and nine incomplete or hacked
controls receive zero. Oracle and the compatible alternative receive one.

The blanket no-decode implementation is now rejected because it breaks the
Base closing-tag behavior. Other controls cover fixture-name special casing,
one entity class, one parser, a missing parser, GLM whitespace, and a closing-tag
substring shortcut. A Rust child-process exit(0) reaches the parser and writes
its marker, but cannot earn reward without the required JUnit and E2E results.

## Historical eight attempts

The original eight gpt-5.6-sol/high rewards remain unchanged. On the v0.0.2
verifier, the five Rust compatibility implementations pass the full grading
entrypoint. The two Python-only implementations still fail the production Rust
path, and the no-patch attempt still reproduces the Base failure. The replay
therefore confirms five v0.0.1 false negatives and three genuine agent failures.

## Identity and final state

Base: `7920ccb97c2d27d0a1a822e42d11ba369c2f255c`.
Image: `sha256:ed097e55f032297db87db864bd650dae51c18262a32dd3a740f7fc88e5160095`.
OpenCode: `1.17.3`. Agent budget: 36000 seconds. The image and dependency
locks are unchanged. Final hashes and actual Docker/Harbor records are stored in
`e2e-evidence.json`. No commit, push or image publication was performed.
