from __future__ import annotations

import json

from lora_fixture import make_manager, swap_live_slots


def main() -> int:
    before, after = swap_live_slots(make_manager())
    result = {
        "entrypoint": "real LRUCacheLoRAModelManager and CPU punica routing",
        "before": before,
        "after": after,
        "routing_preserved": after["resolved"] == after["requested"],
    }
    print(json.dumps(result, indent=2))
    return 0 if result["routing_preserved"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
