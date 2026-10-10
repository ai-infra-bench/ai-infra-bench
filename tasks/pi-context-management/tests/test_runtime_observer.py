"""Parent request binding: semantic equality, single use and diagnostic isolation."""
import json
from pathlib import Path
import tempfile
import unittest
from runtime_observer import NoUnusedProviderObservation, RuntimeObserver, ScoringError
from verify import Scenario, classify_rpc_wait_errors


class RequestBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.observer = RuntimeObserver(self.temp.name, self.temp.name)
        self.observer.preflight()
        self.observer.pid, self.observer.phase = 123, 0
        self.observer.identity = {"start_time": 456}
        self.context = {"kind": "context_ready", "session_id": "s", "messages": [{"role": "user", "content": "actual"}],
                        "system_prompt": "system", "tools": [], "tools_json": "[]", "model": {"contextWindow": 1000}}
        self.wire = {"model": "scripted", "messages": [{"role": "user", "content": "actual"}], "stream": True}

    def fact(self, data):
        self.observer._accept({"schema": "context-observation.v1", **data})

    def request(self):
        self.fact(self.context)
        self.fact({"kind": "provider_request", "session_id": "s", "api": "openai-completions", "payload": self.wire})

    def test_json_object_key_order_is_irrelevant(self):
        self.request()
        reordered = dict(reversed(list(self.wire.items())))
        result = self.observer.consume_model_request(reordered, "openai-completions", timeout=0)
        self.assertEqual(result["context"]["messages"], self.context["messages"])
        self.assertEqual(result["session_id"], "s")

    def test_second_http_cannot_reuse_observation(self):
        self.request()
        self.observer.consume_model_request(self.wire, "openai-completions", timeout=0)
        with self.assertRaisesRegex(NoUnusedProviderObservation, "no unused public provider"):
            self.observer.consume_model_request(self.wire, "openai-completions", timeout=0)

    def test_array_order_and_values_are_preserved(self):
        self.request()
        with self.assertRaisesRegex(ScoringError, "differs from actual HTTP") as caught:
            self.observer.consume_model_request({**self.wire, "stream": False}, "openai-completions", timeout=0)
        self.assertNotIsInstance(caught.exception, NoUnusedProviderObservation)

    def test_boolean_is_not_the_number_one(self):
        self.request()
        with self.assertRaisesRegex(ScoringError, "differs from actual HTTP"):
            self.observer.consume_model_request({**self.wire, "stream": 1}, "openai-completions", timeout=0)

    def test_array_order_is_not_ignored(self):
        self.wire["ordered"] = ["first", "second"]
        self.request()
        with self.assertRaisesRegex(ScoringError, "differs from actual HTTP"):
            self.observer.consume_model_request({**self.wire, "ordered": ["second", "first"]}, "openai-completions", timeout=0)

    def test_abort_can_leave_context_without_http(self):
        self.fact(self.context)
        report = self.observer.finish(expected_completion=False, verifier_cancelled=True)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["request_bindings"], [])

    def test_session_cannot_borrow_another_sessions_context(self):
        self.request()
        self.observer.facts[-1]["fact"]["session_id"] = "other"
        with self.assertRaisesRegex(ScoringError, "no unused public context"):
            self.observer.consume_model_request(self.wire, "openai-completions", timeout=0)

    def test_snapshot_is_detached_from_parent_facts(self):
        self.request()
        snapshot = self.observer.snapshot_events()
        snapshot[0]["fact"]["messages"].clear()
        self.assertTrue(self.observer.snapshot_events()[0]["fact"]["messages"])

    def test_event_diagnostic_cannot_supply_typed_reminder(self):
        self.request()
        observation = self.observer.consume_model_request(self.wire, "openai-completions", timeout=0)
        scenario = Scenario("default_activation")
        scenario.events.append({"type": "context_observation", "reminders": ['{"remaining_tokens":1}']})
        scenario.script = iter([None])
        class Script:
            def send(self, body):
                return {"content": "done"}
        scenario.script = Script()
        scenario.respond(json.loads(json.dumps(self.wire)), observation)
        self.assertEqual(scenario.requests[0]["_reminders"], [])

    def test_missing_asset_is_scoring_error(self):
        with self.assertRaisesRegex(ScoringError, "trusted asset missing"):
            RuntimeObserver(self.temp.name, self.temp.name, assets=self.temp.name).preflight()


class RpcWaitClassificationTests(unittest.TestCase):
    def scenario(self):
        scenario = Scenario("pending_input")
        scenario.rpc_wait_errors.append("Scenario never reached the held external tool")
        return scenario

    def test_trusted_startup_failure_does_not_become_candidate_failure(self):
        scenario = self.scenario()
        scenario.scoring_errors.append("Trusted fixture did not become ready; startup attribution incomplete")
        classify_rpc_wait_errors(scenario)
        self.assertEqual(scenario.errors, [])
        self.assertTrue(scenario.rpc_wait_errors)  # Retain the diagnostic.

    def test_healthy_observer_wait_failure_remains_a_candidate_error(self):
        scenario = self.scenario()
        classify_rpc_wait_errors(scenario)
        self.assertEqual(scenario.errors, scenario.rpc_wait_errors)
        self.assertEqual(scenario.scoring_errors, [])

    def test_concrete_product_error_survives_later_infrastructure_diagnostic(self):
        scenario = self.scenario()
        concrete_error = "Missing public tools: ['new_context']"
        scenario.errors.append(concrete_error)
        scenario.scoring_errors.append("later observer disconnect")
        classify_rpc_wait_errors(scenario)
        self.assertEqual(scenario.errors, [concrete_error])

    def test_known_explicit_early_exit_remains_a_candidate_error(self):
        scenario = self.scenario()
        scenario.errors.append("Candidate explicitly exited while loading before fixture readiness")
        classify_rpc_wait_errors(scenario)
        self.assertEqual(len(scenario.errors), 2)
        self.assertEqual(scenario.scoring_errors, [])


if __name__ == "__main__":
    unittest.main()
