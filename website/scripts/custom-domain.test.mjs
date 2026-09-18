import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const domain = "infrabench.ai";
test("custom domain is included in the public build input", async () => {
  const cname = await readFile(
    new URL("../public/CNAME", import.meta.url),
    "utf8",
  );
  assert.equal(cname, domain + "\n");
  const prepare = await readFile(
    new URL("./prepare-github-pages.mjs", import.meta.url),
    "utf8",
  );
  assert.ok(
    prepare.includes(
      "process.env.NEXT_PUBLIC_SITE_URL ?? 'https://" + domain + "'",
    ),
  );
});

test("validation and publication use the custom origin and guard the emitted CNAME", async () => {
  for (const workflow of ["task-validation.yml", "publish-task-images.yml"]) {
    const source = await readFile(
      new URL("../../.github/workflows/" + workflow, import.meta.url),
      "utf8",
    );
    assert.ok(
      source.includes("NEXT_PUBLIC_SITE_URL: https://" + domain),
      workflow,
    );
    assert.ok(
      source.includes('test "$(cat dist/client/CNAME)" = "' + domain + '"'),
      workflow,
    );
  }
});
