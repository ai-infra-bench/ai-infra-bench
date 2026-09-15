from binding import Binding as ReferenceBinding

class Binding(ReferenceBinding):
    def encode(self, operation, arguments, group):
        args = dict(arguments)
        if operation == 'subagent' and 'communication' in args:
            args['collaborate'] = args.pop('communication')
        if operation == 'team_send' and 'to' in args:
            args['recipient'] = args.pop('to')
        return {'team_members':'colleagues', 'team_send':'share'}.get(operation, operation), args

    def decode(self, operation, result, group):
        if operation == 'team_send':
            return {'accepted':result['queued'], 'failed':result['rejected']}
        return result
