import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const svg = await readFile(new URL("../public/favicon.svg", import.meta.url));

// Retain the legacy 32px asset for cached pages. Search uses the 192px PNG.
for (const size of [32, 192]) {
  // The SVG has a 64px canvas at 72 DPI. Render larger sizes from the vector
  // paths directly, so the search icon never enlarges a small raster image.
  await sharp(svg, { density: 72 * Math.max(1, size / 64) })
    .resize(size, size)
    .png()
    .toFile(fileURLToPath(new URL(`../public/favicon-${size}.png`, import.meta.url)));
}
