#!/usr/bin/env python3
"""Generate self-contained submission collectors in task.toml files."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shlex
import tomllib

from normalize_task_configs import normalize_config


REPO_ROOT = Path(__file__).resolve().parents[1]
COLLECT_BODY = r'''
set -eu
mkdir -p "$output"
printf 'incomplete\n' > "$output/collection-status.txt"
collect_tmp=$(mktemp -d "$output/.collect.XXXXXX")
cleanup() {
  collect_rc=$?
  if [ "$collect_rc" -ne 0 ]; then
    printf 'failed exit=%s\n' "$collect_rc" > "$output/collection-status.txt"
  fi
  rm -rf "$collect_tmp"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
git_capture() {
  env -u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE -u GIT_EXTERNAL_DIFF \
    -u GIT_CONFIG_COUNT -u GIT_CONFIG_PARAMETERS \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_OPTIONAL_LOCKS=0 \
    GIT_NO_REPLACE_OBJECTS=1 \
    git -C "$repo" -c safe.directory="$repo" -c core.fileMode=true -c core.fsmonitor=false \
      -c core.hooksPath=/dev/null --no-pager "$@"
}
git_capture rev-parse --verify "$base^{commit}" > "$collect_tmp/base-commit.txt"
git_capture rev-parse --verify HEAD > "$collect_tmp/head-commit.txt"
git_capture diff --binary --full-index --no-color --no-ext-diff --no-textconv --no-renames \
  --src-prefix=a/ --dst-prefix=b/ "$base" -- > "$collect_tmp/solution.patch"
git_capture status --short --untracked-files=all > "$collect_tmp/git-status.txt"
git_capture ls-files --others --exclude-standard -z > "$collect_tmp/untracked-paths.bin"
env -u TAR_OPTIONS -u GZIP tar -C "$repo" --null --verbatim-files-from \
  -czf "$collect_tmp/untracked-files.tar.gz" -T "$collect_tmp/untracked-paths.bin"
for collect_file in base-commit.txt head-commit.txt solution.patch git-status.txt \
  untracked-paths.bin untracked-files.tar.gz; do
  mv -f "$collect_tmp/$collect_file" "$output/$collect_file"
done
printf 'complete\n' > "$output/collection-status.txt"
'''.lstrip()


def render_command(repo: str, base: str, output: str = "/logs/artifacts") -> str:
    return (
        f"repo={shlex.quote(repo)}\n"
        f"base={shlex.quote(base)}\n"
        f"output={shlex.quote(output)}\n"
        + COLLECT_BODY
    )


def updated_config(text: str, *, template: bool = False) -> str:
    config = tomllib.loads(text)
    repo = config["environment"]["workdir"]
    base = config["metadata"]["base_commit"]
    user = config["agent"]["user"]
    if not template and not re.fullmatch(r"[0-9a-f]{40}", base):
        raise ValueError("metadata.base_commit must be a full commit SHA")
    if len(config["verifier"].get("collect", [])) > 1:
        raise ValueError("multiple collect hooks require manual review before syncing")
    command = render_command(repo, base)
    if "'''" in command:
        raise ValueError("collector command cannot contain a TOML literal delimiter")
    text = re.sub(
        r"(?ms)^\[\[verifier\.collect\]\][ \t]*\n.*?(?=^\[[A-Za-z_\[]|\Z)",
        "",
        text,
    ).rstrip()
    hook = (
        '\n\n[[verifier.collect]]\n'
        'service = "main"\n'
        f'user = "{user}"\n'
        'timeout_sec = 300\n'
        "command = '''\n" + command + "'''\n"
    )
    result = normalize_config(text + hook)
    # Validate the generated TOML before writing it.
    parsed = tomllib.loads(result)
    assert parsed["verifier"]["collect"][0]["command"] == command
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Report stale hooks without editing")
    args = parser.parse_args()
    paths = sorted((REPO_ROOT / "tasks").glob("*/task.toml"))
    paths.append(REPO_ROOT / "templates/harbor-task/task.toml")
    stale = []
    for path in paths:
        original = path.read_text()
        updated = updated_config(original, template="templates" in path.parts)
        if original != updated:
            stale.append(path.relative_to(REPO_ROOT).as_posix())
            if not args.check:
                path.write_text(updated)
    if args.check and stale:
        parser.exit(1, "Stale collection hooks:\n" + "\n".join(stale) + "\n")
    print(f"{'Checked' if args.check else 'Updated'} collection hooks for {len(paths)} task configs")


if __name__ == "__main__":
    main()
