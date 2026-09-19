# syntax=docker/dockerfile:1
# pi (earendil-works/pi) at a pinned commit with an offline, prebuilt Node
# workspace. The agent phase and the verifier run with no network.
# Generated from templates/pi-harbor-node by generate.py; edit the template.

ARG PI_BASE_SHA=__PI_BASE_SHA__
ARG PI_DEPENDENCY_CUTOFF=__PI_DEPENDENCY_CUTOFF__
ARG PI_CACHE_NAMESPACE=__PI_CACHE_NAMESPACE__
ARG PI_LOCK_SHA256=__PI_LOCK_SHA256__
ARG PI_REPO=https://github.com/earendil-works/pi.git

######################### PINNED SOURCE #########################
FROM alpine:3.20@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc AS source
ARG PI_BASE_SHA
ARG PI_REPO
RUN test -n "$PI_BASE_SHA" \
 && apk add --no-cache ca-certificates git \
 && mkdir -p /src/pi \
 && git -C /src/pi init -q \
 && git -C /src/pi config core.logAllRefUpdates false \
 && git -C /src/pi remote add origin "$PI_REPO" \
 && git -C /src/pi fetch --no-tags origin "$PI_BASE_SHA" \
 && git -C /src/pi checkout -q -b main "$PI_BASE_SHA" \
 && test "$(git -C /src/pi rev-parse HEAD)" = "$PI_BASE_SHA" \
 && git -C /src/pi remote remove origin \
 && rm -rf /src/pi/.git/logs \
 && rm -f /src/pi/.git/FETCH_HEAD /src/pi/.git/ORIG_HEAD \
 && test "$(git -C /src/pi branch --show-current)" = main \
 && test ! -e /src/pi/.git/shallow \
 && test -z "$(git -C /src/pi remote)" \
 && test -z "$(git -C /src/pi for-each-ref --format='%(refname)' refs/remotes refs/tags)" \
 && test -z "$(git -C /src/pi fsck --full --no-reflogs --unreachable --no-progress 2>/dev/null)" \
 && test -z "$(git -C /src/pi status --porcelain)"

######################### NODE WORKSPACE #########################
FROM node:22.19.0-bookworm-slim@sha256:4a4884e8a44826194dff92ba316264f392056cbe243dcc9fd3551e71cea02b90
ENV DEBIAN_FRONTEND=noninteractive \
    PI_OFFLINE=1 \
    PI_TELEMETRY=0 \
    PI_NO_LOCAL_LLM=1 \
    CI=1

# python3 runs the verifier's JUnit checker; ripgrep and fd are what pi's
# tools-manager looks for on PATH, so it never tries to download them offline.
# Debian's fd (8.6) predates the --no-require-git flag pi's find tool uses, so fd
# comes from the pinned 10.2.0 release tarball instead.
ARG FD_VERSION=10.2.0
ARG FD_SHA256_AMD64=d9bfa25ec28624545c222992e1b00673b7c9ca5eb15393c40369f10b28f9c932
ARG FD_SHA256_ARM64=4e8e596646d047d904f2c5ca74b39dccc69978b6e1fb101094e534b0b59c1bb0
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      bash ca-certificates curl git jq procps python3 ripgrep \
 && rm -rf /var/lib/apt/lists/* \
 && case "$(uname -m)" in \
      x86_64) fd_arch=x86_64; fd_sha="$FD_SHA256_AMD64" ;; \
      aarch64) fd_arch=aarch64; fd_sha="$FD_SHA256_ARM64" ;; \
      *) echo "unsupported architecture $(uname -m)" >&2; exit 1 ;; \
    esac \
 && curl -fsSL -o /tmp/fd.tar.gz "https://github.com/sharkdp/fd/releases/download/v${FD_VERSION}/fd-v${FD_VERSION}-${fd_arch}-unknown-linux-musl.tar.gz" \
 && echo "${fd_sha}  /tmp/fd.tar.gz" | sha256sum -c - \
 && tar -xzf /tmp/fd.tar.gz -C /tmp \
 && install -m 0755 "/tmp/fd-v${FD_VERSION}-${fd_arch}-unknown-linux-musl/fd" /usr/local/bin/fd \
 && rm -rf /tmp/fd.tar.gz "/tmp/fd-v${FD_VERSION}-${fd_arch}-unknown-linux-musl" \
 && fd --version && rg --version | head -1

COPY --from=source /src/pi /workspace/pi
WORKDIR /workspace/pi
ARG PI_BASE_SHA
ARG PI_DEPENDENCY_CUTOFF
ARG PI_CACHE_NAMESPACE
ARG PI_LOCK_SHA256

# The lock file is the repository's own at the base commit and must be the one
# checked in as environment/lock/package-lock.json (sha256 pinned below). npm ci
# is the only network step; everything after it is offline.
RUN echo "$PI_LOCK_SHA256  package-lock.json" | sha256sum -c - \
 && npm ci --no-audit --no-fund \
 && npm run build \
 && npm cache clean --force

# Smoke: the published entry points exist, the faux provider is importable,
# vitest collects, and the CLI starts without network.
RUN test -f packages/coding-agent/dist/index.js \
 && test -f packages/ai/dist/providers/faux.js \
 && node -e "import('@earendil-works/pi-ai/providers/faux').then(m => { if (typeof m.fauxProvider !== 'function') throw new Error('faux missing'); })" \
 && (cd packages/coding-agent && node ../../node_modules/vitest/vitest.mjs run --reporter=dot test/path-utils.test.ts) \
 && node packages/coding-agent/dist/cli.js --version \
 && node --input-type=module -e "import { DefaultResourceLoader, SettingsManager } from '@earendil-works/pi-coding-agent'; const l = new DefaultResourceLoader({ cwd: '/workspace/pi', agentDir: '/tmp/pi-smoke-agent', settingsManager: SettingsManager.inMemory({}), additionalExtensionPaths: ['/workspace/pi/packages/coding-agent/examples/extensions/hello.ts'], noExtensions: true, noSkills: true, noPromptTemplates: true, noThemes: true, noContextFiles: true }); await l.reload(); const e = l.getExtensions(); if (e.errors.length || e.extensions.length !== 1) { console.error(e.errors); process.exit(1); }" \
 && command -v fd && command -v rg

# Agent-phase view: no verifier, solution, or validation material is present.
# The agent phase runs as the unprivileged `node` user (task.toml `[agent].user`), and
# so does the verifier's execution of candidate code (tests/test.sh runs every suite via
# `su node`). The checkout belongs to the agent; the installed toolchain (node_modules,
# node, python3, bash) stays root-owned and read-only for it, so candidate code cannot
# rewrite the runner, interpreter or baseline that later produce the verifier's reports.
# vite needs a writable temp dir next to each package's node_modules, and root's git must
# accept a checkout owned by another user. This ownership is established BEFORE the
# baseline runs, so the baseline is recorded under the same `node` conditions the
# candidate suite runs under (see below).
RUN chown -R node:node /workspace/pi \
 && find /workspace/pi -type d -name node_modules -prune -exec chown -R root:root {} + \
 && find /workspace/pi -type d -name node_modules -prune -exec chmod -R go-w {} + \
 && for d in $(find /workspace/pi -type d -name node_modules -not -path '*/node_modules/*/node_modules'); do \
      install -d -o node -g node -m 0755 "$d/.vite-temp" "$d/.vite"; \
    done \
 && git config --system --add safe.directory /workspace/pi \
 && su node -c 'cd /workspace/pi && git status --porcelain | wc -l && test ! -w node_modules/vitest/vitest.mjs' \
 && test "$(stat -c %U /workspace/pi/node_modules)" = root

# PASS_TO_PASS baseline: pi's own coding-agent suite on the unmodified Base, run
# with the verifier's environment (offline, no credentials, throwaway HOME) AS THE
# `node` USER, so the baseline pass/fail set matches what the candidate suite (also
# run as `node` by tests/test.sh) produces. A few cases fail in this environment on
# Base itself (install-method detection when the install path is not writable, a
# timing-sensitive coalesced-reload case); baseline_check.py records them and the
# verifier only requires cases that passed on Base to keep passing. --retry 2 absorbs
# the timing-sensitive cases that flake inside containers; the verifier uses the same
# policy. node writes the report to a node-owned scratch dir; root copies it into the
# root-owned /opt/pi-baseline so candidate code can never rewrite the baseline.
COPY <<'PI_BASELINE_CHECK_EOF' /opt/pi-baseline/baseline_check.py
#!/usr/bin/env python3
"""Summarise the PASS_TO_PASS baseline recorded at image build time.

Writes /opt/pi-baseline/summary.json and fails the build when the suite did not
run at all or when the environmental failure set on Base is larger than the
small allowance (install-method detection when the install path is not
writable, and timing-sensitive cases that flake inside containers).
"""
import json
import sys
import xml.etree.ElementTree as ET

ALLOWED_ENVIRONMENTAL_FAILURES = 6

root = ET.parse("/opt/pi-baseline/coding-agent-junit.xml").getroot()
suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
totals = {k: sum(int(s.attrib.get(k, "0")) for s in suites) for k in ("tests", "failures", "errors", "skipped")}
failed = []
for case in root.findall(".//testcase"):
    if case.find("failure") is not None or case.find("error") is not None:
        failed.append(f"{case.attrib.get('classname', '')}::{case.attrib.get('name', '')}")
summary = {"totals": totals, "failed_on_base": failed}
with open("/opt/pi-baseline/summary.json", "w") as stream:
    stream.write(json.dumps(summary, indent=2) + "\n")
print("baseline", totals)
for name in failed:
    print("  failed on base:", name)
if totals["tests"] < 2000:
    print("baseline suite did not run", file=sys.stderr)
    sys.exit(1)
if totals["failures"] + totals["errors"] > ALLOWED_ENVIRONMENTAL_FAILURES:
    print("too many environmental failures on Base; fix the image", file=sys.stderr)
    sys.exit(1)
PI_BASELINE_CHECK_EOF
RUN install -d -o node -g node /tmp/pi-baseline-home /tmp/pi-baseline-out \
 && (su -p node -s /bin/bash -c 'cd /workspace/pi/packages/coding-agent \
      && HOME=/tmp/pi-baseline-home PI_OFFLINE=1 PI_TELEMETRY=0 PI_NO_LOCAL_LLM=1 \
         node ../../node_modules/vitest/vitest.mjs run --retry 2 --reporter=junit \
         --outputFile=/tmp/pi-baseline-out/coding-agent-junit.xml \
         > /tmp/pi-baseline-out/coding-agent-run.log 2>&1' || true) \
 && cp /tmp/pi-baseline-out/coding-agent-junit.xml /opt/pi-baseline/coding-agent-junit.xml \
 && cp /tmp/pi-baseline-out/coding-agent-run.log /opt/pi-baseline/coding-agent-run.log \
 && chown -R root:root /opt/pi-baseline && chmod -R go-w /opt/pi-baseline \
 && python3 /opt/pi-baseline/baseline_check.py \
 && rm -rf /tmp/pi-baseline-out /tmp/pi-baseline-home \
 && for d in $(find /workspace/pi -type d -name node_modules -not -path '*/node_modules/*/node_modules'); do \
      rm -rf "$d/.vite-temp" "$d/.vite"; install -d -o node -g node -m 0755 "$d/.vite-temp" "$d/.vite"; \
    done

# Identity of what the image build generated inside the checkout: the built dist/ trees
# (the verifier's lifecycle suites run the published dist/ entry points) and generated
# sources such as packages/ai/src/providers/data. These files are gitignored, live in the
# agent-owned checkout, and their bytes depend on the image build (the model catalog is
# fetched at build time), so they cannot be pinned in tests/. Record them here, root-owned,
# so tests/check_scope.py can reject a submission that edited the built pi core. A rebuild
# from unchanged sources reproduces these bytes.
RUN cd /workspace/pi \
 && git ls-files --others -z | grep -zv -E '(^|/)node_modules/' | sort -z | xargs -0 sha256sum > /opt/pi-baseline/build-manifest.sha256 \
 && test "$(grep -c -E '  packages/coding-agent/dist/' /opt/pi-baseline/build-manifest.sha256)" -gt 500 \
 && chown root:root /opt/pi-baseline/build-manifest.sha256 && chmod 0444 /opt/pi-baseline/build-manifest.sha256
RUN test ! -e /tests && test ! -e /solution && test ! -e /validation

LABEL ai.infra.bench.environment-template=pi-harbor-node \
      ai.infra.bench.base-commit=$PI_BASE_SHA \
      ai.infra.bench.dependency-cutoff=$PI_DEPENDENCY_CUTOFF \
      ai.infra.bench.cache-namespace=$PI_CACHE_NAMESPACE
ENTRYPOINT []
CMD ["sleep", "infinity"]
