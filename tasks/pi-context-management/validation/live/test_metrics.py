import json
import unittest
from metrics import behavior_metrics, infrastructure_metrics, phase_completion


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.serial = 0

    def tool(self, name, phase=0, error=False, **args):
        self.serial += 1
        identity = f'call-{self.serial}'
        self.events.extend([
            {'type': 'assistant', 'phase': phase, 'message': {'stopReason': 'toolUse', 'content': [
                {'type': 'toolCall', 'id': identity, 'name': name, 'arguments': args}]}},
            {'type': 'tool_execution_end', 'phase': phase, 'toolCallId': identity, 'toolName': name, 'isError': error},
        ])

    def workflow(self):
        for run in ['A', 'B', 'C']:
            self.tool('inspect_run', run_id=run)
            self.tool('notes_write', text='progress')
            self.tool('new_context')

    def test_actual_repeated_resets_are_visible_despite_correct_workflow(self):
        self.workflow()
        for _ in range(8):
            self.tool('notes_write', text='next: new_context')
            self.tool('new_context')
        result = behavior_metrics(self.events)
        self.assertEqual(result['phase0_reset_calls'], 11)
        self.assertEqual(result['extra_phase0_reset_calls'], 8)
        self.assertEqual(result['resets_without_new_evidence'], 8)
        self.assertTrue(all(w['notes_then_reset'] for w in result['workflow']))
        self.assertTrue(result['diagnostic_only'])

    def test_duplicate_event_and_model_retry_do_not_inflate_tool_count(self):
        self.workflow()
        self.events.append(dict(self.events[-1]))
        self.events += [{'type': 'request', 'phase': 0} for _ in range(6)]
        self.assertEqual(behavior_metrics(self.events)['phase0_reset_calls'], 3)

    def test_same_call_id_in_different_phases_is_not_deduplicated(self):
        self.tool('new_context')
        self.events.append(dict(self.events[-1], phase=1))
        self.assertEqual(behavior_metrics(self.events)['completed_tool_calls'], 2)

    def test_failed_write_does_not_satisfy_workflow(self):
        self.tool('inspect_run', run_id='A')
        self.tool('notes_write', error=True, text='lost')
        self.tool('new_context')
        result = behavior_metrics(self.events)
        self.assertFalse(result['workflow'][0]['notes_then_reset'])
        self.assertEqual(result['tool_errors'], 1)

    def test_rereading_after_reset_is_not_same_window_duplication(self):
        self.tool('history_read', window_id='w', item_id='i')
        self.tool('history_read', window_id='w', item_id='i')
        self.tool('new_context')
        self.tool('history_read', window_id='w', item_id='i')
        self.assertEqual(behavior_metrics(self.events)['duplicate_history_reads_same_window'], 1)

    def test_no_fixed_baseline_for_autonomous_policy(self):
        self.workflow()
        self.assertIsNone(behavior_metrics(self.events, expected_resets=None)['extra_phase0_reset_calls'])

    def test_successful_report_and_exit_zero_are_not_final_completion(self):
        self.tool('submit_report', phase=1)
        self.assertFalse(phase_completion(self.events)['1']['completed'])
        self.events.append({'type': 'assistant', 'phase': 1, 'message': {
            'stopReason': 'error', 'content': [], 'errorMessage': 'rate limit'}})
        self.assertFalse(phase_completion(self.events)['1']['completed'])

    def test_later_error_overrides_earlier_success(self):
        for reason in ['stop', 'error']:
            self.events.append({'type': 'assistant', 'phase': 1, 'message': {
                'stopReason': reason, 'content': [{'type': 'text', 'text': 'done'}]}})
        self.assertFalse(phase_completion(self.events)['1']['completed'])

    def test_final_stop_completes_only_its_own_phase(self):
        self.events.append({'type': 'assistant', 'phase': 0, 'message': {
            'stopReason': 'stop', 'content': [{'type': 'text', 'text': 'B'}]}})
        result = phase_completion(self.events)
        self.assertTrue(result['0']['completed'])
        self.assertFalse(result['1']['completed'])

    def test_stream_error_and_response_failed_count_as_one_failed_request(self):
        records = [{'trace_id': 'one', 'upstream_status': 200, 'upstream_sse_blob': '\n'.join(
            'data: ' + json.dumps(event) for event in [
                {'type': 'error', 'error': {'code': 'rate_limit_exceeded'}},
                {'type': 'response.failed', 'response': {'error': {'code': 'rate_limit_exceeded'}}},
            ])}]
        result = infrastructure_metrics(records)
        self.assertEqual(result['stream_failed_requests'], 1)
        self.assertEqual(result['rate_limited_requests'], 1)
        self.assertEqual(result['http_429_attempts'], 0)


if __name__ == '__main__':
    unittest.main()
