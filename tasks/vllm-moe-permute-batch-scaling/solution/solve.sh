#!/usr/bin/env bash
set -euo pipefail
cd /app
git apply /solution/oracle.patch

nvidia_site=/usr/local/lib/python3.12/dist-packages/nvidia
nvidia_includes="$(
  find "${nvidia_site}" -mindepth 2 -maxdepth 2 -type d -name include -print \
    | sort \
    | paste -sd: -
)"
test -n "${nvidia_includes}"
export CPATH="${nvidia_includes}${CPATH:+:${CPATH}}"

cmake_file=/app/CMakeLists.txt
cmake_backup="$(mktemp /tmp/vllm-cmake.XXXXXX)"
cp -p "${cmake_file}" "${cmake_backup}"
restore_cmake() {
  mv "${cmake_backup}" "${cmake_file}"
}
trap restore_cmake EXIT HUP INT TERM

# The upstream top-level project declares unrelated FetchContent projects after
# defining `_moe_C`. This focused task neither builds nor imports them; end
# configuration after the target so the rebuild stays fully offline.
python3 - "${cmake_file}" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text()
marker = "\n# For CUDA and HIP builds also build the triton_kernels external package.\n"
assert text.count(marker) == 1
path.write_text(text.replace(marker, "\nreturn()\n" + marker))
PY

cmake -S /app -B /app/build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CUDA_ARCHITECTURES=80 \
  -DCMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc \
  -DCMAKE_INSTALL_PREFIX=/app \
  -DCUDA_nvrtc_LIBRARY=/usr/local/lib/python3.12/dist-packages/nvidia/cuda_nvrtc/lib/libnvrtc.so.12 \
  -DFETCHCONTENT_BASE_DIR=/app/.deps \
  -DNVCC_THREADS=2 \
  -DVLLM_CUTLASS_SRC_DIR=/opt/cutlass \
  -DVLLM_PYTHON_EXECUTABLE=/usr/bin/python3 \
  -DVLLM_TARGET_DEVICE=cuda
cmake --build /app/build -j 8 --target _moe_C
cmake --install /app/build --prefix /app --component _moe_C

restore_cmake
trap - EXIT HUP INT TERM

