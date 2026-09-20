"""Exercise submission collectors against real Git repositories and tar files."""

import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tools"))
spec = importlib.util.spec_from_file_location(
    "sync_collect_hooks", REPO_ROOT / "tools/sync_collect_hooks.py"
)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class CollectionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.repo = self.root / "repo with ' quotes"
        self.output = self.root / "archive with spaces"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Collector test")
        self.git("config", "user.email", "collector@example.invalid")
        for name, content in {
            "base.txt": b"original\n",
            "deleted.txt": b"delete me\n",
            "renamed.txt": b"rename me\n",
            "binary.dat": b"\x00original\xff",
            "script.sh": b"#!/bin/sh\necho original\n",
            ".gitignore": b"ignored.log\n",
        }.items():
            (self.repo / name).write_bytes(content)
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD").decode().strip()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], stderr=subprocess.PIPE)

    def collect(self, *, base=None, extra_env=None):
        return subprocess.run(
            ["sh", "-c", collector.render_command(str(self.repo), base or self.base, str(self.output))],
            env={**os.environ, **(extra_env or {})},
            capture_output=True,
            text=True,
            timeout=30,
        )

    @staticmethod
    def files(root):
        result = {}
        for path in root.rglob("*"):
            rel = path.relative_to(root)
            if ".git" in rel.parts or rel.as_posix() == "ignored.log":
                continue
            if path.is_symlink():
                result[rel.as_posix()] = ("symlink", os.readlink(path))
            elif path.is_file():
                result[rel.as_posix()] = (path.read_bytes(), bool(path.stat().st_mode & 0o111))
        return result

    def test_round_trip_committed_staged_unstaged_and_untracked_changes(self):
        (self.repo / "base.txt").write_text("committed change\n")
        (self.repo / "committed-new.txt").write_text("new committed file\n")
        self.git("mv", "renamed.txt", "renamed now.txt")
        self.git("rm", "-q", "deleted.txt")
        self.git("add", ".")
        self.git("commit", "-qm", "agent commit")
        (self.repo / "staged.txt").write_text("staged content\n")
        (self.repo / "empty.txt").touch()
        (self.repo / "binary.dat").write_bytes(b"\x00updated\xfe\x80")
        self.git("add", ".")
        (self.repo / "staged.txt").write_text("unstaged update to staged file\n")
        (self.repo / "base.txt").write_text("final unstaged content\n")
        self.git("config", "core.filemode", "false")
        (self.repo / "script.sh").chmod(0o755)
        for name in ("new space.txt", "quote'file.txt", "line\nbreak.txt", "-leading.txt", "新增.bin"):
            (self.repo / name).write_bytes(b"\x00untracked\xff")
        (self.repo / "subdir").mkdir()
        (self.repo / "subdir/new.txt").write_text("nested\n")
        (self.repo / "untracked-link").symlink_to("base.txt")
        (self.repo / "ignored.log").write_text("retained only by the full workspace snapshot\n")
        index_before = (self.repo / ".git/index").read_bytes()
        head_before = self.git("rev-parse", "HEAD")

        result = self.collect()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.output / "collection-status.txt").read_text(), "complete\n")
        self.assertEqual((self.output / "base-commit.txt").read_text().strip(), self.base)
        self.assertEqual((self.output / "head-commit.txt").read_bytes(), head_before)
        self.assertEqual((self.repo / ".git/index").read_bytes(), index_before)
        self.assertEqual(self.git("rev-parse", "HEAD"), head_before)

        restored = self.root / "restored"
        restored.mkdir()
        with tarfile.open(fileobj=io.BytesIO(self.git("archive", self.base))) as archive:
            archive.extractall(restored, filter="fully_trusted")
        subprocess.run(
            ["git", "-C", str(restored), "apply", "--binary", str(self.output / "solution.patch")],
            check=True, capture_output=True,
        )
        with tarfile.open(self.output / "untracked-files.tar.gz") as archive:
            self.assertNotIn("ignored.log", archive.getnames())
            self.assertIn("line\nbreak.txt", archive.getnames())
            archive.extractall(restored, filter="fully_trusted")
        self.assertEqual(self.files(restored), self.files(self.repo))

    def test_clean_checkout_produces_empty_but_valid_outputs(self):
        result = self.collect()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.output / "solution.patch").read_bytes(), b"")
        self.assertEqual((self.output / "untracked-paths.bin").read_bytes(), b"")
        with tarfile.open(self.output / "untracked-files.tar.gz") as archive:
            self.assertEqual(archive.getnames(), [])
        self.assertEqual((self.output / "collection-status.txt").read_text(), "complete\n")

    def test_missing_base_is_reported_without_changing_checkout(self):
        before = self.files(self.repo)
        result = self.collect(base="0" * 40)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.output / "collection-status.txt").read_text().startswith("failed exit="))
        self.assertFalse((self.output / "solution.patch").exists())
        self.assertEqual(self.files(self.repo), before)
        self.assertEqual(list(self.output.glob(".collect.*")), [])

    def test_external_diff_and_inherited_git_paths_do_not_change_collection(self):
        marker = self.root / "external-helper-ran"
        helper = self.root / "external.sh"
        helper.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 99\n")
        helper.chmod(0o755)
        self.git("config", "diff.external", str(helper))
        self.git("config", "diff.candidate.textconv", str(helper))
        self.git("config", "color.ui", "always")
        self.git("config", "core.fsmonitor", str(helper))
        (self.repo / ".gitattributes").write_text("base.txt diff=candidate\n")
        (self.repo / "base.txt").write_text("updated\n")
        result = self.collect(extra_env={
            "GIT_DIR": str(self.root / "absent"),
            "GIT_WORK_TREE": str(self.root / "wrong"),
            "GIT_INDEX_FILE": str(self.root / "wrong-index"),
            "GIT_EXTERNAL_DIFF": str(helper),
            "TAR_OPTIONS": "--exclude=*",
            "GZIP": "invalid-option",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())
        self.assertIn("+updated", (self.output / "solution.patch").read_text())
        self.assertNotIn(b"\x1b[", (self.output / "solution.patch").read_bytes())
        with tarfile.open(self.output / "untracked-files.tar.gz") as archive:
            self.assertIn(".gitattributes", archive.getnames())

    def test_checked_in_hooks_are_current_and_have_independent_timeouts(self):
        paths = sorted((REPO_ROOT / "tasks").glob("*/task.toml"))
        self.assertTrue(paths, "the benchmark corpus must not be empty")
        paths.append(REPO_ROOT / "templates/harbor-task/task.toml")
        for path in paths:
            with self.subTest(path=path):
                text = path.read_text()
                config = tomllib.loads(text)
                self.assertEqual(collector.updated_config(text, template="templates" in path.parts), text)
                hook, = config["verifier"]["collect"]
                self.assertEqual(hook["timeout_sec"], 300)
                self.assertEqual(hook["service"], "main")
                self.assertEqual(hook["user"], config["agent"]["user"])
                self.assertEqual(config["verifier"]["timeout_sec"], 7200)
                self.assertNotIn("environment_mode", config["verifier"])


if __name__ == "__main__":
    unittest.main()
