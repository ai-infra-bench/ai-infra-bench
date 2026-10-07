#!/usr/bin/env bash
set -eu
[ "$(id -u)" -eq 0 ]
umask 077
trusted_tests=$(mktemp -d /opt/pi-rollback-verifier.XXXXXXXX)
cp -R /tests/. "$trusted_tests/"
chown -hR root:root "$trusted_tests"
# Only the SDK transport driver and Node privilege preload must be readable by
# candidate processes. Scenario construction and expected results stay private.
chmod -R go-rwx "$trusted_tests"
chmod 0755 "$trusted_tests"
chmod 0444 "$trusted_tests/sdk_peer.mjs" "$trusted_tests/drop_worker.cjs"
# Harbor uploads /tests after the agent phase. Close that original copy too.
chmod -R go-rwx /tests
exec env -i PATH=/usr/local/bin:/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 python3 "$trusted_tests/run_verifier.py"
