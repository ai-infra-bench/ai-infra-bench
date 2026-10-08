/** Read one approved record without borrowing identity or steps from history. */
export function approvedSnapshot(details) {
  const record = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
  if (!record(details)) throw new Error("Approval details must contain a structured snapshot");
  const fields = ["sessionId", "planId", "revision"];
  // A root identity is authoritative when present, even if incomplete or wrong.
  // Do not silently replace it with an identity found in an extra nested field.
  const identity = fields.some((key) => Object.hasOwn(details, key)) ? details : details.identity;
  if (!record(identity) || fields.some((key) => !Object.hasOwn(identity, key)) ||
      typeof identity.sessionId !== "string" || !identity.sessionId.length ||
      typeof identity.planId !== "string" || !identity.planId.length ||
      typeof identity.revision !== "number" || !Number.isFinite(identity.revision) ||
      !Object.hasOwn(details, "steps") || !Array.isArray(details.steps) ||
      details.steps.some((step) => typeof step !== "string")) {
    throw new Error("Approval details must associate a complete identity with its steps");
  }
  return { sessionId: identity.sessionId, planId: identity.planId, revision: identity.revision, steps: details.steps };
}
