"""CPU grading shared by live and replay quality evaluations."""
import json
import os
import re
import secrets
import subprocess
from decimal import Decimal

DEFAULT_IMAGE = 'sha256:be1575ed968de893bd54f4c56315ff7c4736ce522c1bca08fd521731aafc0d76'
HARNESS = r'''
import sys,json,resource
resource.setrlimit(resource.RLIMIT_CPU,(4,4))
resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))
data=json.load(sys.stdin)
run=exec;make=compile;dump=json.dumps;write=sys.stdout.write
ns={'__name__':'candidate'}
result={'passed':False,'tests_completed':0,'status':'CODE_RUNTIME_ERROR'}
try:
    run(make(data['code'],'<candidate>','exec',dont_inherit=True,optimize=0),ns)
    for test in data['tests']:
        run(make(test,'<test>','exec',dont_inherit=True,optimize=0),ns)
        result['tests_completed']+=1
    result.update(passed=True,status='PASS')
except AssertionError:
    result['status']='WRONG_RESULT'
except SyntaxError:
    result['status']='CODE_SYNTAX_ERROR'
except BaseException as error:
    result['exception']=type(error).__name__
write('\nTASK_RESULT '+data['nonce']+' '+dump(result)+'\n')
'''


def code_test(code, oracle, image=DEFAULT_IMAGE):
    """Execute only inside an isolated, disposable CPU container."""
    nonce = secrets.token_hex(12)
    name = 'task-quality-' + nonce
    run_id = os.environ.get('TASK_QUALITY_RUN_ID', nonce)
    if not re.fullmatch(r'[0-9a-f]{24,32}', run_id):
        raise ValueError('Invalid quality sandbox ownership ID')
    cmd = [
        'docker', 'run', '--rm', '--pull', 'never', '-i', '--name', name,
        '--label', 'ascend-task.quality.run=' + run_id,
        '--runtime', 'runc', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges', '--user', '65534:65534',
        '--pids-limit', '32', '--memory', '256m', '--cpus', '1',
        '--tmpfs', '/tmp:rw,noexec,nosuid,size=16m', '--entrypoint', 'python',
        image, '-I', '-B', '-c', HARNESS,
    ]
    tests = oracle['test_imports'] + oracle['original_tests'] + oracle['extra_tests']
    data = {'code': code, 'tests': tests, 'nonce': nonce}
    try:
        # Bound output without buffering arbitrary candidate stdout in the controller.
        import tempfile
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            proc = subprocess.run(cmd, input=json.dumps(data).encode(), stdout=stdout,
                                  stderr=stderr, timeout=18)
            stdout.seek(0, 2)
            size = stdout.tell()
            stdout.seek(max(0, size - 65536))
            output = stdout.read().decode('utf-8', errors='replace')
            marker = 'TASK_RESULT ' + nonce + ' '
            lines = [line[len(marker):] for line in output.splitlines() if line.startswith(marker)]
            if proc.returncode == 0 and len(lines) == 1:
                result = json.loads(lines[0])
                if result.get('passed') is True and result.get('tests_completed') != len(tests):
                    return {'passed': False, 'status': 'GRADER_ERROR'}
                return {**result, 'container_exit_code': proc.returncode}
            # Docker invocation failures are infrastructure failures, not wrong code.
            return {'passed': False, 'status': 'GRADER_ERROR' if proc.returncode in (125, 126, 127)
                    else 'CODE_EXECUTION_FAILED', 'container_exit_code': proc.returncode}
    except subprocess.TimeoutExpired:
        return {'passed': False, 'status': 'CODE_TIMEOUT'}
    finally:
        cleanup = subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=10)
        if cleanup.returncode and b'No such container' not in cleanup.stderr:
            raise RuntimeError('Unable to remove owned code sandbox: ' + name)


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
