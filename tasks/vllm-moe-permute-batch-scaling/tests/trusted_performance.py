"""Parent-side validation of measurements; never imports candidate code.

This checks completion and recomputes the public performance contract from
samples. It does not claim that self-reported samples prove kernel execution.
The isolated worker, native provenance and final-entrypoint controls are also
required. Rounding tolerance below only accommodates three-decimal JSON reports;
performance thresholds always use the unrounded sample medians.
"""

import math
import statistics

from trusted_expected import EXPECTED_TIMING_PROTOCOL

TIMED_KEYS = ("1", "32", "128", "512", "1024", "2048", "4096")
PROBE_KEYS = ("63", "3000")


def positive(value):
    return (type(value) in (int, float)
            and math.isfinite(value) and value > 0)


def validate_performance(payload):
    errors = []
    medians = {}
    protocol = payload.get("timing_protocol")
    if not isinstance(protocol, dict) or any(
        protocol.get(k) != v for k, v in EXPECTED_TIMING_PROTOCOL.items()
    ):
        errors.append("timing_protocol_mismatch")

    records = payload.get("timing_records")
    expected_keys = set(TIMED_KEYS + PROBE_KEYS)
    if not isinstance(records, dict) or set(records) != expected_keys:
        errors.append("timing_record_case_set_mismatch")
        records = records if isinstance(records, dict) else {}
    for key in expected_keys:
        record = records.get(key)
        if not isinstance(record, dict):
            errors.append(f"missing_record:{key}")
            continue
        if any(record.get(k) != v
               for k, v in EXPECTED_TIMING_PROTOCOL.items()):
            errors.append(f"record_protocol_mismatch:{key}")
        samples = record.get("samples_us")
        if (not isinstance(samples, list)
                or len(samples) != EXPECTED_TIMING_PROTOCOL["repeats"]
                or not all(positive(x) for x in samples)):
            errors.append(f"invalid_samples:{key}")
            continue
        medians[key] = statistics.median(samples)

    for field, keys in (("timings_median_us", TIMED_KEYS),
                        ("probe_median_us", PROBE_KEYS)):
        reported = payload.get(field)
        if not isinstance(reported, dict) or set(reported) != set(keys):
            errors.append(f"reported_case_set_mismatch:{field}")
            continue
        for key in keys:
            value = reported[key]
            if (not positive(value) or key not in medians
                    or not math.isclose(value, medians[key],
                                        rel_tol=1e-12, abs_tol=0.000501)):
                errors.append(f"reported_median_mismatch:{key}")

    ratio = None
    if "4096" in medians and "512" in medians:
        ratio = medians["4096"] / medians["512"]
        if medians["4096"] >= 250.0:
            errors.append("latency_4096_exceeds_contract")
        if ratio >= 3.5:
            errors.append("ratio_4096_over_512_exceeds_contract")
        reported_ratio = payload.get("large_batch_ratio_4096_over_512")
        if (not positive(reported_ratio)
                or not math.isclose(reported_ratio, ratio,
                                    rel_tol=1e-12, abs_tol=0.000501)):
            errors.append("reported_ratio_mismatch")

    # Non-public batch timings remain diagnostic. Their sample completeness is
    # checked, but the 4096-token numerical contract is not silently extended.
    return {"valid": not errors, "errors": sorted(errors),
            "recomputed_medians_us": medians,
            "recomputed_ratio_4096_over_512": ratio}
