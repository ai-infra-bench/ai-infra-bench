"""Observer regressions: aliasing, mutation, exclusion and real storage release."""
import ast
import gc
from pathlib import Path
import unittest
import torch
from torch.utils._python_dispatch import TorchDispatchMode
from torch.utils._pytree import tree_leaves

path = Path(__file__).resolve().parents[2] / 'tests/encoder_storage.py'
tree = ast.parse(path.read_text())
node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'PayloadStorage')
exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'))


class PayloadObserverTests(unittest.TestCase):
    def test_template_factories_do_not_copy_payload_provenance(self):
        factories = {
            'empty': lambda rows, n: torch.empty(n, dtype=torch.bool, device=rows.device),
            'new_empty': lambda rows, n: rows.new_empty((n,), dtype=torch.bool),
            'new_empty_strided': lambda rows, n: rows.new_empty_strided((n,), (1,), dtype=torch.bool),
            'new_zeros': lambda rows, n: rows.new_zeros((n,), dtype=torch.bool),
            'new_ones': lambda rows, n: rows.new_ones((n,), dtype=torch.bool),
            'new_full': lambda rows, n: rows.new_full((n,), False, dtype=torch.bool),
        }
        for name, factory in factories.items():
            for length in (16, 128, 4096):
                with self.subTest(factory=name, length=length):
                    observer = PayloadStorage()
                    try:
                        with observer:
                            rows = torch.ones(8, 16)
                            observer.mark([rows])
                            source_mask = torch.arange(length) < 8
                            mask = factory(rows, length)
                            mask.copy_(source_mask)
                            # Frozen position objects may keep the same Tensor
                            # while adopting equivalent new backing storage.
                            source_mask.set_(mask)
                        self.assertEqual(observer.live_bytes(), 512)
                        self.assertEqual(observer.live_bytes(resources=True), 512)
                        self.assertTrue(torch.equal(mask, torch.arange(length) < 8))
                    finally:
                        observer.close()

    def test_like_factories_are_metadata_but_copies_are_payload(self):
        factories = (torch.empty_like, torch.zeros_like, torch.ones_like,
                     lambda rows: torch.full_like(rows, 7), torch.rand_like,
                     torch.randn_like, lambda rows: torch.randint_like(rows, 0, 2))
        for factory in factories:
            with self.subTest(factory=factory):
                observer = PayloadStorage()
                try:
                    with observer:
                        rows = torch.ones(8, 16)
                        observer.mark([rows])
                        other = factory(rows)
                    self.assertEqual(observer.live_bytes(), 512)
                    with observer:
                        other.copy_(rows)
                    self.assertEqual(observer.live_bytes(), 1024)
                finally:
                    observer.close()

    def test_template_allocation_becomes_payload_when_values_are_copied(self):
        for factory in (lambda rows: rows.new_empty((128, 16)),
                        lambda rows: rows.new_zeros((128, 16))):
            observer = PayloadStorage()
            try:
                with observer:
                    rows = torch.ones(8, 16)
                    observer.mark([rows])
                    expanded = factory(rows)
                    expanded[:8].copy_(rows)
                self.assertEqual(observer.live_bytes(), (8 + 128) * 16 * 4)
            finally:
                observer.close()

    def test_integer_payload_is_not_exempted_as_metadata(self):
        observer = PayloadStorage()
        try:
            with observer:
                rows = torch.ones(8, 16, dtype=torch.uint8)
                observer.mark([rows])
                copied = rows.clone()
            self.assertEqual(observer.live_bytes(), 256)
        finally:
            observer.close()

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
