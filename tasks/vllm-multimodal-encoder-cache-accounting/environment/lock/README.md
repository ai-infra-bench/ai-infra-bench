# Environment sources and lock rationale

This environment represents the parent of vLLM PR 30475:
`676db55eecf8b6d9ec38ea243cf6f35ea8378ec6`. The immutable GitHub commit
archive is verified with SHA-256 before extraction, and its canonical Git tree
must equal `aafa39e6544cbeaf83b72985f83aaefd4e9e3456`.
An isolated Git stage fetches only that exact Base and its parent history. The
final worktree must have the Base itself at `HEAD`, with no remotes, remote
refs, tags, reflogs, fetch metadata, shallow boundary, unreachable objects, or
known future commit.

The nearest official release environment is `vllm/vllm-openai:v0.11.2`.
Docker uses its linux/amd64 platform manifest directly:
`sha256:47a9896f86818fea323b2d38082758c62d9a0155d6fe6c4dbd7d735c556f680a`.
The Dockerfile does not resolve the mutable tag or the multi-platform manifest
list at build time.

CUDA libraries and production Python dependencies are inherited unchanged from
that digest-pinned official image. The image additionally installs a
content-addressed pytest 9.0.3 stack (pytest, iniconfig, packaging, pluggy, and
Pygments wheels), plus tblib 3.1.0 for the upstream test conftest; their versions and SHA-256 values are recorded in
`environment.json`. Candidate Python source comes only from the
verified base commit. Compiled vLLM shared objects come from the official
v0.11.2 image, are copied into `/app/vllm`, and are ignored as generated
artifacts. The generated release `_version.py` is copied by the same exact-path
overlay; no other wheel Python source is overlaid. The Docker build checks that
both `vllm.__file__` and `vllm._C` resolve under `/app`, while PyTorch is 2.9.x
with CUDA 12.9. The validated official image reports PyTorch `2.9.0+cu129`.

The runtime is configured offline and must additionally be launched with
`--network none`. No model or dataset is required for the structural baseline
reproduction: it uses production `PlaceholderRange` and `EncoderCacheManager`
classes with a sparse `P=100`, `E=8` placeholder.

The image contains the normal upstream test tree at the Base commit, including
`tests/v1/core/test_encoder_cache_manager.py`. It contains no curator-authored
reproducer, scoring fixture, solution, or hidden test suite. The pinned pytest
stack and tblib make this normal repository entrypoint usable offline as the
agent user. Docker build checks collection; validation records a separate
execution of its nine tests. The embedding-count behavior may be exposed as
either a property or a method.

This simplified survey environment does not rebuild native extensions from the
exact base commit. They are inherited from the nearest digest-pinned release,
v0.11.2. That tradeoff is acceptable for this task's Python-only PR surface and
is guarded by import/ABI smoke tests, but it is not interchangeable with the
full source-built environment when a task modifies C++/CUDA code or depends on
commit-specific native behavior.
