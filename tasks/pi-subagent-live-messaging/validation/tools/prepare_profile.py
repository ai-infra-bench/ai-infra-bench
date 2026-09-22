#!/usr/bin/env python3
r"""Prepare a reviewed profile in a curator-owned task copy, before mounting tests.

Example (reference adapters must also be explicit curator-owned files):
  printf 'from binding import Binding\n' > /curator/reference_interface.py
  printf 'from scenario import Scenario\n' > /curator/reference_scenario.py
  python3 -I prepare_profile.py --repo /workspace/pi --tests /curator/task/tests \
    --profile-id reference-reviewed-1 --interface /curator/reference_interface.py \
    --scenario /curator/reference_scenario.py --review-evidence /curator/review.json

Do not run against a live candidate. Complete review and stop its processes first.
The adapters and this tool are maintainer inputs, never candidate-supplied Python.
Use --check with --repo and --tests to validate a mounted, root-owned profile
without changing it or starting scoring. See docs/pi-reviewed-replay.md at the
repository root for explicit CI catalog and standalone replay integration.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--tests', type=Path, required=True)
    parser.add_argument('--check', action='store_true',
                        help='Read-only validation of an existing root-owned profile; no scoring')
    parser.add_argument('--profile-id')
    parser.add_argument('--interface', type=Path)
    parser.add_argument('--scenario', type=Path)
    parser.add_argument('--review-evidence', type=Path)
    args = parser.parse_args()
    preparation = (args.profile_id, args.interface, args.scenario, args.review_evidence)
    if args.check and any(value is not None for value in preparation):
        parser.error('--check takes only --repo and --tests; it never prepares or refreshes a profile')
    if not args.check and any(value is None for value in preparation):
        parser.error('preparation requires --profile-id, --interface, --scenario and --review-evidence')
    # Load the module belonging to this tool, not code found in --repo or --tests.
    module_path = Path(__file__).resolve().parents[2] / 'tests' / 'profile.py'
    spec = importlib.util.spec_from_file_location('trusted_profile', module_path)
    profile = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(profile)
    try:
        if args.check:
            _, _, metadata = profile.validate_profile(args.repo, args.tests)
        else:
            metadata = profile.prepare_profile(args.repo, args.tests, args.profile_id,
                                               args.interface, args.scenario,
                                               json.loads(args.review_evidence.read_text()))
    except (profile.IntegrationNeeded, OSError, ValueError) as exc:
        print('integration_needed: ' + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(metadata, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
