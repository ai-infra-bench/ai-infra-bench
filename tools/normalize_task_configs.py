#!/usr/bin/env python3
"""Sort Harbor task configs by reading order, preserving values and comments."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
SECTION_ORDER = (
    "", "task", "metadata", "environment", "agent", "verifier",
    "verifier.collect",
)
KEY_ORDER = {
    "": ("schema_version", "artifacts", "source"),
    "task": ("name", "version", "description", "keywords", "authors"),
    "metadata": ("domain", "task_type", "base_commit", "dependency_cutoff"),
    "environment": (
        "workdir", "os", "docker_image", "cpus", "memory_mb", "storage_mb",
        "gpus", "gpu_types", "network_mode", "allowed_hosts", "build_timeout_sec",
    ),
    "agent": ("user", "network_mode", "allowed_hosts", "timeout_sec", "env"),
    "verifier": (
        "environment_mode", "user", "network_mode", "allowed_hosts", "timeout_sec", "env",
    ),
    "verifier.collect": ("service", "user", "timeout_sec", "command"),
}
HEADER = re.compile(r"^\s*\[\[?([A-Za-z0-9_.-]+)\]\]?(?:\s*#.*)?\s*$")
KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)[ \t]*=")


def rank(name: str, order: tuple[str, ...]) -> int:
    return order.index(name) if name in order else len(order)


def normalize_config(text: str) -> str:
    original = tomllib.loads(text)
    sections = [{"name": "", "header": "", "fields": [], "comments": ""}]
    current = sections[0]
    pending = []
    lines = iter(text.splitlines())

    def attach_trailing_comments():
        comments = "\n".join(pending).strip()
        if comments:
            if current["fields"]:
                current["fields"][-1]["text"] += "\n" + comments
            else:
                current["comments"] = comments
        pending.clear()

    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            pending.append(line)
            continue
        if header := HEADER.fullmatch(line):
            attach_trailing_comments()
            current = {"name": header[1], "header": line, "fields": [], "comments": ""}
            sections.append(current)
            continue
        key = KEY.match(line)
        if key is None:
            raise ValueError(f"Unsupported task config syntax: {line!r}")
        statement = [line]
        while True:
            try:
                tomllib.loads("\n".join(statement) + "\n")
                break
            except tomllib.TOMLDecodeError:
                # Consume complete multiline values before interpreting headers
                # or comments, including shell commands containing '[...]'.
                try:
                    statement.append(next(lines))
                except StopIteration as exc:
                    raise ValueError(f"Incomplete value for {key[1]}") from exc
        prefix = "\n".join(pending).strip()
        pending.clear()
        field_text = (prefix + "\n" if prefix else "") + "\n".join(statement)
        current["fields"].append({"key": key[1], "text": field_text})
    attach_trailing_comments()

    blocks = []
    for section in sorted(sections, key=lambda s: rank(s["name"], SECTION_ORDER)):
        order = KEY_ORDER.get(section["name"], ())
        fields = sorted(section["fields"], key=lambda field: rank(field["key"], order))
        parts = [section["header"], section["comments"], *(field["text"] for field in fields)]
        block = "\n".join(part for part in parts if part)
        if block:
            blocks.append(block)
    result = "\n\n".join(blocks) + "\n"
    if tomllib.loads(result) != original:
        raise ValueError("Sorting would change task semantics; review nested table ordering")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check ordering without editing")
    args = parser.parse_args()
    paths = sorted((REPO_ROOT / "tasks").glob("*/task.toml"))
    paths.append(REPO_ROOT / "templates/harbor-task/task.toml")
    stale = []
    for path in paths:
        original = path.read_text()
        updated = normalize_config(original)
        if updated != original:
            stale.append(path.relative_to(REPO_ROOT).as_posix())
            if not args.check:
                path.write_text(updated)
    if args.check and stale:
        parser.exit(1, "Task configs need normalization:\n" + "\n".join(stale) + "\n")
    print(f"{'Checked' if args.check else 'Normalized'} {len(paths)} task configs")


if __name__ == "__main__":
    main()
