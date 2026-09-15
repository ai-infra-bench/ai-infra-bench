#!/usr/bin/env python3
"""One live migration attempt; preserve failures, never silently reroll.
Requires live-proxy.py on a reachable credential-owning machine.
"""
import argparse,json,time,uuid,urllib.request,traceback
from pathlib import Path
from run import Host,check,disk,dump
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('/workspace/deepseek-harness'));p.add_argument('--source-model',default='gpt-6-astra');p.add_argument('--source-api',choices=['openai-completions','openai-responses'],default='openai-completions');p.add_argument('--destination-model',default='gpt-6-astra');p.add_argument('--destination-api',choices=['openai-completions','openai-responses'],default='openai-responses');p.add_argument('--require-reasoning-field',action='store_true');p.add_argument('--chat-reasoning-text',action='store_true');p.add_argument('--proxy',required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
args.out.mkdir(parents=True);world=args.out/'world';world.mkdir();(world/'.dsh').mkdir()
(world/'invoice-a.txt').write_text('Invoice A: 137\n');(world/'invoice-b.txt').write_text('Invoice B: 251\n')
model=args.source_model
def profile(api,path,route_model):
    # Conservative declared fixture capacities, not a claim about the model's true limit.
    config={'apiKeyEnv':'MIGRATION_FIXTURE_KEY','baseURL':args.proxy+path,'api':api,'models':[{'id':route_model,'contextWindow':65536,'maxTokens':16384,'reasoningEfforts':{'high':'high'}}],'reasoning':'high','retryPolicy':{'mode':'normal','maxRetries':0}}
    if api=='openai-completions' and route_model=='ali-deepseek-v4-pro':
        config['compat']={'supportsDeveloperRole':False,'maxTokensField':'max_tokens','supportsStore':False}
    return config
providers={'origin':profile(args.source_api,'/source',model),'destination':{**profile(args.destination_api,'/destination',args.destination_model),'responsesReasoningText':args.destination_api=='openai-responses'}}
if args.chat_reasoning_text:
    check(args.destination_api=='openai-completions','Chat projection requires Chat destination')
    providers['destination']['chatReasoningText']=True
overlay=args.out/'overlay.json';dump(overlay,[{'id':'llm-deepseek','disabled':True},{'id':'session-title-llm','disabled':True},{'id':'agent-instructions','disabled':True},{'id':'agent-default-model','config':{'provider':'origin','model':model}},{'id':'llm-pi-ai','config':{'providers':providers}},{'id':'agent-presets','config':{'default':'minimal','includeUserRoot':False}},{'id':'session-persistence-jsonl','config':{'root':str(world/'.dsh/sessions'),'packChunks':False}}])
host=None;sid='live-'+uuid.uuid4().hex;stage='boot';result={'status':'running','source_model':model,'destination_model':args.destination_model,'source_api':args.source_api,'destination_api':args.destination_api,'effort':'high','source':'https://aidp.bytedance.net/api/modelhub/online/'+('v2/crawl' if args.source_api=='openai-completions' else 'responses'),'destination':'https://aidp.bytedance.net/api/modelhub/online/'+('v2/crawl' if args.destination_api=='openai-completions' else 'responses')}
def wire():
    with urllib.request.urlopen(args.proxy+'/evidence',timeout=10) as r:return json.load(r)
def turn(text):
    start=len(wire())
    host.rpc('session/prompt',{'request':{'sessionId':sid,'requestId':str(uuid.uuid4()),'mode':'queue','content':[{'type':'text','text':text}]}})
    deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        records=wire();dump(args.out/'wire.json',records)
        failures=[r for r in records[start:] if r['status']!=200]
        check(not failures,'live upstream failure: '+json.dumps([{'status':r['status'],'response':r['response']} for r in failures],ensure_ascii=False)[-1500:])
        rows=host.rpc('session/list',{'_request':{}})['items'];row=next(x for x in rows if x['sessionId']==sid)
        if len(records)>start and not row['running']:return records[start:]
        time.sleep(.5)
    raise TimeoutError('live turn did not settle')
try:
    host=Host(args.root,world,'first',overlay,args.out);host.create(sid);stage='source-real-inference'
    source=turn(f'Read {world}/invoice-a.txt and {world}/invoice-b.txt using tools, in separate calls. Keep the amounts for later; do not write a report yet.')
    def observed(value):
        return any(any((x.get('role')=='tool' or x.get('type')=='function_call_output') and value in str(x.get('content',x.get('output'))) for x in r['body'].get('messages',r['body'].get('input',[]))) for r in source)
    check(observed('137'),'model did not obtain real invoice A tool result')
    check(observed('251'),'model did not obtain real invoice B tool result')
    before_count=len(wire());stage='checked-migration';host.select(sid,'destination',args.destination_model);check(len(wire())==before_count,'admission generated')
    host.stop();first_pid=host.pid;host=None;before=disk(world,args.out,'before-restart')
    stage='disk-restart';host=Host(args.root,world,'second',overlay,args.out);check(host.pid!=first_pid,'process reused');host.create(sid)
    stage='destination-real-inference';destination=turn(f'Using the amounts already inspected, write {world}/report.txt containing exactly three lines: A=<amount>, B=<amount>, Total=<sum>. Verify the file with a tool.')
    check((world/'report.txt').read_text().splitlines()==['A=137','B=251','Total=388'],'live model did not produce the correct report')
    first=destination[0]['body'];inputs=first.get('input',first.get('messages',[]))
    check(first['model']==args.destination_model,'destination model not used')
    if args.destination_api=='openai-responses':
        calls=[x for x in inputs if x.get('type')=='function_call']
        outputs=[x for x in inputs if x.get('type')=='function_call_output']
    else:
        calls=[{'call_id':c['id']} for x in inputs for c in x.get('tool_calls',[])]
        outputs=[{'call_id':x['tool_call_id'],'output':x['content']} for x in inputs if x.get('role')=='tool']
    check(bool(calls),'historical tool calls missing')
    check(len({x['call_id'] for x in calls})==len(calls),'historical call ids collided')
    for call in calls:check(any(x['call_id']==call['call_id'] for x in outputs),'historical call/result unpaired')
    check(any('137' in str(x.get('output')) for x in outputs),'historical tool data missing')
    check(any('251' in str(x.get('output')) for x in outputs),'historical invoice B missing')
    check(any((x.get('role')=='tool' or x.get('type')=='function_call_output') and 'Total=388' in str(x.get('content',x.get('output'))) for r in destination[1:] for x in r['body'].get('input',r['body'].get('messages',[]))),'report was not verified through a real tool result')
    check(all(not x.get('encrypted_content') and not x.get('signature') for x in inputs if x.get('type')=='reasoning'),'foreign native reasoning leaked')
    plaintext=[]
    for record in source:
        chat_reasoning=[]
        for line in record['response'].splitlines():
            if not line.startswith('data: {'):continue
            event=json.loads(line[6:])
            if event.get('type')=='response.output_item.done' and event.get('item',{}).get('type')=='reasoning':
                item=event['item'];plaintext.extend(c['text'] for c in item.get('content',[])+item.get('summary',[]) if c.get('text'))
            for choice in event.get('choices',[]):
                text=choice.get('delta',{}).get('reasoning_content')
                if text:chat_reasoning.append(text)
        if chat_reasoning:plaintext.append(''.join(chat_reasoning))
    source_reasoning=bool(plaintext)
    reasoning_texts=[c['text'] for x in inputs if x.get('type')=='reasoning' for c in x.get('content',[])+x.get('summary',[]) if c.get('text')]
    reasoning_texts.extend(x['reasoning_content'] for x in inputs if x.get('reasoning_content'))
    assistant_texts=[x.get('content','') for x in inputs if x.get('role')=='assistant']
    in_reasoning=bool(plaintext) and all(any(text in target for target in reasoning_texts) for text in plaintext)
    in_text=bool(plaintext) and all(any(text in target for target in assistant_texts if isinstance(target,str)) for text in plaintext)
    result.update(source_returned_reasoning=source_reasoning,source_reasoning_chars=sum(map(len,plaintext)),plaintext_in_reasoning_field=in_reasoning,plaintext_in_assistant_text=in_text,responses_reasoning_extension_tested=args.destination_api=='openai-responses')
    host.stop();host=None;after=disk(world,args.out,'after-restart')
    for key,value in before.items():check(after[key]['rows'][:len(value['rows'])]==value['rows'],'persisted history changed')
    stage='reasoning-contract'
    if args.require_reasoning_field:
        check(source_reasoning,'source did not return plaintext reasoning; coverage missing')
        check(in_reasoning,'source reasoning did not reach the destination reasoning field')
        if args.destination_api=='openai-completions' and args.source_api=='openai-completions':
            expected=[]
            for record in source:
                parts=[];calls={}
                for line in record['response'].splitlines():
                    if not line.startswith('data: {'):continue
                    for choice in json.loads(line[6:]).get('choices',[]):
                        delta=choice.get('delta',{})
                        if delta.get('reasoning_content'):parts.append(delta['reasoning_content'])
                        for call in delta.get('tool_calls',[]):
                            entry=calls.setdefault(call['index'],{'name':'','arguments':''})
                            for key in entry:entry[key]+=call.get('function',{}).get(key) or ''
                expected.append({'reasoning':''.join(parts),'calls':[calls[k] for k in sorted(calls)]})
            # Check every request after migration, including destination-native replay.
            for record in destination:
                actual=[x for x in record['body']['messages'] if x.get('role')=='assistant'][:len(expected)]
                check(len(actual)==len(expected),'source assistant records lost')
                for old,new in zip(expected,actual):
                    check((new.get('reasoning_content') or '')==old['reasoning'],'reasoning reordered or moved to another assistant')
                    replay=new.get('tool_calls',[])
                    check(len(replay)==len(old['calls']),'source tool calls lost or duplicated')
                    for old_call,new_call in zip(old['calls'],replay):
                        check(new_call['function']['name']==old_call['name'] and json.loads(new_call['function']['arguments'])==json.loads(old_call['arguments']),'reasoning/tool association changed')
            result['reasoning_association_checked_on_all_destination_requests']=True
    if args.destination_api=='openai-responses':
        check(not plaintext or in_reasoning,'available plaintext reasoning lost')
    result.update(status='passed',source_returned_reasoning=source_reasoning,session_id=sid)
except Exception:result.update(status='failed',stage=stage,error=traceback.format_exc())
finally:
    if host is not None:
        try:host.stop()
        except Exception:result['shutdown_error']=traceback.format_exc()
    dump(args.out/'result.json',result);print(json.dumps(result,ensure_ascii=False),flush=True)
check(result['status']=='passed','live acceptance did not pass')
