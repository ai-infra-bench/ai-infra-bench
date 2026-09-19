"""CPU regression tests of the parent measurement validator, not GPU evidence."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from trusted_expected import EXPECTED_TIMING_PROTOCOL
from trusted_performance import PROBE_KEYS, TIMED_KEYS, validate_performance


def complete_observation():
    medians = {k: 50.0 for k in TIMED_KEYS + PROBE_KEYS}
    medians["4096"] = 130.0
    return {
        "timing_protocol": dict(EXPECTED_TIMING_PROTOCOL),
        "timing_records": {
            k: {**EXPECTED_TIMING_PROTOCOL, "samples_us": [v] * 5}
            for k, v in medians.items()
        },
        "timings_median_us": {k: medians[k] for k in TIMED_KEYS},
        "probe_median_us": {k: medians[k] for k in PROBE_KEYS},
        "large_batch_ratio_4096_over_512": 2.6,
    }


class PerformanceScoringTests(unittest.TestCase):
    def test_complete_measurement(self):
        self.assertTrue(validate_performance(complete_observation())["valid"])

    def test_empty_missing_and_extra_records(self):
        for change in (lambda r: r.clear(), lambda r: r.pop("4096"),
                       lambda r: r.update({"8192": r["4096"]})):
            p = complete_observation()
            change(p["timing_records"])
            self.assertFalse(validate_performance(p)["valid"])

    def test_invalid_samples(self):
        for samples in ([], [50.0] * 4, [50.0] * 6,
                        [float("nan")] * 5, [float("inf")] * 5,
                        [True] * 5, [0.0] * 5, [-1.0] * 5):
            with self.subTest(samples=samples):
                p = complete_observation()
                p["timing_records"]["512"]["samples_us"] = samples
                self.assertFalse(validate_performance(p)["valid"])

    def test_protocol_per_record_and_global(self):
        for per_record in (True, False):
            p = complete_observation()
            protocol = (p["timing_records"]["4096"] if per_record
                        else p["timing_protocol"])
            protocol["timed_iters"] = 20
            self.assertFalse(validate_performance(p)["valid"])

    def test_recomputes_thresholds_instead_of_trusting_pass(self):
        for large, small in ((250.0, 100.0), (175.0, 50.0), (9999.0, 1.0)):
            p = complete_observation()
            for key, value in (("4096", large), ("512", small)):
                p["timing_records"][key]["samples_us"] = [value] * 5
                p["timings_median_us"][key] = value
            p["large_batch_ratio_4096_over_512"] = large / small
            p["verdict"] = "PASS"
            self.assertFalse(validate_performance(p)["valid"])

    def test_false_reported_median_and_ratio(self):
        for field, key in (("timings_median_us", "4096"),
                           ("probe_median_us", "63")):
            p = complete_observation()
            p[field][key] = 1.0
            self.assertFalse(validate_performance(p)["valid"])
        p = complete_observation()
        p["large_batch_ratio_4096_over_512"] = 1.0
        self.assertFalse(validate_performance(p)["valid"])

    def test_diagnostic_probe_does_not_add_hidden_threshold(self):
        p = complete_observation()
        p["timing_records"]["3000"]["samples_us"] = [9999.0] * 5
        p["probe_median_us"]["3000"] = 9999.0
        self.assertTrue(validate_performance(p)["valid"])


if __name__ == "__main__":
    unittest.main()
