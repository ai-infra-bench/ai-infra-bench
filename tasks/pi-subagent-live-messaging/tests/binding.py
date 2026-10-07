"""The public tool interface pinned by instruction.md. Never accesses or injects recipient context.

Tool names, arguments and result shapes are identical to the instruction, so
encode/decode are identities. No candidate code is imported here.
"""


class Binding:
    def encode(self, operation, arguments, group):
        return operation, arguments

    def decode(self, operation, result, group):
        return result

    def sender_identity(self, group, role):
        return role

    def tool_name(self, operation):
        return self.encode(operation, {}, 'one')[0]

    def invalid_rejected(self, result):
        return isinstance(result, dict) and result.get("accepted") == [] and bool(result.get("failed"))

    def malformed_sends(self):
        return [{'message':'no recipient'}, {'to':'B','broadcast':True,'message':'ambiguous'},
                {'to':'B','broadcast':False,'message':'ambiguous false'},
                {'to':'B','message':{'unexpected':True}}]
