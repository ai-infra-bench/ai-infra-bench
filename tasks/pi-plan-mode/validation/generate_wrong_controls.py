#!/usr/bin/env python3
"""Regenerate one-defect controls against an Oracle checkout, without editing it.

Usage: python3 validation/generate_wrong_controls.py --oracle-dir /path/to/pi-oracle
Each generated patch is applied after solution/solve.sh. Exact replacement counts
fail closed if the Oracle changes. Node checks parsing, not runtime correctness.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

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
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracle-dir", type=Path, required=True)
    parser.add_argument("--node", default=shutil.which("node"))
    args = parser.parse_args()
    oracle_dir = args.oracle_dir.resolve()
    source = (oracle_dir / RELATIVE).read_text()
    output = Path(__file__).resolve().parent
    generated = variants(source)
    entries = []
    provenance = []
    with tempfile.TemporaryDirectory(prefix="pi-plan-controls-") as temporary:
        temporary = Path(temporary)
        for name, mutated, description, expected_cases in generated:
            if mutated == source:
                raise RuntimeError(f"Control {name} has no change")
            # Parse only. Never execute candidate mutations (especially early exit).
            if args.node:
                syntax_file = temporary / f"{name}.ts"
                syntax_file.write_text(mutated)
                subprocess.run([args.node, "--check", str(syntax_file)], check=True, capture_output=True, text=True)
            patch = ''.join(difflib.unified_diff(
                source.splitlines(keepends=True), mutated.splitlines(keepends=True),
                fromfile=f"a/{RELATIVE.as_posix()}", tofile=f"b/{RELATIVE.as_posix()}",
            ))
            patch_path = output / f"{name}.patch"
            patch_path.write_text(patch)
            # --check is read-only, including when the Oracle has unstaged changes.
            subprocess.run(["git", "apply", "--check", str(patch_path)], cwd=oracle_dir, check=True, capture_output=True, text=True)
            entries.append({
                "name": name, "patch": patch_path.name, "apply_after": "oracle", "expected_reward": 0,
                "patch_sha256": hashlib.sha256(patch.encode()).hexdigest(),
            })
            provenance.append({
                "name": name, "defect": description, "expected_target_checks": expected_cases,
                "syntax_checked": bool(args.node), "git_apply_checked": True, "runtime_validation": "not_run",
            })
    manifest_path = output / "ci-cases.json"
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"cases": []}
    generated_names = {case[0] for case in generated}
    # Root may append a completed alternative later. Regeneration preserves it.
    retained = [case for case in previous["cases"] if case["name"] not in generated_names]
    manifest = {"schema_version": "ai_infra_bench_validation_cases.v1", "cases": retained + entries}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "wrong-control-provenance.json").write_text(json.dumps({
        "oracle_index_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "relative_file": RELATIVE.as_posix(), "cases": provenance,
        "note": "Expected failures require runtime confirmation; these checks prove patch application and syntax only.",
    }, indent=2) + "\n")
    print(f"Generated {len(entries)} controls; Oracle checkout unchanged. Runtime checks remain required.")


if __name__ == "__main__":
    main()
