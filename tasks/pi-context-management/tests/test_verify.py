"""Regression checks for the trusted scorer's history recovery boundary."""
import json
import unittest

from verify import Scenario


def tool_result(value):
    return {"messages": [{"role": "tool", "content": json.dumps(value)}]}


class HistoryRecoveryTests(unittest.TestCase):
    original = 'anchor\n古🙂e\u0301 log\\n literal\nreceipt'

    def recover(self, payload):
        scenario = Scenario("history")
        script = scenario.recover("anchor", self.original)
        next(script)
        script.send(tool_result({"items": [{"window_id": "window", "item_id": "record"}]}))
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


if __name__ == "__main__":
    unittest.main()
