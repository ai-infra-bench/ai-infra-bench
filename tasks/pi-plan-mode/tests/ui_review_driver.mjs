/** Observe public review controls before sending real terminal keys. */
import { stripVTControlCharacters } from "node:util";

export const REVIEW_ACTIONS = ["Execute", "Stay", "Refine"];
export function readReview(lines) {
  const text = lines.map(stripVTControlCharacters).join("\n");
  // Borders, indentation and explanatory prose are free. The arrow must be
  // immediately before a complete action word, not before Executed/StayHere.
  const selected = [...text.matchAll(/→[^\S\n]*([^\n]+)/g)].map((match) => match[1].trim());
  if (selected.length !== 1) return undefined;
  const action = /^(Execute|Stay|Refine)(?![\p{L}\p{N}_])/u.exec(selected[0])?.[1];
  return { selected: action ?? selected[0], action, text, selectionLine: text.split("\n").find((line) => line.includes("→")) };

}

export async function navigateReview(surface, target, checkpoint = async () => {}) {
  const action = REVIEW_ACTIONS.find((name) => name.toLowerCase() === target.toLowerCase());
  if (!action) throw new Error(`Unknown review action: ${target}`);
  const visited = new Set();
  // Clamp and wrap both work, including a middle initial selection. Rendered
  // states, not private indices or a fixed option order, delimit each sweep.
  for (const key of ["\x1b[B", "\x1b[A"]) {
    const seen = new Set();
    for (;;) {
      const observed = surface.read();
      if (!observed) throw new Error("UI observer: review is no longer active or its visible selection is ambiguous");
      if (observed.action) visited.add(observed.action);
      if (seen.has(observed.selected)) break;
      seen.add(observed.selected);
      if (visited.size === REVIEW_ACTIONS.length && observed.selected === action) return visited;
      await surface.key(key);
      await checkpoint();
    }
  }
  if (visited.size !== REVIEW_ACTIONS.length) throw new Error(`UI observer: Up/Down did not reach all review actions (saw ${[...visited].join(", ")})`);
  // After checking all actions, select the requested one using the same public
  // navigation. Selection is established before Enter, never from its effects.
  for (const key of ["\x1b[B", "\x1b[A"]) {
    const seen = new Set();
    for (;;) {
      const observed = surface.read();
      if (!observed) throw new Error("UI observer: review disappeared during navigation");
      if (observed.selected === action) return visited;
      if (seen.has(observed.selected)) break;
      seen.add(observed.selected);
      await surface.key(key);
      await checkpoint();
    }
  }
  throw new Error(`UI observer: cannot select ${action}`);
}
