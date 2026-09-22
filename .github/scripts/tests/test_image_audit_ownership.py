"""Exercise the image audit with real Git, including its ownership guard."""

import argparse
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import task_ci


class ImageAuditOwnershipTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "repository with spaces"
        self.repo.mkdir()
        self.env = dict(os.environ, HOME=str(self.root), GIT_CONFIG_NOSYSTEM="1")
        self.env.pop("GIT_TEST_ASSUME_DIFFERENT_OWNER", None)
        self.real_run = subprocess.run
        self.git("init", "-q")
        self.git("config", "core.logAllRefUpdates", "false")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.org",
                 "commit", "--allow-empty", "-qm", "Base")
        self.head = self.git("rev-parse", "HEAD").stdout.strip()

    def git(self, *args):
        return self.real_run(["git", "-C", str(self.repo), *args],
                             env=self.env, check=True, capture_output=True, text=True)

    def audit(self, expected_head=None):
        # Only replace the Docker boundary. Run the production shell and Git
        # against a real repository; Git's test flag reproduces foreign ownership
        # without root privileges or chown on the test host.
        def docker(args, **kwargs):
            if args[:3] == ["docker", "image", "inspect"]:
                return subprocess.CompletedProcess(args, 0, stdout=json.dumps([{"Id": "fixture"}]))
            if args[:2] == ["docker", "run"]:
                return self.real_run(["bash", "-lc", args[-1]], check=True,
                                     capture_output=True, text=True,
                                     env=dict(self.env, GIT_TEST_ASSUME_DIFFERENT_OWNER="1"))
            raise AssertionError(f"Unexpected external command: {args[:3]}")

        config = {"metadata": {"base_commit": expected_head or self.head},
                  "environment": {"workdir": str(self.repo)}}
        with patch.object(task_ci, "task_contract", return_value=(config, {})), \
             patch.object(task_ci.subprocess, "run", side_effect=docker), \
             redirect_stdout(io.StringIO()):
            task_ci.command_image_check(argparse.Namespace(task="fixture", image="fixture"))

    def test_accepts_clean_repository_owned_by_agent(self):
        before = (self.repo / ".git/config").read_bytes()
        self.audit()
        self.assertEqual((self.repo / ".git/config").read_bytes(), before)
        self.assertFalse((self.root / ".gitconfig").exists())

    def test_rejects_dirty_repository_despite_allowed_ownership(self):
        (self.repo / "unexpected.txt").write_text("unreviewed")
        with self.assertRaises(subprocess.CalledProcessError):
            self.audit()

    def test_rejects_wrong_base_commit(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.audit("0" * 40)

    def test_rejects_retained_remote(self):
        self.git("remote", "add", "origin", "https://example.org/repo.git")
        with self.assertRaises(subprocess.CalledProcessError):
            self.audit()


if __name__ == "__main__":
    unittest.main()
