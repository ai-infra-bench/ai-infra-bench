"""Harbor agent: Grok Build authenticated with the host's grok CLI login instead of an API key.

Harbor's built-in ``grok-build`` agent hard-requires ``XAI_API_KEY``. This subclass keeps
everything else (install, headless flags, trajectory conversion, watchdog) and swaps the
credential: it copies the host's ``~/.grok/auth.json`` (the OIDC session written by
``grok login``) into the container before the agent runs, and strips the placeholder API key
from the agent's environment so the CLI falls back to that session.

Usage (from the repository root, so the module resolves):

    PYTHONPATH=. uvx --from harbor==0.22.0 harbor run --path <task> \
        --agent tools.harbor_agents.grok_build_oauth:GrokBuildOAuth --model grok-4.6 ...

Environment:
    GROK_AUTH_JSON   host path of the session file (default ~/.grok/auth.json)

Caveats:
- The session's access token expires (see ``expires_at`` in auth.json); if the CLI refreshes
  it inside the container, the rotated refresh token is not written back to the host, and the
  host's own session may need a fresh ``grok login`` afterwards. Keep runs shorter than the
  remaining token lifetime.
- The file carries the account's identity. It is uploaded into the trial container only,
  never into the image or the task directory.
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Any

from harbor.agents.installed.grok_build import GrokBuild
from harbor.environments.base import BaseEnvironment

_PLACEHOLDER = "oauth-session-from-auth-json"


class GrokBuildOAuth(GrokBuild):
    @staticmethod
    def name() -> str:
        return "grok-build-oauth"

    # --- credential ------------------------------------------------------------------

    def _auth_json_path(self) -> Path:
        return Path(os.environ.get("GROK_AUTH_JSON", "~/.grok/auth.json")).expanduser()

    def _get_env(self, key: str, *alternatives: str) -> str | None:
        value = super()._get_env(key, *alternatives)
        if key == "XAI_API_KEY" and not value:
            # Satisfies GrokBuild.run()'s "key required" check; removed again below.
            return _PLACEHOLDER
        return value

    async def exec_as_agent(
        self,
        environment: BaseEnvironment,
        command: str,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout_sec: int | None = None,
    ) -> Any:
        if env and env.get("XAI_API_KEY") == _PLACEHOLDER:
            env = {k: v for k, v in env.items() if k != "XAI_API_KEY"}
        return await super().exec_as_agent(
            environment, command, env=env, cwd=cwd, timeout_sec=timeout_sec
        )

    # --- install: the built-in flow plus the session file --------------------------------

    async def install(self, environment: BaseEnvironment) -> None:
        await super().install(environment)
        await self._upload_session(environment)

    async def _upload_session(self, environment: BaseEnvironment) -> None:
        source = self._auth_json_path()
        if not source.is_file():
            raise FileNotFoundError(
                f"{source} not found: run `grok login` on the host or set GROK_AUTH_JSON"
            )
        home = await environment.exec(command='printf "%s" "$HOME"')
        remote_home = (home.stdout or "").strip() or "/root"
        remote_dir = f"{remote_home}/.grok"
        remote_file = f"{remote_dir}/auth.json"
        await environment.exec(command=f"mkdir -p {shlex.quote(remote_dir)}")
        await environment.upload_file(source, remote_file)
        # The agent phase may run as a non-root user (task.toml [agent].user); the upload
        # is owned by root, so make the session file and its directory readable by the
        # agent. This is a throwaway per-trial container, so a readable session file is
        # acceptable here (the real grok-build agent authenticates with XAI_API_KEY, not a
        # home-directory file, so nothing about the task environment relies on this).
        # The agent user differs per task (`node`, `pi-agent`, `agent`, ...): hand the
        # directory to whoever owns the HOME it was resolved from.
        await environment.exec(
            command=(
                f"chmod 700 {shlex.quote(remote_dir)} && chmod 644 {shlex.quote(remote_file)} "
                f'&& chown -R "$(stat -c %u:%g {shlex.quote(remote_home)})" {shlex.quote(remote_dir)}'
            ),
            user="root",
        )
        self.logger.info("uploaded grok session file to %s (readable by the agent user)", remote_file)
