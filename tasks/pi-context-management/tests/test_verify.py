"""Regression checks for the trusted scorer's history recovery boundary."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

from verify import CASES, Scenario, TOOLS, classify_rpc_wait_errors, communicate_reminder_boundary, result


def tool_result(value):
    return {"messages": [{"role": "tool", "content": json.dumps(value)}]}


class HistoryRecoveryTests(unittest.TestCase):
    original = 'anchor\n古🙂e\u0301 log\\n literal\nreceipt'

    def recover(self, payload, identity=None):
        scenario = Scenario("history")
        script = scenario.recover("anchor", self.original)
        next(script)
        script.send(tool_result({"items": [identity or {"window_id": "window", "item_id": "record"}]}))
        try:
            script.send(tool_result({"text": payload}))
        except StopIteration:
            return True
        except AssertionError:
            return False
        self.fail("Recovery did not finish after reading the only matching record")

    def test_plain_and_lossless_json_records_recover_complete_original(self):
        for payload in [self.original, json.dumps(self.original),
                        json.dumps({"role": "toolResult", "content": [{"type": "text", "text": self.original}]}),
                        json.dumps({"message": {"content": [{"text": json.dumps(self.original)}]}})]:
            with self.subTest(payload=payload):
                self.assertTrue(self.recover(payload))

    def test_incomplete_or_changed_records_cannot_pass_as_lossless_history(self):
        for payload in ["", "anchor: log summarized; receipt", self.original[:-1],
                        self.original.replace("古", "今"),
                        json.dumps({"text": self.original.replace("\n", " ")}),
                        json.dumps({"parts": self.original.split("\n")}),
                        json.dumps(self.original)[1:-1],
                        json.dumps({self.original: "not original content"})]:
            with self.subTest(payload=payload):
                self.assertFalse(self.recover(payload))

    def test_numeric_opaque_ids_are_passed_back_without_format_restrictions(self):
        self.assertTrue(self.recover(self.original, {"window_id": 42, "item_id": 7}))



class FreshContextTests(unittest.TestCase):
    def setUp(self):
        self.scenario = Scenario("rollover")

    def request(self, *extra):
        return {"messages": [
            {"role": "system", "content": self.scenario.system},
            {"role": "user", "content": self.scenario.summary},
            *({"role": "user", "content": value} for value in extra),
        ]}

    def test_fresh_context_does_not_require_consumed_user_text(self):
        self.scenario.check_fresh(self.request())

    def test_fresh_context_rejects_consumed_user_text_not_saved_in_notes(self):
        with self.assertRaisesRegex(AssertionError, "[Uu]ser"):
            self.scenario.check_fresh(self.request(self.scenario.goal))

    def test_model_may_choose_to_copy_user_text_into_notes(self):
        self.scenario.summary += "\n" + self.scenario.goal
        self.scenario.check_fresh(self.request())

    def test_new_unconsumed_user_input_is_not_mistaken_for_old_history(self):
        self.scenario.check_fresh(self.request(self.scenario.correction))

    def test_complete_notes_may_be_json_encoded_inside_recovery_guidance(self):
        self.scenario.summary += '\n"保留原文" literal \\n'
        for encoded in [json.dumps(self.scenario.summary),
                        json.dumps(self.scenario.summary, ensure_ascii=False),
                        json.dumps({"notes": self.scenario.summary})]:
            with self.subTest(encoded=encoded):
                body = self.request()
                body["messages"][1]["content"] = "Recovery guidance\nSaved notes:\n" + encoded
                self.scenario.check_fresh(body)

    def test_opaque_window_id_may_contain_an_old_call_id(self):
        old_call = "call_from_reset"
        self.scenario.emitted.append({"id": old_call})
        body = self.request()
        body["messages"][1]["content"] += "\nOpaque window_id: session:" + old_call
        self.scenario.check_fresh(body)

    def test_actual_old_assistant_call_and_result_are_rejected(self):
        old_call = "call_from_reset"
        self.scenario.emitted.append({"id": old_call})
        body = self.request()
        body["messages"][1:1] = [
            {"role": "assistant", "content": "", "tool_calls": [{
                "id": old_call,
                "function": {"name": "new_context", "arguments": "{}"},
            }]},
            {"role": "tool", "tool_call_id": old_call, "content": '{"window_id":"w"}'},
        ]
        with self.assertRaisesRegex(AssertionError, "tool-call/result"):
            self.scenario.check_fresh(body)

    def test_json_encoded_old_prose_is_still_rejected(self):
        body = self.request(json.dumps({"old_assistant": self.scenario.hypothesis}, ensure_ascii=True))
        with self.assertRaisesRegex(AssertionError, "assistant text"):
            self.scenario.check_fresh(body)

    def test_prefixed_or_fenced_json_encoded_old_prose_is_still_rejected(self):
        encoded = json.dumps({"old_assistant": self.scenario.hypothesis}, ensure_ascii=True)
        for value in ["Recovery record:\n" + encoded,
                      "Archived value:\n```json\n" + encoded + "\n```"]:
            with self.subTest(value=value):
                body = self.request(value)
                with self.assertRaisesRegex(AssertionError, "assistant text"):
                    self.scenario.check_fresh(body)

    def test_separate_fields_are_not_joined_into_old_prose(self):
        self.scenario.check_fresh(self.request(*self.scenario.hypothesis.split("\n")))

    def test_encoded_notes_must_still_contain_the_complete_unchanged_value(self):
        self.scenario.summary += '\n"保留原文" literal \\n'
        for value in [self.scenario.summary[:-1],
                      self.scenario.summary.replace("保留", "修改"),
                      self.scenario.summary.split("\n"), ""]:
            with self.subTest(value=value):
                body = self.request()
                body["messages"][1]["content"] = "Saved notes:\n" + json.dumps(value)
                with self.assertRaisesRegex(AssertionError, "Latest working notes"):
                    self.scenario.check_fresh(body)


class ToolResultTests(unittest.TestCase):
    def test_tool_result_is_selected_by_call_id_before_appended_guidance(self):
        body = {"messages": [
            {"role": "tool", "tool_call_id": "old", "content": '{"text":"stale"}'},
            {"role": "tool", "tool_call_id": "requested", "content": '{"text":"current"}'},
            {"role": "user", "content": "Remember to save working notes."},
        ]}
        self.assertEqual(result(body, "requested"), {"text": "current"})

    def test_an_older_result_cannot_replace_a_missing_requested_result(self):
        body = {"messages": [
            {"role": "tool", "tool_call_id": "old", "content": '{"text":"same value"}'},
        ]}
        with self.assertRaisesRegex(AssertionError, "requested tool"):
            result(body, "requested")


class BatchHistoryTimingTests(unittest.TestCase):
    def test_batch_does_not_require_searchable_active_history(self):
        scenario = Scenario("batch")
        script = scenario.script_main()
        next(script)
        script.send({"tools": [{"function": {"name": name}} for name in TOOLS]})
        script.send({"messages": [{"role": "tool", "content": scenario.evidence["old"]}]})
        script.send({"messages": []})
        fresh = {"messages": [{"role": "system", "content": scenario.system},
                              {"role": "user", "content": scenario.summary}]}
        script.send(fresh)
        response = script.send({"messages": [{"role": "tool", "content": scenario.evidence["before"]}]})
        self.assertEqual([item["function"]["name"] for item in response["tool_calls"]],
                         ["new_context", "evidence", "notes_write", "new_context"])


class LiteralHistoryIdentityTests(unittest.TestCase):
    def run_literal(self, *, omit_original=False, include_original_for_nonmatch=False):
        scenario = Scenario("history_literal")
        script = scenario.script_main()
        next(script)
        body = {"tools": [{"function": {"name": name}} for name in TOOLS]}
        originals = {"tool-original": scenario.evidence["old"], "user-original": scenario.goal}
        observed_queries = []
        for _ in range(80):
            response = script.send(body)
            if "tool_calls" not in response:
                self.assertTrue(scenario.done)
                return observed_queries
            item = response["tool_calls"][0]
            name = item["function"]["name"]
            arguments = json.loads(item["function"]["arguments"])
            if name == "evidence":
                body = {"messages": [{"role": "tool", "content": originals["tool-original"]}]}
            elif name == "new_context":
                body = {"messages": [{"role": "system", "content": scenario.system}]}
            elif name == "history_search":
                query = arguments["query"]
                observed_queries.append(query)
                matches = []
                for key, value in originals.items():
                    original_match = query in value
                    # Later search/read records can legitimately contain a
                    # complete copy; they must not substitute for original IDs.
                    if original_match:
                        matches.append({"window_id": 9, "item_id": key + "-copy"})
                    if original_match and not (omit_original and ("\n" in query or '"' in query)):
                        matches.append({"window_id": 9, "item_id": key})
                    elif not original_match and include_original_for_nonmatch:
                        matches.append({"window_id": 9, "item_id": key})
                # Real encoded read results can match an escaped query.
                if "\\" in query:
                    matches.extend({"window_id": 9, "item_id": key + "-copy"} for key in originals)
                # For independent anchor lookup, expose originals first. The
                # later literal lookups above deliberately put copies first.
                if not any(character in query for character in ('\n', '"', "\\")):
                    matches.sort(key=lambda value: value["item_id"].endswith("-copy"))
                body = tool_result({"items": matches, "next_cursor": None})
            elif name == "history_read":
                key = arguments["item_id"].removesuffix("-copy")
                body = tool_result({"text": json.dumps({"complete": originals[key]}, ensure_ascii=True)})
            else:
                self.fail("Unexpected literal-history action: " + name)
        self.fail("Literal history scenario did not finish")

    def test_literal_queries_accept_lossless_json_and_new_matching_copies(self):
        queries = self.run_literal()
        self.assertTrue(any("\n" in query for query in queries))
        self.assertTrue(any('"' in query for query in queries))

    def test_copied_record_cannot_replace_missing_original_literal_match(self):
        with self.assertRaisesRegex(AssertionError, "original.*identity"):
            self.run_literal(omit_original=True)

    def test_nonmatching_query_must_not_return_original_identity(self):
        with self.assertRaisesRegex(AssertionError, "[Nn]onmatching.*identity"):
            self.run_literal(include_original_for_nonmatch=True)


class ReminderBoundaryTests(unittest.TestCase):
    def run_boundary(self, *, meter=11987, old=True, pending=True):
        scenario = Scenario("capacity_reminder_boundary")
        script = scenario.script_main()
        next(script)
        script.send({"tools": [{"function": {"name": name}} for name in TOOLS]})
        baseline = {"messages": [{"role": "system", "content": scenario.system}],
                    "_observed_context": {"messages": [], "model": {"contextWindow": 13024}},
                    "_base_meter": {"tokens": 1000}}
        response = script.send(baseline)
        messages = [{"role": "system", "content": scenario.system}]
        if old:
            messages.append({"role": "assistant", "content": response["content"]})
        if pending:
            messages.append({"role": "user", "content": scenario.correction})
        target = {"messages": messages,
                  "_observed_context": {"messages": [], "model": {"contextWindow": 13024}},
                  "_base_meter": {"tokens": meter}}
        script.send(target)
        self.assertTrue(scenario.done)
        return scenario.saved["capacity_boundary"]

    def test_actual_input_below_reminder_accepts_no_reminder_and_no_reset(self):
        record = self.run_boundary()
        self.assertEqual(record["actual_meter"], 11987)
        self.assertEqual(record["coverage"], "not_exercised")

    def test_actual_fresh_request_keeps_pending_input_and_is_metered(self):
        record = self.run_boundary(meter=1291, old=False)
        self.assertEqual(record["actual_meter"], 1291)
        self.assertEqual(record["coverage"], "fresh_request_observed")

    def test_actual_outgoing_request_at_rollover_is_rejected(self):
        with self.assertRaisesRegex(AssertionError, "[Bb]udget|[Rr]ollover"):
            self.run_boundary(meter=12000)

    def test_missing_unpresented_input_is_rejected(self):
        with self.assertRaisesRegex(AssertionError, "[Uu]npresented"):
            self.run_boundary(meter=1291, old=False, pending=False)

    def test_actual_unreminded_input_at_reminder_is_rejected(self):
        with self.assertRaisesRegex(AssertionError, "Reminder presence"):
            self.run_boundary(meter=11999)

    def incomplete(self):
        scenario = Scenario("capacity_reminder_boundary")
        scenario.saved["capacity_boundary"] = {
            "actual_required_request": None, "actual_meter": None,
            "pending_prompt_sent": True, "turn_settled": True,
        }
        return scenario

    def test_no_http_reports_unfinished_required_turn_without_fabricated_meter(self):
        scenario = self.incomplete()
        classify_rpc_wait_errors(scenario)
        self.assertEqual(scenario.errors, ["required_pending_turn_did_not_complete"])
        self.assertIsNone(scenario.saved["capacity_boundary"]["actual_meter"])
        self.assertIsNone(scenario.saved["capacity_boundary"]["actual_required_request"])

    def test_observer_or_rpc_driver_fault_is_not_an_unfinished_candidate_turn(self):
        for fault in ("observer failed", "RPC driver could not write prompt"):
            with self.subTest(fault=fault):
                scenario = self.incomplete()
                scenario.scoring_errors.append(fault)
                classify_rpc_wait_errors(scenario)
                self.assertEqual(scenario.errors, [])

    def drive_public_protocol(self, *, idle_reply_success, baseline=True, observer_error=None):
        scenario = self.incomplete()
        scenario.saved["capacity_boundary"].update(
            baseline={"actual_meter": 1000}, visible_errors=[], pending_prompt_sent=False, turn_settled=False)
        if not baseline:
            scenario.saved["capacity_boundary"].pop("baseline")
        scenario.requests = [{}, {}] if baseline else []
        scenario.observer = SimpleNamespace(mark_cancelled=lambda: None)
        # This peer supplies only the RPC input/output boundary. The real
        # production driver must distinguish a completed abort from a bad reply.
        source = '''import json,sys
for line in sys.stdin:
    command=json.loads(line)
    if command["type"] == "get_state":
        event={"type":"response","id":command["id"],"success":%s,"data":{"isStreaming":False}}
        print(json.dumps(event),flush=True)
    else:
        if command["id"] in ("boundary-initial", "boundary-pending"):
            print(json.dumps({"type":"extension_error","error":"capacity abort"}),flush=True)
        print(json.dumps({"type":"agent_end"}),flush=True)
''' % repr(idle_reply_success)
        with subprocess.Popen([sys.executable, "-u", "-c", source], text=True,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              start_new_session=True) as process:
            communicate_reminder_boundary(process, scenario)
        if observer_error:
            scenario.scoring_errors.append(observer_error)
        classify_rpc_wait_errors(scenario)
        return scenario

    def test_public_abort_settles_without_turning_into_an_rpc_timeout(self):
        scenario = self.drive_public_protocol(idle_reply_success=True)
        self.assertEqual(scenario.rpc_wait_errors, [])
        self.assertEqual(scenario.scoring_errors, [])
        self.assertEqual(scenario.errors, ["required_pending_turn_did_not_complete"])
        self.assertTrue(scenario.saved["capacity_boundary"]["turn_settled"])
        self.assertIsNone(scenario.saved["capacity_boundary"]["actual_meter"])

    def test_initial_abort_is_candidate_failure_after_healthy_observation(self):
        scenario = self.drive_public_protocol(idle_reply_success=True, baseline=False)
        self.assertEqual(scenario.scoring_errors, [])
        self.assertIn("Initial required prompt did not reach the provider", scenario.errors)
        self.assertFalse(scenario.saved["capacity_boundary"]["pending_prompt_sent"])

    def test_initial_abort_with_late_observer_fault_remains_unscored(self):
        scenario = self.drive_public_protocol(idle_reply_success=True, baseline=False,
                                             observer_error="Native observation failed")
        self.assertEqual(scenario.scoring_errors, ["Native observation failed"])
        self.assertEqual(scenario.errors, [])

    def test_failed_idle_reply_is_driver_error_without_candidate_failure(self):
        scenario = self.drive_public_protocol(idle_reply_success=False)
        self.assertTrue(scenario.scoring_errors)
        self.assertEqual(scenario.errors, [])


class UpstreamContextCoverageTests(unittest.TestCase):
    def test_thinking_scenarios_remain_in_full_capacity_inventory(self):
        self.assertEqual(len(CASES), 42)
        self.assertIn("thinking_search", CASES)
        self.assertIn("thinking_read", CASES)
        self.assertIn("capacity_oversized_input", CASES)

    def test_reasoning_and_visible_text_must_come_from_the_same_record(self):
        scenario = Scenario("thinking_read")
        script = scenario.recover("visible", "reasoning\n古🙂e\u0301", also="visible original")
        next(script)
        script.send(tool_result({"items": [
            {"window_id": "w", "item_id": "reasoning-only"},
            {"window_id": "w", "item_id": "visible-only"}]}))
        script.send(tool_result({"text": "reasoning\n古🙂e\u0301"}))
        with self.assertRaisesRegex(AssertionError, "complete original record"):
            script.send(tool_result({"text": "visible original"}))

    def test_complete_json_message_recovers_reasoning_and_visible_text(self):
        scenario = Scenario("thinking_search")
        script = scenario.recover("anchor", "anchor\n古🙂e\u0301", also="visible original")
        next(script)
        script.send(tool_result({"items": [{"window_id": "w", "item_id": "original"}]}))
        record = {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "anchor\n古🙂e\u0301"},
            {"type": "text", "text": "visible original"}]}
        with self.assertRaises(StopIteration):
            script.send(tool_result({"text": json.dumps(record)}))

    def test_tool_result_remains_call_matched_with_trailing_guidance(self):
        body = {"messages": [{"role": "tool", "tool_call_id": "wanted", "content": '{"text":"ok"}'},
                             {"role": "user", "content": "legal trailing recovery guidance"}]}
        self.assertEqual(result(body, "wanted"), {"text": "ok"})
        with self.assertRaisesRegex(AssertionError, "JSON object"):
            result({"messages": [{"role": "tool", "content": "[]"}]})

    def test_disabled_path_uses_real_builtin_bash_command(self):
        scenario = Scenario("ordinary")
        script = scenario.script_main()
        next(script)
        script.send({"messages": [], "tools": []})
        step = script.send({"messages": [{"role": "tool", "content": scenario.evidence["side"]}]})
        function = step["tool_calls"][0]["function"]
        self.assertEqual(function["name"], "bash")
        self.assertIn("builtin-output.txt", json.loads(function["arguments"])["command"])
        script.send({"messages": [{"role": "tool", "content": "builtin-bash-" + scenario.nonce}]})
        self.assertIn("disabled_builtin_bash_output", [x["name"] for x in scenario.checks])




class CapacityCompactionRepresentationTests(unittest.TestCase):
    def request(self, scenario, *, content='', value=None, reminder=False, tokens=60000):
        messages = [{'role': 'system', 'content': scenario.system}]
        if content:
            messages.append({'role': 'tool', 'content': content})
        if value is not None:
            messages.append({'role': 'tool', 'content': json.dumps(value)})
        observed = []
        if reminder:
            notice = json.dumps({'remaining_tokens': 30000, 'message': 'Save notes'})
            messages.append({'role': 'user', 'content': notice})
            observed.append({'role': 'custom', 'customType': 'context_capacity_reminder', 'content': notice})
        return {'messages': messages, '_observed_context': {'messages': observed,
                'model': {'contextWindow': 100000}}, '_base_meter': {'tokens': tokens}}

    def at_recovery(self):
        scenario = Scenario('capacity_compaction')
        script = scenario.script_capacity(self.request(scenario), 0)
        next(script)  # Original large evidence triggers the first reminder.
        script.send(self.request(scenario, content=scenario.evidence['old'], reminder=True))
        script.send(self.request(scenario, value={'text': ''}))
        search = script.send(self.request(scenario))  # Completed large batch rolled over.
        query = json.loads(search['tool_calls'][0]['function']['arguments'])['query']
        self.assertIn(query, scenario.goal)
        self.assertNotIn(query, scenario.evidence['old'])
        self.assertNotIn(query, scenario.evidence['side'])
        script.send(self.request(scenario, value={'items': [{'window_id': 'old', 'item_id': 'goal'}]}))
        return scenario, script

    def test_duplicate_lossless_json_recovers_without_reading_capacity_payload(self):
        scenario, script = self.at_recovery()
        original = {'role': 'user', 'content': scenario.goal}
        value = {'text': json.dumps({'original': original}), 'original': original}
        tool = script.send(self.request(scenario, value=value, tokens=2000))
        self.assertEqual(tool['tool_calls'][0]['function']['name'], 'evidence')
        self.assertEqual(json.loads(tool['tool_calls'][0]['function']['arguments']), {'key': 'old'})
        final = script.send(self.request(scenario, content=scenario.evidence['old'], reminder=True))
        self.assertTrue(scenario.done)
        self.assertTrue(final['content'].startswith('VERIFIED-'))

    def test_incomplete_short_original_still_rejected(self):
        scenario, script = self.at_recovery()
        with self.assertRaisesRegex(AssertionError, 'complete original'):
            script.send(self.request(scenario, value={'text': scenario.goal[:-1]}))

    def test_second_window_requires_actual_payload_budget_and_one_reminder(self):
        for mode in ['missing', 'duplicate', 'over-budget', 'below-reminder', 'reset-away']:
            with self.subTest(mode=mode):
                scenario, script = self.at_recovery()
                script.send(self.request(scenario, value={'text': scenario.goal}))
                response = self.request(scenario, content=scenario.evidence['old'], reminder=mode!='missing')
                if mode == 'duplicate': response['_observed_context']['messages'] *= 2
                if mode == 'over-budget': response['_base_meter']['tokens'] = 95904
                if mode == 'below-reminder': response['_base_meter']['tokens'] = 39999
                if mode == 'reset-away': response['messages'] = [{'role': 'system', 'content': scenario.system}]
                with self.assertRaises(AssertionError): script.send(response)

if __name__ == "__main__":
    unittest.main()
