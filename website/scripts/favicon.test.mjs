import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import sharp from "sharp";

test("selected favicon is the three-line monochrome contour with a matching high-resolution PNG", async () => {
  const svg = await readFile(new URL("../public/favicon.svg", import.meta.url));
  const source = svg.toString();
  assert.match(source, /viewBox="0 0 64 64"/);
  assert.equal((source.match(/<path /g) || []).length, 3);
  assert.match(source, /stroke="#3D657C"/);
  assert.match(source, /fill="#F6F0E9"/);
  assert.doesNotMatch(source, /#A16454|#B74F3D|<image|<script/);
  const png = await readFile(
    new URL("../public/favicon-192.png", import.meta.url),
  );
  const metadata = await sharp(png).metadata();
  assert.equal(metadata.width, 192);
  assert.equal(metadata.height, 192);
  const expected = await sharp(svg, { density: 216 })
    .ensureAlpha()
    .raw()
    .toBuffer();
  const actual = await sharp(png).ensureAlpha().raw().toBuffer();
  assert.deepEqual(actual, expected);
});

test("favicon metadata supports base paths and advertises a high-resolution search icon", async () => {
  const layout = await readFile(
    new URL("../app/layout.tsx", import.meta.url),
    "utf8",
  );
  assert.match(layout, /withBasePath\("\/favicon-192\.png"\)/);
  assert.doesNotMatch(layout, /favicon-32\.png/);
  assert.match(layout, /withBasePath\("\/favicon\.svg\?v=contour-mono"\)/);
  assert.match(layout, /sizes: "192x192"/);
  assert.match(layout, /sizes: "any"/);
});
