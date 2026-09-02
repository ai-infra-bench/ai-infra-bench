from __future__ import annotations

from lora_fixture import activate, make_manager, route, swap_live_slots


def test_live_slot_swap_preserves_each_requested_adapter() -> None:
    _, after = swap_live_slots(make_manager())
    assert after["slots"] == [2, 1]
    assert after["resolved"] == [1, 2]


def test_three_token_batch_preserves_repeated_adapter_ids() -> None:
    manager = make_manager()
    activate(manager, 1, 2)
    route(manager, (1, 2))
    activate(manager, 3, 1, 2)
    observed = route(manager, (1, 1, 2))
    assert observed["resolved"] == [1, 1, 2]


def test_mapping_change_without_slot_change_still_routes_correctly() -> None:
    manager = make_manager()
    activate(manager, 1, 2)
    assert route(manager, (1, 2))["resolved"] == [1, 2]
    assert route(manager, (2, 1))["resolved"] == [2, 1]


def test_repeated_mapping_without_slot_change_is_stable() -> None:
    manager = make_manager()
    activate(manager, 1, 2)
    first = route(manager, (1, 2))
    second = route(manager, (1, 2))
    assert first == second


def test_single_adapter_routing_remains_correct() -> None:
    manager = make_manager()
    activate(manager, 1)
    assert route(manager, (1,))["resolved"] == [1]


def test_unactivated_registration_does_not_change_live_routing() -> None:
    manager = make_manager()
    activate(manager, 1, 2)
    before = route(manager, (1, 2))
    after = route(manager, (1, 2))
    assert before["slots"] == after["slots"] == [1, 2]
    assert after["resolved"] == [1, 2]


def test_multiple_eviction_cycles_follow_current_slot_order() -> None:
    manager = make_manager()
    activate(manager, 1, 2)
    route(manager, (1, 2))
    for transient in (3, 4, 3):
        activate(manager, transient, 1, 2)
        assert route(manager, (1, 2))["resolved"] == [1, 2]


def test_reversed_live_batch_survives_slot_swap() -> None:
    manager = make_manager()
    activate(manager, 1, 2)
    route(manager, (2, 1))
    activate(manager, 3, 1, 2)
    assert route(manager, (2, 1))["resolved"] == [2, 1]


def test_base_model_tokens_remain_unadapted() -> None:
    manager = make_manager()
    activate(manager, 1, 2)
    observed = route(manager, (0, 1, 0, 2))
    assert observed["resolved"] == [0, 1, 0, 2]


def test_eviction_keeps_registered_adapters_available() -> None:
    manager = make_manager()
    activate(manager, 1, 2, 3, 1, 2)
    assert set(manager.list_adapters()) == {1, 2, 3, 4}
    assert route(manager, (1, 2))["resolved"] == [1, 2]
