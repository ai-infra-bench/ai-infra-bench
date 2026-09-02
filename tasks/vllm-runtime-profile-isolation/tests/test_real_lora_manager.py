from __future__ import annotations

import json

from lora_fixture import make_manager, swap_live_slots


def main() -> int:
    before, after = swap_live_slots(make_manager())
    print(
        json.dumps(
            {
                "entrypoint": "real LRUCacheLoRAModelManager with CPU punica metadata",
                "before": before,
                "after": after,
                "slot_layout_changed": before["slots"] != after["slots"],
                "routing_preserved": after["resolved"] == after["requested"],
            },
            separators=(",", ":"),
        )
    )
    assert before["resolved"] == before["requested"]
    assert before["slots"] != after["slots"]
    assert after["resolved"] == after["requested"]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
