import json
import multiprocessing as mp
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gpu_pool import Pool


def lease_worker(config, count, ready, release):
    with Pool(Path(config)).acquire(count, timeout=5) as selected:
        ready.put([index for index, _ in selected])
        release.wait(5)


class GpuPoolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self.root / "pool.json"
        self.config.write_text(json.dumps({
            "gpu_uuids": [f"GPU-00000000-0000-0000-0000-{i:012d}" for i in range(4)],
            "state_dir": str(self.root / "state"),
        }))
        self.pool = Pool(self.config)

    def worker(self, count):
        ready, release = mp.Queue(), mp.Event()
        worker = mp.Process(target=lease_worker, args=(str(self.config), count, ready, release))
        worker.start()
        def finish():
            if worker.is_alive():
                release.set()
            worker.join(3)
            if worker.is_alive():
                worker.kill()
                worker.join()
        self.addCleanup(finish)
        return worker, ready, release

    def test_four_single_card_jobs_have_distinct_devices(self):
        workers = [self.worker(1) for _ in range(4)]
        assignments = [ready.get(timeout=4)[0] for _, ready, _ in workers]
        self.assertEqual(set(assignments), {0, 1, 2, 3})
        with self.assertRaises(TimeoutError):
            with self.pool.acquire(1, timeout=0.2):
                self.fail("overlapping allocation")

    def test_two_two_card_jobs_fill_pool(self):
        workers = [self.worker(2) for _ in range(2)]
        assignments = [ready.get(timeout=4) for _, ready, _ in workers]
        self.assertEqual(set(assignments[0]) | set(assignments[1]), {0, 1, 2, 3})
        self.assertFalse(set(assignments[0]) & set(assignments[1]))

    def test_four_card_waiter_blocks_new_single_card_jobs(self):
        active, ready, release = self.worker(1)
        ready.get(timeout=4)
        large, large_ready, large_release = self.worker(4)
        deadline = time.monotonic() + 3
        while True:
            gate = self.pool._try_lock(self.pool.state / "admission.lock")
            if gate is None:
                break
            gate.close()
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.02)
        with self.assertRaises(TimeoutError):
            with self.pool.acquire(1, timeout=0.2):
                self.fail("small job bypassed draining four-card waiter")
        release.set()
        self.assertEqual(large_ready.get(timeout=4), [0, 1, 2, 3])

    def test_killed_holder_releases_file_locks(self):
        worker, ready, _ = self.worker(4)
        ready.get(timeout=4)
        worker.kill()
        worker.join()
        with self.pool.acquire(4, timeout=1) as selected:
            self.assertEqual(len(selected), 4)

    def test_invalid_counts_fail_without_waiting(self):
        for count in (0, 3, 5, 8):
            with self.subTest(count=count), self.assertRaises(ValueError):
                with self.pool.acquire(count):
                    self.fail("invalid request admitted")

    def test_exception_releases_lease(self):
        with self.assertRaises(RuntimeError):
            with self.pool.acquire(4):
                raise RuntimeError("simulated failure")
        with self.pool.acquire(4, timeout=1) as selected:
            self.assertEqual(len(selected), 4)

    def test_duplicate_device_configuration_is_rejected(self):
        data = json.loads(self.config.read_text())
        data["gpu_uuids"][1] = data["gpu_uuids"][0]
        self.config.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            Pool(self.config)

    def test_cancellation_terminates_child_before_releasing(self):
        # Fake Docker only for cleanup; real process and flock lifecycle.
        docker = self.root / "docker"
        docker.write_text("#!/bin/sh\nexit 0\n")
        docker.chmod(0o755)
        marker = self.root / "child.pid"
        script = Path(__file__).resolve().parents[1] / "gpu_pool.py"
        env = dict(os.environ, PATH=f"{self.root}:{os.environ['PATH']}")
        child_code = "import os,pathlib,time;pathlib.Path(%r).write_text(str(os.getpid()));time.sleep(60)" % str(marker)
        supervisor = subprocess.Popen(
            [sys.executable, str(script), "--config", str(self.config), "--count", "4", "--", sys.executable, "-c", child_code],
            env=env, stdout=subprocess.DEVNULL,
        )
        self.addCleanup(lambda: supervisor.poll() is None and supervisor.kill())
        deadline = time.monotonic() + 4
        while not marker.exists():
            self.assertIsNone(supervisor.poll())
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.02)
        child_pid = int(marker.read_text())
        supervisor.send_signal(signal.SIGTERM)
        self.assertEqual(supervisor.wait(timeout=5), 143)
        self.assertFalse(Path(f"/proc/{child_pid}").exists())
        with self.pool.acquire(4, timeout=1) as selected:
            self.assertEqual(len(selected), 4)

    def test_killing_supervisor_does_not_free_live_child_lease(self):
        docker = self.root / "docker"
        docker.write_text("#!/bin/sh\nexit 0\n")
        docker.chmod(0o755)
        marker = self.root / "inherited-child.pid"
        script = Path(__file__).resolve().parents[1] / "gpu_pool.py"
        child_code = "import os,pathlib,time;pathlib.Path(%r).write_text(str(os.getpid()));time.sleep(60)" % str(marker)
        supervisor = subprocess.Popen(
            [sys.executable, str(script), "--config", str(self.config), "--count", "4", "--", sys.executable, "-c", child_code],
            env=dict(os.environ, PATH=f"{self.root}:{os.environ['PATH']}"), stdout=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 4
            while not marker.exists():
                self.assertIsNone(supervisor.poll())
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.02)
            child_pid = int(marker.read_text())
            supervisor.kill()
            supervisor.wait()
            with self.assertRaises(TimeoutError):
                with self.pool.acquire(4, timeout=0.2):
                    self.fail("a live Harbor process lost its inherited GPU lease")
        finally:
            if supervisor.poll() is None:
                supervisor.kill()
                supervisor.wait()
            if marker.exists():
                try:
                    os.kill(int(marker.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass
        with self.pool.acquire(4, timeout=2) as selected:
            self.assertEqual(len(selected), 4)


if __name__ == "__main__":
    unittest.main()
