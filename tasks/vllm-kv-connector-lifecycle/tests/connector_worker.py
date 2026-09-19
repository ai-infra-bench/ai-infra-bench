#!/usr/bin/env python3
"""Unprivileged adapter: invoke real public APIs and return observations, never scores.

The parent owns the test sequence and expected results. stdout is only a log.
Each request is a single public operation, so exiting cannot complete later checks.
"""
from __future__ import annotations

import json
import socket
import sys
from types import ModuleType, SimpleNamespace

channel = socket.socket(fileno=int(sys.argv[1]))
sys.path.insert(0, sys.argv[2])

import torch
from vllm.distributed.kv_transfer.kv_connector.factory import KVConnectorFactory
from vllm.distributed.kv_transfer.kv_connector.v1 import KVConnectorBase_V1, KVConnectorRole
from vllm.distributed.kv_transfer.kv_transfer_state import (
    ensure_kv_transfer_initialized, ensure_kv_transfer_shutdown,
    get_kv_transfer_group, has_kv_transfer_group,
)
from vllm.v1.kv_cache_interface import (
    FullAttentionSpec, KVCacheConfig, KVCacheGroupSpec, KVCacheTensor,
)

configs = {}
instances = []  # Retain identities across shutdown, avoiding Python id reuse.
events = []
active = {}


def observe(event, instance, config=None, role=None):
    entry = {"event": event, "instance": id(instance)}
    if event == "construct":
        entry.update(
            config=next((key for key, value in configs.items() if value is config), None),
            blocks=getattr(config, "num_blocks", None),
            groups=len(getattr(config, "kv_cache_groups", ())),
            tensors=len(getattr(config, "kv_cache_tensors", ())),
            role=role.name,
        )
        instances.append(instance)
    events.append(entry)


class Minimal(KVConnectorBase_V1):
    def get_num_new_matched_tokens(self, request, num_computed_tokens):
        return 0, False

    def update_state_after_alloc(self, request, blocks, num_external_tokens):
        pass

    def build_connector_meta(self, scheduler_output):
        return None

    def start_load_kv(self, forward_context, **kwargs):
        pass

    def wait_for_layer_load(self, layer_name):
        pass

    def save_kv_layer(self, layer_name, kv_layer, attn_metadata, **kwargs):
        pass

    def wait_for_save(self):
        pass


class Current(Minimal):
    def __init__(self, vllm_config, role, kv_cache_config):
        observe("construct", self, kv_cache_config, role)
        super().__init__(vllm_config, role, kv_cache_config)

    def shutdown(self):
        observe("shutdown", self)


class Inherited(Current):
    pass


class Defaulted(Current):
    def __init__(self, vllm_config, role, kv_cache_config=None):
        super().__init__(vllm_config, role, kv_cache_config)


class Forwarded(Current):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class Legacy(Minimal):
    def __init__(self, vllm_config, role):
        observe("construct", self, role=role)
        super().__init__(vllm_config, role)


class BindingError(Current):
    def __init__(self, vllm_config, role, kv_cache_config, *, transport):
        super().__init__(vllm_config, role, kv_cache_config)


class Exploding(Current):
    def __init__(self, vllm_config, role, kv_cache_config):
        observe("construct", self, kv_cache_config, role)
        raise active["exception"]


module = ModuleType("external_connector_contract")
for cls in (Current, Inherited, Defaulted, Forwarded, Legacy, BindingError, Exploding):
    setattr(module, cls.__name__, cls)
sys.modules[module.__name__] = module


def engine_config(command):
    name = command.get("plugin", "Current")
    path = module.__name__
    if command.get("registry"):
        name = command["registry"]
        path = None
    return SimpleNamespace(
        kv_transfer_config=SimpleNamespace(
            kv_connector=name, kv_connector_module_path=path,
            engine_id=command["id"], is_kv_transfer_instance=True,
        ),
        scheduler_config=SimpleNamespace(disable_hybrid_kv_cache_manager=True),
    )


def invoke(command):
    op = command["op"]
    if op == "config":
        blocks = command["blocks"]
        spec = FullAttentionSpec(block_size=16, num_kv_heads=1, head_size=8, dtype=torch.float16)
        configs[command["key"]] = KVCacheConfig(
            num_blocks=blocks,
            kv_cache_tensors=[KVCacheTensor(size=blocks * spec.page_size_bytes, shared_by=["layer.0"])],
            kv_cache_groups=[KVCacheGroupSpec(layer_names=["layer.0"], kv_cache_spec=spec)],
        )
        return {"stored": command["key"]}
    if op == "register":
        KVConnectorFactory.register_connector(command["name"], module.__name__, command["plugin"])
        return None
    if op == "shutdown":
        ensure_kv_transfer_shutdown()
        return {"has_group": has_kv_transfer_group()}
    config = engine_config(command)
    role = KVConnectorRole[command.get("role", "WORKER")]
    if op == "base_missing_config":
        Minimal(config, role)
        return None
    cache = configs[command["key"]]
    if op == "initialize":
        ensure_kv_transfer_initialized(config, cache)
        obj = get_kv_transfer_group()
    elif op == "create":
        if command.get("exception"):
            cls = {"TypeError": TypeError, "ValueError": ValueError, "RuntimeError": RuntimeError}[command["exception"]]
            active["exception"] = cls(command["message"])
        obj = KVConnectorFactory.create_connector(config, role, cache)
    else:
        raise ValueError(f"Unknown test operation {op}")
    return {"instance": id(obj), "role": getattr(getattr(obj, "role", None), "name", None),
            "plugin": isinstance(obj, getattr(module, command.get("plugin", "Current")))}


channel.send(json.dumps({"ready": True}).encode())
while packet := channel.recv(1 << 20):
    command = json.loads(packet)
    start = len(events)
    try:
        value = invoke(command)
        error = None
    except Exception as exc:
        value = None
        error = {"type": type(exc).__name__, "message": str(exc)}
    channel.send(json.dumps({"id": command["id"], "value": value,
                             "error": error, "events": events[start:]}).encode())
