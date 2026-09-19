import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";

const read = (file) =>
  readFileSync(new URL("../" + file, import.meta.url), "utf8");

test("accepted Index edition is unconditional in development and production", () => {
  const layout = read("app/layout.tsx"),
    config = read("next.config.ts");
  assert.match(layout, /<html lang="en" className="editorial-index">/);
  assert.match(layout, /import "\.\/editorial-index\.css"/);
  assert.doesNotMatch(
    layout + config,
    /DESIGN_FINISH|designFinish|data-design-(family|finish)/,
  );
  for (const file of [
    "app/lib/design-finishes.ts",
    "app/design-finishes.css",
    "scripts/build-design-finishes.mjs",
  ])
    assert.equal(existsSync(new URL("../" + file, import.meta.url)), false);
});

test("accepted task layout keeps two desktop columns and mobile stacking", () => {
  const css = read("app/editorial-index.css");
  const desktop = css
    .split("@media (min-width: 768px)")[1]
    .split("@container")[0];
  assert.match(
    desktop,
    /\.catalogue-grid\s*\{\s*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/,
  );
  assert.match(
    desktop,
    /\.catalogue-card\s*\{\s*display: flex;\s*flex-direction: column/,
  );
  const mobile = css.split("@media (max-width: 767px)")[1];
  assert.match(
    mobile,
    /\.catalogue-grid\s*\{[^}]*grid-template-columns: minmax\(0, 1fr\)/,
  );
  assert.doesNotMatch(css, /data-design-|\.(?:folio|margin|register)-/);
});

test("Index annotations, numeric alignment, sidebar and expanded results are retained", () => {
  const css = read("app/editorial-index.css");
  assert.match(css, /--plot-point-label-layout: inline/);
  assert.match(
    css,
    /\.pass-average-pair\s*\{[^}]*grid-template-columns: 6ch 1ch 6ch/,
  );
  assert.match(
    css,
    /\.explorer-search\s*\{[^}]*border: 1px solid var\(--line\)/,
  );
  assert.match(
    css,
    /@container \(min-width:\s*1100px\)\s*\{\s*\.editorial-index \.task-breakdown\s*\{\s*grid-template-columns: repeat\(3, minmax\(0, 1fr\)\)/,
  );
});
