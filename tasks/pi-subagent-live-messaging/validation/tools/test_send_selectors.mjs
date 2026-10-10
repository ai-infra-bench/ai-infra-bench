import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

// Run under the frozen Pi environment, whose dependencies include typebox.
// TEAM_EXTENSION_DIRECTORY can point to a solved tree or another control.
const extensionDirectory = process.env.TEAM_EXTENSION_DIRECTORY
  ?? '/workspace/pi/packages/coding-agent/examples/extensions/subagent';
const { default: teamWorker } = await import(pathToFileURL(path.join(extensionDirectory, 'team-worker.ts')).href);
const { createTeam, inbox } = await import(pathToFileURL(path.join(extensionDirectory, 'team.ts')).href);

const cases = [
  ['missing selectors', {message: 'finding'}, null],
  ['empty private selector', {to: '', message: 'finding'}, null],
  ['private selector', {to: 'B', message: 'finding'}, ['B']],
  ['private selector and false broadcast', {to: 'B', broadcast: false, message: 'finding'}, ['B']],
  ['broadcast with omitted to', {broadcast: true, message: 'finding'}, ['B', 'C']],
  ['nonempty to and true broadcast', {to: 'B', broadcast: true, message: 'finding'}, null],
  ['empty to and true broadcast', {to: '', broadcast: true, message: 'finding'}, null],
];
for (const [name, args, expected] of cases) test(name, async () => {
  const oldDirectory = process.env.PI_TEAM_DIRECTORY;
  const oldMember = process.env.PI_TEAM_MEMBER;
  const team = createTeam(['A', 'B', 'C'].map(id => ({id, agent: 'worker'})));
  try {
    let directory;
    for (let i = 0; i < 3; i++) ({directory} = await team.start(i));
    process.env.PI_TEAM_DIRECTORY = directory;
    process.env.PI_TEAM_MEMBER = 'A';
    const tools = new Map();
    teamWorker({on() {}, registerTool(tool) {tools.set(tool.name, tool);}});
    assert.ok(tools.has('team_send'));
    let result, error;
    try { result = await tools.get('team_send').execute('boundary-case', args); }
    catch (caught) { error = caught; }
    const writes = ['A', 'B', 'C'].flatMap(id => fs.readdirSync(inbox(directory, id)).map(file => ({
      recipient: id, envelope: JSON.parse(fs.readFileSync(path.join(inbox(directory, id), file), 'utf8')),
    })));
    if (expected === null) {
      assert.deepEqual(writes, [], `malformed request wrote inbox files: ${JSON.stringify(writes)}`);
      assert.ok(error instanceof Error, `malformed request was not explicitly rejected: ${JSON.stringify(result)}`);
    } else {
      assert.equal(error, undefined);
      assert.deepEqual(result.details, {accepted: expected, failed: []});
      assert.deepEqual(writes.map(write => write.recipient).sort(), expected);
      for (const {envelope} of writes) {
        assert.equal(envelope.text, args.message);
        assert.equal(envelope.from, 'A');
        assert.equal(envelope.sequence, 1);
      }
    }
  } finally {
    team.dispose();
    if (oldDirectory === undefined) delete process.env.PI_TEAM_DIRECTORY;
    else process.env.PI_TEAM_DIRECTORY = oldDirectory;
    if (oldMember === undefined) delete process.env.PI_TEAM_MEMBER;
    else process.env.PI_TEAM_MEMBER = oldMember;
  }
});
