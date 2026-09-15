from binding import Binding as ReferenceBinding


def address(role):
    return f'worker-{ord(role) - ord("A") + 1}' if isinstance(role, str) and role in 'ABCDE' and len(role) == 1 else role


def role(address):
    return chr(ord('A') + int(address[7:]) - 1) if isinstance(address, str) and address in [f'worker-{i}' for i in range(1, 6)] else address


class Binding(ReferenceBinding):
    def encode(self, operation, arguments, group):
        args = dict(arguments)
        if operation == 'subagent' and 'tasks' in args:
            args['tasks'] = [{k: v for k, v in task.items() if k != 'id'} for task in args['tasks']]
        if operation == 'team_send':
            if 'message' in args:
                args['text'] = args.pop('message')
            if args.pop('broadcast', False):
                args['to'] = '*'
            if 'to' in args:
                args['to'] = address(args['to'])
        return operation, args

    def decode(self, operation, result, group):
        if isinstance(result, str) and result.startswith('No teammates match recipient '):
            return {'accepted': [], 'failed': [{'id': role(result.removeprefix('No teammates match recipient ')), 'reason': result}]}
        if not isinstance(result, dict):
            return result
        if result.get('kind') == 'roster':
            return {'self': role(result['self']), 'members': [dict(m, id=role(m['id'])) for m in result['workers']]}
        if result.get('kind') == 'sent':
            return {'accepted': [role(x) for x in result['accepted']], 'failed': [
                {'id': role(x['id']), 'reason': x['reason']} for x in result['failed']]}
        return result

    def sender_identity(self, group, worker_role):
        return address(worker_role)

    def invalid_rejected(self, result):
        return (isinstance(result, dict) and result.get('kind') == 'error' and bool(result.get('error'))) or super().invalid_rejected(result)

    def malformed_sends(self):
        return [{'message': 'no recipient'}, {'to': {}, 'message': 'invalid address type'},
                {'to': 'B', 'message': ''}, {'to': 'B', 'message': {'unexpected': True}}]
