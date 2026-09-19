"""Check that reference fixtures exercise the promised output behaviors."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from reference import AmbiguousReference, build_reference


class ReferenceWorkloadTests(unittest.TestCase):
    def test_unsuitable_weights_are_retryable_before_candidate_execution(self):
        # Captured from a failed fixture construction during independent review.
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(AmbiguousReference, "stop-reason refresh"):
                build_reference(Path(directory), 2651101967022555681)

    def test_multitoken_lengths_text_and_budget_do_not_depend_on_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            workload, expected = build_reference(Path(directory), 686053689780348139)
        self.assertEqual(len(workload["cases"]), 19)
        self.assertEqual({len(item["tokens"]) for item in expected["single_multitoken"]},
                         {4})
        for name in ("multitoken_burst", "multitoken_delayed", "multitoken_include_stop"):
            for item in expected[name]:
                self.assertGreaterEqual(item["segments"][0]["length"], 3)
                self.assertTrue(all(segment["reason"] == "stop"
                                    for segment in item["segments"]))
                self.assertLess(len(item["tokens"]), workload["cases"][name]["budget"])
                self.assertTrue(item["text"])
        without_stop = {tuple(item["tokens"]): item["text"]
                        for item in expected["multitoken_delayed"]}
        with_stop = {tuple(item["tokens"]): item["text"]
                     for item in expected["multitoken_include_stop"]}
        self.assertEqual(without_stop.keys(), with_stop.keys())
        for tokens in without_stop:
            self.assertNotEqual(without_stop[tokens], with_stop[tokens])
        self.assertTrue(expected["ordinary_before"][0]["text"])


if __name__ == "__main__":
    unittest.main()
