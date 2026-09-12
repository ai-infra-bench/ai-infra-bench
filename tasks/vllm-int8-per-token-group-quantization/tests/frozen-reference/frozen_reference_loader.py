# SPDX-License-Identifier: Apache-2.0
"""Loader for the frozen INT8 Triton reference baseline.

The frozen reference (``reference_int8_utils.py``) is a BYTE-IDENTICAL copy of
``vllm/model_executor/layers/quantization/utils/int8_utils.py`` at the task's base
commit. Keeping it byte-identical is what makes its SHA-256 verifiable against real
upstream git history, so the performance baseline cannot be silently redefined.

Because it is byte-identical, it carries two file-level ``vllm.*`` imports:

    from vllm.platforms import current_platform
    from vllm.triton_utils import tl, triton

Importing those from the candidate's tree would let the candidate influence the
baseline it is measured against. This loader therefore installs minimal, root-owned
stub modules in ``sys.modules`` BEFORE executing the frozen code, so nothing is
resolved from ``/workspace/repo``:

  * ``vllm.triton_utils`` re-exports the real upstream ``triton`` / ``triton.language``
  * ``vllm.platforms.current_platform`` answers the only import-time query the frozen
    module makes (``is_rocm()``), plus ``get_device_name()`` used by cache config lookup

The stubs live here, in verifier infrastructure, and never inside the frozen reference.
"""

import os
import sys
import types

FROZEN_DIR = os.path.dirname(os.path.abspath(__file__))
FROZEN_REFERENCE = os.path.join(FROZEN_DIR, "reference_int8_utils.py")

# SHA-256 of the byte-identical base-commit copy of int8_utils.py.
EXPECTED_SHA256 = "36406a44b95e54cf99988105d0fe9a69645a0d2fcbfe2e60b1982d3ac9fdcff3"


def _verify_frozen_reference() -> None:
    """Fail closed unless the frozen reference matches its recorded SHA-256."""
    import hashlib

    with open(FROZEN_REFERENCE, "rb") as handle:
        actual = hashlib.sha256(handle.read()).hexdigest()
    if actual != EXPECTED_SHA256:
        raise RuntimeError(
            "frozen reference SHA-256 mismatch: expected "
            f"{EXPECTED_SHA256}, got {actual}"
        )


def _install_stub_modules() -> None:
    """Install minimal vllm.* stubs so the frozen module imports nothing candidate-owned."""
    import triton
    import triton.language as tl

    vllm_pkg = sys.modules.get("vllm")
    if vllm_pkg is None:
        vllm_pkg = types.ModuleType("vllm")
        vllm_pkg.__path__ = []  # namespace-like, no filesystem search path
        sys.modules["vllm"] = vllm_pkg

    triton_utils = types.ModuleType("vllm.triton_utils")
    triton_utils.triton = triton
    triton_utils.tl = tl
    sys.modules["vllm.triton_utils"] = triton_utils
    vllm_pkg.triton_utils = triton_utils

    class _FrozenBaselinePlatform:
        """Answers only the queries the frozen reference makes at import/config time."""

        @staticmethod
        def is_rocm() -> bool:
            return False

        @staticmethod
        def get_device_name() -> str:
            try:
                import torch

                if torch.cuda.is_available():
                    return torch.cuda.get_device_name(0)
            except Exception:
                pass
            return "frozen-baseline-cpu"

    platforms = types.ModuleType("vllm.platforms")
    platforms.current_platform = _FrozenBaselinePlatform()
    sys.modules["vllm.platforms"] = platforms
    vllm_pkg.platforms = platforms


def load_frozen_reference():
    """Return the frozen reference module with candidate code excluded from sys.path.

    Callers MUST run this in a dedicated subprocess: it mutates ``sys.path`` and
    ``sys.modules`` for the remainder of the process (see the cleanup note below).
    Stripping ``/workspace/repo`` from ``sys.path`` is what guarantees an ``import``
    inside the frozen module can never resolve to candidate-authored files.
    """
    _verify_frozen_reference()

    # NOTE ON CLEANUP: this function deliberately does NOT restore ``sys.modules``.
    # Triton keeps process-global state (``triton.runtime.driver.DriverConfig`` holds a
    # lazily-initialised driver). Purging ``triton`` from ``sys.modules`` after load
    # makes later kernel launches re-import a second, uninitialised DriverConfig, which
    # fails with "target must be of GPUTarget type". The ``vllm.*`` stubs must persist
    # too: the frozen module calls ``current_platform.get_device_name()`` lazily from
    # its config lookup. This loader is therefore only valid in a dedicated subprocess,
    # which is how the verifier invokes it.
    sys.path = [
        entry
        for entry in sys.path
        if entry and not os.path.abspath(entry).startswith("/workspace/repo")
    ]
    sys.path.insert(0, FROZEN_DIR)
    _install_stub_modules()

    module = types.ModuleType("frozen_int8_reference")
    module.__file__ = FROZEN_REFERENCE
    with open(FROZEN_REFERENCE, "r", encoding="utf-8") as handle:
        source = handle.read()
    exec(compile(source, FROZEN_REFERENCE, "exec"), module.__dict__)
    return module


if __name__ == "__main__":
    mod = load_frozen_reference()
    fn = getattr(mod, "per_token_group_quant_int8", None)
    if fn is None:
        raise SystemExit("frozen reference does not expose per_token_group_quant_int8")
    print("frozen reference loaded OK:", FROZEN_REFERENCE)
