#!/usr/bin/env python3
"""Live Chat protocol experiment, independent of the DSH implementation.

Two fresh Python processes use real model inference and file tools. The target
receives the exact persisted source messages, including reasoning_content.
This establishes an endpoint contract, not a passing DSH implementation.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid

URL = 'https://aidp.bytedance.net/api/modelhub/online/v2/crawl'
MODELS = ['ali-deepseek-v4-pro', 'Minimax-M3']


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def function(name, description, properties):
    return {'type': 'function', 'function': {
        'name': name, 'description': description, 'parameters': {
            'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False,
        },
    }}


TOOLS = [
    function('read_invoice', 'Read one invoice from the actual workspace file.',
             {'invoice': {'type': 'string', 'enum': ['A', 'B']}}),
    function('write_report', 'Write the exact supplied text to report.txt.',
             {'content': {'type': 'string'}}),
    function('read_report', 'Read report.txt from the actual workspace.', {}),
]


def worker(args):
    from dotenv import dotenv_values
    keys = ast.literal_eval(dotenv_values(args.env_file)['GPT56_EXPERIMENT_API_KEYS'])
    secret = keys[args.key_index]
    source = args.phase == 'source'
    model = args.source_model if source else args.destination_model
    world = args.out / 'world'
    transcript = args.out / 'source-transcript.json'
    tool_records, wire = [], []
    messages = ([
        {'role': 'system', 'content': 'Use file tools for this invoice task.'},
        {'role': 'user', 'content': 'Read invoice A and invoice B using separate '
         'read_invoice calls. Keep their amounts for later. Do not write a report.'},
    ] if source else json.loads(transcript.read_text()))
    source_prefix = json.loads(json.dumps(messages))
    if not source:
        messages.append({'role': 'user', 'content':
            'Continue using the two invoice amounts already in the tool history. '
            'Do not read the invoices again. Use write_report to write exactly '
            'three lines: A=<amount>, B=<amount>, Total=<sum>. '
            'Then use read_report to verify the file.'})
    result = {'status': 'running', 'pid': os.getpid(), 'phase': args.phase,
              'model': model, 'protocol': 'chat-completions', 'effort': 'high',
              'implementation_under_test': 'direct-api-contract-not-dsh'}
    try:
        for step in range(10):
            if not source:
                check(messages[:len(source_prefix)] == source_prefix,
                      'source history was changed')
            body = {'model': model, 'messages': messages, 'tools': TOOLS,
                    'stream': False, 'max_tokens': 4096, 'reasoning_effort': 'high'}
            request = urllib.request.Request(
                URL + '?ak=' + urllib.parse.quote(secret, safe=''),
                data=json.dumps(body).encode(), headers={
                    'Content-Type': 'application/json',
                    'X-TT-LOGID': uuid.uuid4().hex.upper(),
                    'extra': json.dumps({'session_id': args.out.name + '-' + model}),
                })
            started = time.time()
            try:
                with urllib.request.urlopen(request, timeout=180) as response:
                    status, raw = response.status, response.read().decode()
            except urllib.error.HTTPError as error:
                status, raw = error.code, error.read().decode()
            for key in keys:
                raw = raw.replace(key, '<redacted>')
            wire.append({'url': URL, 'body': json.loads(json.dumps(body)),
                         'status': status, 'response': raw,
                         'elapsed': time.time() - started})
            dump(args.out / (args.phase + '-wire.json'), wire)
            check(status == 200, 'upstream HTTP ' + str(status) + ': ' + raw[:1200])
            choice = json.loads(raw)['choices'][0]
            check(choice.get('finish_reason') in ['stop', 'tool_calls'],
                  'incomplete model response: ' + str(choice.get('finish_reason')))
            observed = choice['message']
            check(observed['role'] == 'assistant', 'unexpected role')
            # The wire contract consists of readable text and ordinary tool IDs.
            # Never transplant opaque provider signatures or response metadata.
            message = {k: observed[k] for k in
                       ['role', 'content', 'reasoning_content', 'tool_calls']
                       if k in observed and observed[k] is not None}
            check(not any(observed.get(k) for k in
                          ['encrypted_content', 'signature', 'reasoning_signature']),
                  'opaque reasoning requires a separate contract')
            messages.append(message)
            calls = message.get('tool_calls', [])
            if not calls:
                break
            for call in calls:
                name = call['function']['name']
                values = json.loads(call['function']['arguments'])
                if name == 'read_invoice':
                    check(source, 'target must use restored tool history')
                    check(values.get('invoice') in ['A', 'B'], 'unknown invoice')
                    output = (world / ('invoice-' + values['invoice'] + '.txt')).read_text()
                elif name == 'write_report':
                    check(not source, 'source must not write the report')
                    (world / 'report.txt').write_text(values['content'])
                    output = 'Report saved.'
                elif name == 'read_report':
                    check(not source, 'source must not read the report')
                    output = (world / 'report.txt').read_text()
                else:
                    raise AssertionError('unknown tool ' + name)
                tool_records.append({'name': name, 'arguments': values,
                                     'call_id': call['id'], 'output': output})
                messages.append({'role': 'tool', 'tool_call_id': call['id'],
                                 'content': output})
                dump(args.out / (args.phase + '-tools.json'), tool_records)
        else:
            raise AssertionError('model did not finish within 10 requests')
        if source:
            check({r['arguments']['invoice'] for r in tool_records} == {'A', 'B'},
                  'source did not read both invoices')
            reasoned_calls = [m for m in messages
                              if m.get('reasoning_content') and m.get('tool_calls')]
            check(bool(reasoned_calls), 'source returned no reasoning with tool calls')
            dump(transcript, messages)
            result['reasoned_tool_messages'] = len(reasoned_calls)
        else:
            a = int((world / 'invoice-A.txt').read_text().strip())
            b = int((world / 'invoice-B.txt').read_text().strip())
            expected = f'A={a}\nB={b}\nTotal={a+b}\n'
            # The report's three values are the observable result. A trailing
            # newline is incidental and must not decide migration correctness.
            check((world / 'report.txt').read_text().splitlines() == expected.splitlines(),
                  'incorrect report')
            check(any(r['name'] == 'read_report' and r['output'].splitlines() == expected.splitlines()
                      for r in tool_records), 'report not verified with an actual tool')
            check(any(m.get('role') == 'tool' and isinstance(m.get('content'), str)
                      and m['content'].splitlines() == expected.splitlines()
                      for row in wire for m in row['body']['messages']),
                  'report verification was not returned to the target model')
            check(json.loads(transcript.read_text()) == source_prefix,
                  'persisted source history changed')
            dump(args.out / 'destination-transcript.json', messages)
            result['original_history_sent_unchanged'] = True
        result.update(status='passed',requests=len(wire),tool_calls=len(tool_records))
    except Exception:
        # urllib exception strings can contain credential-bearing URLs.
        detail = traceback.format_exc()
        for key in keys:
            detail = detail.replace(key, '<redacted>')
        result.update(status='failed', error=detail)
    finally:
        dump(args.out / (args.phase + '-result.json'), result)
    check(result['status'] == 'passed', args.phase + ' contract failed; see evidence')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-model', choices=MODELS, required=True)
    parser.add_argument('--destination-model', choices=MODELS, required=True)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--key-index', type=int, default=1)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--phase', choices=['source', 'destination'])
    args = parser.parse_args()
    if args.phase:
        worker(args)
        return
    args.out.mkdir(parents=True)
    world = args.out / 'world'
    world.mkdir()
    for invoice in ['A', 'B']:
        (world / ('invoice-' + invoice + '.txt')).write_text(str(100 + secrets.randbelow(900)) + '\n')
    result = {'status': 'running', 'source_model': args.source_model,
              'destination_model': args.destination_model,
              'implementation_under_test': 'direct-api-contract-not-dsh',
              'effort': 'high', 'automatic_retries': 0}
    try:
        transcript_hash = None
        for phase in ['source', 'destination']:
            command = [sys.executable, str(Path(__file__).resolve()),
                       '--source-model', args.source_model,
                       '--destination-model', args.destination_model,
                       '--env-file', str(args.env_file), '--key-index', str(args.key_index),
                       '--out', str(args.out), '--phase', phase]
            with (args.out / (phase + '-process.log')).open('w') as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
                code = process.wait()
            dump(args.out / (phase + '-process.json'), {'pid': process.pid, 'exit_code': code})
            result[phase] = json.loads((args.out / (phase + '-result.json')).read_text())
            check(code == 0, phase + ' process failed')
            digest = hashlib.sha256((args.out / 'source-transcript.json').read_bytes()).hexdigest()
            if phase == 'source':
                transcript_hash = digest
            else:
                check(digest == transcript_hash, 'source transcript changed on disk')
        check(result['source']['pid'] != result['destination']['pid'], 'PID reused')
        result.update(status='passed', source_transcript_sha256=transcript_hash)
    except Exception:
        result.update(status='failed', error=traceback.format_exc())
    dump(args.out / 'result.json', result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    check(result['status'] == 'passed', 'live contract did not pass')


if __name__ == '__main__':
    main()
