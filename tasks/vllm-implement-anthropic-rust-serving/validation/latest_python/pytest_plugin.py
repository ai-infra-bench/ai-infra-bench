"""Change server plumbing only; keep the existing requests and assertions."""

from adapter import PythonServer


def pytest_collection_modifyitems(items):
    for item in items:
        if hasattr(item.module, "RustServer"):
            item.module.RustServer = PythonServer
