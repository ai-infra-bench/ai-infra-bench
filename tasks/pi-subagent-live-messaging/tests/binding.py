"""Curator-owned call adapter. Never accesses or injects recipient context.

An adapter describes one implementation's documented public interface. It is
selected explicitly by the reviewer, never imported from candidate source.
"""
import json
from profile import IntegrationNeeded


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
                {'to':'B','message':{'unexpected':True}}]


def load_binding(path):
    if path is None:
        raise IntegrationNeeded('An explicit reviewed public-interface binding is required')
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location('reviewed_binding', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.Binding()
    except IntegrationNeeded:
        raise
    except Exception as exc:
        # This is curator code selected by the sealed profile, not a candidate
        # behavior check. Runtime encode/decode calls remain outside this guard.
        raise IntegrationNeeded(f'Cannot load reviewed interface binding {path}: {type(exc).__name__}: {exc}') from exc
