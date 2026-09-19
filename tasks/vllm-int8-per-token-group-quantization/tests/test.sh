#!/usr/bin/env bash
set -euo pipefail
mkdir -p /logs/verifier
printf '0\n' > /logs/verifier/reward.txt

# Create a writable Triton cache directory for the nobody-user worker. Triton's
# JIT compiler needs to write compiled kernels; the default cache path under
# HOME fails for nobody (HOME=/nonexistent, directory does not exist).
triton_cache=/tmp/triton-cache-nobody
mkdir -p "${triton_cache}"
chmod 1777 "${triton_cache}"
export TRITON_CACHE_DIR="${triton_cache}"

fail_provenance() {
  local stage="$1"
  printf 'provenance_failed stage=%s\n' "${stage}" \
    > /logs/verifier/failure-stage.txt
  printf '0\n' > /logs/verifier/reward.txt
  exit 0
}

repo=/workspace/repo
base_commit="$(git -c safe.directory="${repo}" -C "${repo}" rev-parse HEAD)" \
  || fail_provenance base_commit
candidate_patch_sha256="$(
  git -c safe.directory="${repo}" -c core.fsmonitor=false -c core.hooksPath=/dev/null -C "${repo}" diff --binary --no-ext-diff --no-textconv HEAD \
    | sha256sum | awk '{print $1}'
)" || fail_provenance candidate_patch
candidate_status="$(git -c safe.directory="${repo}" -c core.fsmonitor=false -c core.hooksPath=/dev/null -C "${repo}" status --short)" \
  || fail_provenance candidate_status
{
  printf 'base_commit=%s\n' "${base_commit}"
  printf 'candidate_patch_sha256=%s\n' "${candidate_patch_sha256}"
  printf '%s\n' "${candidate_status}"
} > /logs/verifier/candidate-provenance.txt

# Verify the frozen performance baseline is present and byte-identical to the
# base-commit copy of int8_utils.py. A missing or tampered baseline is fail-closed:
# without a trusted baseline the performance comparison is meaningless.
frozen_dir=/opt/ai-infra-bench/reference-int8
mkdir -p "${frozen_dir}"
cp /tests/frozen-reference/reference_int8_utils.py \
   /tests/frozen-reference/frozen_reference_loader.py "${frozen_dir}/"
chown -R 0:0 "${frozen_dir}"
chmod 755 "${frozen_dir}"
chmod 444 "${frozen_dir}"/*.py
frozen_ref="${frozen_dir}/reference_int8_utils.py"
frozen_loader="${frozen_dir}/frozen_reference_loader.py"
for required in "${frozen_ref}" "${frozen_loader}"; do
  if [[ ! -f "${required}" ]]; then
    printf 'frozen_reference_missing path=%s\n' "${required}" \
      > /logs/verifier/failure-stage.txt
    printf '0\n' > /logs/verifier/reward.txt
    exit 0
  fi
done

expected_sha256=36406a44b95e54cf99988105d0fe9a69645a0d2fcbfe2e60b1982d3ac9fdcff3
actual_sha256="$(sha256sum "${frozen_ref}" | awk '{print $1}')"
if [[ "${actual_sha256}" != "${expected_sha256}" ]]; then
  printf 'frozen_reference_tampered expected=%s actual=%s\n' \
    "${expected_sha256}" "${actual_sha256}" \
    > /logs/verifier/failure-stage.txt
  printf '0\n' > /logs/verifier/reward.txt
  exit 0
fi
printf 'frozen_reference_verified sha256=%s\n' "${actual_sha256}" \
  > /logs/verifier/frozen-reference-stage.txt

# Rebuild native extension as the agent user (uid 1000). The rebuild script is
# root-owned at /opt/bench/rebuild_native.sh, but it writes into /workspace/repo
# (agent-owned), so it must run as agent, not root.
set +e
runuser -u agent -- bash /tests/rebuild_for_verification.sh \
  > /logs/verifier/native-build.stdout.log \
  2> /logs/verifier/native-build.stderr.log
build_status=$?
set -e
if [[ ${build_status} -ne 0 ]]; then
  printf 'build_failed exit=%s\n' "${build_status}" \
    > /logs/verifier/failure-stage.txt
  printf '0\n' > /logs/verifier/reward.txt
  exit 0
fi
printf 'build_passed\n' > /logs/verifier/build-stage.txt

# Run trusted parent/worker verifier (writes reward.txt itself)
cd /workspace/repo
exec python3 -I /tests/verify_int8_quant.py > /logs/verifier/verification.log 2>&1
