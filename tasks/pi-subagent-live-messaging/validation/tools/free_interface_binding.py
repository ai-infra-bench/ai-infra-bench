from binding import Binding as Base
class Binding(Base):
    def encode(self, operation, arguments, group):
        args = dict(arguments)
        if operation == 'subagent' and 'communication' in args:
            args['collaboration'] = args.pop('communication')
        if operation == 'team_send' and 'message' in args:
            args['body'] = args.pop('message')
        return {'team_members':'crew_roster','team_send':'crew_send'}.get(operation,operation), args
    def decode(self, operation, result, group):
        if not isinstance(result,dict): return result
        if operation == 'team_members':
            return {'self':result['me'],'members':[{'id':m['address']} for m in result['peers']]}
        if operation == 'team_send':
            return {'accepted':result['delivered'],'failed':result['rejected']}
        return result
