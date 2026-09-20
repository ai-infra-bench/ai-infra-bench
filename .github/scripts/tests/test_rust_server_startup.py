"""Server startup must notice an address already delivered in the pipe."""

import importlib.util
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
TESTS = ROOT / "tasks/vllm-rust-tool-entity-preservation/tests"
saved_support = sys.modules.pop("verifier_support", None)
sys.path.insert(0, str(TESTS))
try:
    spec = importlib.util.spec_from_file_location("rust_opencode", TESTS / "test_real_opencode_edit.py")
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)
finally:
    sys.path.remove(str(TESTS))
    sys.modules.pop("verifier_support", None)
    if saved_support is not None:
        sys.modules["verifier_support"] = saved_support


class ServerStartupTests(unittest.TestCase):
    def read_address(self, script):
        process = subprocess.Popen(
            [sys.executable, "-u", "-c", script], stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        server = object.__new__(harness.VllmServer)
        server.process, server.output = process, []
        clock = time.monotonic
        try:
            # Keep production's 120-second budget while making timeout cases
            # finish in two seconds. The child remains alive without more output.
            with patch.object(harness.time, "monotonic", side_effect=lambda: clock() * 60):
                return server._read_address()
        finally:
            process.terminate()
            process.communicate(timeout=5)

    def test_address_in_the_same_write_as_the_test_header(self):
        address = self.read_address(
            'import os,time; os.write(1, b"running 1 test\\nAI_INFRA_VLLM_SERVER=http://127.0.0.1:12345/v1\\n"); time.sleep(5)'
        )
        self.assertEqual(address, "http://127.0.0.1:12345/v1")

    def test_address_split_across_pipe_writes(self):
        address = self.read_address(
            'import os,time; os.write(1, b"running 1 test\\nAI_INFRA_VLLM_SER"); time.sleep(0.05); '
            'os.write(1, b"VER=http://127.0.0.1:12345/v1\\n"); time.sleep(5)'
        )
        self.assertEqual(address, "http://127.0.0.1:12345/v1")

    def test_unfinished_line_still_obeys_startup_timeout(self):
        with self.assertRaisesRegex(AssertionError, "timed out starting vLLM server: starting"):
            self.read_address('import os,time; os.write(1, b"starting"); time.sleep(5)')


if __name__ == "__main__":
    unittest.main()
