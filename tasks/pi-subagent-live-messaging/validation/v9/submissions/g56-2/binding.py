"""Translate documented public text receipts; no delivery or context changes."""
import re
from binding import Binding as ReferenceBinding


class Binding(ReferenceBinding):
    def __init__(self):
        self.last_target = {}

    def encode(self, operation, arguments, group):
        args = dict(arguments)
        if operation == 'team_members':
            return 'team_list', args
        if operation == 'team_send':
            if args.pop('broadcast', False):
                return 'team_broadcast', args
            if 'to' in args:
                args['recipient'] = args.pop('to')
                self.last_target[group] = args['recipient']
        return operation, args

    def decode(self, operation, result, group):
        if operation == 'team_members' and isinstance(result, dict):
            return {'self': result['self']['id'], 'members': [result['self'], *result['teammates']]}
        if isinstance(result, str) and operation in ['team_send', 'team_broadcast']:
            accepted = re.fullmatch(r'Message accepted for delivery to: (.+)\.', result)
            if accepted:
                return {'accepted': accepted[1].split(', '), 'failed': []}
            if result.startswith('Message not accepted: '):
                reason = result[len('Message not accepted: '):]
                target = re.fullmatch(r'(?:unknown teammate|teammate is not running): (.+)\.', reason)
                recipient = target[1] if target else None
                if reason == 'cannot send a message to yourself.':
                    recipient = self.last_target.get(group)
                return {'accepted': [], 'failed': [{'id': recipient, 'reason': reason}]}
        return result

    def malformed_sends(self):
        return [{'message': 'no recipient'}, {'to': {}, 'message': 'invalid address type'},
                {'to': 'B', 'message': ''}, {'to': 'B', 'message': {'unexpected': True}}]
