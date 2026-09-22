#!/usr/bin/env python3
"""Curator-only: derive the plausible-wrong control patches from the Oracle and run the verifier suites on each.

Runs inside the pi dev checkout (scratchpad pi-base): the Oracle extension lives there as untracked files.
For each control the transformed index.ts is written in place, a full patch (README + index.ts + unit test)
is generated with git, the contract and lifecycle suites are run, and the Oracle file is restored.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PI = Path(sys.argv[1]).resolve()
TASK = Path(sys.argv[2]).resolve()
ONLY = set(sys.argv[3:])
EXT_DIR = PI / "packages/coding-agent/examples/extensions/agent-trace"
INDEX = EXT_DIR / "index.ts"
UNIT = PI / "packages/coding-agent/test/agent-trace-extension.test.ts"
PATHS = ["packages/coding-agent/examples/extensions/agent-trace", "packages/coding-agent/test/agent-trace-extension.test.ts"]
VERIFIER = PI / "packages/coding-agent/test/__verifier__"
ENV = dict(os.environ, PI_WORKSPACE=str(PI), PI_VERIFIER_FIXTURES=str(TASK / "tests/fixtures"), PI_OFFLINE="1", PI_TELEMETRY="0", PI_NO_LOCAL_LLM="1", HOME="/tmp/at-home")
sys.path.insert(0, str(TASK / "tests"))
from case_contract import CONTRACT_CASES

ORACLE = INDEX.read_text()


def must_replace(text: str, old: str, new: str) -> str:
    if old not in text:
        raise SystemExit(f"transform anchor missing: {old[:80]!r}")
    return text.replace(old, new)


FORGED_NAMES = json.dumps(sorted(CONTRACT_CASES))


def forged_junit(text: str) -> str:
    hook = f"""
	// CONTROL: write a passing contract JUnit and leave before vitest can report.
	{{
		const names: string[] = {FORGED_NAMES};
		const dir = "/logs/verifier";
		if (existsSync(dir)) {{
			const cases = names.map((name) => `<testcase classname="agent-trace contract" name="${{name.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;")}}" time="0.01"></testcase>`).join("");
			writeFileSync(`${{dir}}/contract-junit.xml`, `<?xml version="1.0"?><testsuites><testsuite name="forged" tests="${{names.length}}" failures="0" errors="0" skipped="0">${{cases}}</testsuite></testsuites>`);
			setTimeout(() => process.exit(0), 50);
		}}
	}}
"""
    return must_replace(text, "export default function (pi: ExtensionAPI) {\n", "export default function (pi: ExtensionAPI) {\n" + hook)


CONTROLS: dict[str, tuple[str, callable]] = {
    "control-int-attributes-as-numbers": (
        "intValue is encoded as a JSON number instead of the OTLP/JSON decimal string",
        lambda t: must_replace(t, "{ intValue: String(Math.trunc(value)) }", "{ intValue: Math.trunc(value) }"),
    ),
    "control-chat-written-before-persist": (
        "chat spans are written at message_end, before pi persists the assistant entry, so they carry no entry id",
        lambda t: must_replace(t, "\t\tturnChats.push(chat);\n", "\t\twrite(chat);\n"),
    ),
    "control-trace-id-per-process": (
        "the trace id is random per extension instance instead of derived from the session id",
        lambda t: must_replace(t, 'return createHash("sha256").update(`${SCOPE_NAME}:${sessionId}`).digest("hex").slice(0, 32);', "void sessionId;\n\treturn randomBytes(16).toString(\"hex\");"),
    ),
    "control-wakeup-as-prompt": (
        "every run that is not a continuation is reported as a prompt run",
        lambda t: must_replace(t, 'runTrigger = sawBeforeAgentStart ? "prompt" : previousRunSettled ? "wakeup" : "continuation";', 'runTrigger = sawBeforeAgentStart || previousRunSettled ? "prompt" : "continuation";'),
    ),
    "control-continuation-as-wakeup": (
        "agent_settled is not tracked, so a continuation run is reported as a wakeup",
        lambda t: must_replace(t, "\t\tpreviousRunSettled = false;\n", ""),
    ),
    "control-tool-error-status-ok": (
        "a failing tool result keeps status OK (only the is_error attribute changes)",
        lambda t: must_replace(t, "\t\tif (event.isError) fail(span, resultText(event.result));\n", ""),
    ),
    "control-compaction-under-last-run": (
        "compaction spans are parented to the run that just ended, which they do not fit inside",
        lambda t: must_replace(
            must_replace(
                must_replace(t, "\tlet run: Span | undefined;\n", "\tlet run: Span | undefined;\n\tlet lastRun: Span | undefined;\n"),
                "\t\twrite(end(run));\n\t\trun = undefined;", "\t\twrite(end(run));\n\t\tlastRun = run;\n\t\trun = undefined;",
            ),
            'compaction = start("pi.compaction", KIND_INTERNAL, undefined, Date.now(), [', 'compaction = start("pi.compaction", KIND_INTERNAL, run ?? lastRun, Date.now(), [',
        ),
    ),
    "control-missing-line-terminator": (
        "lines are appended without a newline terminator",
        lambda t: must_replace(t, "appendFileSync(file, `${JSON.stringify(line)}\\n`);", "appendFileSync(file, JSON.stringify(line));"),
    ),
    "control-error-status-without-message": (
        "ERROR statuses carry no message",
        lambda t: must_replace(t, "\t\tspan.status = { code: STATUS_ERROR, message };", "\t\tvoid message;\n\t\tspan.status = { code: STATUS_ERROR };"),
    ),
    "control-chat-held-until-turn-end": (
        "the chat span is only written at turn_end, so a process killed during a tool execution loses it",
        lambda t: must_replace(t, 'pi.on("tool_execution_start", async (event, ctx) => {\n\t\tflushChats(ctx);\n', 'pi.on("tool_execution_start", async (event, ctx) => {\n\t\tvoid ctx;\n'),
    ),
    "control-no-shutdown-flush": (
        "session_shutdown discards open spans instead of closing them with status shutdown",
        lambda t: must_replace(t, "\t\tfor (const span of closing) {", "\t\tfor (const span of [] as Span[]) {\n\t\t\tvoid closing;"),
    ),
    "control-write-failure-throws": (
        "a failed write throws out of the event handler instead of being caught and reported",
        lambda t: must_replace(t, "\t\tif (!file || !resourceAttributes) return;\n\t\ttry {\n\t\t\twriteLine(span, phase);", "\t\tif (!file || !resourceAttributes) return;\n\t\twriteLine(span, phase);\n\t\ttry {"),
    ),
    "control-aborted-as-ok": (
        "an aborted assistant message leaves chat and turn spans OK",
        lambda t: must_replace(
            must_replace(t, '\t\telse if (message.stopReason === "aborted") fail(chat, message.errorMessage ?? "aborted");\n', ""),
            'if (chatFailed || message?.stopReason === "error" || message?.stopReason === "aborted") {', 'if (chatFailed || message?.stopReason === "error") {',
        ),
    ),
    "control-no-start-lines": (
        "spans are written only when they end, so the file does not update while a span is in progress",
        lambda t: must_replace(t, '\t\twrite(span, "start");\n\t\treturn span;', "\t\treturn span;"),
    ),
    "control-end-line-keeps-phase": (
        "end lines keep pi.span.phase = start, so a reader cannot tell finished spans from open ones",
        lambda t: must_replace(t, '\t\tif (phase === "start") attributes.set("pi.span.phase", "start");', '\t\tattributes.set("pi.span.phase", "start");'),
    ),
    "control-single-tool-slot": (
        "only one tool span is tracked at a time, so concurrent tool calls lose all but the last",
        lambda t: must_replace(t, "\t\ttools.set(event.toolCallId, span);", "\t\ttools.clear();\n\t\ttools.set(event.toolCallId, span);"),
    ),
    "control-steer-messages-unrecorded": (
        "steering messages are not recorded on the run (steer_count stays 0)",
        lambda t: must_replace(t, "\t\t\t\tif (runMessagesSeen > 1) steerThisTurn += 1;\n", ""),
    ),
    "control-compaction-usage-omitted": (
        "compaction spans omit the summary requests' token usage",
        lambda t: must_replace(t, "\t\tif (usage) {\n\t\t\tcompaction.attributes.set(\"gen_ai.usage.input_tokens\", usage.input);", "\t\tif (usage && false) {\n\t\t\tcompaction.attributes.set(\"gen_ai.usage.input_tokens\", usage.input);"),
    ),
    "control-no-trace-propagation": (
        "the propagation variable is neither read at bind nor published while tools run",
        lambda t: must_replace(
            must_replace(t, "\tconst inheritedTraceParent = process.env[TRACE_PARENT_ENV];", "\tconst inheritedTraceParent = undefined as string | undefined;"),
            "\t\tif (current && traceId) process.env[TRACE_PARENT_ENV] = `${traceId}-${current}`;\n", "\t\tvoid current;\n",
        ),
    ),
    "control-retry-run-claims-a-message": (
        "an overflow retry run resolves an entry id like any other run and claims an unrelated custom message",
        lambda t: must_replace(t, "\t\trunEntryResolved = retryAfterCompaction !== undefined;", "\t\trunEntryResolved = false;"),
    ),
    "control-overflow-will-retry-false": (
        "compaction spans report will_retry false even for overflow recovery",
        lambda t: must_replace(t, '\t\t\t["pi.compaction.will_retry", event.willRetry],', '\t\t\t["pi.compaction.will_retry", false],'),
    ),
    "control-forged-junit": ("writes a passing contract JUnit then exits the process", forged_junit),
    "control-process-exit-zero-after-registration": (
        "process.exit(0) 50 ms after the extension loads",
        lambda t: must_replace(t, "export default function (pi: ExtensionAPI) {\n", "export default function (pi: ExtensionAPI) {\n\tsetTimeout(() => process.exit(0), 50);\n"),
    ),
}


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, env=ENV, text=True, capture_output=True, check=check)


def suites(label: str) -> dict:
    VERIFIER.mkdir(parents=True, exist_ok=True)
    for name in ["at_support.ts", "at.contract.test.ts", "at.lifecycle.test.ts"]:
        shutil.copy2(TASK / "tests" / name, VERIFIER / name)
    out = {}
    for suite in ["contract", "lifecycle"]:
        junit = Path(f"/tmp/at-{label}-{suite}.xml")
        junit.unlink(missing_ok=True)
        proc = run(
            ["node", "../../node_modules/vitest/vitest.mjs", "run", "--reporter=junit", f"--outputFile={junit}", f"test/__verifier__/at.{suite}.test.ts"],
            PI / "packages/coding-agent",
            check=False,
        )
        cases = ET.parse(junit).getroot().findall(".//testcase") if junit.exists() else []
        failed = [c.attrib.get("name") for c in cases if c.find("failure") is not None or c.find("error") is not None]
        out[suite] = {"exit": proc.returncode, "cases": len(cases), "failed": failed}
    shutil.rmtree(VERIFIER, ignore_errors=True)
    return out


def patch(name: str) -> Path:
    run(["git", "add", "-N", *PATHS], PI)
    diff = run(["git", "diff", "--", *PATHS], PI).stdout
    run(["git", "reset", "-q", "--", *PATHS], PI)
    target = TASK / "validation" / "patches" / f"{name}.patch"
    target.write_text(diff)
    return target


# Real-agent submissions kept as alternative cases: applied to Base with the Oracle files moved aside.
CANDIDATES = {name: TASK / "validation" / "patches" / f"{name}.patch" for name in ["alt-grok-run1", "alt-grok-run3", "alt-grok-run4", "alt-grok-run5", "alt-grok-run6"]}


def candidate(name: str, patch_path: Path) -> dict:
    off = EXT_DIR.with_name("agent-trace.off")
    unit_off = UNIT.with_suffix(".off")
    EXT_DIR.rename(off)
    UNIT.rename(unit_off)
    try:
        # The examples index README is already modified in the dev checkout; the hunk is cosmetic.
        run(["git", "apply", "--exclude=packages/coding-agent/examples/extensions/README.md", str(patch_path)], PI)
        try:
            return suites(name)
        finally:
            # Remove everything the candidate patch created (it may add files outside PATHS), then restore tracked files.
            touched = {line.split(" b/", 1)[1].strip() for line in patch_path.read_text().splitlines() if line.startswith("diff --git ")}
            for rel in touched | set(PATHS):
                target = PI / rel
                if rel.endswith("examples/extensions/README.md"):
                    continue
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink(missing_ok=True)
            run(["git", "checkout", "--", *PATHS], PI, check=False)
    finally:
        off.rename(EXT_DIR)
        unit_off.rename(UNIT)


def main() -> None:
    report = {}
    try:
        if not ONLY or "oracle" in ONLY:
            report["oracle"] = suites("oracle")
        if not ONLY or "base" in ONLY:
            off = EXT_DIR.with_name("agent-trace.off")
            EXT_DIR.rename(off)
            try:
                report["base"] = suites("base")
            finally:
                off.rename(EXT_DIR)
        for name, (description, transform) in CONTROLS.items():
            if ONLY and name not in ONLY:
                continue
            INDEX.write_text(transform(ORACLE))
            try:
                target = patch(name)
                result = suites(name)
                result["patch_lines"] = len(target.read_text().splitlines())
                result["description"] = description
                report[name] = result
            finally:
                INDEX.write_text(ORACLE)
        for name, patch_path in CANDIDATES.items():
            if (ONLY and name not in ONLY) or not patch_path.exists():
                continue
            result = candidate(name, patch_path)
            result["patch_lines"] = len(patch_path.read_text().splitlines())
            result["description"] = "real-agent submission kept as an alternative case"
            report[name] = result
    finally:
        INDEX.write_text(ORACLE)
        shutil.rmtree(VERIFIER, ignore_errors=True)
    for name, result in report.items():
        c, l = result["contract"], result["lifecycle"]
        print(f"{name:48s} contract exit={c['exit']} {len(c['cases'] and c['failed']) if False else len(c['failed'])}/{c['cases']} failed | lifecycle exit={l['exit']} {len(l['failed'])}/{l['cases']} failed")
        for suite in ("contract", "lifecycle"):
            for failed in result[suite]["failed"][:4]:
                print(f"    {suite} FAIL: {failed}")
    (TASK.parent.parent / "validation-report.json").unlink(missing_ok=True)
    Path("/tmp/at-controls-report.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
