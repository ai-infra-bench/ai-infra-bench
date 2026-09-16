#!/usr/bin/env python3
"""Regenerate complete Base-applicable negative controls from the Oracle patch.

Usage: python3 validation/generate_controls.py --base-repo /path/to/pi
The repository must contain the pinned Base object. It is never modified.
Compilation and behavioral grading are separate validation steps.
"""

import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

BASE = "d981de1229ef899957bbe968bc8dcda02a21f477"
STORE = Path("packages/coding-agent/src/core/safe-rollback.ts")
SDK = Path("packages/coding-agent/src/core/sdk.ts")
SCHEMA = "ai_infra_bench_validation_cases.v1"


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f"Expected one source anchor, found {source.count(old)}: {old!r}")
    return source.replace(old, new)


def memory_only(source):
    source = replace_once(
        source,
        'import { existsSync, lstatSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";',
        'import { existsSync, lstatSync, readFileSync } from "node:fs";',
    )
    start = source.index("\tprivate save(): void {")
    return source[:start] + "\tprivate save(): void {\n\t\tvoid this.journalPath;\n\t}\n}\n"


def end_only(source):
    return replace_once(source, "\t\tthis.save();\n\t\tthis.liveRequest = true;", "\t\tthis.liveRequest = true;")


def files_only(source):
    return replace_once(source, "\t\t\trestoreConversation(target.entryId, target.id);", "\t\t\tvoid restoreConversation;")


def conversation_only(source):
    source = replace_once(source, "\t\tconst intent = this.journal.intent!;", "\t\tconst intent = { ...this.journal.intent!, files: {} as Record<string, FileImage | null> };")
    return source


def ignore_conflicts(source):
    return replace_once(source, "\t\tif (conflicts.size > 0) {", "\t\tconflicts.clear();\n\t\tif (conflicts.size > 0) {")


def skip_startup_recovery(source):
    anchor = "\tasync recover(restoreConversation: (entryId: string | null, checkpointId: string) => void): Promise<void> {"
    return replace_once(source, anchor, anchor + "\n\t\tif (this.journal.intent || this.journal.active) {\n\t\t\tdelete this.journal.intent;\n\t\t\tdelete this.journal.active;\n\t\t\treturn;\n\t\t}")


def abandoned_branch(source):
    source = replace_once(source,
        "\t\tconst ancestors = new Set(this.sessionManager.getBranch().map((entry) => entry.id));\n", "")
    source = replace_once(source,
        "\t\t\t.filter(({ entryId }) => entryId === null || ancestors.has(entryId))\n", "")
    return replace_once(
        source,
        "\t\t\t\tcheckpoints: [...this.journal.checkpoints.slice(0, index), { ...target, after: target.before }],",
        "\t\t\t\tcheckpoints: this.journal.checkpoints.map((checkpoint) => checkpoint.id === target.id ? { ...target, after: target.before } : checkpoint),",
    )


def early_exit(source):
    return replace_once(source, "\tawait session.initializeSafeRollback();", "\tif (options.safeRollback === true) await new Promise<void>(() => { process.exit(0); });\n\tawait session.initializeSafeRollback();")


CONTROLS = [
    ("memory-only", STORE, memory_only, "Keeps checkpoint state only in process memory; restart loses enablement and recovery history."),
    ("checkpoint-at-request-end", STORE, end_only, "Publishes a checkpoint only at completion, losing the current checkpoint when a request is killed."),
    ("files-only", STORE, files_only, "Restores workspace files while retaining the abandoned effective conversation."),
    ("conversation-only", STORE, conversation_only, "Restores the conversation while leaving request file mutations in place."),
    ("ignore-conflicts", STORE, ignore_conflicts, "Discards preflight idle-edit conflicts and overwrites externally edited paths."),
    ("skip-startup-recovery", STORE, skip_startup_recovery, "Reports ready on restart by discarding unresolved request or restore intent."),
    ("abandoned-branch-included", STORE, abandoned_branch, "Retains abandoned descendant checkpoints and exposes them as eligible public targets without ancestry validation."),
    ("early-process-exit-zero", SDK, early_exit, "Exits successfully during enabled safe-rollback SDK construction without serving the public protocol; ordinary disabled sessions remain unaffected."),
]


def run(args, cwd=None, accepted=(0,)):
    result = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode not in accepted:
        raise RuntimeError(result.stderr.decode(errors="replace"))
    return result.stdout


def fingerprint(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-repo", type=Path, required=True)
    args = parser.parse_args()
    validation = Path(__file__).resolve().parent
    oracle = validation.parent / "solution/oracle.patch"
    archive = run(["git", "archive", BASE], cwd=args.base_repo)
    cases = []
    provenance = {"base_commit": BASE, "oracle_patch_sha256": hashlib.sha256(oracle.read_bytes()).hexdigest(), "controls": []}
    with tempfile.TemporaryDirectory(prefix="pi-safe-rollback-controls-") as temp:
        temp = Path(temp)
        base = temp / "base"
        base.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(base, filter="data")
        for name, source_path, mutate, rationale in CONTROLS:
            candidate = temp / "candidate"
            applied = temp / "applied"
            shutil.copytree(base, candidate, symlinks=True)
            run(["git", "apply", "--check", str(oracle)], cwd=candidate)
            run(["git", "apply", str(oracle)], cwd=candidate)
            source = candidate / source_path
            source.write_text(mutate(source.read_text()))
            patch = run(["git", "diff", "--no-index", "--binary", "--", "base", "candidate"], cwd=temp, accepted=(1,))
            for prefix in (b"a/base/", b"a/candidate/"):
                patch = patch.replace(prefix, b"a/")
            for prefix in (b"b/base/", b"b/candidate/"):
                patch = patch.replace(prefix, b"b/")
            patch_file = temp / f"{name}.patch"
            patch_file.write_bytes(patch)
            shutil.copytree(base, applied, symlinks=True)
            run(["git", "apply", "--check", str(patch_file)], cwd=applied)
            run(["git", "apply", str(patch_file)], cwd=applied)
            if fingerprint(applied) != fingerprint(candidate):
                raise RuntimeError(f"Full patch result differs from generated candidate: {name}")
            digest = hashlib.sha256(patch).hexdigest()
            (validation / patch_file.name).write_bytes(patch)
            cases.append({"name": name, "patch": patch_file.name, "apply_after": "base", "expected_reward": 0, "patch_sha256": digest, "rationale": rationale})
            provenance["controls"].append({"name": name, "patch_sha256": digest, "base_apply_check": True, "complete_result_equality": True})
            shutil.rmtree(candidate)
            shutil.rmtree(applied)
    case_file = validation / "ci-cases.json"
    existing = json.loads(case_file.read_text()) if case_file.exists() else {"schema_version": SCHEMA, "cases": []}
    controlled_names = {item[0] for item in CONTROLS}
    existing["cases"] = [case for case in existing["cases"] if case["name"] not in controlled_names] + cases
    case_file.write_text(json.dumps(existing, indent=2) + "\n")
    (validation / "control-generation.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"Generated and checked {len(cases)} standalone Base patches")


if __name__ == "__main__":
    main()
