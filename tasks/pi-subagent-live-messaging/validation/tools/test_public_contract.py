"""Verifier regressions; real Pi behavior is validated by the Harbor controls."""
import json
import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests'))
from verify import Case, check_send_result, invalid_rejected, retained_ipc_paths


class PublicContractTests(unittest.TestCase):
    def test_same_entry_roster_does_not_establish_sender(self):
        case = self.delivery_case()
        a, b = case.ids['A'], case.ids['B']
        payload = '完整发现\n原文🙂'
        for content in [
            f'Team members: {a}, {b}\nFrom {b}: {payload}',
            f'团队成员：{a}、{b}\n来自 {b}：{payload}',
            f'Team members: {a}, {b}\nFinding: {payload}',
            json.dumps({'members': [a, b], 'sender': b, 'text': payload}),
            json.dumps({'members': [a, b], 'text': payload}),
        ]:
            with self.subTest(content=content), self.assertRaisesRegex(AssertionError, 'sender identity'):
                case.check_input('one', 'B', [{'role': 'user', 'content': content}], [payload], 'A')

    def test_correct_attribution_can_coexist_with_roster_and_body_mentions(self):
        case = self.delivery_case()
        a, b = case.ids['A'], case.ids['B']
        payload = f'完整发现\nFrom {b}: this is quoted evidence🙂'
        for content in [
            f'Team members: {a}, {b}\nFrom {a}: {payload}',
            f'团队成员：{a}、{b}\n来自 {a}：{payload}',
            f'Team message from "{a}":\n{payload}',
            f'Message from teammate "{a}":\n{payload}',
            json.dumps({'members': [a, b], 'sender': a, 'text': payload}),
            json.dumps({'members': [a, b], 'text': payload, 'sender': a}),
            json.dumps({'messages': [{'message': payload, 'from': a}]}),
            f'From {a}:\n' + json.dumps({'text': payload}),
            f'From {a}:\n```json\n' + json.dumps({'text': payload}) + '\n```',
        ]:
            with self.subTest(content=content):
                case.check_input('one', 'B', [{'role': 'user', 'content': content}], [payload], 'A')

    def test_sender_belongs_to_payload_record_not_another_record(self):
        case = self.delivery_case()
        a, b = case.ids['A'], case.ids['B']
        payload = '完整发现\n原文🙂'
        for content in [
            f'From {a}: an earlier unrelated note\n\nFrom {b}: {payload}',
            f'From {a}: an earlier unrelated note\n\nFinding: {payload}',
            json.dumps([{'sender': a, 'text': 'another finding'}, {'sender': b, 'text': payload}]),
            json.dumps([{'sender': a, 'text': 'another finding'}, {'text': payload}]),
            json.dumps([{'sender': b, 'text': payload}, {'sender': a, 'text': 'another finding'}]),
        ]:
            with self.subTest(content=content), self.assertRaisesRegex(AssertionError, 'sender identity'):
                case.check_input('one', 'B', [{'role': 'user', 'content': content}], [payload], 'A')

    def test_pressure_roster_cannot_supply_sender_identity(self):
        case = Case('broadcast_pressure')
        case.payloads['one'] = ['finding']
        case.pressure_targets = {'B', 'C'}
        case.requests = [{'group': 'one', 'role': 'B', 'body': {'messages': [
            {'role': 'user', 'content': f"Team members: {case.ids['A']}, {case.ids['B']}\nFrom {case.ids['B']}: finding"}]}}]
        with self.assertRaisesRegex(AssertionError, 'sender identity'):
            case.check_pressure_input('one', 'B')

    def test_explicit_adjacent_sender_headers_allow_separate_body(self):
        for header in ['Message from {sender}:',
                       'Teammate message from {sender}. The following message is its complete body.',
                       '来自 {sender} 的消息，下一条为完整正文。',
                       '{{"sender": "{sender}"}}']:
            with self.subTest(header=header):
                case = self.delivery_case()
                messages = [
                    {'role': 'user', 'content': header.format(sender=case.ids['A'])},
                    {'role': 'user', 'content': '完整正文\n发现🙂'},
                ]
                case.check_input('one', 'B', messages, ['完整正文\n发现🙂'], 'A')

    def test_separate_sender_header_must_be_attribution_not_a_roster(self):
        case = self.delivery_case()
        for header in [case.ids['A'], 'Available teammate: ' + case.ids['A'],
                       'Message from ' + case.ids['B'] + ':',
                       'Message from ' + case.ids['A'] + ': an earlier unrelated note',
                       'Message from ' + case.ids['A'] + ' or ' + case.ids['B'] + ':']:
            with self.subTest(header=header), self.assertRaisesRegex(AssertionError, 'sender identity'):
                case.check_input('one', 'B', [
                    {'role': 'user', 'content': header},
                    {'role': 'user', 'content': 'finding'},
                ], ['finding'], 'A')

    def test_sender_header_cannot_override_body_identity_or_skip_an_entry(self):
        case = self.delivery_case()
        header = {'role': 'user', 'content': 'Message from ' + case.ids['A'] + ':'}
        for tail in [
            [{'role': 'user', 'content': 'Message from ' + case.ids['B'] + ': finding'}],
            [{'role': 'tool', 'content': 'Unrelated work completed.'},
             {'role': 'user', 'content': 'finding'}],
        ]:
            with self.subTest(tail=tail), self.assertRaisesRegex(AssertionError, 'sender identity'):
                case.check_input('one', 'B', [header, *tail], ['finding'], 'A')

    def test_pressure_uses_the_same_adjacent_sender_association(self):
        case = Case('broadcast_pressure')
        case.payloads['one'] = ['finding']
        case.pressure_targets = {'B', 'C'}
        case.requests = [{'group': 'one', 'role': 'B', 'body': {'messages': [
            {'role': 'user', 'content': 'Message from ' + case.ids['A'] + ':'},
            {'role': 'user', 'content': 'finding'}]}}]
        case.check_pressure_input('one', 'B')

    def test_pressure_observation_distinguishes_history_from_duplicate_insertion(self):
        case = Case('broadcast_pressure')
        case.payloads['one'] = ['finding']
        case.pressure_targets = {'B', 'C'}
        message = {'role': 'user', 'content': 'From ' + case.ids['A'] + ': finding'}
        request = {'group': 'one', 'role': 'B', 'body': {'messages': [message]}}
        case.requests = [request, request]
        case.check_pressure_input('one', 'B')
        case.requests.append({'group': 'one', 'role': 'B', 'body': {'messages': [message, message]}})
        with self.assertRaisesRegex(AssertionError, 'duplicated'):
            case.check_pressure_input('one', 'B')

    def test_pressure_acceptance_requires_body_and_sender_in_real_input(self):
        case = Case('broadcast_pressure')
        case.payloads['one'] = ['finding']
        case.pressure_targets = {'B', 'C'}
        with self.assertRaisesRegex(AssertionError, 'absent'):
            case.check_pressure_input('one', 'B')
        case.requests = [{'group': 'one', 'role': 'B', 'body': {'messages': [
            {'role': 'user', 'content': 'From ' + case.ids['B'] + ': finding'}]}}]
        with self.assertRaisesRegex(AssertionError, 'sender identity'):
            case.check_pressure_input('one', 'B')
        case.pressure_targets = set()
        case.prefill_calls = {'call': 'queued payload'}
        case.requests = [{'group': 'one', 'role': 'C', 'body': {'messages': [
            {'role': 'user', 'content': 'From ' + case.ids['A'] + ': queued payload'}]}}]
        with self.assertRaisesRegex(AssertionError, 'rejected or private'):
            case.check_pressure_input('one', 'C')

    def test_closed_socket_and_fifo_still_need_filesystem_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            endpoint = root / 'arbitrary-endpoint'
            with socket.socket(socket.AF_UNIX) as sock:
                sock.bind(str(endpoint))
            fifo = root / 'arbitrary-channel'
            os.mkfifo(fifo)
            self.assertEqual(retained_ipc_paths(root), sorted([str(endpoint), str(fifo)]))
            endpoint.unlink()
            fifo.unlink()
            self.assertEqual(retained_ipc_paths(root), [])

    def test_logs_and_symlink_targets_are_not_ipc_leaks(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            (root / 'pi-team-log').write_text('A retained communication log is allowed.')
            os.mkfifo(Path(outside) / 'unrelated-fifo')
            (root / 'other-run').symlink_to(outside, target_is_directory=True)
            (root / 'other-channel').symlink_to(Path(outside) / 'unrelated-fifo')
            self.assertEqual(retained_ipc_paths(root), [])

    def test_json_findings_allow_surrounding_guidance(self):
        for wrapper in ['{}\n{record}\nPlease continue.',
                        'From a teammate:\n```json\n{record}\n```\nPlease continue.',
                        '{record}']:
            with self.subTest(wrapper=wrapper):
                case = self.delivery_case()
                payload = '第一行\n第二行🙂 "quoted" \\path'
                record = json.dumps({'sender': case.ids['A'], 'text': payload})
                content = wrapper.replace('{record}', record)
                case.check_input('one', 'B', [{'role': 'user', 'content': content}], [payload], 'A')

    def test_separate_json_envelopes_preserve_order_and_duplicate_checks(self):
        case = self.delivery_case('ordered')
        payloads = ['First finding\n完整🙂', 'Second finding\n更正🙂']
        envelopes = [json.dumps({'sender': case.ids['A'], 'text': p}) for p in payloads]
        message = lambda parts: {'role': 'user', 'content': '\nPlease consider:\n'.join(parts) + '\nContinue.'}
        case.check_input('one', 'B', [message(envelopes)], payloads, 'A')
        with self.assertRaisesRegex(AssertionError, 'duplicat'):
            case.audit_input('one', 'B', [message(envelopes + [envelopes[0]])])
        with self.assertRaisesRegex(AssertionError, 'order'):
            case.check_input('one', 'B', [message(envelopes[::-1])], payloads, 'A')

    def test_json_guidance_does_not_hide_wrong_sender_or_changed_body(self):
        case = self.delivery_case()
        payload = 'Original line\n原文🙂'
        for changed in [payload[:-1], payload.replace('\n', ' '), payload.replace('原文', '改写')]:
            with self.subTest(changed=changed), self.assertRaises(AssertionError):
                content = json.dumps({'sender': case.ids['A'], 'text': changed}) + '\nContinue.'
                case.check_input('one', 'B', [{'role': 'user', 'content': content}], [payload], 'A')
        with self.assertRaisesRegex(AssertionError, 'sender identity'):
            content = json.dumps({'sender': case.ids['B'], 'text': payload}) + '\nContinue.'
            case.check_input('one', 'B', [{'role': 'user', 'content': content}], [payload], 'A')

    def delivery_case(self, name='direct'):
        case = Case(name)
        case.event('one', 'B', 'tool_end:slow_work')
        return case

    def test_failure_entries_need_ids_and_reasons(self):
        for failed in [['anything'], [{'id': 'B'}], [{'id': 'B', 'reason': ''}],
                       [{'id': 'B', 'reason': 'closed'}, {'id': 'B', 'reason': 'again'}]]:
            with self.subTest(failed=failed):
                self.assertFalse(invalid_rejected({'accepted': [], 'failed': failed}))
        self.assertTrue(invalid_rejected({'accepted': [], 'failed': [{'id': 'B', 'reason': 'closed'}]}))

    def test_sender_is_an_address_not_a_letter_in_agent(self):
        case = self.delivery_case()
        with self.assertRaisesRegex(AssertionError, 'sender identity'):
            case.check_input('one', 'B', [{'role': 'user', 'content': 'Agent B says: finding'}], ['finding'], 'A')

    def test_finished_sender_does_not_invalidate_accepted_delivery(self):
        case = self.delivery_case('completion_boundary')
        case.event('one', 'A', 'session_shutdown')
        case.check_input('one', 'B', [{'role': 'user', 'content': 'From ' + case.ids['A'] + ': finding'}], ['finding'], 'A')

    def test_assistant_role_delivery_and_model_quote_are_distinct(self):
        case = self.delivery_case()
        messages = [{'role': 'assistant', 'content': 'From ' + case.ids['A'] + ': finding'}]
        case.check_input('one', 'B', messages, ['finding'], 'A')
        case.model_texts[('one', 'B')] = {'I used finding in my answer.'}
        messages.append({'role': 'assistant', 'content': 'I used finding in my answer.'})
        case.audit_input('one', 'B', messages)
        case.audit_input('one', 'B', messages)  # Existing history is not redelivery.
        with self.assertRaisesRegex(AssertionError, 'duplicat'):
            case.audit_input('one', 'B', messages + [messages[0]])

    def test_broadcast_must_not_insert_an_incoming_copy_for_sender(self):
        case = Case('broadcast')
        payload = case.payloads['one'][0]
        messages = [{'role': 'tool', 'toolName': 'test_work', 'content': payload}]
        case.audit_input('one', 'A', messages)
        with self.assertRaisesRegex(AssertionError, 'broadcast delivered to sender'):
            case.audit_input('one', 'A', messages + [{'role': 'user', 'content': payload}])

    def test_foreign_reply_is_private_too(self):
        case = self.delivery_case('isolation')
        with self.assertRaisesRegex(AssertionError, 'across teams'):
            case.check_input('one', 'B', [{'role': 'user', 'content': 'From ' + case.ids['A'] + ': finding\n' + case.replies['two']}], ['finding'], 'A')

    def test_rejected_request_must_not_deliver(self):
        case = self.delivery_case('malformed')
        with self.assertRaisesRegex(AssertionError, 'rejected'):
            case.check_input('one', 'B', [{'role': 'user', 'content': 'From ' + case.ids['A'] + ': finding\nno recipient'}], ['finding'], 'A')

    def test_duplicate_in_a_later_model_call_is_rejected(self):
        case = self.delivery_case()
        case.pids[('one', 'B')] = 123
        case.steps[('one', 'B')] = 3
        case.observed.add(('one', 'A'))
        p = case.payloads['one'][0]
        messages = [{'role': 'user', 'content': 'ROLE:B GROUP:one'},
                    {'role': 'user', 'content': 'From ' + case.ids['A'] + ': ' + p}]
        case.check_input('one', 'B', messages, [p], 'A')
        messages += [{'role': 'user', 'content': 'From ' + case.ids['A'] + ': ' + p},
                     {'role': 'tool', 'content': '{"accepted":["A"],"failed":[]}'}]
        with self.assertRaisesRegex(AssertionError, 'duplicat'):
            case.respond({'messages': messages, 'tools': [{'function': {'name': n}} for n in ['team_send', 'team_members']]}, 123)

    def test_submission_needs_no_curator_adapter(self):
        case = Case('direct')
        call = case.tool('team_send', {'to': 'peer-1', 'message': '发现🙂'})
        self.assertEqual(call['function']['name'], 'team_send')

    def test_queued_input_allows_continuation_but_still_rejects_duplicate_delivery(self):
        case = Case('queued_steering_ordered')
        case.pids[('one', 'B')] = 123
        case.steps[('one', 'B')] = 4
        case.completed.add(('one', 'B'))
        messages = [{'role': 'user', 'content': 'ROLE:B GROUP:one'},
                    {'role': 'user', 'content': 'From ' + case.ids['A'] + ': ' + '\n'.join(case.payloads['one'])}]
        case.check_input('one', 'B', messages, case.payloads['one'], 'A')
        body = {'messages': messages, 'tools': [{'function': {'name': n}} for n in ['team_send', 'team_members']]}
        self.assertIn('content', case.respond(body, 123))
        body['messages'] = messages + [messages[-1]]
        with self.assertRaisesRegex(AssertionError, 'duplicat'):
            case.respond(body, 123)

    def test_additive_fields_and_recipient_order_are_free(self):
        check_send_result({'accepted': ['C', 'B'], 'failed': [], 'queued': 2}, ['B', 'C'])
        check_send_result({'accepted': ['B'], 'failed': [{'id': 'C', 'reason': 'closed', 'code': 9}]}, ['B'], ['C'])

    def test_duplicate_or_contradictory_acceptance_is_not_success(self):
        for result in [
            {'accepted': ['B', 'B'], 'failed': []},
            {'accepted': ['B'], 'failed': [{'id': 'B', 'reason': 'closed'}]},
            {'accepted': ['B'], 'failed': [{'id': 'C', 'reason': ''}]},
            {'accepted': ['B'], 'failed': [{'id': 'C', 'reason': 1}]},
            {'delivered': ['B'], 'rejected': []},
        ]:
            with self.subTest(result=result), self.assertRaises(AssertionError):
                check_send_result(result, ['B'])

    def test_size_probe_uses_utf8_bytes_and_keeps_end_markers(self):
        for name, length in [('size_below', 65535), ('size_at', 65536), ('size_over', 65537)]:
            case = Case(name)
            self.assertIsNotNone(case.oversize, 'large probes must allow explicit rejection')
            payload = case.oversize
            self.assertEqual(len(payload.encode('utf8')), length)
            self.assertTrue(payload.startswith('开头'))
            self.assertTrue(payload.endswith('🙂结尾'))


if __name__ == '__main__':
    unittest.main()
