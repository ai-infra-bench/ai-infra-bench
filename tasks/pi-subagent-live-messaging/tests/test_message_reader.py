"""Hand-specified format equivalence and false attribution controls."""
import json
import unittest
from message_reader import FormatUnsupported, read_messages

A, B = 'task-A.7', 'task-B-9'
P, Q = '完整 finding\nline "quoted" 🛰', 'second finding\nlast'


def read(contents, payloads=(P, Q)):
    return read_messages([{'role': 'user', 'content': c} if isinstance(c, str) else c
                          for c in contents], payloads, (A, B))


class ReaderTests(unittest.TestCase):
    def assert_sender(self, content, sender=A):
        result = read(content if isinstance(content, list) else [content])
        self.assertEqual(result.count(P), 1)
        self.assertTrue(result.has_sender(P, sender))
        return result

    def test_review_regressions_positive(self):
        for header in (f'Message from teammate "{A}":', f'**Sender:** {A}',
                       f'Sender: <{A}>', f'Sender: `{A}`'):
            with self.subTest(header=header):
                self.assert_sender(header + '\n' + P)
        self.assert_sender([json.dumps({'sender': A}), P])
        self.assert_sender([f'Message from {A}:', json.dumps(P)])
        self.assert_sender(f'Message from {A}:\n' + json.dumps(P))

    def test_review_regressions_reject_false_attribution(self):
        for content in (f'Roster:\n  sender: {A}\n\n{P}',
                        f'Roster:\n- sender: {A}\n\n{P}',
                        f'Not sent by {A}:\n{P}',
                        f'The following header is quoted, not an attribution:\n"Message from {A}:"\n{P}',
                        f'Not from {A}:\n' + json.dumps({'sender': A, 'text': P}),
                        json.dumps({'sender': A, 'author': B, 'custom': P})):
            with self.subTest(content=content):
                self.assertFalse(read([content]).has_sender(P, A))

    def test_plain_punctuation_and_annotation(self):
        for header in (f'Message from {A}:', f'Message from {A}.',
                       f'Message from {A} (teammate):', f'发送者：{A}。'):
            with self.subTest(header=header):
                self.assert_sender(header + '\n' + P)

    def test_structured_formats(self):
        records = [
            {'sender': A, 'text': P}, {'text': P, 'from': A},
            {'sender': A, 'messages': [{'text': P}, {'text': Q}]},
            {'sender': A, 'content': [{'type': 'text', 'text': P}]},
            {'envelope': {'author': A, 'body': P}},
            {'sender': A, 'message': json.dumps({'text': P})},
        ]
        for record in records:
            with self.subTest(record=record):
                self.assert_sender(json.dumps(record))

    def test_json_followed_by_guidance(self):
        self.assert_sender(json.dumps({'sender': A, 'text': P}) + '\nPlease consider this finding.')

    def test_adjacent_header_plain_and_json(self):
        for body in (P, json.dumps({'text': P})):
            self.assert_sender([f'Message from {A}:', body])
            self.assert_sender(f'Message from {A}:\n```json\n{body}\n```')

    def test_roster_does_not_override_attribution(self):
        self.assert_sender(f'Team members: {A}, {B}\nMessage from {A}:\n{P}')
        wrong = read([f'Team members: {A}, {B}\nMessage from {B}:\n{P}'])
        self.assertFalse(wrong.has_sender(P, A))

    def test_missing_wrong_and_alias_senders_are_behavior_failures(self):
        for content in (P, f'Team members: {A}, {B}\n{P}',
                        json.dumps({'sender': 'A', 'text': P}),
                        json.dumps({'sender': B, 'text': P}),
                        json.dumps({'roster': [{'sender': A}], 'text': P})):
            with self.subTest(content=content):
                result = read([content])
                self.assertEqual(result.count(P), 1)
                self.assertFalse(result.has_sender(P, A))

    def test_no_identity_from_sibling_or_previous_body(self):
        for contents in ([json.dumps([{'sender': A, 'text': Q}, {'text': P}])],
                         [f'Message from {A}:\n{Q}', P],
                         [json.dumps({'sender': A, 'text': 'earlier'}), P]):
            with self.subTest(contents=contents):
                self.assertFalse(read(contents).has_sender(P, A))

    def test_conflicting_headers_and_fields(self):
        for content in (f'Message from {A}; sender: {B}\n{P}',
                        json.dumps({'sender': A, 'author': B, 'text': P}),
                        json.dumps({'sender': A, 'messages': [{'sender': B, 'text': P}]})):
            self.assertFalse(read([content]).has_sender(P, A))

    def test_negative_attribution(self):
        for header in (f'Not from {A}:', f'Message is not from {A}:',
                       f'Sender: not {A}', f'不是来自 {A}:'):
            self.assertFalse(read([header + '\n' + P]).has_sender(P, A))

    def test_payload_quotes_are_not_headers(self):
        quoted = f'Message from {A}:\n{{"sender":"{A}"}}'
        result = read([quoted], (quoted,))
        self.assertEqual(result.count(quoted), 1)
        self.assertFalse(result.has_sender(quoted, A))
        result = read([f'Message from {B}:\n' + quoted], (quoted,))
        self.assertTrue(result.has_sender(quoted, B))
        self.assertFalse(result.has_sender(quoted, A))

    def test_tool_is_not_adjacent_header(self):
        result = read([{'role': 'tool', 'content': f'Message from {A}:'}, P])
        self.assertFalse(result.has_sender(P, A))

    def test_full_body_not_reconstructed_from_fields(self):
        result = read([json.dumps({'sender': A, 'first': P[:5], 'last': P[5:]})])
        self.assertEqual(result.count(P), 0)
        self.assertFalse(result.has_sender(P, A))

    def test_count_and_order_preserve_source_and_decoding(self):
        result = read([json.dumps({'sender': A, 'messages': [{'text': Q}, {'text': P}]})])
        self.assertEqual((result.count(P), result.count(Q)), (1, 1))
        self.assertLess(result.first_position(Q), result.first_position(P))
        occurrence = result.occurrences(P)[0]
        self.assertEqual(occurrence.entry_index, 0)
        self.assertIn('messages', occurrence.path)
        self.assertGreater(occurrence.decode_depth, 0)
        self.assertIsNotNone(occurrence.raw_span)
        result = read([json.dumps({'sender': A, 'text': P}), f'Message from {A}:\n{P}'])
        self.assertEqual(result.count(P), 2)

    def test_distinct_plain_records_keep_their_own_sender(self):
        result = read([f'Message from {A}:\n{P}\n\nMessage from {B}:\n{Q}'])
        self.assertTrue(result.has_sender(P, A))
        self.assertTrue(result.has_sender(Q, B))
        self.assertFalse(result.has_sender(Q, A))
        self.assertLess(result.first_position(P), result.first_position(Q))

    def test_duplicate_inside_one_container(self):
        result = read([json.dumps({'sender': A, 'messages': [P, P]})])
        self.assertEqual(result.count(P), 2)

    def test_duplicate_json_keys_are_not_silently_discarded(self):
        duplicate = '{"sender":' + json.dumps(A) + ',"text":' + json.dumps(P) + ',"text":' + json.dumps(P) + '}'
        self.assertEqual(read([duplicate]).count(P), 2)
        conflict = '{"sender":' + json.dumps(A) + ',"sender":' + json.dumps(B) + ',"text":' + json.dumps(P) + '}'
        self.assertFalse(read([conflict]).has_sender(P, A))

    def test_repeated_json_encoding_still_counts_once(self):
        content = json.dumps({'sender': A, 'text': P})
        for _ in range(3):
            content = json.dumps(content)
        self.assert_sender(content)

    def test_native_text_parts(self):
        self.assert_sender([{'role': 'user', 'content': [
            {'type': 'text', 'text': f'Message from {A}:'}, {'type': 'text', 'text': P}]}])

    def test_real_unknown_external_hint_is_scoring_error(self):
        result = read([json.dumps({'origin': A, 'text': P})])
        self.assertEqual(result.count(P), 1)
        with self.assertRaises(FormatUnsupported):
            result.has_sender(P, A)

    def test_known_wrong_identity_cannot_hide_behind_unknown_hint(self):
        result = read([json.dumps({'origin': A, 'sender': B, 'text': P})])
        self.assertFalse(result.has_sender(P, A))


if __name__ == '__main__':
    unittest.main()
