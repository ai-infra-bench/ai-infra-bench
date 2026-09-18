import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

// Small source-level contracts for the two reported layout regressions.
// Real wheel handoff and responsive geometry are also checked in the browser.
async function declarations(file, selector) {
  const css = (await readFile(new URL('../app/' + file, import.meta.url), 'utf8'))
    .replace(/\/\*[\s\S]*?\*\//g, '');
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = css.match(new RegExp('(?:^|})\\s*' + escaped + '\\s*\\{([^{}]*)\\}'));
  assert.ok(match, 'Missing rule: ' + selector);
  return Object.fromEntries(match[1].split(';').filter(part => part.trim()).map(part => {
    const colon = part.indexOf(':');
    return [part.slice(0, colon).trim(), part.slice(colon + 1).trim()];
  }));
}

test('Instruction stays centred while Metadata follows the left reading edge', async () => {
  const instruction = await declarations('site-chrome.css', '.markdown-body');
  const metadata = await declarations('site-chrome.css', '.metadata-sheet');
  assert.equal(instruction['margin-inline'], 'auto');
  assert.equal(instruction['max-width'], '850px');
  assert.equal(metadata['margin-inline'], '0');
});

test('Results permits vertical boundary scroll chaining and contains horizontal swipes', async () => {
  const table = await declarations('plot-interactions.css', '.leaderboard-table-wrap');
  const [x, y = x] = table['overscroll-behavior'].split(/\s+/);
  assert.equal(x, 'contain');
  assert.equal(y, 'auto');
  assert.equal(table.overflow, 'auto');
});
