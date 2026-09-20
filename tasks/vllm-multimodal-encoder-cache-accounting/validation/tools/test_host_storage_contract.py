"""Allocation-policy invariants for the host-memory behavior comparison."""
import copy
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[2] / 'tests/host_storage_contract.py'
spec = importlib.util.spec_from_file_location('host_contract', path)
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


def observations(initial=lambda width, rows: 0, growth=lambda width, rows, n: 0):
    return {'widths': [16, 256], 'spans': [32, 4096],
            'retained_bytes': [[0, 0], [0, 0]], 'row_counts': [4, 8],
            'checkpoints': [4, 16, 32], 'completed_requests': 32,
            'lifecycle_bytes': [[[initial(width, rows) + growth(width, rows, n)
                                 for n in (4, 16, 32)] for rows in (4, 8)]
                               for width in (16, 256)]}


class HostComparisonTests(unittest.TestCase):
    def test_lazy_bounded_position_history_is_accepted(self):
        result = observations(growth=lambda width, rows, n: min(n, 64) * 8192)
        self.assertIsNone(contract.host_storage_failure(result))

    def test_width_dependent_bookkeeping_is_only_diagnostic(self):
        result = observations(growth=lambda width, rows, n: min(n, 64) * 8192 * width)
        signals = contract.host_storage_diagnostics(result)
        self.assertGreater(signals['width_growth_by_row_count_bytes'][0][-1], 1 << 20)
        self.assertEqual(signals['row_width_interaction_bytes'], [0, 0, 0])
        self.assertIsNone(contract.host_storage_failure(result))

    def test_row_dependent_bookkeeping_is_only_diagnostic(self):
        result = observations(growth=lambda width, rows, n: n * rows * 32768)
        self.assertIsNone(contract.host_storage_failure(result))

    def test_fixed_buffers_cannot_mask_real_payload_accumulation(self):
        leak = lambda width, rows, n: max(0, n - 2) * rows * width * 4
        small = observations(growth=leak)
        large = observations(initial=lambda width, rows: (1 << 28) + width * rows * 19,
                             growth=leak)
        self.assertIsNotNone(contract.host_storage_failure(small))
        self.assertEqual(contract.host_storage_diagnostics(small),
                         contract.host_storage_diagnostics(large))
        self.assertIsNotNone(contract.host_storage_failure(large))

    def test_pool_filled_after_first_checkpoint_can_stabilize(self):
        result = observations(growth=lambda width, rows, n: (n >= 8) * rows * width * 100)
        self.assertIsNone(contract.host_storage_failure(result))

    def test_signed_intervals_preserve_the_comparison(self):
        positive = observations(initial=lambda width, rows: 1000000,
                                growth=lambda width, rows, n: n * width)
        signed = copy.deepcopy(positive)
        for width in signed['lifecycle_bytes']:
            for curve in width:
                curve[:] = [value - (1 << 26) for value in curve]
        self.assertEqual(contract.host_storage_diagnostics(positive),
                         contract.host_storage_diagnostics(signed))
        self.assertIsNone(contract.host_storage_failure(signed))

    def test_missing_cell_cannot_count_as_completed_comparison(self):
        result = observations()
        result['lifecycle_bytes'][1].pop()
        with self.assertRaises(ValueError):
            contract.host_storage_failure(result)

    def test_boolean_is_not_a_byte_observation(self):
        result = observations()
        result['lifecycle_bytes'][0][0][0] = False
        with self.assertRaises(ValueError):
            contract.host_storage_failure(result)


if __name__ == '__main__':
    unittest.main()
