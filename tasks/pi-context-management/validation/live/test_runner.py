from types import SimpleNamespace
import threading
import unittest
from unittest.mock import patch
import run


class RunnerTests(unittest.TestCase):
    def trial(self):
        return SimpleNamespace(lock=threading.Lock(), events=[{'type':'request','phase':0}]*2)

    def test_exit_between_budget_observation_and_stop_does_not_signal(self):
        class Process:
            pid = 123
            returncode = 0
            polls = 0
            def poll(self):
                self.polls += 1
                return None if self.polls == 1 else 0
        with patch.object(run, 'MAX_REQUESTS', 1), patch.object(run.os, 'killpg') as kill:
            code, stop = run.wait_phase(Process(), 0, self.trial())
        self.assertEqual(code, 0)
        self.assertIsNone(stop)
        kill.assert_not_called()

    def test_budget_stop_is_bound_to_original_phase_process(self):
        class Process:
            pid = 456
            returncode = None
            def poll(self): return self.returncode
            def wait(self, timeout): self.returncode = -15; return -15
        with patch.object(run, 'MAX_REQUESTS', 1), patch.object(run.os, 'killpg') as kill:
            code, stop = run.wait_phase(Process(), 0, self.trial())
        self.assertEqual(code, -1)
        self.assertEqual(stop['phase'], 0)
        self.assertEqual(stop['reason'], 'request_budget')
        kill.assert_called_once_with(456, run.signal.SIGTERM)

    def test_prior_phase_requests_do_not_exhaust_next_phase_budget(self):
        class Process:
            pid = 789
            returncode = 0
            polls = 0
            def poll(self):
                self.polls += 1
                return None if self.polls == 1 else 0
        with patch.object(run, 'MAX_REQUESTS', 1), patch.object(run.time, 'sleep'), patch.object(run.os, 'killpg') as kill:
            code, stop = run.wait_phase(Process(), 1, self.trial())
        self.assertEqual(code, 0)
        self.assertIsNone(stop)
        kill.assert_not_called()


if __name__ == '__main__': unittest.main()
