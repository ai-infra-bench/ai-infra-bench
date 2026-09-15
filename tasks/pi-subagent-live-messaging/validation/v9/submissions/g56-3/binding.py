import re
from binding import Binding as ReferenceBinding


class Binding(ReferenceBinding):
    def __init__(self):
        self.agents = {}

    def encode(self, operation, arguments, group):
        args = dict(arguments)
        if operation == 'subagent':
            for t in args.get('tasks', []):
                match = re.search(r'GROUP:([a-z]+)', t.get('task', ''))
                dispatch_group = match[1] if match else group
                self.agents.setdefault(dispatch_group, {})[t['id']] = t['agent']
        if operation == 'team_members':
            return 'team_list', args
        if operation == 'team_send':
            if args.pop('broadcast', False):
                return 'team_broadcast', args
            if 'to' in args:
                args['recipient'] = args.pop('to')
        return operation, args

    def decode(self, operation, result, group):
        if not isinstance(result, str):
            return result
        if operation == 'team_members':
            own = re.fullmatch(r'You are (.+?)\. Running teammates: (.*)\.', result)
            if own:
                members = [{'id': own[1], 'agent': self.agents[group][own[1]]}]
                members += [{'id': m[1], 'agent': m[2]} for m in re.finditer(r'(?:^|, )([^(),]+) \(([^()]+)\)', own[2])]
                return {'self': own[1], 'members': members}
        if operation in ['team_send', 'team_broadcast']:
            receipt = re.fullmatch(r'Accepted for delivery: (.*?)\.(?: Failed: (.*)\.)?', result)
            if receipt:
                failed = [{'id': m[1], 'reason': m[2]} for m in re.finditer(r'(?:^|, )([^(),]+) \(([^()]+)\)', receipt[2] or '')]
                return {'accepted': [] if receipt[1] == 'none' else receipt[1].split(', '), 'failed': failed}
            if result == 'Message must be a non-empty string.' or re.fullmatch(r'Message is [0-9]+ bytes; maximum supported size is [0-9]+ bytes\.', result):
                return {'error': result}
        return result

    def invalid_rejected(self, result):
        return (isinstance(result, dict) and bool(result.get('error'))) or super().invalid_rejected(result)

    def malformed_sends(self):
        return [{'message': 'no recipient'}, {'to': {}, 'message': 'invalid address type'},
                {'to': 'B', 'message': ''}, {'to': 'B', 'message': {'unexpected': True}}]
