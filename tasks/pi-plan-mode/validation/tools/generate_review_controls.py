"""Generate curator-only approval and UI controls from Oracle plan-mode index.ts.

No variant calls verifier internals. Generation does not run or certify controls.
Outputs must stay outside the task; merge reviewed patches and catalog additions
only after validating them against the target task version.
"""
from __future__ import annotations

CHOICES = '["Execute the plan (track progress)", "Stay in plan mode", "Refine the plan"]'
SELECT = '''\t\t\tconst choice = await ctx.ui.select(
\t\t\t\t`Plan ${displayed.planId}, revision ${displayed.revision}\\n${displayed.steps.map((step, i) => `${i + 1}. ${step}`).join("\\n")}\\nWhat next?`,
\t\t\t\t["Execute the plan (track progress)", "Stay in plan mode", "Refine the plan"],
\t\t\t);'''
TITLE = '''`Plan ${displayed.planId}, revision ${displayed.revision}\\n${displayed.steps.map((step, i) => `${i + 1}. ${step}`).join("\\n")}\\nWhat next?`'''

VARIANTS = {
    "select-reordered-help": {"expected": "pass", "description": "Real ui.select; Refine, Help, Execute, Stay order; unrelated Help item allowed."},
    "custom-select-list": {"expected": "pass", "description": "Public SelectList, initial Stay, wrap navigation, themed rendering."},
    "custom-component": {"expected": "pass", "description": "Independent public Component, initial Refine, clamp navigation."},
    "widget-terminal": {"expected": "pass", "description": "Public widget and onTerminalInput; initial Stay, wrap; no custom/select dialog."},
    "execute-noop": {"expected": "fail", "description": "Visible Execute closes review without approval or dispatch."},
    "stay-approves": {"expected": "fail", "description": "Stay invokes approval and dispatch despite its label."},
    "navigation-approves": {"expected": "fail", "description": "Custom component approves as soon as Up/Down moves selection."},
    "stale-approves-current": {"expected": "fail", "description": "Old unchanged menu uses latest state identity/revision instead of displayed snapshot."},
    "select-cancel-stale": {"expected": "pass", "description": "AbortSignal dismisses the old select on new submission; old callback cannot approve anything."},
    "custom-refine-editor": {"expected": "pass", "description": "Custom Component Refine opens a separate real custom editor and waits for Enter or Escape."},
    "custom-delayed-render": {"expected": "pass", "description": "Custom Component updates selection and requests redraw asynchronously after 20ms."},
    "custom-refresh-current": {"expected": "pass", "description": "Same custom control refreshes visible snapshot before accepting keys after revision change; preliminary lifecycle control."},
}


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"Expected exactly one Oracle anchor, got {source.count(old)}: {old[:100]!r}")
    return source.replace(old, new, 1)


def custom_component(*, navigation_approves: bool = False, refresh: bool = False) -> str:
    on_move = '''
                    if (displayed.planId) {
                        const error = approve(ctx, displayed.sessionId, displayed.planId, displayed.revision);
                        result("approve", error);
                    }''' if navigation_approves else ""
    refresh_fn = '''
                const refresh = () => {
                    if (state.mode === "planning" && state.planId === displayed.planId && state.revision !== displayed.revision) {
                        displayed = snapshot();
                        title = TITLE;
                    }
                };'''.replace("TITLE", TITLE) if refresh else ""
    refresh_call = "refresh();" if refresh else ""
    return '''            const choice = await ctx.ui.custom<string | undefined>((tui, _theme, _keys, done) => {
                const options = CHOICES;
                let selected = 2;
                let title = TITLE;
                REFRESH_FN
                return {
                    render(_width: number) {
                        REFRESH_CALL
                        return [...title.split("\\n"), ...options.map((label, i) => `${i === selected ? "→ " : "  "}${label}`)];
                    },
                    invalidate() {},
                    handleInput(data: string) {
                        if (matchesKey(data, "up") || matchesKey(data, "down")) {
                            selected = Math.max(0, Math.min(options.length - 1, selected + (matchesKey(data, "up") ? -1 : 1)));
                            ON_MOVE
                            tui.requestRender();
                        } else if (matchesKey(data, "enter")) done(options[selected]);
                        else if (matchesKey(data, "escape")) done(undefined);
                    },
                };
            });'''.replace("CHOICES", CHOICES).replace("TITLE", TITLE).replace("REFRESH_FN", refresh_fn).replace("REFRESH_CALL", refresh_call).replace("ON_MOVE", on_move)


SELECT_LIST = '''            const choice = await ctx.ui.custom<string | undefined>((tui, theme, _keys, done) => {
                const options = CHOICES;
                const title = TITLE;
                const list = new SelectList(options.map((label) => ({ label, value: label })), 5, {
                    selectedPrefix: (text) => theme.fg("accent", text),
                    selectedText: (text) => theme.fg("accent", text),
                    description: (text) => theme.fg("muted", text),
                    scrollInfo: (text) => theme.fg("muted", text),
                    noMatch: (text) => theme.fg("muted", text),
                });
                list.setSelectedIndex(1);
                list.onSelect = (item) => done(item.value);
                list.onCancel = () => done(undefined);
                return {
                    render(width: number) { return [...title.split("\\n"), ...list.render(width)]; },
                    invalidate() { list.invalidate(); },
                    handleInput(data: string) { list.handleInput(data); tui.requestRender(); },
                };
            });'''.replace("CHOICES", CHOICES).replace("TITLE", TITLE)

WIDGET = '''            const choice = await new Promise<string | undefined>((resolve) => {
                const options = CHOICES;
                const title = TITLE;
                let selected = 1;
                const redraw = () => ctx.ui.setWidget("plan-review-actions", [
                    ...title.split("\\n"),
                    ...options.map((label, i) => `${i === selected ? "→ " : "  "}${label}`),
                ]);
                let unsubscribe = () => {};
                const finish = (choice: string | undefined) => {
                    unsubscribe();
                    ctx.ui.setWidget("plan-review-actions", undefined);
                    resolve(choice);
                };
                unsubscribe = ctx.ui.onTerminalInput((data) => {
                    if (matchesKey(data, "up") || matchesKey(data, "down")) {
                        selected = (selected + (matchesKey(data, "up") ? -1 : 1) + options.length) % options.length;
                        redraw();
                    } else if (matchesKey(data, "enter")) finish(options[selected]);
                    else if (matchesKey(data, "escape")) finish(undefined);
                    else return undefined;
                    return { consume: true };
                });
                redraw();
            });'''.replace("CHOICES", CHOICES).replace("TITLE", TITLE)


def transform(source: str, variant: str) -> str:
    if variant not in VARIANTS:
        raise ValueError(f"Unknown variant: {variant}")
    if variant == "select-cancel-stale":
        source = replace_once(source, "\tlet reviewOpen = false;", "\tlet reviewOpen = false;\n\tlet cancelReview: (() => void) | undefined;")
        source = replace_once(source, "\t\tconst displayed = snapshot();", "\t\tconst displayed = snapshot();\n\t\tconst controller = new AbortController();\n\t\tconst cancelThisReview = () => controller.abort();\n\t\tcancelReview = cancelThisReview;")
        source = replace_once(source, SELECT, SELECT.replace(CHOICES + ",", CHOICES + ",\n\t\t\t\t{ signal: controller.signal },"))
        source = replace_once(source, "\t\t} finally {\n\t\t\treviewOpen = false;", "\t\t} finally {\n\t\t\tif (cancelReview === cancelThisReview) cancelReview = undefined;\n\t\t\treviewOpen = false;")
        return replace_once(source, "\t\t\tstate = { ...state, revision: state.revision + 1, steps: [...steps], approvedRevision: null };", "\t\t\tcancelReview?.();\n\t\t\tstate = { ...state, revision: state.revision + 1, steps: [...steps], approvedRevision: null };")
    if variant == "select-reordered-help":
        return replace_once(source, CHOICES, '["Refine the plan", "Help: review keyboard", "Execute the plan (track progress)", "Stay in plan mode"]')
    if variant in {"execute-noop", "stay-approves", "stale-approves-current"}:
        if variant == "execute-noop":
            return replace_once(source, 'if (choice === "Execute the plan (track progress)" && displayed.planId)', 'if (choice === "Never selected" && displayed.planId)')
        if variant == "stay-approves":
            return replace_once(source, 'if (choice === "Execute the plan (track progress)" && displayed.planId)', 'if ((choice === "Execute the plan (track progress)" || choice === "Stay in plan mode") && displayed.planId)')
        return replace_once(source, 'const error = approve(ctx, displayed.sessionId, displayed.planId, displayed.revision);', 'const error = approve(ctx, state.sessionId, state.planId!, state.revision);')
    imports = 'import { Key, matchesKey' + (', SelectList' if variant == "custom-select-list" else '') + ' } from "@earendil-works/pi-tui";'
    source = replace_once(source, 'import { Key } from "@earendil-works/pi-tui";', imports)
    if variant == "custom-select-list":
        body = SELECT_LIST
    elif variant == "widget-terminal":
        body = WIDGET
    else:
        body = custom_component(navigation_approves=variant == "navigation-approves", refresh=variant == "custom-refresh-current")
    if variant == "custom-delayed-render":
        body = body.replace('selected = Math.max(0, Math.min(options.length - 1, selected + (matchesKey(data, "up") ? -1 : 1)));', 'const delta = matchesKey(data, "up") ? -1 : 1;\n                            setTimeout(() => { selected = Math.max(0, Math.min(options.length - 1, selected + delta)); tui.requestRender(); }, 20);')
        body = body.replace("                            tui.requestRender();", "")
    if variant == "custom-refine-editor":
        editor = '''const refinement = await ctx.ui.custom<string | undefined>((tui, _theme, _keys, done) => {
                    let buffer = "";
                    return {
                        render(_width: number) { return ["Refine the plan:", `> ${buffer}`, "Enter to submit; Escape to cancel"]; },
                        invalidate() {},
                        handleInput(data: string) {
                            if (matchesKey(data, "enter")) done(buffer);
                            else if (matchesKey(data, "escape")) done(undefined);
                            else if (matchesKey(data, "backspace")) { buffer = [...buffer].slice(0, -1).join(""); tui.requestRender(); }
                            else if (![...data].some((char) => char.charCodeAt(0) < 32 || char.charCodeAt(0) === 127)) { buffer += data; tui.requestRender(); }
                        },
                    };
                });'''
        source = replace_once(source, 'const refinement = await ctx.ui.editor("Refine the plan:", "");', editor)
    if variant == "custom-refresh-current":
        source = replace_once(source, '\t\tconst displayed = snapshot();', '\t\tlet displayed = snapshot();')
    return replace_once(source, SELECT, body)


APPROVAL_CONTROLS = {
    "approved-identity-envelope": (
        '{ identity: { sessionId: approved.sessionId, planId: approved.planId, revision: approved.revision }, steps: approved.steps }',
        1, "A complete identity envelope preserves the same approved snapshot as the flat representation."),
    "approved-wrong-revision": (
        '{ identity: { sessionId: approved.sessionId, planId: approved.planId, revision: approved.revision - 1 }, steps: approved.steps }',
        0, "Approval details contain an older revision despite unchanged correct text and execution context."),
    "approved-missing-steps": (
        '{ identity: { sessionId: approved.sessionId, planId: approved.planId, revision: approved.revision }, steps: approved.steps.slice(1) }',
        0, "Approval details omit a submitted step despite preserving the complete identity."),
    "approved-history-only": (
        '{ current: { ...approved, revision: approved.revision - 1 }, history: [approved] }',
        0, "A correct historical snapshot cannot substitute for the incorrect current approval."),
}


def generate(source: str, output):
    import difflib
    import hashlib
    import json
    path = "packages/coding-agent/examples/extensions/plan-mode/index.ts"
    prepared = [("ui-" + name, transform(source, name), int(meta["expected"] == "pass"), meta["description"])
                for name, meta in VARIANTS.items()]
    prepared.extend((name, replace_once(source, "details: approved,", "details: " + replacement + ","), reward, rationale)
                    for name, (replacement, reward, rationale) in APPROVAL_CONTROLS.items())
    output.mkdir(parents=True, exist_ok=False)
    (output / "patches").mkdir()
    cases = []
    for name, changed, reward, rationale in prepared:
        patch = f"diff --git a/{path} b/{path}\n" + "".join(difflib.unified_diff(
            source.splitlines(keepends=True), changed.splitlines(keepends=True),
            fromfile="a/" + path, tofile="b/" + path))
        if changed == source:
            raise ValueError("Control did not change source: " + name)
        raw = patch.encode()
        (output / "patches" / (name + ".patch")).write_bytes(raw)
        cases.append({"name": name, "patch": "patches/" + name + ".patch", "apply_after": "oracle",
                      "expected_reward": reward, "patch_sha256": hashlib.sha256(raw).hexdigest(), "rationale": rationale})
    (output / "ci-cases.additions.json").write_text(json.dumps(
        {"schema_version": "ai_infra_bench_validation_cases.v2", "cases": cases}, indent=2) + "\n")
    (output / "source-sha256.txt").write_text(hashlib.sha256(source.encode()).hexdigest() + "\n")


if __name__ == "__main__":
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("oracle_index", type=Path, help="index.ts after applying the current Oracle patch")
    parser.add_argument("--output", type=Path, required=True, help="New output directory outside this task")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(Path(__file__).resolve().parents[2]):
        parser.error("Output must be outside the task directory")
    generate(args.oracle_index.read_text(), output)
