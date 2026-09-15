"""Public interface mapping for frozen G6 submission f9f34e0e…; no delivery logic."""
from binding import Binding as ReferenceBinding

class Binding(ReferenceBinding):
    def encode(self, operation, arguments, group):
        args = dict(arguments)
        if operation == 'team_send':
            if 'message' in args:
                args['text'] = args.pop('message')
            if args.pop('broadcast', False):
                args['to'] = '*'
        return operation, args

    def invalid_rejected(self, result):
        return (isinstance(result, dict) and result.get('kind') == 'error' and bool(result.get('error'))) or super().invalid_rejected(result)

    def malformed_sends(self):
        return [{'message':'no recipient'}, {'to':{},'message':'invalid address type'},
                {'to':'B','message':''}, {'to':'B','message':{'unexpected':True}}]
