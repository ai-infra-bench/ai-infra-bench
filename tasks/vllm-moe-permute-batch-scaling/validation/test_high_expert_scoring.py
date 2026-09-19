"""Check output semantics and representation freedom, independently of CUDA."""

from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
import trusted_high_experts as ref
from trusted_expected import REQUIRED_CASE_KEYS, expected_digests


def observation(experts, aligned, reverse=False):
    routes = ref.routes_for(experts)
    sources = sorted(range(len(routes)),
                     key=lambda source: (routes[source], -source if reverse else source))
    counts = [routes.count(expert) for expert in range(experts)]
    offsets = [0]
    for count in counts:
        width = ((count + ref.ALIGN - 1) // ref.ALIGN * ref.ALIGN
                 if aligned else count)
        offsets.append(offsets[-1] + width)
    cap = ref.capacity(experts, aligned)
    payload = bytearray(b"\xa5") * (cap * ref.ROW_BYTES)
    inverse = [-29] * len(routes)
    forward, mids = [len(routes)] * cap, [-1] * cap
    next_row = offsets[:-1].copy()
    for source in sources:
        expert = routes[source]
        row = next_row[expert]
        next_row[expert] += 1
        inverse[source], forward[row] = row, source
        token = source // ref.TOPK
        payload[row * ref.ROW_BYTES:(row + 1) * ref.ROW_BYTES] = struct.pack(
            f"<{ref.HIDDEN}e", *range(token * ref.HIDDEN, (token + 1) * ref.HIDDEN)
        )
    if aligned:
        for expert, count in enumerate(counts):
            if count:
                start, end = offsets[expert:expert + 2]
                mids[start:end] = [expert] * (end - start)
    return [payload, offsets, inverse, forward, mids]


class HighExpertScoringTests(unittest.TestCase):
    def test_first_middle_final_and_repeated_experts_receive_tokens(self):
        for experts in ref.EXPERT_COUNTS:
            routes = ref.routes_for(experts)
            self.assertEqual(len(routes), ref.TOKENS * ref.TOPK)
            self.assertTrue(all(0 <= expert < experts for expert in routes))
            self.assertTrue({0, experts // 4, experts // 2,
                             3 * experts // 4, experts - 2, experts - 1} <= set(routes))
            self.assertGreater(routes.count(experts - 1), 1)
            for start in range(0, len(routes), ref.TOPK):
                self.assertEqual(len(set(routes[start:start + ref.TOPK])), ref.TOPK)

    def test_different_valid_orders_have_the_same_observation(self):
        for experts in ref.EXPERT_COUNTS:
            for aligned in (False, True):
                for reverse in (False, True):
                    with self.subTest(experts=experts, aligned=aligned, reverse=reverse):
                        self.assertEqual(
                            ref.validate_outputs(experts, aligned,
                                                 *observation(experts, aligned, reverse)),
                            ref.expected_digest(experts, aligned),
                        )

    def test_high_expert_offsets_rejected(self):
        values = observation(1025, True)
        values[1][-2] -= ref.ALIGN
        with self.assertRaisesRegex(ValueError, "expert offsets"):
            ref.validate_outputs(1025, True, *values)

    def test_duplicate_destination_for_final_expert_rejected(self):
        values = observation(1025, False)
        sources = [i for i, expert in enumerate(ref.routes_for(1025)) if expert == 1024]
        values[2][sources[1]] = values[2][sources[0]]
        with self.assertRaisesRegex(ValueError, "inverse must fill"):
            ref.validate_outputs(1025, False, *values)

    def test_corrupted_final_expert_payload_rejected(self):
        values = observation(1025, True)
        row = values[2][ref.routes_for(1025).index(1024)]
        values[0][row * ref.ROW_BYTES] ^= 0x80
        with self.assertRaisesRegex(ValueError, "payload bytes"):
            ref.validate_outputs(1025, True, *values)

    def test_inconsistent_high_expert_forward_map_rejected(self):
        values = observation(1025, True)
        row = values[2][ref.routes_for(1025).index(1024)]
        values[3][row] = 0
        with self.assertRaisesRegex(ValueError, "round trip"):
            ref.validate_outputs(1025, True, *values)

    def test_padding_forward_sentinel_rejected(self):
        values = observation(1025, True)
        values[3][2] = 0  # The first expert has two payload rows, then padding.
        with self.assertRaisesRegex(ValueError, "padding forward sentinel"):
            ref.validate_outputs(1025, True, *values)

    def test_high_expert_range_and_tail_rejected(self):
        for tail in (False, True):
            values = observation(1025, True)
            row = values[1][-1] if tail else values[1][-2]
            values[4][row] = 0
            with self.assertRaisesRegex(ValueError, "aligned expert ranges"):
                ref.validate_outputs(1025, True, *values)

    def test_unused_storage_is_not_prescribed(self):
        for aligned in (False, True):
            values = observation(1025, aligned, reverse=True)
            occupied = set(values[2])
            for row in range(len(values[3])):
                if row not in occupied:
                    values[0][row * ref.ROW_BYTES:(row + 1) * ref.ROW_BYTES] = bytes(ref.ROW_BYTES)
            if not aligned:
                values[4][:] = [123] * len(values[4])
            self.assertEqual(ref.validate_outputs(1025, aligned, *values),
                             ref.expected_digest(1025, aligned))

    def test_all_high_expert_cases_are_required_by_parent(self):
        keys = {ref.case_key(experts, aligned) for experts in ref.EXPERT_COUNTS
                for aligned in (False, True)}
        self.assertEqual(len(keys), 8)
        self.assertTrue(keys <= set(REQUIRED_CASE_KEYS))
        self.assertTrue(keys <= set(expected_digests()))
        self.assertEqual(len(REQUIRED_CASE_KEYS), len(set(REQUIRED_CASE_KEYS)))


if __name__ == "__main__":
    unittest.main()
