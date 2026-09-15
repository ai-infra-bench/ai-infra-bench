#!/usr/bin/env python3
"""Actual CLI + Remote + disk recovery acceptance; parent owns all assertions.

No model forward computation in deterministic mode. A strict HTTP provider
checks requests BEFORE producing SSE; every DSH component and tool is real.
Run with a built, complete candidate checkout, never against patched helpers.
"""
import argparse, sys, ctypes, hashlib, http.client, http.server, json, os, re, signal
import subprocess, tempfile, threading, time, traceback, uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIBC = ctypes.CDLL(None, use_errno=True)

def candidate_identity():
    if LIBC.prctl(38, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'PR_SET_NO_NEW_PRIVS failed')
    os.setgroups([])
    os.setgid(65534)
    os.setuid(65534)

def own_world(world):
    for base, dirs, files in os.walk(world, followlinks=False):
        os.chown(base,65534,65534)
        for name in files:
            path=Path(base)/name
            if not path.is_symlink():os.chown(path,65534,65534)

def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def check(condition, message):
    if not condition:
        raise AssertionError(message)

def completion(text='', calls=(), reasoning=None):
    deltas = [{'role':'assistant','content':''}]
    if reasoning: deltas.append({'reasoning_content':reasoning})
    if text: deltas.append({'content':text})
    if calls:
        deltas.append({'tool_calls':[{'index':i,'id':cid,'type':'function','function':{'name':'bash','arguments':json.dumps({'command':cmd})}} for i,(cid,cmd) in enumerate(calls)]})
    return [{'choices':[{'index':0,'delta':d,'finish_reason':None}]} for d in deltas] + [{'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls' if calls else 'stop'}],'usage':{'prompt_tokens':11,'completion_tokens':7}}, '[DONE]']

def responses(text=None, command=None):
    items = ([{'type':'function_call','id':'fc_native_report','call_id':'call_report','name':'bash','arguments':json.dumps({'command':command}),'status':'completed'}] if command else [{'type':'message','id':'msg_native_report','role':'assistant','status':'completed','content':[{'type':'output_text','text':text,'annotations':[]}]}])
    response = {'id':'resp_native_destination','model':'next-model','status':'completed','output':items,'usage':{'input_tokens':13,'output_tokens':9,'total_tokens':22}}
    return [{'type':'response.created','response':dict(response,status='in_progress',output=[])}] + [event for i,item in enumerate(items) for event in [{'type':'response.output_item.added','output_index':i,'item':item},{'type':'response.output_item.done','output_index':i,'item':item}]] + [{'type':'response.completed','response':response}]

class Provider:
    def __init__(self, evidence):
        self.requests, self.errors, self.expected = [], [], []
        self.evidence = evidence
        owner = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.requests.append({'path':self.path,'body':body})
                dump(evidence/'requests.json',owner.requests)
                try:
                    check(bool(owner.expected), 'unexpected generation: ' + self.path)
                    validate, events = owner.expected.pop(0)
                    validate(self.path, body)
                    if callable(events): events = events(body)
                    self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.end_headers()
                    for event in events:
                        self.wfile.write(('data: ' + (event if isinstance(event,str) else json.dumps(event)) + '\n\n').encode())
                    self.wfile.flush()
                except Exception as exc:
                    owner.errors.append(str(exc)); dump(evidence/'provider-errors.json',owner.errors)
                    self.send_response(422); self.end_headers(); self.wfile.write(str(exc).encode())
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)
    def add(self, validate, events): self.expected.append((validate,events))
    def close(self): self.server.shutdown();self.server.server_close();self.thread.join()

def route(model, cap=None, api=None):
    def validate(path, body):
        check(body['model']==model, f'wrong destination: {body.get("model")} != {model}')
        expected_path = '/chat/completions' if model=='old-model' or api=='openai-completions' else '/responses'
        check(path==expected_path, f'wrong protocol: {path}')
        if cap is not None:
            actual=body.get('max_output_tokens',body.get('max_completion_tokens',body.get('max_tokens')))
            check(actual==cap, f'caller/default allowance lost: expected {cap}, got {actual}')
    return validate

class Host:
    def __init__(self, root, world, phase, overlay, evidence):
        self.evidence=evidence;self.phase=phase;self.rpc_records=[]
        env={k:v for k,v in os.environ.items() if not re.search(r'KEY|SECRET|TOKEN|PASSWORD',k,re.I)}
        env.update(DSH_HOME=str(world/'.dsh'),DSH_AGENTS_HOME=str(world/'.agents'),DSH_TELEMETRY_DISABLED='1',DSH_PERMISSION_MODE='danger-full-access',NODE_NO_WARNINGS='1',SSH_CONNECTION='',SSH_TTY='',MIGRATION_FIXTURE_KEY='local-only',TSX_TSCONFIG_PATH=str(root/'tsconfig.json'))
        self.log=evidence/(phase+'-host.log'); self.log_handle=self.log.open('w')
        self.argv=['node','--import',str(root/'node_modules/tsx/dist/loader.mjs'),str(root/'apps/cli/src/bin.ts'),'web','--patch',str(overlay),'--no-open','--port','0']
        self.child=subprocess.Popen(self.argv,cwd=world,env=env,stdout=self.log_handle,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=candidate_identity)
        self.pid=self.child.pid;self.stopped=False
        dump(evidence/(phase+'-launch.json'),{'pid':self.pid,'uid':65534,'argv':self.argv,'cwd':str(world),'home':env['DSH_HOME']})
        try:
            deadline=time.monotonic()+90
            while time.monotonic()<deadline:
                text=self.log.read_text()
                match=re.search(r'dsh web: (http://[^\s]+)',text)
                if match: break
                check(self.child.poll() is None, 'host failed before readiness: '+text[-6000:])
                time.sleep(.1)
            else: raise TimeoutError('host readiness: '+text[-6000:])
            from urllib.parse import urlsplit
            u=urlsplit(match[1]);self.port=u.port
            c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=30)
            c.request('GET',u.path+'?'+u.query);r=c.getresponse();r.read()
            check(r.status==303,'token exchange failed')
            self.cookie=r.getheader('Set-Cookie').split(';',1)[0];c.close()
        except BaseException:
            self.stop();raise
    def rpc(self, method, args=None, allow_error=False):
        c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=45)
        body={'type':'client-request','rpcId':str(uuid.uuid4()),'method':method,'payload':{'args':args or {}}}
        c.request('POST','/api/'+method,json.dumps(body),{'Content-Type':'application/json','Cookie':self.cookie})
        r=c.getresponse();data=r.read().decode();c.close()
        check(r.status==200, f'HTTP {r.status}: {data}')
        result=json.loads(data)['result']
        self.rpc_records.append({'method':method,'args':args,'result':result});dump(self.evidence/(self.phase+'-rpc.json'),self.rpc_records)
        if allow_error:return result
        check(result.get('ok'),f'{method}: {result}')
        return result.get('value')
    def create(self,sid):return self.rpc('session/create',{'request':{'sessionId':sid,'agentPreset':'minimal'}})
    def select(self,sid,provider,model,checked=True,allow_error=False):
        req={'sessionId':sid,'provider':provider,'model':model}
        if checked:req['migration']='checked'
        return self.rpc('session/selectModel',{'request':req},allow_error)
    def turn(self,sid,text,provider):
        start=len(provider.requests)
        self.rpc('session/prompt',{'request':{'sessionId':sid,'requestId':str(uuid.uuid4()),'mode':'queue','content':[{'type':'text','text':text}]}})
        deadline=time.monotonic()+50
        while time.monotonic()<deadline:
            check(not provider.errors, '\n'.join(provider.errors))
            rows=self.rpc('session/list',{'_request':{}})['items']
            row=next((x for x in rows if x['sessionId']==sid),None)
            if row and not row['running'] and len(provider.requests)>start and not provider.expected:return
            check(self.child.poll() is None,'host exited during turn')
            time.sleep(.15)
        raise TimeoutError(f'turn incomplete: expected {len(provider.expected)} further requests; last row {row}')
    def stop(self):
        if self.stopped:return
        self.stopped=True;forced=False
        if self.child.poll() is None:
            self.child.send_signal(signal.SIGTERM)
            try:self.child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                forced=True;os.killpg(self.pid,signal.SIGKILL);self.child.wait(timeout=5)
        self.log_handle.close()
        # Persist diagnostic logs without the browser bearer token.
        self.log.write_text(re.sub(r'([?&]token=)[^\s)]+',r'\1<redacted>',self.log.read_text()))
        dump(self.evidence/(self.phase+'-exit.json'),{'pid':self.pid,'exit_code':self.child.returncode,'forced':forced})
        check(not forced,'host required SIGKILL; orderly persistence not proved')
        check(self.child.returncode in (0,-signal.SIGTERM),f'host shutdown exit {self.child.returncode}')
        try:os.kill(self.pid,0)
        except ProcessLookupError:pass
        else:raise AssertionError('first host still exists')


def disk(world,evidence,label):
    result={}
    for file in (world/'.dsh/sessions').rglob('*.jsonl.zstd'):
        decoded=subprocess.check_output([sys.executable,'-I',str(HERE/'decode-zstd.py'),str(file)],text=True)
        rows=[json.loads(line) for line in decoded.splitlines() if line.strip()]
        result[str(file.relative_to(world))]={'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'rows':rows}
    check(result,'no real persistence files')
    check(any(row.get('type')=='assistant/message' for value in result.values() for row in value['rows']), 'disk observer did not read real assistant events')
    dump(evidence/(label+'-disk.json'),result)
    return result


def profiles(url,optin,chat=False,same_provider=False):
    def profile(api,model,cap,window=65536):
        return {'apiKeyEnv':'MIGRATION_FIXTURE_KEY','baseURL':url,'api':api,'models':[{'id':model,'contextWindow':window,'maxTokens':cap}], 'retryPolicy':{'mode':'normal','maxRetries':0}}
    p={'origin':profile('openai-completions','old-model',512),'destination':profile('openai-responses','next-model',256),'third':profile('openai-responses','third-model',384),'tiny':profile('openai-responses','tiny-model',256,1)}
    if optin:
        p['destination']['responsesReasoningText']=True
        p['third']['responsesReasoningText']=True
    if chat:
        p['destination']=profile('openai-completions','next-model',256)
        p['destination']['chatReasoningText']=True
        if same_provider:
            p['origin']['chatReasoningText']=True
            p['origin']['models'].append({'id':'next-model','contextWindow':65536,'maxTokens':256})
    return p


def run_case(root,out,case):
    evidence=out/case;evidence.mkdir(parents=True)
    world=Path(tempfile.mkdtemp(prefix='dsh-process-'));(world/'.dsh').mkdir()
    (world/'invoice-a.txt').write_text('137\n');(world/'invoice-b.txt').write_text('251\n')
    provider=Provider(evidence);host=None
    baseline=case=='baseline';chat=case.startswith('chat-');same_provider=case.endswith('model')
    caller=case in ('main','empty-same','empty-third') or chat
    sid='migration-'+case
    patches=[{'id':'llm-deepseek','disabled':True},{'id':'session-title-llm','disabled':True},{'id':'agent-instructions','disabled':True},{'id':'agent-default-model','config':{'provider':'origin','model':'old-model'}},{'id':'llm-pi-ai','config':{'providers':profiles(provider.url,not baseline,chat,same_provider)}},{'id':'agent-presets','config':{'default':'minimal','includeUserRoot':False}},{'id':'session-persistence-jsonl','config':{'root':str(world/'.dsh/sessions'),'packChunks':False}}]
    overlay=world/'second-overlay.json';dump(overlay,patches)
    first_overlay=world/'first-overlay.json'
    first=patches.copy()
    if caller:first=first+[{'insert':[{'id':'caller-input','name':str(HERE/'create-caller.mjs'),'config':{'sessionId':sid,'maxTokens':73,'readyFile':str(world/'caller-ready.json')}}]}]
    dump(first_overlay,first)
    own_world(world)
    try:
        host=Host(root,world,'first',first_overlay,evidence)
        if caller:
            deadline=time.monotonic()+20
            while not (world/'caller-ready.json').exists() and time.monotonic()<deadline:time.sleep(.1)
            check((world/'caller-ready.json').exists(),'caller factory not ready: '+host.log.read_text()[-5000:])
        host.create(sid)
        host.create('sibling')
        provider.add(route('old-model'),completion('sibling initialized'))
        host.turn('sibling','Remember this independent session.',provider)
        before_catalog=host.rpc('session/modelCatalog')
        settings_path=world/'.dsh/settings.yaml'
        before_settings=settings_path.read_bytes() if settings_path.exists() else None
        if baseline:
            provider.add(route('old-model'),completion('before-restart'))
            host.turn(sid,'Remember reference A173.',provider)
        elif case in ('main','reject') or chat:
            def validate_tools(path,body):
                route('old-model',73 if caller else None)(path,body)
                names=[t['function']['name'] for t in body['tools']]
                check('bash' in names,'real bash tool missing')
            provider.add(validate_tools,completion(calls=[('call.alpha','cat invoice-a.txt'),('call/alpha','cat invoice-b.txt')],reasoning='Keep invoice A and invoice B distinct.'))
            def validate_results(path,body):
                route('old-model')(path,body)
                results=[x for x in body['messages'] if x.get('role')=='tool']
                check(len(results)==2,'source tools not both executed')
                for cid,value in [('call.alpha','137'),('call/alpha','251')]:
                    check(any(x['tool_call_id']==cid and value in str(x['content']) for x in results),f'source result lost: {cid}')
            provider.add(validate_results,completion('' if case.startswith('chat-empty-') else 'Invoices inspected.',reasoning='Both values have been verified.' if chat else None))
            host.turn(sid,'Read invoice-a.txt and invoice-b.txt separately. Keep their amounts for a later report.',provider)
        count=len(provider.requests)
        if not baseline:
            if case=='reject':
                result=host.select(sid,'tiny','tiny-model',allow_error=True)
                check(not result.get('ok'),'insufficient capacity migration accepted')
            else:host.select(sid,'origin' if same_provider else 'destination','next-model')
            check(len(provider.requests)==count,'checked admission generated')
        host.stop();first_pid=host.pid;host=None
        prior=disk(world,evidence,'before-restart')
        if chat:
            source_messages=[row['data']['message'] for value in prior.values() for row in value['rows'] if row.get('type')=='assistant/message']
            check(any(any(block.get('type')=='reasoning' and block.get('text')=='Both values have been verified.' for block in message['content']) for message in source_messages), 'source reasoning was not persisted')
        host=Host(root,world,'second',overlay,evidence)
        check(host.pid!=first_pid,'host process reused')
        host.create(sid) # public cold adoption; no seed or maxTokens
        if case.startswith('empty-'):
            third=case=='empty-third';host.select(sid,'third' if third else 'destination','third-model' if third else 'next-model')
            provider.add(route('third-model' if third else 'next-model',73),responses(text='empty continuation'))
            host.turn(sid,'Reply ready.',provider)
        elif chat:
            def validate_chat(path,body):
                route('next-model',73,'openai-completions')(path,body)
                messages=body['messages'];assistants=[x for x in messages if x.get('role')=='assistant']
                check(len(assistants)>=2,'assistant history missing')
                check(assistants[0].get('reasoning_content')=='Keep invoice A and invoice B distinct.','source tool reasoning lost or moved')
                check(assistants[1].get('reasoning_content')=='Both values have been verified.','source reasoning without tool calls lost or moved')
                if case.startswith('chat-empty-'):
                    check(assistants[1].get('content') in (None,''), 'reasoning-only replay fabricated visible text')
                calls=assistants[0].get('tool_calls',[])
                check(len(calls)==2 and len({x['id'] for x in calls})==2,'foreign Chat call IDs collided')
                results=[x for x in messages if x.get('role')=='tool']
                for call in calls:
                    command=json.loads(call['function']['arguments'])['command']
                    val='137' if 'invoice-a.txt' in command else '251'
                    check(any(x['tool_call_id']==call['id'] and val in str(x['content']) for x in results),'Chat tool result pairing lost')
            provider.add(validate_chat,completion('Writing report.',calls=[('call_report',"printf 'A=137\\nB=251\\nTotal=388\\n' > report.txt; cat report.txt")],reasoning='Sum the two observed amounts.'))
            def validate_chat_native(path,body):
                validate_chat(path,body)
                messages=body['messages']
                native=[x for x in messages if x.get('role')=='assistant' and any(c['id']=='call_report' for c in x.get('tool_calls',[]))]
                check(len(native)==1 and native[0].get('reasoning_content')=='Sum the two observed amounts.','native Chat replay lost')
                check(any(x.get('role')=='tool' and x.get('tool_call_id')=='call_report' and 'Total=388' in str(x.get('content')) for x in messages),'real Chat report tool did not run')
            provider.add(validate_chat_native,completion('Report written.'))
            host.turn(sid,'Use the saved invoice amounts to write and verify the report.',provider)
            check((world/'report.txt').read_text().splitlines()==['A=137','B=251','Total=388'],'actual Chat tool artifact incorrect')
        elif case=='main':
            def validate_migrated(path,body):
                route('next-model',73)(path,body)
                inputs=body['input'];calls=[x for x in inputs if x.get('type')=='function_call'];results=[x for x in inputs if x.get('type')=='function_call_output']
                check(len(calls)==2 and len({x['call_id'] for x in calls})==2,'foreign call IDs collided')
                for call in calls:
                    val='137' if 'invoice-a.txt' in call['arguments'] else '251'
                    check(any(x['call_id']==call['call_id'] and val in str(x['output']) for x in results),'historical tool result pairing lost')
                reasons=[(i,x) for i,x in enumerate(inputs) if x.get('type')=='reasoning']
                check(any('Keep invoice A and invoice B distinct.' in json.dumps(x) and i<next(j for j,x in enumerate(inputs) if x.get('type')=='function_call') for i,x in reasons),'plaintext reasoning missing/out of order')
                check(all('encrypted_content' not in x and 'signature' not in x for _,x in reasons),'foreign opaque reasoning metadata replayed')
            provider.add(validate_migrated,responses(command="printf 'A=137\\nB=251\\nTotal=388\\n' > report.txt; cat report.txt"))
            def validate_native(path,body):
                route('next-model',73)(path,body)
                calls=[x for x in body['input'] if x.get('type')=='function_call' and x.get('call_id')=='call_report']
                check(len(calls)==1 and calls[0].get('id')=='fc_native_report','destination native replay lost')
                check(any(x.get('type')=='function_call_output' and x.get('call_id')=='call_report' and 'Total=388' in str(x.get('output')) for x in body['input']),'new tool execution not observed')
            provider.add(validate_native,responses(text='Report written.'))
            host.turn(sid,'Use the amounts already inspected to write report.txt with A, B and Total, then verify it.',provider)
            check((world/'report.txt').read_text()=='A=137\nB=251\nTotal=388\n','actual tool artifact incorrect')
        elif case=='defaults':
            provider.add(route('next-model',256),responses(text='destination default'))
            host.turn(sid,'Reply ready.',provider)
            count=len(provider.requests);host.select(sid,'third','third-model');check(len(provider.requests)==count,'reselection generated')
            provider.add(route('third-model',384),responses(text='third default'))
            host.turn(sid,'Reply ready again.',provider)
        else:
            def retained(path,body):
                route('old-model')(path,body)
                check(('A173' if baseline else '137') in json.dumps(body),'disk history not restored')
            provider.add(retained,completion('continuation on original route'))
            host.turn(sid,'Continue from the saved work.',provider)
        provider.add(route('old-model'),completion('sibling still on original route'))
        host.turn('sibling','Reply ready.',provider)
        after_catalog=host.rpc('session/modelCatalog')
        check(before_catalog==after_catalog,'deployment model defaults/catalog changed')
        check((settings_path.read_bytes() if settings_path.exists() else None)==before_settings,'deployment settings file changed')
        host.stop();host=None
        after=disk(world,evidence,'after-restart')
        for key,value in prior.items():
            check(key in after,'persisted identity/path changed')
            check(after[key]['rows'][:len(value['rows'])]==value['rows'],'durable history prefix mutated')
        check(not provider.errors and not provider.expected,'provider script incomplete')
        return {'case':case,'status':'passed','requests':len(provider.requests),'persistence_files':len(after)}
    finally:
        if host is not None:host.stop()
        provider.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path('/workspace/deepseek-harness'));parser.add_argument('--out',type=Path,required=True);parser.add_argument('--cases',default='main,chat-provider,chat-model,empty-same,empty-third,reject,defaults');args=parser.parse_args()
    check(os.getuid()==0,'the independent verifier parent must run as root')
    args.out.mkdir(parents=True,exist_ok=True)
    inputs={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in HERE.iterdir() if f.is_file()}
    dump(args.out/'inputs.json',{'files':inputs,'root':str(args.root),'parent_uid':os.getuid(),'candidate_uid':65534})
    results=[]
    for case in args.cases.split(','):
        try:result=run_case(args.root,args.out,case)
        except Exception:result={'case':case,'status':'failed','error':traceback.format_exc()}
        results.append(result);dump(args.out/'results.json',results);print(json.dumps(result),flush=True)
    check(all(r['status']=='passed' for r in results),'process acceptance failed; see results.json')

if __name__=='__main__':main()
