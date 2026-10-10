"""Execute real file/spool worker handlers with substituted SDK event dispatch.

This checks candidate mailbox/acceptance transitions, not real Pi retry scheduling.
Use the full verifier for HTTP/native-provider/SDK and process-lifetime evidence.
"""
import argparse,json,os,re,subprocess,tempfile
from pathlib import Path


def check(source):
    with tempfile.TemporaryDirectory(prefix='messaging-settled-check-') as temporary:
        root=Path(temporary)
        for name in ['team.ts','team-worker.ts']:
            body=(source/name).read_text()
            body=re.sub(r'^import type .*?;\n','',body,flags=re.M)
            if name=='team-worker.ts':
                body=body.replace('import { Type } from "typebox";','type ExtensionAPI = any; type AgentMessage = any; const Type = new Proxy({}, {get:()=>()=>({})}) as any;')
            (root/name).write_text(body)
        (root/'check.mjs').write_text('''import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import install from './team-worker.ts';
import {inbox,saveMembers,readMembers} from './team.ts';
const directory=path.join(import.meta.dirname,'mail');fs.mkdirSync(directory);
for(const id of ['A','B'])fs.mkdirSync(inbox(directory,id));
const reset=()=>saveMembers(directory,[{id:'A',agent:'worker',state:'running'},{id:'B',agent:'worker',state:'running'}]);reset();
process.env.PI_TEAM_DIRECTORY=directory;process.env.PI_TEAM_MEMBER='B';
const handlers=new Map(),tools=new Map(),delivered=[];let deferred;
const pi={on(n,f){handlers.set(n,f)},registerTool(t){tools.set(t.name,t)},sendMessage(m){delivered.push(m);deferred=Promise.resolve().then(async()=>{await handlers.get('turn_end')({message:{role:'assistant',stopReason:'stop'}},{hasPendingMessages:()=>false});await handlers.get('agent_settled')?.();});}};
install(pi);
await handlers.get('turn_end')({message:{role:'assistant',stopReason:'error'}},{hasPendingMessages:()=>false});
assert.equal(readMembers(directory).find(x=>x.id==='B').state,'running','retry error turn closed live acceptance');
assert(handlers.has('agent_settled'),'no settled lifecycle handler');
await handlers.get('agent_settled')();
assert.equal(readMembers(directory).find(x=>x.id==='B').state,'finished');
reset();
const envelope={id:'one',from:'A',text:'finding \\n Unicode 🙂',sequence:1};
// Both archive transports implement their real send path, so no wire is invented.
process.env.PI_TEAM_MEMBER='A';const senderTools=new Map();install({on(){},registerTool(t){senderTools.set(t.name,t)},sendMessage(){}});
const result=await senderTools.get('team_send').execute('send',{to:'B',broadcast:false,message:envelope.text});
assert.deepEqual(JSON.parse(result.content[0].text).accepted,['B'],'to + broadcast:false is legal');
await handlers.get('agent_settled')();await deferred;
assert.equal(delivered.length,1,'settled acceptance must produce one continuation');
assert(delivered[0].content.includes(envelope.text));
assert.equal(readMembers(directory).find(x=>x.id==='B').state,'finished','continuation must settle before finish');
console.log(JSON.stringify({passed:true,checks:6,scope:'real file/spool handlers; substituted SDK dispatch'}));
''')
        env={k:v for k,v in os.environ.items() if k not in ['NODE_OPTIONS','NODE_PATH']}
        return subprocess.run(['node','--experimental-strip-types',str(root/'check.mjs')],env=env,text=True,capture_output=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);args=parser.parse_args()
    run=check(args.source);print(json.dumps({'exit_code':run.returncode,'stdout':run.stdout,'stderr':run.stderr},indent=2));raise SystemExit(run.returncode)
