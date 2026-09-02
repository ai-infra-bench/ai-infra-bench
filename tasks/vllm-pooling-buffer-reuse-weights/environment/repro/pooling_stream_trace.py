from __future__ import annotations

import json

from pooling_fixture import run


def main() -> int:
    mismatched, output_matches = run()
    result = {
        "entrypoint": "production pooling adapter with a buffer-reusing iterator",
        "mismatched_parameters": mismatched,
        "output_matches_reference": output_matches,
    }
    print(json.dumps(result, indent=2))
    return 0 if not mismatched and output_matches else 3


if __name__ == "__main__":
    raise SystemExit(main())
