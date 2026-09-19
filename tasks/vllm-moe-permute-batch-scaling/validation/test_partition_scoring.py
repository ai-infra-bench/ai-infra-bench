"""CPU checks of the EP observation validator; these are not native GPU runs."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
import trusted_partition as ref
from trusted_expected import REQUIRED_CASE_KEYS, expected_digests


def observation(name, aligned, reverse_ties=False):
    """Construct a valid grouping independently of the validator's reference."""
    routes = ref.routes_for(name)
    local = [(ref.EXPERT_MAP[expert], source) for source, expert in enumerate(routes)
             if ref.EXPERT_MAP[expert] >= 0]
    local.sort(key=lambda pair: (pair[0], -pair[1] if reverse_ties else pair[1]))
    cap = ref.capacity(aligned)
    payload = bytearray([0xA5] * (cap * ref.HIDDEN))
    offsets, inverse = [0], [-29] * len(routes)
    forward, mids = [len(routes)] * cap, [-1] * cap
    cursor = 0
    for expert in range(ref.LOCAL_EXPERTS):
        start = cursor
        for routed, source in local:
            if routed != expert:
                continue
            inverse[source] = cursor
            forward[cursor] = source
            payload[cursor * ref.HIDDEN:(cursor + 1) * ref.HIDDEN] = bytes(
                (37 * (source // ref.TOPK) + column) % 256 for column in range(ref.HIDDEN)
            )
            cursor += 1
        if aligned:
            cursor = start + ((cursor - start + ref.ALIGN - 1) // ref.ALIGN) * ref.ALIGN
            mids[start:cursor] = [expert] * (cursor - start)
        offsets.append(cursor)
    remote_sources = [source for source, expert in enumerate(routes) if ref.EXPERT_MAP[expert] == -1]
    if reverse_ties:
        remote_sources.reverse()
    for rank, source in enumerate(remote_sources):
        inverse[source] = cursor if aligned else cursor + rank
    return [payload, offsets, inverse, forward, mids]


class PartitionScoringTests(unittest.TestCase):
    def test_all_cases_accept_distinct_valid_orderings(self):
        for name in ref.PARTITION_CASES:
            for aligned in (False, True):
                for reverse in (False, True):
                    with self.subTest(name=name, aligned=aligned, reverse=reverse):
                        digest = ref.validate_partition_outputs(name, aligned, *observation(name, aligned, reverse))
                        self.assertEqual(digest, ref.expected_partition_digest(name, aligned))

    def test_every_payload_row_contains_all_encodings(self):
        raw = ref.payload_bytes()
        for row in range(ref.TOKENS):
            self.assertEqual(set(raw[row * ref.HIDDEN:(row + 1) * ref.HIDDEN]), set(range(256)))

    def test_corrupted_sign_bit_rejected(self):
        values = observation("all-local", True)
        values[0] = bytes(byte & 0x7F for byte in values[0])
        with self.assertRaisesRegex(ValueError, "local payload bytes"):
            ref.validate_partition_outputs("all-local", True, *values)

    def test_wrong_offsets_rejected(self):
        values = observation("mixed", True)
        values[1][-1] += 128
        with self.assertRaisesRegex(ValueError, "expert offsets"):
            ref.validate_partition_outputs("mixed", True, *values)

    def test_duplicate_local_destination_rejected(self):
        values = observation("all-local", False)
        values[2][2] = values[2][0]
        with self.assertRaisesRegex(ValueError, "local inverse"):
            ref.validate_partition_outputs("all-local", False, *values)

    def test_incorrect_skipped_destinations_rejected(self):
        for aligned in (False, True):
            values = observation("mixed", aligned)
            source = next(i for i, expert in enumerate(ref.routes_for("mixed")) if ref.EXPERT_MAP[expert] == -1)
            values[2][source] = -29
            with self.assertRaisesRegex(ValueError, "nonlocal inverse"):
                ref.validate_partition_outputs("mixed", aligned, *values)

    def test_copying_all_remote_routes_rejected(self):
        values = observation("all-remote", True)
        values[3][0] = 0
        with self.assertRaisesRegex(ValueError, "forward sentinel"):
            ref.validate_partition_outputs("all-remote", True, *values)

    def test_wrong_forward_and_aligned_ranges_rejected(self):
        for index, message in ((3, "round trip"), (4, "expert ranges")):
            values = observation("all-local", True)
            values[index][0] = -99
            with self.assertRaisesRegex(ValueError, message):
                ref.validate_partition_outputs("all-local", True, *values)

    def test_unused_payload_and_unaligned_mids_not_prescribed(self):
        values = observation("all-remote", False)
        values[0][:] = bytes(len(values[0]))
        values[4][:] = [123] * len(values[4])
        self.assertEqual(ref.validate_partition_outputs("all-remote", False, *values),
                         ref.expected_partition_digest("all-remote", False))

    def test_scoring_requires_all_40_cases(self):
        self.assertEqual(len(REQUIRED_CASE_KEYS), 40)
        self.assertEqual(set(REQUIRED_CASE_KEYS), set(expected_digests()))


if __name__ == "__main__":
    unittest.main()
