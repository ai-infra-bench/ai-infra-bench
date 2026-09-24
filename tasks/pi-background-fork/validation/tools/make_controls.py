#!/usr/bin/env python3
"""Derive every control patch from the Oracle.

Each control rewrites the Oracle's extension source with one plausible defect and is
emitted as a full patch against Base (README and unit test unchanged), so a control
applies to a clean checkout exactly like a submission. Re-run after any Oracle change:

    python3 validation/tools/make_controls.py
"""
import re
import sys
from pathlib import Path

TASK = Path(__file__).resolve().parents[2]
ORACLE = TASK / "solution/oracle.patch"
EXTENSION = "packages/coding-agent/examples/extensions/fork/index.ts"


def split_patch(text):
    files = {}
    for chunk in re.split(r"(?m)^(?=diff --git )", text):
        if not chunk.strip():
            continue
        path = re.match(r"diff --git a/(\S+) b/", chunk).group(1)
        files[path] = chunk
    return files


def new_file_source(chunk):
    lines = chunk.split("\n")
    start = next(i for i, line in enumerate(lines) if line.startswith("@@"))
    return "\n".join(line[1:] for line in lines[start + 1:] if line.startswith("+")) + "\n"


def new_file_patch(path, source):
    body = source.split("\n")
    if body and body[-1] == "":
        body = body[:-1]
    return (f"diff --git a/{path} b/{path}\nnew file mode 100644\n--- /dev/null\n+++ b/{path}\n"
            f"@@ -0,0 +1,{len(body)} @@\n" + "".join(f"+{line}\n" for line in body))


def replace(source, old, new, count=1):
    if source.count(old) < 1:
        raise SystemExit(f"control anchor not found: {old[:60]!r}")
    return source.replace(old, new, count)


CONTROLS = {
    # The tool waits for the fork to finish: the parent run cannot continue meanwhile.
    "control-blocking-tool": [(
        "\t\t\tconst fork = await startFork(ctx, toolCallId, task, pi.getThinkingLevel());\n",
        "\t\t\tconst fork = await startFork(ctx, toolCallId, task, pi.getThinkingLevel());\n"
        "\t\t\tawait new Promise((resolve) => fork.child.once(\"close\", resolve));\n",
    )],
    # The fork's session ends at the forking assistant message: its calls stay unanswered.
    "control-dangling-fork-call": [(
        "\tfor (const part of leaf.message.content) {\n\t\tif (part.type !== \"toolCall\") continue;",
        "\tfor (const part of [] as typeof leaf.message.content) {\n\t\tif (part.type !== \"toolCall\") continue;",
    )],
    # The fork is not told its task.
    "control-task-not-given": [(
        "\t\t\"-p\",\n\t\ttask,\n",
        "\t\t\"-p\",\n\t\t\"Continue.\",\n",
    )],
    # The extension also registers the tool inside forks.
    "control-fork-can-fork": [(
        "\t\twatchParent(Number(process.env[PARENT_PID_ENV]));\n\t\treturn;\n",
        "\t\twatchParent(Number(process.env[PARENT_PID_ENV]));\n",
    )],
    # The fork runs on a fixed model and thinking level instead of the parent's current ones.
    "control-default-model": [(
        "\t\t\"--model\",\n\t\t`${model.provider}/${model.id}`,\n\t\t\"--thinking\",\n\t\tthinking,\n",
        "\t\t\"--model\",\n\t\t\"fork-test/scripted-a\",\n\t\t\"--thinking\",\n\t\t\"off\",\n",
    )],
    # The fork session does not name its parent.
    "control-no-parent-session": [(
        "\t\tparentSession: parentSessionFile,\n",
        "",
    )],
    # The result is only appended: an idle parent never looks at it.
    "control-result-without-turn": [(
        "{ triggerTurn: true });",
        "{ triggerTurn: false });",
    )],
    # /reload is treated like quitting: forks die with the old runtime.
    "control-reload-stops-forks": [(
        "\t\tif (event.reason === \"reload\") return;\n",
        "",
    )],
    # Session ends never stop forks.
    "control-forks-outlive-session": [(
        "\t\tstopForks(sessionFile);\n",
        "",
    )],
    # Failures are dropped silently.
    "control-silent-failures": [(
        "\tif (fork.settled) return;\n\tfork.settled = true;\n\tregistry.forks.delete(fork.id);\n\tconst api = registry.api;",
        "\tif (fork.settled) return;\n\tfork.settled = true;\n\tregistry.forks.delete(fork.id);\n\tif (status === \"failed\") return;\n\tconst api = registry.api;",
    )],
    # The fork copies the raw message history and ignores compaction.
    "control-uncompacted-history": [(
        "\tconst branch = manager.getBranch();\n",
        "\tconst branch = (() => {\n"
        "\t\tconst kept = manager.getBranch().filter((entry) => entry.type === \"message\");\n"
        "\t\treturn kept.map((entry, i) => ({ ...entry, parentId: i === 0 ? null : kept[i - 1]!.id }));\n"
        "\t})();\n",
    )],
    # An empty task starts a fork anyway.
    "control-empty-task-accepted": [(
        "\t\t\tif (!task) throw new Error(\"fork: the task must not be empty\");\n",
        "",
    )],
    # Bookkeeping lives in the module: a reloaded runtime has lost its forks.
    "control-module-state": [(
        "const registry: Registry = (globals[registryKey] ??= { forks: new Map(), undelivered: new Map() });",
        "const registry: Registry = { forks: new Map(), undelivered: new Map() };\nvoid globals;",
    )],
    # A result can be delivered more than once.
    "control-deliver-twice": [(
        "\tif (fork.settled) return;\n\tfork.settled = true;\n\tregistry.forks.delete(fork.id);\n\tconst api = registry.api;",
        "\tregistry.forks.delete(fork.id);\n\tconst api = registry.api;",
    ), (
        "\tchild.once(\"close\", (code, signal) => {\n\t\tif (fork.settled) return;",
        "\tchild.once(\"close\", (code, signal) => {\n\t\tif (fork.settled) return;\n\t\tsetTimeout(() => deliver(fork, \"completed\", \"(duplicate)\"), 200);",
    )],
    # Every result is attributed to the most recently started fork.
    "control-latest-fork-id": [(
        "\tconst details: Record<string, string> = { forkId: fork.id,",
        "\tconst latest = [...registry.forks.keys()].pop() ?? lastStarted ?? fork.id;\n"
        "\tconst details: Record<string, string> = { forkId: latest,",
    ), (
        "\tregistry.forks.set(forkId, fork);\n",
        "\tregistry.forks.set(forkId, fork);\n\tlastStarted = forkId;\n",
    ), (
        "const KILL_GRACE_MS = 2_000;\n",
        "const KILL_GRACE_MS = 2_000;\nlet lastStarted: string | undefined;\n",
    )],
    # Forks never notice that their parent died.
    "control-no-parent-watch": [(
        "\t\twatchParent(Number(process.env[PARENT_PID_ENV]));\n",
        "",
    )],
    # The result keeps only the start of the fork's answer.
    "control-truncated-answer": [(
        "\t\treturn { text: textOf(message.content) };",
        "\t\treturn { text: textOf(message.content).slice(0, 8_000) };",
    )],
    # A result discarded by the user's interrupt is never sent again.
    "control-no-redelivery": [(
        "\tpi.on(\"agent_settled\", (_event, ctx) => resendUndelivered(ctx));\n",
        "\tvoid resendUndelivered;\n",
    )],
}


def main():
    oracle = split_patch(ORACLE.read_text())
    source = new_file_source(oracle[EXTENSION])
    out = TASK / "validation/patches"
    out.mkdir(parents=True, exist_ok=True)
    for name, edits in CONTROLS.items():
        edited = source
        for old, new in edits:
            edited = replace(edited, old, new)
        parts = [chunk if path != EXTENSION else new_file_patch(path, edited) for path, chunk in oracle.items()]
        (out / f"{name}.patch").write_text("".join(part if part.endswith("\n") else part + "\n" for part in parts))
        print(name)


if __name__ == "__main__":
    sys.exit(main())
