import assert from "node:assert/strict";
import test from "node:test";
import { approvedSnapshot } from "../../tests/approval_snapshot.mjs";

const identity = { sessionId: "session", planId: "opaque/计划", revision: 7 };
const steps = ["  Read\n原文  ", "Check the result"];
const expected = { ...identity, steps };
const accepts = (details) => {
  try { assert.deepEqual(approvedSnapshot(details), expected); return true; }
  catch { return false; }
};

test("root and identity envelope preserve exact approved values and allow metadata", () => {
  assert.equal(accepts({ ...expected, mode: "approved", description: "extra" }), true);
  assert.equal(accepts({ identity, steps, description: "extra" }), true);
});

test("each wrong identity field fails in either representation", () => {
  for (const [field, value] of [["sessionId", "other"], ["planId", "other"], ["revision", 6]]) {
    const wrong = { ...identity, [field]: value };
    assert.equal(accepts({ ...wrong, steps }), false);
    assert.equal(accepts({ identity: wrong, steps }), false);
  }
});

test("steps cannot be missing, shortened, reordered or rewritten", () => {
  for (const wrong of [undefined, steps.slice(0, 1), [...steps].reverse(), steps.map((s) => s.trim()), steps.join("\n")]) {
    assert.equal(accepts({ identity, steps: wrong }), false);
  }
});

test("history, text and unrelated branches cannot supply the approved record", () => {
  for (const details of [
    { current: { ...expected, revision: 6 }, history: [expected] },
    { identity: { ...identity, revision: 6 }, steps, history: [expected] },
    { sessionId: "wrong", identity, steps },
    { sessionId: identity.sessionId, identity: { planId: identity.planId, revision: identity.revision }, steps },
    { identity, history: [{ steps }] },
    { text: JSON.stringify(expected) },
    [expected],
  ]) assert.equal(accepts(details), false);
});
