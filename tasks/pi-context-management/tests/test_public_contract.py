"""Public configuration and pagination must work without curator adapters."""
import hashlib
import json
import os
from pathlib import Path
import unittest

from verify import (BaseMeterGap, CAPACITY_CASES, CASES, INVALID_FLAG_CASES,
                    NoUnusedProviderObservation, ScoringError, Scenario, active_automatic_compaction,
                    base_estimate_message, base_observed_meter,
                    claim_ordinary_compaction_request, exit_codes_acceptable,
                    is_ordinary_compaction_result, is_visible_error_event, js_json_stringify,
                    public_events, utf16_length)


def reply(value):
    return {"messages": [{"role": "tool", "content": json.dumps(value)}]}


class PublicContractTests(unittest.TestCase):
    def test_fixed_base_meter_uses_utf16_per_message_ceil_and_js_arguments(self):
        arguments = {"10": "z", "2": "y", "label": "🙂"}
        self.assertEqual(js_json_stringify(arguments), '{"2":"y","10":"z","label":"🙂"}')
        tools = [{"name": "t", "description": "🙂", "parameters": {"type": "object"}}]
        tools_json = js_json_stringify(tools)
        context = {
            "messages": [
                {"role": "user", "content": "a"},
                {"role": "assistant", "content": [{"type": "toolCall", "name": "x", "arguments": arguments}]},
            ],
            "system_prompt": "S🙂",
            "tools": tools,
            "tools_json": tools_json,
            "model": {"contextWindow": 1000},
        }
        expected_setup = (utf16_length("S🙂\n" + tools_json) + 3) // 4
        expected_messages = 1 + (utf16_length("x" + js_json_stringify(arguments)) + 3) // 4
        meter = base_observed_meter(context)
        self.assertEqual(meter["tokens"], expected_setup + expected_messages)
        self.assertEqual(meter["messages"], expected_messages)

    def test_fixed_base_meter_fails_closed_on_unsupported_legal_shape(self):
        self.assertTrue(issubclass(BaseMeterGap, ScoringError))
        with self.assertRaisesRegex(BaseMeterGap, "Unsupported observed AgentMessage role"):
            base_estimate_message({"role": "unsupportedObservedRole", "content": "text"})

    def test_fixed_base_meter_uses_ecmascript_number_serialization(self):
        inherited = os.environ.get("NODE_OPTIONS")
        os.environ["NODE_OPTIONS"] = "--require=/candidate-controlled-loader.js"
        try:
            self.assertEqual(
                js_json_stringify({"decimal": 42.5, "exponent": 1e-7, "large": 10**20}),
                '{"decimal":42.5,"exponent":1e-7,"large":100000000000000000000}',
            )
        finally:
            if inherited is None:
                os.environ.pop("NODE_OPTIONS", None)
            else:
                os.environ["NODE_OPTIONS"] = inherited

    def test_invalid_flag_rejection_accepts_normal_nonzero_exit_only(self):
        self.assertTrue(exit_codes_acceptable("capacity_invalid_zero", [2]))
        self.assertTrue(exit_codes_acceptable("capacity_invalid_order", [0]))
        self.assertFalse(exit_codes_acceptable("capacity_invalid_headroom", [-9]))
        self.assertFalse(exit_codes_acceptable("capacity_notes", [2]))

    def test_public_visible_error_channels(self):
        self.assertTrue(is_visible_error_event({"type": "extension_error", "error": "too large"}))
        self.assertTrue(is_visible_error_event({"type": "extension_ui_request", "method": "notify",
                                                "notifyType": "error", "message": "too large"}))
        self.assertTrue(is_visible_error_event({"type": "message_end", "message": {
            "role": "assistant", "stopReason": "error", "errorMessage": "aborted"}}))
        self.assertTrue(is_visible_error_event({"type": "turn_end", "message": {
            "role": "assistant", "stopReason": "error", "errorMessage": "aborted"}}))
        self.assertFalse(is_visible_error_event({"type": "extension_ui_request", "method": "notify",
                                                 "notifyType": "info", "message": "large"}))

    def test_non_capacity_scenarios_use_explicit_public_budgets(self):
        scenario = Scenario("history")
        arguments = scenario.configuration["arguments"]
        reminder = int(arguments[arguments.index("--context-reminder-tokens") + 1])
        rollover = int(arguments[arguments.index("--context-rollover-tokens") + 1])
        headroom = int(arguments[arguments.index("--context-response-headroom") + 1])
        self.assertLess(reminder, rollover)
        self.assertLess(headroom, 1_000_000)

    def test_capacity_scenarios_have_explicit_headroom_without_candidate_adapter(self):
        scenario = Scenario("capacity_empty")
        arguments = scenario.configuration["arguments"]
        self.assertEqual(arguments[arguments.index("--context-reminder-tokens") + 1], "40000")
        self.assertEqual(arguments[arguments.index("--context-rollover-tokens") + 1], "150000")
        self.assertIn("--context-response-headroom", arguments)

    def test_compaction_http_requires_a_current_trusted_automatic_attempt(self):
        scenario = Scenario("capacity_compaction")
        class Observer:
            def __init__(self, facts):
                self.facts = facts
                self.consumed_providers = {6}
            def snapshot_events(self): return self.facts
        provider = {"observation_seq": 6, "fact": {"kind": "provider_request", "session_id": "s"}}
        attempt = {"observation_seq": 7, "fact": {
            "kind": "compaction_attempt", "reason": "threshold", "session_id": "s"}}
        error = NoUnusedProviderObservation("observation_incompatible: HTTP request has no unused public provider observation")
        body = {"messages": [{"role": "user", "content": "summary"}]}
        scenario.observer = Observer([provider, attempt])
        self.assertTrue(claim_ordinary_compaction_request(scenario, error, body))
        self.assertEqual(scenario.ordinary_compaction_requests, [{"attempt": attempt, "request": body}])
        for closing in [
            {"observation_seq": 8, "fact": {"kind": "session_compact", "reason": "threshold", "session_id": "s"}},
            {"observation_seq": 8, "fact": {"kind": "session_compact_failed", "event": {"reason": "threshold"}, "session_id": "s"}},
        ]:
            with self.subTest(closing=closing["fact"]["kind"]):
                scenario.observer = Observer([provider, attempt, closing])
                self.assertIsNone(active_automatic_compaction(scenario.observer.snapshot_events(), "s"))
                self.assertFalse(claim_ordinary_compaction_request(scenario, error, body))

    def test_manual_or_unrelated_missing_binding_is_not_claimed_as_compaction(self):
        scenario = Scenario("capacity_compaction")
        class Observer:
            consumed_providers = {6}
            def snapshot_events(self):
                return [
                    {"observation_seq": 6, "fact": {"kind": "provider_request", "session_id": "s"}},
                    {"observation_seq": 7, "fact": {"kind": "compaction_attempt", "reason": "manual", "session_id": "s"}},
                ]
        scenario.observer = Observer()
        missing = NoUnusedProviderObservation("observation_incompatible: HTTP request has no unused public provider observation")
        self.assertFalse(claim_ordinary_compaction_request(scenario, missing, {}))
        self.assertFalse(claim_ordinary_compaction_request(scenario, ScoringError("observer failed"), {}))

    def test_successful_compaction_is_projected_from_native_observation(self):
        events = public_events([{"fact": {"kind": "session_compact", "reason": "threshold", "from_extension": False}}])
        self.assertEqual(events, [{"type": "session_compact", "reason": "threshold", "from_extension": False}])

    def test_only_nonmanual_base_summary_results_are_rejected(self):
        self.assertTrue(is_ordinary_compaction_result(
            {"type": "session_compact", "reason": "threshold", "from_extension": False}))
        self.assertFalse(is_ordinary_compaction_result(
            {"type": "session_compact", "reason": "threshold", "from_extension": True}))
        self.assertFalse(is_ordinary_compaction_result(
            {"type": "session_compact", "reason": "manual", "from_extension": False}))

    def test_configured_headroom_differs_from_model_max_tokens(self):
        scenario = Scenario("capacity_configured_headroom")
        arguments = scenario.configuration["arguments"]
        headroom = int(arguments[arguments.index("--context-response-headroom") + 1])
        self.assertEqual(headroom, 100000)
        self.assertEqual(scenario.configuration["provider"]["max_tokens"], 250000)

    def test_public_flag_cases_cover_positive_adjacent_and_invalid_values(self):
        self.assertIn("capacity_legal_flags", CAPACITY_CASES)
        self.assertEqual(set(INVALID_FLAG_CASES),
                         {"capacity_invalid_zero", "capacity_invalid_order", "capacity_invalid_headroom"})
        arguments = Scenario("capacity_legal_flags").configuration["arguments"]
        reminder = int(arguments[arguments.index("--context-reminder-tokens") + 1])
        rollover = int(arguments[arguments.index("--context-rollover-tokens") + 1])
        self.assertEqual(rollover - reminder, 1)

    def test_default_activation_smoke_has_no_fixed_budget_flags(self):
        self.assertIn("default_activation", CASES)
        self.assertNotIn("default_activation", CAPACITY_CASES)
        self.assertNotIn("arguments", Scenario("default_activation").configuration)

    def test_history_all_matches_is_a_real_scenario(self):
        self.assertIn("history_all", CASES)

    def test_abc_controls_are_cataloged_with_current_hashes(self):
        task = Path(__file__).parents[1]
        catalog = json.loads((task / "validation/ci-cases.json").read_text())
        cases = {item["name"]: item for item in catalog["cases"]}
        expected = {
            "documented-small-defaults": 1,
            "ascii-json-everywhere": 1,
            "call-derived-ids": 1,
            "stateful-pages": 1,
            "oldest-only": 0,
            "page-shift-omission": 0,
        }
        for name, reward in expected.items():
            with self.subTest(name=name):
                item = cases[name]
                patch = task / "validation" / item["patch"]
                self.assertEqual(item["expected_reward"], reward)
                self.assertEqual(hashlib.sha256(patch.read_bytes()).hexdigest(), item["patch_sha256"])

    def test_d_controls_are_cataloged_with_current_hashes(self):
        task = Path(__file__).parents[1]
        catalog = json.loads((task / "validation/ci-cases.json").read_text())
        cases = {item["name"]: item for item in catalog["cases"]}
        for name in ("messages-only-capacity", "unmetered-carried-notes", "no-idle-capacity-check",
                     "allow-oversized-request", "accept-zero-context-flags", "repeat-capacity-reminder",
                     "model-max-headroom", "drop-unpresented-input"):
            with self.subTest(name=name):
                item = cases[name]
                patch = task / "validation" / item["patch"]
                self.assertEqual(item["expected_reward"], 0)
                self.assertEqual(hashlib.sha256(patch.read_bytes()).hexdigest(), item["patch_sha256"])

    def test_search_uses_opaque_public_cursor_without_adapter(self):
        scenario = Scenario("history")
        search = scenario.search_items("anchor")
        next(search)
        cursor = {"position": [9, "opaque"], "snapshot": "first page"}
        request = search.send(reply({"items": [{"item_id": 1}], "next_cursor": cursor}))
        self.assertEqual(json.loads(request["tool_calls"][0]["function"]["arguments"]),
                         {"query": "anchor", "cursor": cursor})
        with self.assertRaises(StopIteration) as end:
            search.send(reply({"items": [{"item_id": 2}], "next_cursor": None}))
        self.assertEqual(end.exception.value[1], [{"item_id": 1}, {"item_id": 2}])

    def test_stateful_repeated_cursor_and_finite_empty_page_are_accepted(self):
        search = Scenario("history").search_items("anchor")
        next(search)
        request = search.send(reply({"items": [{"item_id": 1}], "next_cursor": "stateful"}))
        self.assertEqual(json.loads(request["tool_calls"][0]["function"]["arguments"]),
                         {"query": "anchor", "cursor": "stateful"})
        request = search.send(reply({"items": [{"item_id": 2}], "next_cursor": "stateful"}))
        self.assertEqual(json.loads(request["tool_calls"][0]["function"]["arguments"]),
                         {"query": "anchor", "cursor": "stateful"})
        request = search.send(reply({"items": [], "next_cursor": "stateful"}))
        self.assertEqual(json.loads(request["tool_calls"][0]["function"]["arguments"]),
                         {"query": "anchor", "cursor": "stateful"})
        with self.assertRaises(StopIteration) as end:
            search.send(reply({"items": [{"item_id": 3}], "next_cursor": None}))
        self.assertEqual(end.exception.value[1],
                         [{"item_id": 1}, {"item_id": 2}, {"item_id": 3}])

    def test_all_match_recovery_reads_each_page_before_requesting_the_next(self):
        scenario = Scenario("history_all")
        expected = {"match_a": scenario.evidence["match_a"]}
        recovery = scenario.recover_all(scenario.shared_query, expected)
        first = next(recovery)
        self.assertEqual(first["tool_calls"][0]["function"]["name"], "history_search")
        identity = {"window_id": {"opaque": 1}, "item_id": ["record"]}
        read = recovery.send(reply({"items": [identity], "next_cursor": {"state": "same"}}))
        self.assertEqual(read["tool_calls"][0]["function"]["name"], "history_read")
        next_page = recovery.send(reply({"text": expected["match_a"]}))
        self.assertEqual(next_page["tool_calls"][0]["function"]["name"], "history_search")
        self.assertEqual(json.loads(next_page["tool_calls"][0]["function"]["arguments"]),
                         {"query": scenario.shared_query, "cursor": {"state": "same"}})


if __name__ == "__main__":
    unittest.main()
