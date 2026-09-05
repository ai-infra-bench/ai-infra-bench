#!/usr/bin/env python3
"""Export full Base-relative controls from a qualified Oracle source checkout."""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import subprocess
from pathlib import Path


def patch_for(base, changed):
    parts = []
    for path, new in sorted(changed.items()):
        old = base.get(path, "")
        if old == new:
            continue
        parts.append(f"diff --git a/{path} b/{path}\n")
        if path not in base:
            parts.append("new file mode 100644\n")
        parts.extend(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                         fromfile=f"a/{path}" if path in base else "/dev/null",
                                         tofile=f"b/{path}"))
    return "".join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    task = Path(__file__).resolve().parents[1]
    names = subprocess.check_output(["git", "diff", "--name-only", "--", "rust/src"], cwd=source, text=True).splitlines()
    oracle = {name: (source / name).read_text() for name in names}
    base = {}
    for name in names:
        result = subprocess.run(["git", "show", f"HEAD:{name}"], cwd=source, text=True, capture_output=True)
        if result.returncode == 0:
            base[name] = result.stdout
    route = "rust/src/server/src/routes/derender/mod.rs"
    state = "rust/src/server/src/routes/derender/types.rs"
    detok = "rust/src/server/src/routes/derender/detok.rs"
    lp = "rust/src/server/src/routes/derender/logprobs.rs"
    controls = []

    def save(name, files, reward, purpose):
        path = task / "validation" / f"{name}.patch"
        payload = patch_for(base, files)
        path.write_text(payload)
        controls.append({"name": name, "patch": path.name, "patch_sha256": hashlib.sha256(payload.encode()).hexdigest(),
                         "expected_reward": reward, "purpose": purpose})

    files = dict(oracle)
    needle = "let mut state = request.stream_state.map(|state| *state).unwrap_or_default();"
    assert files[route].count(needle) == 2
    files[route] = files[route].replace(needle, "let mut state = types::DerenderStreamState::default();")
    save("discard-client-state", files, 0, "Expose both endpoints but restart decoding for each chunk, losing cross-call state.")

    files = dict(oracle)
    needle = "if ctx.has_parser()\n"
    assert needle in files[route]
    files[route] = files[route].replace(needle, "if false && ctx.has_parser()\n", 1)
    save("plain-text-only", files, 0, "Keep native decoding but bypass non-streaming reasoning and tool parsing.")

    files = dict(oracle)
    needle = "content: Some(resolved_content),"
    assert needle in files[lp]
    files[lp] = files[lp].replace(needle, "content: Some(Vec::new()),", 1)
    save("discard-logprobs", files, 0, "Return empty logprob entries while ordinary response text remains valid.")

    files = dict(oracle)
    needle = "let prompt_tokens = request.prompt_tokens.unwrap_or(0);"
    assert needle in files[route]
    files[route] = files[route].replace(needle, "let prompt_tokens = 0usize;", 1)
    save("ignore-prompt-usage", files, 0, "Drop caller-supplied prompt accounting in non-streaming chat responses.")

    files = dict(oracle)
    needle = "pub(crate) struct DerenderStreamState {\n"
    assert needle in files[state]
    files[state] = files[state].replace(needle, needle + "    #[serde(default)]\n    pub replay_ids: Vec<u32>,\n    #[serde(default)]\n    pub emitted_text: String,\n", 1)
    files[detok] = '''// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: Copyright contributors to the vLLM project

use vllm_text::tokenizer::DynTokenizer;
use super::types::DerenderStreamState;
use crate::error::ApiError;

// Deliberately different state and algorithm: replay all prior IDs through the
// production incremental decoder, then emit only the newly available suffix.
pub(super) fn detokenize_delta(
    tokenizer: &DynTokenizer,
    delta_token_ids: &[u32],
    state: &DerenderStreamState,
    skip_special_tokens: bool,
) -> Result<(String, DerenderStreamState), ApiError> {
    let mut updated = state.clone();
    updated.replay_ids.extend_from_slice(delta_token_ids);
    let mut decoder = tokenizer.create_decode_stream(&[], skip_special_tokens, 0);
    for &token_id in &updated.replay_ids {
        decoder.push_token(token_id).map_err(|error| {
            ApiError::invalid_request(format!("decode failed: {error}"), None)
        })?;
    }
    let text = decoder.next_chunk().map(|chunk| chunk.text).unwrap_or_default();
    let suffix = text.strip_prefix(&updated.emitted_text).ok_or_else(|| {
        ApiError::invalid_request("inconsistent continuation state", None)
    })?.to_string();
    updated.emitted_text = text;
    Ok((suffix, updated))
}
'''
    save("alternative-native-decoder-replay", files, 1, "Use full token history and native decoder replay instead of the Oracle's bounded decode window.")
    manifest = {"schema_version": "ai_infra_bench_validation_cases.v1", "cases": controls}
    (task / "validation" / "ci-cases.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps([{k: c[k] for k in ["name", "expected_reward"]} for c in controls]))


if __name__ == "__main__":
    main()
