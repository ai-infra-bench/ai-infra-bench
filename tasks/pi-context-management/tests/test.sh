#!/bin/bash
set -u
umask 022
mkdir -p /logs/verifier
printf '0\n' > /logs/verifier/reward.txt
# Snapshot of what the agent changed, for reviewing real rollouts. It never affects the
# reward, and it is taken as the unprivileged agent user: the checkout and its .git belong to
# the agent, and git run as root there would execute whatever .git/config names.
(
  out=/tmp/agent-changes-snapshot; rm -rf "$out"; install -d -o agent -g agent "$out"
  su agent -s /bin/bash -c "cd /workspace/pi && cp .git/index $out/index && export GIT_INDEX_FILE=$out/index && {
    git status --short --untracked-files=all
    echo '--- diff vs Base (tracked + untracked, excluding node_modules) ---'
    git add -N --all -- . ':!**/node_modules/**' 2>/dev/null
    git diff HEAD -- . ':!**/node_modules/**' 2>/dev/null | head -c 4000000
  } > $out/agent-changes.patch 2>&1"
  cp "$out/agent-changes.patch" /logs/verifier/agent-changes.patch
  rm -rf "$out"
) >/dev/null 2>&1 || true
# Scorer stays in the parent; candidate Pi runs as the agent user.
chmod 755 /tests 2>/dev/null || true
chmod 600 /tests/verify.py 2>/dev/null || true
python3 /tests/verify.py --repo /workspace/pi --output /logs/verifier/behavior
status=$?
if [ "$status" -eq 0 ]; then
    printf '1\n' > /logs/verifier/reward.txt
fi
exit "$status"
