import json
import unittest
from metrics import recovery_preconditions


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.row = {'audit_receipt': 'receipt-unique-123', 'checksum': 'checksum-unique-456',
                    'boundary_sample_id': '边界样本-独立789'}
        self.data = {'B': self.row}

    def answer(self, text, phase=0):
        return {'type': 'assistant', 'phase': phase, 'message': {
            'stopReason': 'stop', 'content': [{'type': 'text', 'text': text}]}}

    def request(self, text, phase=1):
        return {'type': 'request', 'phase': phase, 'payload': {
            'input': [{'role': 'assistant', 'content': [{'type': 'output_text', 'text': text}]}]}}

    def recovered(self, data, tool='history_read', error=False):
        return {'type': 'tool_execution_end', 'phase': 1, 'toolName': tool, 'isError': error,
                'result': {'content': [{'type': 'text', 'text': json.dumps(data)}]}}

    def test_each_audit_field_in_final_answer_is_rejected(self):
        for field, value in self.row.items():
            with self.subTest(field=field):
                result = recovery_preconditions([self.answer('B\n' + value)], self.data)
                self.assertFalse(result['phase0_final_answer_clean'])
                self.assertEqual(result['copied_fields_in_final_answer'], ['B.' + field])

    def test_leaked_prior_reply_in_next_phase_input_is_rejected(self):
        events = [self.answer('B'), self.request('Previously retained: ' + self.row['checksum'])]
        result = recovery_preconditions(events, self.data)
        self.assertFalse(result['values_appear_only_after_history_recovery'])
        self.assertEqual(result['requests_with_unrecovered_values'][0]['fields'], ['B.checksum'])

    def test_values_are_allowed_after_successful_original_record_read(self):
        original = json.dumps(self.row, ensure_ascii=False)
        events = [self.answer('B'), self.request('find original'),
                  self.recovered({'text': original}), self.request(original), self.answer(original, phase=1)]
        result = recovery_preconditions(events, self.data)
        self.assertTrue(result['phase0_final_answer_clean'])
        self.assertTrue(result['values_appear_only_after_history_recovery'])
        self.assertEqual(len(result['recovered_fields']), 3)

    def test_search_preview_can_legitimately_recover_a_value(self):
        value = self.row['audit_receipt']
        events = [self.recovered({'items': [{'preview': value}]}, tool='history_search'), self.request(value)]
        self.assertTrue(recovery_preconditions(events, self.data)['values_appear_only_after_history_recovery'])

    def test_partial_recovery_does_not_allow_unseen_fields(self):
        events = [self.recovered({'text': self.row['audit_receipt']}), self.request(json.dumps(self.row, ensure_ascii=False))]
        result = recovery_preconditions(events, self.data)
        self.assertFalse(result['values_appear_only_after_history_recovery'])
        self.assertEqual(set(result['requests_with_unrecovered_values'][0]['fields']), {'B.checksum', 'B.boundary_sample_id'})

    def test_failed_read_does_not_count_as_successful_recovery(self):
        value = self.row['checksum']
        events = [self.recovered({'text': value}, error=True), self.request(value)]
        self.assertFalse(recovery_preconditions(events, self.data)['values_appear_only_after_history_recovery'])

    def test_initial_evidence_and_discarded_commentary_are_not_final_answer(self):
        value = self.row['audit_receipt']
        events = [self.request(value, phase=0), self.answer(value), self.answer('B'), self.request('B')]
        result = recovery_preconditions(events, self.data)
        self.assertTrue(result['phase0_final_answer_clean'])
        self.assertTrue(result['values_appear_only_after_history_recovery'])

    def test_unicode_json_escape_in_tool_response_is_decoded(self):
        value = self.row['boundary_sample_id']
        events = [self.recovered({'text': value}), self.request(value)]
        result = recovery_preconditions(events, self.data)
        self.assertTrue(result['values_appear_only_after_history_recovery'])
        self.assertEqual(result['recovered_fields'], ['B.boundary_sample_id'])


if __name__ == '__main__': unittest.main()
