"""Local deterministic model transport. Never implements any Pi behavior."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class ScriptedProvider:
    def __init__(self):
        self.steps = []
        self.requests = []
        self.errors = []
        self.request_check = None
        self.condition = threading.Condition()
        self.releases = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                try:
                    payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                    if owner.request_check is not None:
                        try:
                            owner.request_check(payload)
                        except Exception as exc:
                            owner.errors.append('At actual model request: ' + str(exc))
                    with owner.condition:
                        owner.requests.append(payload)
                        if not owner.steps:
                            owner.errors.append('Unscripted model request')
                            step = {'text': 'UNSCRIPTED MODEL REQUEST'}
                        else:
                            step = owner.steps.pop(0)
                        owner.condition.notify_all()
                    if step.get('hold'):
                        step['release'].wait(90)
                    if 'status' in step:
                        body = json.dumps({'error': {'message': step.get('message', 'Service unavailable'),
                                                     'type': 'server_error', 'code': 'server_error'}}).encode()
                        self.send_response(step['status'])
                        self.send_header('Content-Type', 'application/json')
                        self.send_header('Content-Length', str(len(body)))
                        self.send_header('Connection', 'close')
                        self.end_headers()
                        self.wfile.write(body)
                        self.wfile.flush()
                        return
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/event-stream')
                    self.send_header('Connection', 'close')
                    self.end_headers()

                    def emit(delta, finish=None, usage=None):
                        chunk = {'id': 'local-completion', 'object': 'chat.completion.chunk',
                                 'created': int(time.time()), 'model': 'rollback-model',
                                 'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish}]}
                        if usage:
                            chunk['usage'] = usage
                        self.wfile.write(('data: ' + json.dumps(chunk) + '\n\n').encode())
                        self.wfile.flush()

                    emit({'role': 'assistant'})
                    if 'tool' in step:
                        tool = step['tool']
                        emit({'tool_calls': [{'index': 0, 'id': tool.get('id', 'call_' + str(len(owner.requests))),
                                              'type': 'function', 'function': {'name': tool['name'],
                                              'arguments': json.dumps(tool['arguments'])}}]})
                        emit({}, 'tool_calls', {'prompt_tokens': 20, 'completion_tokens': 10, 'total_tokens': 30})
                    else:
                        emit({'content': step.get('text', 'done')})
                        emit({}, 'stop', {'prompt_tokens': 20, 'completion_tokens': 5, 'total_tokens': 25})
                    self.wfile.write(b'data: [DONE]\n\n')
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except Exception as exc:
                    owner.errors.append(repr(exc))

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f'http://127.0.0.1:{self.server.server_address[1]}/v1'

    def script(self, *steps):
        with self.condition:
            for step in steps:
                step = dict(step)
                if step.get('hold'):
                    step['release'] = threading.Event()
                    self.releases.append(step['release'])
                self.steps.append(step)

    def wait_requests(self, count, timeout=20):
        with self.condition:
            ok = self.condition.wait_for(lambda: len(self.requests) >= count, timeout)
            if not ok:
                raise AssertionError(f'Expected {count} provider requests, got {len(self.requests)}')
            return self.requests[count - 1]

    def close(self):
        for release in self.releases:
            release.set()
        self.server.shutdown()
        self.server.server_close()


def tool(name, **arguments):
    return {'tool': {'name': name, 'arguments': arguments}}
