"""CPU grading shared by live and replay quality evaluations."""
import json
import os
import re
import secrets
import subprocess
from decimal import Decimal

DEFAULT_IMAGE = 'sha256:be1575ed968de893bd54f4c56315ff7c4736ce522c1bca08fd521731aafc0d76'
# Assertions and expected answers remain in this trusted process. The disposable
# container runs candidate code and exchanges only plain function inputs/outputs.
from pathlib import Path
import select
import time
import code_protocol
from code_worker import WORKER


def code_test(code, oracle, image=DEFAULT_IMAGE):
    name = 'task-quality-' + secrets.token_hex(12)
    cmd = ['docker','run','--rm','--pull','never','-i','--name',name,
           '--label','ascend-task.quality.run='+name,'--runtime','runc','--network','none',
           '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
           '--user','65534:65534','--pids-limit','32','--memory','256m','--cpus','1',
           '--tmpfs','/tmp:rw,noexec,nosuid,size=16m','--entrypoint','python',image,
           '-I','-u','-B','-c',Path(code_protocol.__file__).read_text()+'\n'+WORKER]
    process = None
    completed = 0
    buffer = b''
    consumed = 0
    deadline = time.monotonic() + 18
    try:
        process = subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        os.set_blocking(process.stdout.fileno(),False)
        os.set_blocking(process.stdin.fileno(),False)

        def exchange(payload, expected_status):
            nonlocal buffer,consumed
            request_id=secrets.token_hex(12)
            message=json.dumps({**payload,'id':request_id},allow_nan=False).encode()+b'\n'
            if len(message)>1048576:raise ValueError('Oversized request')
            pending=memoryview(message)
            while pending:
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError('Candidate input deadline exceeded')
                _,ready,_=select.select([],[process.stdin],[],remaining)
                if not ready:raise TimeoutError('Candidate input deadline exceeded')
                try:pending=pending[os.write(process.stdin.fileno(),pending):]
                except BlockingIOError:continue
            while True:
                while b'\n' in buffer:
                    line,buffer=buffer.split(b'\n',1)
                    try:reply=json.loads(line)
                    except (ValueError,UnicodeError):continue
                    if not isinstance(reply,dict) or reply.get('id')!=request_id:continue
                    if reply.get('status')!=expected_status:raise RuntimeError('Candidate execution failed')
                    return reply
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError('Candidate time budget exceeded')
                ready,_,_=select.select([process.stdout],[],[],remaining)
                if not ready:raise TimeoutError('Candidate time budget exceeded')
                chunk=os.read(process.stdout.fileno(),65536)
                if not chunk:raise RuntimeError('Candidate exited before completing calls')
                consumed+=len(chunk)
                if consumed>1048576:raise ValueError('Candidate output limit exceeded')
                buffer+=chunk

        exchange({'code':code,'entrypoint':oracle['entrypoint']},'READY')

        def candidate(*args,**kwargs):
            reply=exchange({'args':code_protocol.encode(args),'kwargs':code_protocol.encode(kwargs)},'RESULT')
            value=code_protocol.decode(reply['value'])
            code_protocol.restore_mutation(args,code_protocol.decode(reply['args']))
            updated=code_protocol.decode(reply['kwargs'])
            for key,original in kwargs.items():code_protocol.restore_mutation(original,updated[key])
            return value

        # These statements originate only from frozen, reviewed verifier assets.
        # Candidate text is never compiled or executed in the trusted process.
        namespace={'__name__':'trusted_tests',oracle['entrypoint']:candidate}
        for test in oracle['test_imports']+oracle['original_tests']+oracle['extra_tests']:
            exec(compile(test,'<trusted-test>','exec',dont_inherit=True,optimize=0),namespace)
            completed+=1
        return {'passed':True,'status':'PASS','tests_completed':completed}
    except AssertionError:
        return {'passed':False,'status':'WRONG_RESULT','tests_completed':completed}
    except TimeoutError:
        return {'passed':False,'status':'CODE_TIMEOUT','tests_completed':completed}
    except Exception as error:
        infrastructure = process is None or process.poll() in (125,126,127)
        return {'passed':False,'status':'GRADER_ERROR' if infrastructure else 'CODE_RUNTIME_ERROR',
                'tests_completed':completed,'error_type':type(error).__name__}
    finally:
        removed = False
        for attempt in range(3):
            cleanup=subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=10)
            if cleanup.returncode == 0 or b'no such container' in cleanup.stderr.lower():
                removed = True;break
            # Docker --rm may already be asynchronously removing an exited worker.
            probe=subprocess.run(['docker','inspect',name],capture_output=True,timeout=10)
            if probe.returncode and (b'no such object' in probe.stderr.lower() or b'no such container' in probe.stderr.lower()):
                removed = True;break
            time.sleep(0.1)
        if process is not None:
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            process.stdin.close();process.stdout.close()
        if not removed:raise RuntimeError('Unable to remove owned code sandbox: '+name)


def evaluate(case, oracle, row, evaluation_lib, image=DEFAULT_IMAGE):
    if row.get('request_status') != 'SUCCEEDED':
        return {'passed': False, 'status': 'REQUEST_ERROR'}
    reason = row.get('metadata', {}).get('finish_reason', {})
    reason = reason.get('type') if isinstance(reason, dict) else reason
    if reason == 'length':
        return {'passed': False, 'status': 'TRUNCATED'}
    if reason != 'stop' or not isinstance(row.get('output'), str):
        return {'passed': False, 'status': 'RESPONSE_ERROR'}
    tokens = row.get('metadata', {}).get('completion_tokens')
    if type(tokens) is not int or tokens <= 0:
        return {'passed': False, 'status': 'RESPONSE_ERROR'}
    if tokens > case['max_new_tokens']:
        return {'passed': False, 'status': 'OUTPUT_BUDGET_EXCEEDED'}
    text = row['output']
    if case['category'] == 'code':
        blocks = re.findall(r'```(?:python|py)\s*\n(.*?)```', text, re.S | re.I)
        return code_test(blocks[-1].strip() if blocks else text.strip(), oracle, image)
    if case['category'] == 'math':
        lines = re.findall(r'(?im)^\s*FINAL_ANSWER:\s*(.*?)\s*$', text)
        if not lines:
            return {'passed': False, 'status': 'FORMAT_ERROR'}
        number = lines[-1].replace(',', '').strip()
        if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)', number):
            return {'passed': False, 'status': 'FORMAT_ERROR', 'answer': number}
        ok = Decimal(number) == Decimal(str(oracle['expected']).replace(',', ''))
        return {'passed': ok, 'status': 'PASS' if ok else 'WRONG_RESULT', 'answer': number}
    inp = evaluation_lib.InputExample(**oracle['input_example'])
    result = evaluation_lib.test_instruction_following_strict(inp, {inp.prompt: text})
    return {'passed': result.follow_all_instructions,
            'status': 'PASS' if result.follow_all_instructions else 'INSTRUCTION_FAILURE',
            'constraint_ids': oracle['input_example']['instruction_id_list'],
            'constraint_results': result.follow_instruction_list}
