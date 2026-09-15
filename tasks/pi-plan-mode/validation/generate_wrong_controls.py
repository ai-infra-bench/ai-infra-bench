#!/usr/bin/env python3
"""Generate self-contained one-defect controls that apply directly to pinned Base.

Read Base from a local Git checkout or the retained offline image, apply the task
Oracle in a disposable directory, then vary one behavior per complete patch.
Patch application, resulting file bytes, and parsing are checked; runtime reward
validation remains a separate formal verifier step.
"""
from __future__ import annotations

import argparse
import io
import tarfile
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

BASE_SHA = "d981de1229ef899957bbe968bc8dcda02a21f477"
EXTENSION = "packages/coding-agent/examples/extensions/plan-mode"
LEGACY_TEST = "packages/coding-agent/test/plan-mode-extension.test.ts"
RELATIVE = Path("packages/coding-agent/examples/extensions/plan-mode/index.ts")


def replace(source: str, old: str, new: str, *, count: int = 1) -> str:
    actual = source.count(old)
    if actual != count:
        raise RuntimeError(f"Oracle anchor count changed: expected {count}, got {actual}: {old!r}")
    return source.replace(old, new)


def variants(source: str) -> list[tuple[str, str, str, list[str]]]:
    cases = []
    cases.append((
        "accept-stale-revision",
        replace(source, 'if (revision !== state.revision) return "stale_revision";',
                'if (revision < 0) return "stale_revision";'),
        "Approval checks that the revision is nonnegative instead of matching the submitted revision.",
        ["C06"],
    ))
    cases.append((
        "accept-extension-control",
        replace(source,
                '\t\telse if (operation !== "status" && event.source !== "interactive" && event.source !== "rpc")\n\t\t\terror = "forbidden_source";\n',
                ''),
        "The normal input handler accepts extension-origin enter and approval controls.",
        ["C07"],
    ))
    cases.append((
        "replay-duplicate-approval",
        replace(source, '\t\tif (state.mode === "approved") return null;\n', ''),
        "A repeated approval schedules the already-approved execution again.",
        ["C10"],
    ))
    custom = replace(
        source,
        'toolsBeforePlanning.filter((name) => READ_TOOLS.has(name))',
        'toolsBeforePlanning.filter((name) => READ_TOOLS.has(name) || !["bash", "powershell", "edit", "write"].includes(name))',
        count=2,
    )
    custom = replace(
        custom,
        '!(READ_TOOLS.has(event.toolName) && toolsBeforePlanning.includes(event.toolName))',
        '!((READ_TOOLS.has(event.toolName) || !["bash", "powershell", "edit", "write"].includes(event.toolName)) && toolsBeforePlanning.includes(event.toolName))',
    )
    cases.append((
        "allow-custom-planning-tools", custom,
        "Planning preserves arbitrary previously active custom tools, using the same erroneous policy for dispatch and restore.",
        ["C02", "C09"],
    ))
    start = source.index('\t\tconst approved = {')
    end = source.index('\n\t\treturn null;', start)
    approval_dispatch = source[start:end]
    replay_dispatch = '\n'.join('\t\t' + line if line else line for line in approval_dispatch.split('\n'))
    restore_approved = '\t\t\t} else if (state.mode === "approved") {\n\t\t\t\tpi.setActiveTools([...toolsBeforePlanning]);\n\t\t\t}'
    cases.append((
        "replay-approved-resume",
        replace(source, restore_approved,
                restore_approved[:-len('\n\t\t\t}')] + '\n' + replay_dispatch + '\n\t\t\t}'),
        "Restoring an approved session dispatches its persisted snapshot again despite the earlier execution.",
        ["L02"],
    ))
    cases.append((
        "resume-original-toolset",
        replace(source,
                '\t\t\t\tpi.setActiveTools([...toolsBeforePlanning.filter((name) => READ_TOOLS.has(name)), "plan_submit"]);',
                '\t\t\t\tpi.setActiveTools([...toolsBeforePlanning, "plan_submit"]);'),
        "Planning resume restores the original advertised tool set instead of the read-only subset; the ordinary dispatch guard is otherwise retained.",
        ["L01"],
    ))
    cases.append((
        "drop-approved-request-context",
        replace(source,
                '(message) => !(message.role === "custom" && message.customType === "plan-mode-context"),',
                '(message) => !(message.role === "custom" && ["plan-mode-context", "plan-approved"].includes(message.customType)),'),
        "The approved snapshot is saved correctly but is filtered out of the actual provider request.",
        ["C10", "C16"],
    ))
    cases.append((
        "early-exit-zero",
        replace(source,
                'export default function planModeExtension(pi: ExtensionAPI): void {\n',
                'export default function planModeExtension(pi: ExtensionAPI): void {\n\tprocess.exit(0);\n'),
        "The extension terminates the candidate process with status zero before any behavior is exercised.",
        ["contract inventory", "lifecycle child observation"],
    ))
    begin = source.index('\tpi.on("turn_end", (event, ctx) => {')
    end = source.index('\tpi.on("agent_settled"', begin)
    cases.append((
        "drop-done-progress",
        source[:begin] + '\t// Completed-turn progress updates are omitted.\n' + source[end:],
        "Approved steps remain unchanged, but completed turns no longer update the progress displayed by /todos.",
        ["C12"],
    ))
    ui = replace(source, '\tlet reviewOpen = false;',
                 '\tlet reviewOpen = false;\n\tlet suppressUIApprovalContext = false;')
    ui = replace(ui,
                 '\t\t\t\tconst error = approve(ctx, displayed.sessionId, displayed.planId, displayed.revision);',
                 '\t\t\t\tsuppressUIApprovalContext = true;\n'
                 '\t\t\t\tconst error = approve(ctx, displayed.sessionId, displayed.planId, displayed.revision);\n'
                 '\t\t\t\tif (error) suppressUIApprovalContext = false;')
    ui = replace(ui,
                 '\t\telse if (operation === "approve") error = approve(ctx, parts[2], parts[3], revision);',
                 '\t\telse if (operation === "approve") {\n'
                 '\t\t\tsuppressUIApprovalContext = false;\n'
                 '\t\t\terror = approve(ctx, parts[2], parts[3], revision);\n\t\t}')
    ui = replace(ui,
                 '(message) => !(message.role === "custom" && message.customType === "plan-mode-context"),',
                 '(message) => !(message.role === "custom" && (message.customType === "plan-mode-context" || '
                 '(suppressUIApprovalContext && message.customType === "plan-approved"))),')
    cases.append((
        "drop-ui-approved-request-context", ui,
        "Only UI Execute filters the approved snapshot out of provider context; RPC approval, saved state, tools, and execution scheduling remain intact.",
        ["C16"],
    ))
    return cases


def run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True)


def files(work: Path) -> dict[str, str]:
    return {
        path.relative_to(work).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in work.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(work).parts
    }


def complete_patch(base: Path, work: Path) -> bytes:
    # Full-file hunks remain ordinary git-apply patches, while avoiding nested
    # context-line whitespace that obscures repository diff --check results.
    parts: list[str] = []
    for relative in sorted(set(files(base)) | set(files(work))):
        before, after = base / relative, work / relative
        old = before.read_text() if before.exists() else ""
        new = after.read_text() if after.exists() else ""
        if old == new:
            continue
        if (old and not old.endswith("\n")) or (new and not new.endswith("\n")):
            raise RuntimeError(f"Expected newline-terminated source: {relative}")
        old_lines, new_lines = old.splitlines(keepends=True), new.splitlines(keepends=True)
        parts.append(f"diff --git a/{relative} b/{relative}\n")
        if not before.exists():
            parts.append("new file mode 100644\n")
        if not after.exists():
            parts.append("deleted file mode 100644\n")
        parts.append(f"--- {'a/' + relative if before.exists() else '/dev/null'}\n")
        parts.append(f"+++ {'b/' + relative if after.exists() else '/dev/null'}\n")
        parts.append(f"@@ -{1 if old_lines else 0},{len(old_lines)} +{1 if new_lines else 0},{len(new_lines)} @@\n")
        parts.extend("-" + line for line in old_lines)
        parts.extend("+" + line for line in new_lines)
    return "".join(parts).encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--base-dir", type=Path, help="Local Git checkout containing pinned Base")
    source_group.add_argument("--image", help="Retained image containing /workspace/pi at pinned Base")
    parser.add_argument("--node", default=shutil.which("node"), help="Node with TypeScript stripping support")
    args = parser.parse_args()
    output = Path(__file__).resolve().parent
    oracle_patch = output.parent / "solution/oracle.patch"
    if args.image:
        prefix = ["docker", "run", "--rm", "--network=none", args.image, "git", "-C", "/workspace/pi"]
        actual_base = run(prefix + ["rev-parse", "HEAD"]).stdout.decode().strip()
        if actual_base != BASE_SHA:
            raise RuntimeError(f"Image Base mismatch: {actual_base}")
    else:
        prefix = ["git", "-C", str(args.base_dir.resolve())]
    archive = run(prefix + ["archive", BASE_SHA, EXTENSION, LEGACY_TEST]).stdout
    entries, provenance, patches = [], [], {}
    with tempfile.TemporaryDirectory(prefix="pi-plan-controls-") as temporary:
        temporary = Path(temporary)
        base = temporary / "base"
        base.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as contents:
            for member in contents.getmembers():
                path = Path(member.name)
                if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
                    raise RuntimeError(f"Unexpected archive entry: {member.name}")
                if member.isfile():
                    target = base / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(contents.extractfile(member).read())
        run(["git", "init", "-q"], base)
        run(["git", "add", "--all"], base)
        oracle = temporary / "oracle"
        shutil.copytree(base, oracle)
        run(["git", "apply", "--check", str(oracle_patch)], oracle)
        run(["git", "apply", str(oracle_patch)], oracle)
        source = (oracle / RELATIVE).read_text()
        generated = variants(source)
        for name, mutated, description, expected_cases in generated:
            if mutated == source:
                raise RuntimeError(f"Control {name} has no change")
            work = temporary / name
            shutil.copytree(oracle, work)
            (work / RELATIVE).write_text(mutated)
            if args.node:
                # Parsing only: never execute mutations, especially the exit control.
                run([args.node, "--experimental-strip-types", "--check", str(work / RELATIVE)])
            patch = complete_patch(base, work)
            scratch_patch = temporary / f"{name}.patch"
            scratch_patch.write_bytes(patch)
            checked = temporary / f"{name}-base-check"
            shutil.copytree(base, checked)
            run(["git", "apply", "--check", str(scratch_patch)], checked)
            run(["git", "apply", str(scratch_patch)], checked)
            if files(checked) != files(work):
                raise RuntimeError(f"Standalone patch changed resulting bytes for {name}")
            patches[name] = patch
            entries.append({
                "name": name, "patch": f"{name}.patch", "apply_after": "base", "expected_reward": 0,
                "patch_sha256": hashlib.sha256(patch).hexdigest(),
            })
            provenance.append({
                "name": name, "defect": description, "expected_target_checks": expected_cases,
                "syntax_checked": bool(args.node), "base_apply_checked": True,
                "resulting_files_equal": True, "source_sha256": hashlib.sha256(mutated.encode()).hexdigest(),
                "runtime_validation": "not_run",
            })
    # Publish only after every generated patch has passed the static checks.
    for name, patch in patches.items():
        (output / f"{name}.patch").write_bytes(patch)
    manifest_path = output / "ci-cases.json"
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"cases": []}
    generated_names = {case[0] for case in generated}
    retained = [case for case in previous["cases"] if case["name"] not in generated_names]
    manifest = {"schema_version": "ai_infra_bench_validation_cases.v1", "cases": retained + entries}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "wrong-control-provenance.json").write_text(json.dumps({
        "base_commit": BASE_SHA,
        "oracle_patch_sha256": hashlib.sha256(oracle_patch.read_bytes()).hexdigest(),
        "oracle_index_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "relative_file": RELATIVE.as_posix(), "cases": provenance,
        "patch_format": "Each complete patch contains the Oracle changes plus one deliberate defect and applies directly to Base.",
        "note": "Expected failures require runtime confirmation; these checks prove Base applicability, resulting bytes, and syntax only.",
    }, indent=2) + "\n")
    print(f"Generated {len(entries)} self-contained controls; all apply to Base. Runtime checks remain required.")


if __name__ == "__main__":
    main()
