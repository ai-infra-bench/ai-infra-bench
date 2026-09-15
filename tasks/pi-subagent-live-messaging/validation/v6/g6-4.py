from binding import Binding as ReferenceBinding


class Binding(ReferenceBinding):
    def encode(self, operation, arguments, group):
        args = dict(arguments)
        if operation == 'team_members':
            return 'team_list', args
        if operation == 'team_send':
            if 'message' in args:
                args['text'] = args.pop('message')
            if args.pop('broadcast', False):
                return 'team_broadcast', args
        return operation, args

    def decode(self, operation, result, group):
        if isinstance(result, dict) and result.get('kind') == 'delivery':
            return {'accepted': result['accepted'], 'failed': [
                {'id': x['to'], 'reason': x['reason']} for x in result['failed']]}
        return result

    def invalid_rejected(self, result):
        return (isinstance(result, dict) and result.get('kind') == 'error' and bool(result.get('error'))) or super().invalid_rejected(result)

    def malformed_sends(self):
        return [{'message': 'no recipient'}, {'to': {}, 'message': 'invalid address type'},
                {'to': 'B', 'message': ''}, {'to': 'B', 'message': {'unexpected': True}}]
