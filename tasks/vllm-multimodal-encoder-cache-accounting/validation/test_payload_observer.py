"""Observer regressions: aliasing, mutation, exclusion and real storage release."""
import ast
import gc
from pathlib import Path
import unittest
import torch
from torch.utils._python_dispatch import TorchDispatchMode
from torch.utils._pytree import tree_leaves

path = Path(__file__).resolve().parents[1] / 'tests/encoder_storage.py'
tree = ast.parse(path.read_text())
node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'PayloadStorage')
exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'))


class PayloadObserverTests(unittest.TestCase):
    def test_aliases_count_once_and_storage_owner_survives_tensor(self):
        observer = PayloadStorage()
        try:
            with observer:
                rows = torch.ones(8, 16)
                observer.mark([rows])
                alias = rows.transpose(0, 1)
                storage = alias.untyped_storage()
            self.assertEqual(observer.live_bytes(), 512)
            del rows, alias
            gc.collect()
            self.assertEqual(observer.live_bytes(), 512)
            del storage
            gc.collect()
            self.assertEqual(observer.live_bytes(), 0)
        finally:
            observer.close()

    def test_in_place_scatter_is_payload_but_masks_are_not(self):
        observer = PayloadStorage()
        try:
            with observer:
                mask = torch.arange(128) < 8
                rows = torch.ones(8, 16)
                observer.mark([rows])
                expanded = torch.zeros(128, 16)
                expanded[mask] = rows
            self.assertEqual(observer.live_bytes(), (8 + 128) * 16 * 4)
            del expanded
            gc.collect()
            self.assertEqual(observer.live_bytes(), 512)
        finally:
            observer.close()

    def test_preallocated_decoder_buffer_is_excluded(self):
        observer = PayloadStorage()
        try:
            with observer:
                buffer = torch.zeros(128, 16)
                observer.exclude_existing()
                rows = torch.ones(8, 16)
                observer.mark([rows])
                buffer[:8].copy_(rows)
            self.assertEqual(observer.live_bytes(), 512)
        finally:
            observer.close()

    def test_preallocated_payload_remains_visible(self):
        cache = torch.zeros(128, 16)
        observer = PayloadStorage()
        try:
            with observer:
                baseline = observer.baseline()
                rows = torch.ones(8, 16)
                observer.mark([rows])
                cache[:8].copy_(rows)
            self.assertEqual(observer.live_bytes(), (128 + 8) * 16 * 4)
            self.assertGreaterEqual(observer.live_bytes(include=baseline),
                                    (128 + 8) * 16 * 4)
        finally:
            observer.close()

    def test_sparse_values_and_index_resources(self):
        observer = PayloadStorage()
        try:
            with observer:
                rows = torch.ones(8, 16)
                observer.mark([rows])
                sparse = rows.to_sparse(1)
            del rows
            gc.collect()
            self.assertEqual(observer.live_bytes(), 512)
            self.assertEqual(observer.live_bytes(resources=True), 512 + 8 * 8)
            self.assertEqual(tuple(sparse.shape), (8, 16))
        finally:
            observer.close()


if __name__ == '__main__':
    unittest.main()
