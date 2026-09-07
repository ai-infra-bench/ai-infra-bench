#!/usr/bin/env python3
import sys
from types import ModuleType, SimpleNamespace

sys.path.insert(0, "/workspace/repo")

from vllm.distributed.kv_transfer.kv_connector.factory import KVConnectorFactory
from vllm.distributed.kv_transfer.kv_connector.v1 import (
    KVConnectorBase_V1,
    KVConnectorRole,
)
from vllm.distributed.kv_transfer.kv_transfer_state import (
    ensure_kv_transfer_initialized,
    ensure_kv_transfer_shutdown,
    get_kv_transfer_group,
)
from vllm.v1.kv_cache_interface import KVCacheConfig


class MinimalConnector(KVConnectorBase_V1):
    def get_num_new_matched_tokens(self, request, num_computed_tokens):
        return 0, False

    def update_state_after_alloc(
        self, request, blocks, num_external_tokens
    ) -> None:
        pass

    def build_connector_meta(self, scheduler_output):
        return None

    def start_load_kv(self, forward_context, **kwargs) -> None:
        pass

    def wait_for_layer_load(self, layer_name) -> None:
        pass

    def save_kv_layer(self, layer_name, kv_layer, attn_metadata, **kwargs) -> None:
        pass

    def wait_for_save(self) -> None:
        pass


class CurrentConnector(MinimalConnector):
    constructed = 0
    received_configs = []

    def __init__(self, vllm_config, role, kv_cache_config):
        type(self).constructed += 1
        type(self).received_configs.append(kv_cache_config)
        super().__init__(vllm_config, role, kv_cache_config)


class LegacyConnector(MinimalConnector):
    constructed = 0

    def __init__(self, vllm_config, role):
        type(self).constructed += 1
        super().__init__(vllm_config, role)


class ExplodingConnector(MinimalConnector):
    constructed = 0

    def __init__(self, vllm_config, role, kv_cache_config):
        type(self).constructed += 1
        raise TypeError("connector-internal sentinel")


def make_config(connector_name, module_name):
    transfer = SimpleNamespace(
        kv_connector=connector_name,
        kv_connector_module_path=module_name,
        engine_id="harbor-constructor-contract",
        is_kv_transfer_instance=True,
    )
    scheduler = SimpleNamespace(disable_hybrid_kv_cache_manager=True)
    return SimpleNamespace(
        kv_transfer_config=transfer,
        scheduler_config=scheduler,
    )


def main():
    print("contract_device=cpu")

    module_name = "harbor_external_kv_connectors"
    connector_module = ModuleType(module_name)
    connector_module.CurrentConnector = CurrentConnector
    connector_module.LegacyConnector = LegacyConnector
    connector_module.ExplodingConnector = ExplodingConnector
    sys.modules[module_name] = connector_module

    kv_cache_config = KVCacheConfig(
        num_blocks=0,
        kv_cache_tensors=[],
        kv_cache_groups=[],
    )

    current_config = make_config("CurrentConnector", module_name)
    try:
        ensure_kv_transfer_initialized(current_config, kv_cache_config)
        current = get_kv_transfer_group()
        assert isinstance(current, CurrentConnector)
        assert CurrentConnector.constructed == 1
        assert CurrentConnector.received_configs == [kv_cache_config]
        assert current.role is KVConnectorRole.WORKER
        print("current_consumer_path=PASS")
    finally:
        ensure_kv_transfer_shutdown()

    exploding_config = make_config("ExplodingConnector", module_name)
    try:
        KVConnectorFactory.create_connector(
            exploding_config,
            KVConnectorRole.SCHEDULER,
            kv_cache_config,
        )
    except TypeError as exc:
        assert str(exc) == "connector-internal sentinel"
        assert ExplodingConnector.constructed == 1
        print("internal_type_error_boundary=PASS")
    else:
        raise AssertionError("connector-internal TypeError was swallowed")

    legacy_config = make_config("LegacyConnector", module_name)
    factory_rejected = False
    try:
        KVConnectorFactory.create_connector(
            legacy_config,
            KVConnectorRole.SCHEDULER,
            kv_cache_config,
        )
    except (TypeError, ValueError) as exc:
        message = str(exc).lower()
        factory_rejected = (
            "legacyconnector" in message
            and ("kvcacheconfig" in message or "kv_cache_config" in message)
        )

    base_rejected = False
    try:
        MinimalConnector(legacy_config, KVConnectorRole.SCHEDULER)
    except TypeError:
        base_rejected = True

    if not factory_rejected or LegacyConnector.constructed != 0 or not base_rejected:
        print(
            "FAIL: legacy lifecycle remained accepted",
            "factory_rejected=", factory_rejected,
            "legacy_constructed=", LegacyConnector.constructed,
            "base_rejected=", base_rejected,
        )
        raise SystemExit(1)

    print("PASS: current consumer works and legacy lifecycle is rejected")


if __name__ == "__main__":
    main()
