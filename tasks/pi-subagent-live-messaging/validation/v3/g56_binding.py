"""Public tool mapping for G56 submission 19220b33…; no transport/context logic."""
from binding import Binding as ReferenceBinding


class Binding(ReferenceBinding):
    def encode(self, operation, arguments, group):
        args = dict(arguments)
        if operation == 'team_members':
            return 'team_list', args
        if operation == 'team_send':
            if args.pop('broadcast', False):
                return 'team_broadcast', args
            if 'to' in args:
                args['recipient'] = args.pop('to')
        return operation, args

    def decode(self, operation, result, group):
        if not isinstance(result, dict):
            return result
        if operation == 'team_members' and isinstance(result.get('self'), dict):
            return {'self': result['self']['id'], 'members': [result['self'], *result['teammates']]}
        if operation == 'team_send' and isinstance(result.get('accepted'), bool):
            if result['accepted']:
                return {'accepted': [result['recipient']], 'failed': []}
            return {'accepted': [], 'failed': [{'id': result.get('recipient'), 'reason': result.get('error')}]}
        if operation == 'team_broadcast' and isinstance(result.get('accepted'), list):
            return {'accepted': result['accepted'], 'failed': [
                {'id': item['recipient'], 'reason': item['error']} for item in result['failed']]}
        return result

    def malformed_sends(self):
        return [{'message': 'no recipient'}, {'to': {}, 'message': 'invalid address type'},
                {'to': 'B', 'message': ''}, {'to': 'B', 'message': {'unexpected': True}}]
