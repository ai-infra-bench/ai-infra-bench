"""CI snapshot compaction must preserve every trial's logical filesystem."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compact_task_artifacts import deduplicate, package


class SnapshotCompactionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.results = self.root / "task-results"
        self.index = self.results / ".snapshot-index.json"

    def file(self, job, name, content=b"unchanged content", mode=0o644, mtime=1700000000000000000):
        path = self.results / job / "trial/artifacts/workspace/repo" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(mode)
        os.utime(path, ns=(mtime, mtime))
        return path

    def dedupe(self, job):
        return deduplicate(self.results / job, self.index, "/workspace/repo")

    def test_identical_files_share_storage_without_changing_content_or_metadata(self):
        first = self.file("base", ".git/objects/pack/base.pack", b"x" * 65536)
        self.assertEqual(self.dedupe("base")["files_linked"], 0)
        second = self.file("oracle", ".git/objects/pack/base.pack", b"x" * 65536)
        before = second.stat()
        summary = self.dedupe("oracle")
        self.assertEqual(summary["files_linked"], 1)
        self.assertEqual(summary["duplicate_bytes"], 65536)
        self.assertTrue(os.path.samefile(first, second))
        after = second.stat()
        self.assertEqual(second.read_bytes(), b"x" * 65536)
        for attribute in ("st_mode", "st_uid", "st_gid", "st_mtime_ns"):
            self.assertEqual(getattr(before, attribute), getattr(after, attribute))
        self.assertEqual(self.dedupe("oracle")["files_linked"], 0)

    def test_changed_content_permissions_or_mtime_are_not_merged(self):
        first = self.file("base", "source.py")
        self.dedupe("base")
        changed = [
            self.file("different", "source.py", b"modified content!"),
            self.file("executable", "source.py", mode=0o755),
            self.file("newer", "source.py", mtime=1700000000000000001),
        ]
        for job in ("different", "executable", "newer"):
            self.assertEqual(self.dedupe(job)["files_linked"], 0)
        self.assertTrue(all(not os.path.samefile(first, path) for path in changed))

    def test_distinct_paths_remain_independent_within_each_snapshot(self):
        for job in ("base", "oracle"):
            first = self.file(job, "first.py")
            second = self.file(job, "second.py")
            self.dedupe(job)
            self.assertFalse(os.path.samefile(first, second))

    def test_symlinks_and_live_convention_directory_are_not_deduplicated(self):
        first = self.file("base", "same.txt")
        self.dedupe("base")
        second = self.file("oracle", "same.txt")
        outside = self.root / "outside"
        outside.mkdir()
        external = outside / "external.txt"
        external.write_bytes(b"unchanged content")
        (second.parent / "linked-directory").symlink_to(outside, target_is_directory=True)
        (second.parent / "linked-file").symlink_to(external)
        live = self.results / "oracle/trial/artifacts/logs/artifacts/status.txt"
        live.parent.mkdir(parents=True)
        live.write_bytes(first.read_bytes())
        os.utime(live, ns=(first.stat().st_mtime_ns, first.stat().st_mtime_ns))
        summary = self.dedupe("oracle")
        self.assertEqual(summary["files_checked"], 1)
        self.assertTrue((second.parent / "linked-file").is_symlink())
        self.assertFalse(os.path.samefile(first, external))
        self.assertFalse(os.path.samefile(first, live))

    def test_link_failure_keeps_original_snapshot(self):
        self.file("base", "source.py")
        self.dedupe("base")
        second = self.file("oracle", "source.py")
        with patch("compact_task_artifacts.os.link", side_effect=PermissionError("test")):
            with self.assertRaises(PermissionError):
                self.dedupe("oracle")
        self.assertEqual(second.read_bytes(), b"unchanged content")
        self.assertEqual(list(second.parent.glob(".snapshot-link-*")), [])

    def test_pack_round_trip_preserves_all_trials_hidden_files_and_links(self):
        for job in ("base", "oracle", "control"):
            self.file(job, ".git/objects/pack/base.pack", bytes(range(256)) * 1024)
            self.file(job, "new file\nwith spaces.txt", b"same untracked file")
            self.file(job, "candidate.py", job.encode())
            self.dedupe(job)
            (self.results / job / "result.json").write_text(json.dumps({"case": job}))
        source = self.results / "oracle/trial/artifacts/workspace/repo"
        (source / "symlink").symlink_to("candidate.py")
        archive_path = self.root / "uploads/results.tar.gz"
        with redirect_stdout(io.StringIO()):
            self.assertTrue(package(self.results, archive_path))
        restored = self.root / "restored"
        with tarfile.open(archive_path) as archive:
            self.assertTrue(any(member.islnk() for member in archive.getmembers()))
            self.assertIn("task-results/.snapshot-index.json", archive.getnames())
            archive.extractall(restored, filter="fully_trusted")
        for original in self.results.rglob("*"):
            extracted = restored / "task-results" / original.relative_to(self.results)
            if original.is_symlink():
                self.assertTrue(extracted.is_symlink())
                self.assertEqual(os.readlink(extracted), os.readlink(original))
            elif original.is_file():
                self.assertEqual(extracted.read_bytes(), original.read_bytes())
                self.assertEqual(extracted.stat().st_mode, original.stat().st_mode)
        a = restored / "task-results/base/trial/artifacts/workspace/repo/.git/objects/pack/base.pack"
        b = restored / "task-results/oracle/trial/artifacts/workspace/repo/.git/objects/pack/base.pack"
        self.assertTrue(os.path.samefile(a, b))

    def test_missing_results_do_not_create_a_misleading_archive(self):
        output = self.root / "absent.tar.gz"
        with redirect_stdout(io.StringIO()):
            self.assertFalse(package(self.results, output))
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
