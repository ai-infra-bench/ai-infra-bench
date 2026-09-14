"""Live models use the frozen Oracle extension; this is not a solver pilot.

Only incident data and report collection are synthetic. All decisions and tool
arguments come from the selected real model. The scenario deliberately asks for
window transitions, so it does not measure autonomous timing policy.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen
import uuid
from metrics import behavior_metrics, completed_tools, phase_completion, infrastructure_metrics, recovery_preconditions

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parents[3]
HERE = None
PHASE_TIMEOUT = 900
MAX_REQUESTS = 60
THINKING = "high"
PI = ROOT/'artifacts/pi-context-hardening-20260914/oracle'
PYTHON = ROOT/'artifacts/cpu-run-20260909/.venv/bin/python'
MODELS = [('gpt-5.6-sol', 0, 20311), ('gpt-6-astra', 1, 20312)]

PROMPT = '''我们在评审三组网关超时配置实验 A、B、C。选择满足 error_rate <= 0.005 且 p95_ms <= 500 的方案；若多个满足，选择 p95 最小者。
请按 A、B、C 顺序调用 inspect_run 读取诊断快照。每份快照只能读取一次，之后原始信息只能从本 session 的历史中找回。
每处理完一组，使用 notes_write 替换当前工作笔记，保留当前目标、各组核心指标、候选判断和可检索的来源线索，然后调用 new_context，再处理下一组。处理完 C 也要切换一次，然后给出简短结论。这是持续进行的同一个目标；切换后请依据笔记继续，不要重新读取过期快照。
为了让工作上下文保持精简，audit_receipt、checksum、boundary_sample_id 是原始审计字段，第一阶段不要把它们复制到任何笔记或最终回答。需要时我们会再从历史中核验。
工作笔记可按需读取和更新。目前只需要完成第一阶段，不要调用 submit_report。'''

FOLLOWUP = '''现在进入同一个调查目标的第二阶段。请使用 history_search 和 history_read 找回推荐方案的原始诊断快照，核验 audit_receipt、checksum 和 boundary_sample_id 的精确值。
这轮允许且要求提交上述审计字段。请调用 submit_report，填写推荐 run、p95、三个原始审计字段、为什么选择它的解释，以及真实检索得到的 window_id/item_id。不要重新调用 inspect_run，也不要猜测字段值。提交后简短结束。'''


SYSTEM = 'You are an investigation agent. Use the available tools and preserve evidence. Follow the user workflow. No shell or filesystem tools are available.'

def flatten_strings(value):
    if isinstance(value,str): return value
    if isinstance(value,list): return '\n'.join(flatten_strings(x) for x in value)
    if isinstance(value,dict): return '\n'.join(flatten_strings(x) for x in value.values())
    return ''

def content_text(value):
    content = value.get('content', [])
    return content if isinstance(content,str) else '\n'.join(x.get('text','') for x in content if x.get('type')=='text')


class Trial:
    def __init__(self, model):
        self.model = model
        self.out = HERE/model
        self.out.mkdir()
        self.phase = 0
        self.events, self.reports, self.errors, self.seen = [], [], [], []
        self.stops = []
        self.lock = threading.Lock()
        self.started = time.time()
        self.data = {}
        for name, rate, p95 in [('A',0.018,780),('B',0.002,410),('C',0.008,260)]:
            self.data[name] = {
                'run_id':name,'requests':100000,'error_rate':rate,'p95_ms':p95,
                'config':{'timeout_ms':{'A':500,'B':900,'C':300}[name], 'retry_limit':{'A':2,'B':1,'C':0}[name]},
                'diagnostic_log':'\n'.join(f'bulk-{name}-{i:04d} worker={i%9} route=/api/query trace={uuid.uuid4().hex} 状态=已采样' for i in range(160)),
                'audit_receipt':'receipt-'+uuid.uuid4().hex,
                'checksum':hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
                'boundary_sample_id':'边界样本-'+uuid.uuid4().hex,
            }
        (self.out/'scenario.json').write_text(json.dumps({'prompt':PROMPT,'followup':FOLLOWUP,'data':self.data},ensure_ascii=False,indent=2))

    def event(self, event):
        with self.lock:
            event = dict(event, sequence=len(self.events), phase=self.phase, time=time.time())
            self.events.append(event)
            with (self.out/'events.jsonl').open('a') as file: file.write(json.dumps(event,ensure_ascii=False)+'\n')
            requests = sum(e['type']=='request' for e in self.events)
            tools = [e.get('toolName') for e in self.events if e['type']=='tool_execution_end']
            (self.out/'status.json').write_text(json.dumps({'model':self.model,'phase':self.phase,'requests':requests,'last_tools':tools[-6:],'efficiency':behavior_metrics(self.events), 'elapsed':round(time.time()-self.started)},ensure_ascii=False))


def handler(trial):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_): pass
        def do_POST(self):
            try:
                data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                code = 200
                if self.path == '/event':
                    trial.event(data)
                    response = 'ok'
                elif self.path == '/run':
                    run = data['run_id']
                    if run in trial.seen:
                        code, response = 409, 'The rolling diagnostic snapshot has expired. Recover the previously returned snapshot from session history.'
                    else:
                        trial.seen.append(run)
                        response = json.dumps(trial.data[run],ensure_ascii=False)
                elif self.path == '/report':
                    trial.reports.append(dict(data, phase=trial.phase))
                    response = json.dumps({'recorded':True})
                else: raise ValueError('Unknown endpoint')
                payload = response.encode()
                self.send_response(code)
                self.send_header('Content-Type','text/plain; charset=utf-8')
                self.send_header('Content-Length',str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as exc:
                trial.errors.append(repr(exc))
                self.send_error(500)
    return Handler


def assess(trial, exits):
    events = trial.events
    tools = completed_tools(events)
    resets = [e for e in tools if e['toolName']=='new_context' and not e['isError']]
    requests = [e for e in events if e['type']=='request']
    checked = []
    for reset in resets:
        following = next((e for e in requests if e['sequence']>reset['sequence']),None)
        before = [e for e in tools if e['sequence']<reset['sequence'] and e['toolName']=='inspect_run' and not e['isError']]
        old = [json.loads(content_text(e['result'])) for e in before]
        payload = flatten_strings(following['payload']) if following else ''
        prior_writes = [e['arguments'].get('text', '') for e in tools
                        if e['toolName'] == 'notes_write' and not e['isError']
                        and following and e['sequence'] < following['sequence']]
        latest_note = prior_writes[-1] if prior_writes else None
        checked.append({'request_exists':bool(following),'latest_note_present':latest_note is not None and latest_note in payload,'goal_present':PROMPT in payload,'system_present':SYSTEM in payload,'old_receipts_absent':all(x['audit_receipt'] not in payload for x in old),
                        # A short log keyword is a valid source clue in notes.
                        # Check full original lines, including random trace IDs.
                        'bulk_logs_absent':all(all(line not in payload for line in x['diagnostic_log'].splitlines()[:3]) for x in old),
                        'input_characters':len(payload)})
    notes_clean = all(not any(trial.data[k][field] in content_text(e['result']) for k in trial.data for field in ['audit_receipt','checksum','boundary_sample_id'])
                      for e in tools if e['toolName'] == 'notes_read' and e['phase'] == 0)
    # Original tool-call arguments are in assistant events; check what the model actually wrote.
    writes = [part.get('arguments',{}).get('text','') for e in events if e['type']=='assistant' and e['phase']==0
              for part in e['message'].get('content',[]) if part.get('type')=='toolCall' and part.get('name')=='notes_write']
    notes_clean = notes_clean and all(not any(row[field] in note for row in trial.data.values() for field in ['audit_receipt','checksum','boundary_sample_id']) for note in writes)
    expected = trial.data['B']
    report = trial.reports[-1] if trial.reports else {}
    report_ok = bool(report) and report.get('phase')==1 and all(report.get(k)==expected[k] for k in ['audit_receipt','checksum','boundary_sample_id','p95_ms']) and report.get('chosen_run')=='B'
    reads = [e for e in tools if e['toolName']=='history_read' and not e['isError'] and e['phase']==1]
    read_data = []
    for e in reads:
        try: read_data.append(json.loads(content_text(e['result'])))
        except ValueError: pass
    call_args = {part['id']:part.get('arguments',{}) for e in events if e['type']=='assistant'
                 for part in e['message'].get('content',[]) if part.get('type')=='toolCall'}
    successful_reads = []
    for e in reads:
        args=call_args.get(e.get('toolCallId'),{})
        try: record=json.loads(content_text(e['result']))
        except ValueError: continue
        successful_reads.append((args,record))
    refs_ok = bool(report.get('history_refs')) and all(
        any(all(ref.get(k)==args.get(k) for k in ['window_id','item_id'])
            and all(expected[field] in record.get('text','') for field in ['audit_receipt','checksum','boundary_sample_id'])
            for args,record in successful_reads) for ref in report.get('history_refs',[]))
    evidence_recovered = all(any(expected[field] in r.get('text','') for r in read_data) for field in ['audit_receipt','checksum','boundary_sample_id'])
    sessions = {e['id'] for e in events if e['type']=='session'}
    request_sessions = {e['session_id'] for e in requests}
    workspace_ok = (trial.out/'workspace/keep.txt').exists() and (trial.out/'workspace/keep.txt').read_text() == 'workspace-survives-'+trial.model
    issues = []
    efficiency = behavior_metrics(events)
    completion = phase_completion(events)
    recovery = recovery_preconditions(events, trial.data)
    if not recovery['phase0_final_answer_clean']: issues.append('Raw audit values copied into the phase-one final answer')
    if not recovery['values_appear_only_after_history_recovery']: issues.append('Audit values reached phase-two model input before recovery from history')
    if not all(p['completed'] for p in completion.values()): issues.append('A phase lacks a normal final assistant reply')
    if [w['run'] for w in efficiency['workflow']] != ['A','B','C'] or not all(w['notes_then_reset'] for w in efficiency['workflow']): issues.append('Required per-snapshot note/reset workflow was not completed')
    if len(exits)!=2 or any(exits): issues.append('Process/model execution did not finish both phases')
    if trial.seen != ['A','B','C']: issues.append('Did not read the three snapshots in order')
    if len(resets)<3: issues.append('Fewer than three requested context transitions')
    if not all(x['request_exists'] and x['old_receipts_absent'] and x['bulk_logs_absent'] and x['latest_note_present'] and x['goal_present'] and x['system_present'] for x in checked): issues.append('Context transition retained old evidence or failed to continue')
    if not notes_clean: issues.append('Raw audit values copied into notes during phase one')
    if not report_ok: issues.append('Final report absent or incorrect')
    if not refs_ok or not evidence_recovered: issues.append('Original audit evidence not recovered through valid history references')
    if len(sessions)!=1 or request_sessions != sessions: issues.append('Session identity changed')
    if not workspace_ok: issues.append('Workspace contents changed')
    result = {'model':trial.model,'status':'passed' if not issues and not trial.errors else 'needs-investigation','issues':issues,'observer_errors':trial.errors,
              'phase_completion':completion,'efficiency':efficiency,'phase_stops':trial.stops,'recovery_preconditions':recovery,
              'process_exits':exits,'model_requests':len(requests),'context_transitions':len(resets),'transition_checks':checked,
              'tool_calls':[e['toolName'] for e in tools], 'tool_errors':[{'name':e['toolName'],'text':content_text(e['result'])[:1000]} for e in tools if e['isError']],
              'notes_exclude_audit_values':notes_clean,'report_correct':report_ok,'history_references_valid':refs_ok,
              'evidence_recovered':evidence_recovered,'session_count':len(sessions),'workspace_preserved':workspace_ok,'report':report,'elapsed_seconds':round(time.time()-trial.started)}
    capture = trial.out/'capture/router_trace.jsonl'
    records = [json.loads(line) for line in capture.read_text().splitlines()] if capture.exists() else []
    log = trial.out/'router-console.log'
    result['infrastructure'] = infrastructure_metrics(records, log.read_text() if log.exists() else '')
    (trial.out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result


def run(config):
    model, key, port = config
    trial = Trial(model)
    capture = trial.out/'capture'
    capture.mkdir()
    (capture/'retry-policy.json').write_text(json.dumps({'max_attempts':5,'base_delay':10,'max_delay':60}))
    command = [str(PYTHON),str(ROOT/'scripts/model_gateway/launch_router.py'),'--env-file','/home/tiger/.env','--key-index',str(key),
               '--model',model,'--host','127.0.0.1','--port',str(port),'--timeout','600','--out',str(capture)]
    router_log = (trial.out/'router-console.log').open('w')
    router = subprocess.Popen(command,stdout=router_log,stderr=subprocess.STDOUT,start_new_session=True)
    server = ThreadingHTTPServer(('127.0.0.1',0),handler(trial))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    exits = []
    try:
        for _ in range(60):
            if router.poll() is not None: raise RuntimeError('Router exited before becoming healthy')
            try:
                with urlopen(f'http://127.0.0.1:{port}/healthz',timeout=1) as r:
                    if r.status==200: break
            except Exception: time.sleep(.5)
        else: raise RuntimeError('Router health timeout')
        for path in ['agent','home','tmp','workspace']: (trial.out/path).mkdir()
        (trial.out/'workspace/keep.txt').write_text('workspace-survives-'+trial.model)
        (trial.out/'agent/settings.json').write_text(json.dumps({'compaction':{'enabled':False},'retry':{'enabled':True,'maxRetries':4,'baseDelayMs':10000,'maxDelayMs':60000}}))
        env = {'PATH':os.environ['PATH'],'HOME':str(trial.out/'home'),'TMPDIR':str(trial.out/'tmp'),'LANG':'C.UTF-8',
               'PI_CODING_AGENT_DIR':str(trial.out/'agent'),'PI_LIVE_OBSERVER':f'http://127.0.0.1:{server.server_port}',
               'PI_LIVE_MODEL':model,'PI_LIVE_GATEWAY':f'http://127.0.0.1:{port}/v1',
               'NODE_OPTIONS':f'--import={PI}/node_modules/tsx/dist/loader.mjs','TSX_TSCONFIG_PATH':str(PI/'tsconfig.json'),
               'PI_NO_LOCAL_LLM':'1','AWS_EC2_METADATA_DISABLED':'true','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'}
        for phase,prompt in enumerate([PROMPT,FOLLOWUP]):
            trial.phase = phase
            cmd = ['node',str(PI/'packages/coding-agent/src/cli.ts'),'--mode','json','-p','--session',str(trial.out/'session.jsonl'),
                   '--model','live-eval/'+model,'--thinking',THINKING,'--tools','new_context,notes_write,notes_read,history_search,history_read,inspect_run,submit_report',
                   '-e',str(SOURCE/'provider.ts'),'-e',str(PI/'packages/coding-agent/examples/extensions/context-management/index.ts'),
                   '--system-prompt',SYSTEM,prompt]
            with (trial.out/f'phase-{phase}.jsonl').open('w') as out, (trial.out/f'phase-{phase}.stderr').open('w') as err:
                proc = subprocess.Popen(cmd,cwd=trial.out/'workspace',env=env,stdout=out,stderr=err,start_new_session=True)
                code, stop = wait_phase(proc, phase, trial)
                if stop: trial.stops.append(stop)
                exits.append(code)
            print(json.dumps({'model':model,'phase':phase,'exit_code':code,'tool_calls':len([e for e in trial.events if e['type']=='tool_execution_end'])}),flush=True)
            # JSON-mode Pi may exit zero with a final model error. Do not
            # start the next phase unless the current model turn finished.
            if code or not phase_completion(trial.events, [phase])[str(phase)]['completed']: break
        result = assess(trial,exits)
    except Exception as exc:
        trial.errors.append(repr(exc))
        result = assess(trial,exits)
    finally:
        server.shutdown();server.server_close()
        if router.poll() is None:
            os.killpg(router.pid,signal.SIGTERM)
            try: router.wait(timeout=10)
            except subprocess.TimeoutExpired: os.killpg(router.pid,signal.SIGKILL);router.wait()
        router_log.close()
    print(json.dumps({'model':model,'status':result['status'],'issues':result['issues'],'errors':result['observer_errors']}),flush=True)
    return result


def wait_phase(proc, phase, trial):
    """Only stop the captured process for this phase; never rediscover it by PID/name."""
    started = time.monotonic()
    while proc.poll() is None:
        with trial.lock:
            count = sum(e['type'] == 'request' and e['phase'] == phase for e in trial.events)
        reason = 'request_budget' if count > MAX_REQUESTS else 'phase_timeout' if time.monotonic() - started > PHASE_TIMEOUT else None
        if reason:
            # The process may have finished between observation and this check.
            # The next phase cannot start until this function returns.
            if proc.poll() is not None: break
            try: os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try: proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL); proc.wait()
            return -1, {'phase': phase, 'reason': reason, 'requests': count}
        time.sleep(.2)
    return proc.returncode, None


def main():
    global HERE, PI, PYTHON, PHASE_TIMEOUT, MAX_REQUESTS, THINKING
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New output directory; existing trials are never overwritten')
    parser.add_argument('--repo', type=Path, default=PI)
    parser.add_argument('--gateway-python', type=Path, default=PYTHON)
    parser.add_argument('--models', nargs='+', choices=['gpt-5.6-sol','gpt-6-astra'], default=['gpt-5.6-sol','gpt-6-astra'])
    parser.add_argument('--thinking', default='high', choices=['low','medium','high'])
    parser.add_argument('--phase-timeout', type=int, default=900)
    parser.add_argument('--max-requests-per-phase', type=int, default=60)
    parser.add_argument('--port-base', type=int, default=20411)
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    if min(args.phase_timeout,args.max_requests_per_phase,args.workers) <= 0: parser.error('Budgets/workers must be positive')
    if len(args.models) != len(set(args.models)): parser.error('Use a fresh output directory for each repetition')
    HERE=args.output.resolve(); HERE.mkdir(parents=True, exist_ok=False)
    PI=args.repo.resolve(); PYTHON=args.gateway_python.absolute()
    PHASE_TIMEOUT=args.phase_timeout; MAX_REQUESTS=args.max_requests_per_phase; THINKING=args.thinking
    models=[(model, 0 if model=='gpt-5.6-sol' else 1, args.port_base+i) for i,model in enumerate(args.models)]
    paths=[SOURCE/'run.py', SOURCE/'provider.ts', SOURCE/'metrics.py', PI/'packages/coding-agent/examples/extensions/context-management/index.ts']
    plan={'type':'real model uses implementation; directed workflow; not solver evaluation', 'models':args.models,
          'reasoning_effort':THINKING, 'trials_per_model':1, 'max_output_tokens':8192,
          'phase_timeout_sec':PHASE_TIMEOUT, 'max_requests_per_phase':MAX_REQUESTS,
          'efficiency_is_diagnostic_only':True, 'no_progress_does_not_trigger_termination':True,
          'input_hashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    (HERE/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool: results=list(pool.map(run,models))
    (HERE/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    return 0 if all(r['status']=='passed' for r in results) else 1


if __name__ == '__main__': raise SystemExit(main())
