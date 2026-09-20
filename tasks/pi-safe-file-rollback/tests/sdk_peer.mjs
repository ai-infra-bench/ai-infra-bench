// Transport only: all rollback, tools, persistence and model calls run in Pi.
import { createInterface } from 'node:readline';
import { pathToFileURL } from 'node:url';
import { join } from 'node:path';

const send = value => process.stdout.write(`${JSON.stringify(value)}\n`);
const config = JSON.parse(process.env.ROLLBACK_PEER_CONFIG);
let session;
let runtime;
try {
  const sdk = await import(pathToFileURL(join(config.pi, 'packages/coding-agent/dist/index.js')).href);
  const modelRuntime = await sdk.ModelRuntime.create({authPath: join(config.agentDir, 'auth.json'), modelsPath: join(config.agentDir, 'models.json'), allowModelNetwork: false});
  const options = {
    cwd: config.cwd, agentDir: config.agentDir, modelRuntime,
    model: modelRuntime.getModel('rollback-test', 'rollback-model'), thinkingLevel: 'off',
    sessionManager: config.inMemory ? sdk.SessionManager.inMemory(config.cwd) : sdk.SessionManager.open(config.sessionFile, undefined, config.cwd),
    settingsManager: sdk.SettingsManager.inMemory({compaction: {enabled: false},
      retry: {enabled: config.retry === true, maxRetries: 1, baseDelayMs: 1, provider: {maxRetries: 0}},
      defaultTools: ['read','edit','write','bash']}),
  };
  if (config.enable !== undefined) options.safeRollback = config.enable;
  // Runtime owns session replacement in the pinned SDK. Keep the task's public
  // createAgentSession option as the entrypoint for enabling rollback.
  const factory = async ({cwd, agentDir, sessionManager, sessionStartEvent}) => {
    const services = await sdk.createAgentSessionServices({cwd, agentDir, modelRuntime,
      settingsManager: options.settingsManager});
    const created = await sdk.createAgentSession({...options, cwd, agentDir, sessionManager,
      sessionStartEvent, resourceLoader: services.resourceLoader});
    return {...created, services, diagnostics: services.diagnostics};
  };
  runtime = await sdk.createAgentSessionRuntime(factory, {
    cwd: config.cwd, agentDir: config.agentDir, sessionManager: options.sessionManager,
  });
  if (typeof runtime.fork !== 'function') throw new Error('Public runtime fork API is unavailable');
  session = runtime.session;
  session.subscribe(event => send({kind:'event', event}));
  send({kind:'ready', sessionId:session.sessionId, sessionFile:session.sessionFile,
    capabilities:Object.fromEntries(['listCheckpoints','getRollbackState','rollbackCheckpoint'].map(name => [name,typeof session[name] === 'function']))});
} catch (error) {
  send({kind:'setup_error', error:String(error?.stack ?? error)});
  process.exit(0);
}

const lines = createInterface({input:process.stdin});
lines.on('line', line => {
  let command;
  try { command = JSON.parse(line); } catch { return; }
  void (async () => {
    let data;
    switch (command.op) {
      case 'list': data = await session.listCheckpoints(); break;
      case 'state': data = await session.getRollbackState(); break;
      case 'rollback': data = await session.rollbackCheckpoint(command.checkpointId); break;
      case 'prompt': data = await session.prompt(command.text, command.options); break;
      case 'bash': data = await session.executeBash(command.command); break;
      case 'abort': data = await session.abort(); break;
      case 'steer': data = await session.steer(command.text); break;
      case 'follow_up': data = await session.followUp(command.text); break;
      case 'navigate': data = await session.navigateTree(command.entryId, {summarize:false}); break;
      case 'fork':
        try {
          data = await runtime.fork(command.entryId, command.options);
        } finally {
          // Observe the actual runtime even if replacement partially succeeded.
          if (session !== runtime.session) {
            session = runtime.session;
            session.subscribe(event => send({kind:'event', event}));
          }
        }
        break;
      case 'compact': data = await session.compact(); break;
      case 'inspect': data = {messages:session.messages, entries:session.sessionManager.getEntries(), leafId:session.sessionManager.getLeafId(), sessionId:session.sessionId, isIdle:session.isIdle}; break;
      case 'close':
        session.dispose(); send({kind:'reply',id:command.id,ok:true}); process.exit(0); break;
      default: throw new Error(`Unknown peer operation: ${command.op}`);
    }
    send({kind:'reply',id:command.id,ok:true,data:data ?? null});
  })().catch(error => send({kind:'reply',id:command.id,ok:false,error:String(error?.stack ?? error)}));
});
