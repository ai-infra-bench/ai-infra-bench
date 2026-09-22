"""Curator-owned call adapter. Never accesses or injects recipient context.

An adapter describes one implementation's documented public interface. It is
selected explicitly by the reviewer, never imported from candidate source.
"""
import json


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
                {'to':'B','message':''}, {'to':'B','message':{'unexpected':True}}]


def load_binding(path):
    if path is None:
        return Binding()
    import importlib.util
    spec = importlib.util.spec_from_file_location('reviewed_binding', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Binding()
