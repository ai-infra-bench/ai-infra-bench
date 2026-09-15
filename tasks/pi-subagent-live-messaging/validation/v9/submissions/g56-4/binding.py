import re
from binding import Binding as ReferenceBinding


class Binding(ReferenceBinding):
    def encode(self, operation, arguments, group):
        args = dict(arguments)
        if operation == 'team_members':
            return 'subagent_teammates', args
        if operation == 'team_send':
            if args.pop('broadcast', False):
                return 'subagent_broadcast', args
            if 'to' in args:
                args['recipient'] = args.pop('to')
            return 'subagent_send', args
        return operation, args

    def decode(self, operation, result, group):
        if not isinstance(result, str):
            return result
        if operation == 'team_members':
            own = re.search(r'^You are (.+?) \(agent: (.+?)\)\.$', result, re.M)
            if not own:
                return result
            members = [{'id': own[1], 'agent': own[2]}]
            members += [{'id': m[1], 'agent': m[2]} for m in re.finditer(r'^- (.+?) \((.+?), ([^)]+)\):', result, re.M)]
            return {'self': own[1], 'members': members}
        if operation in ['team_send', 'subagent_broadcast']:
            accepted = re.search(r'^Accepted: (.+)$', result, re.M)
            failed = [{'id': m[1], 'reason': m[2]} for m in re.finditer(r'^- ([^:]+): (.+)$', result, re.M)]
            if accepted or failed:
                return {'accepted': accepted[1].split(', ') if accepted else [], 'failed': failed}
            if result == 'Message must not be empty.' or result.startswith(('Invalid send request:', 'Invalid broadcast request:', 'Message is ')):
                return {'error': result}
        return result

    def invalid_rejected(self, result):
        return (isinstance(result, dict) and bool(result.get('error'))) or super().invalid_rejected(result)

    def malformed_sends(self):
        return [{'message': 'no recipient'}, {'to': {}, 'message': 'invalid address type'},
                {'to': 'B', 'message': ''}, {'to': 'B', 'message': {'unexpected': True}}]
