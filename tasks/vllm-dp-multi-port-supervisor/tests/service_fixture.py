"""Verifier-only substitutes for model execution and model-specific HTTP routes.

Production run_server, setup_server, run_server_worker, CLI dispatch and the
candidate supervisor remain real. Function identities are retained so aliases
and imports of the existing entrypoints do not select a different test path.
"""
import asyncio
import contextlib
import json
import os
import subprocess
import socket
import sys
import time
from types import SimpleNamespace

from aiohttp import web

ENGINE = '''import socket,json,os,time
s=socket.socket(); s.bind(("127.0.0.1",0)); s.listen()
print(json.dumps({"pid":os.getpid(),"port":s.getsockname()[1]}),flush=True)
time.sleep(3600)
'''

@contextlib.asynccontextmanager
async def engine(args, **kwargs):
    child = subprocess.Popen([sys.executable, '-S', '-c', ENGINE], stdout=subprocess.PIPE, text=True,
                             start_new_session=os.environ.get('DP_FIXTURE_DETACHED_ENGINE') == '1')
    identity = json.loads(child.stdout.readline())
    try:
        yield SimpleNamespace(args=args, identity=identity)
    finally:
        if child.poll() is None:
            child.terminate()
        child.wait(timeout=5)

async def serve(engine_client, listen_address, sock, args, **kwargs):
    config = {'healthy': False, 'delay': 0.0, 'sequence': [], 'epoch': 0}
    events = []
    stopped = asyncio.Event()

    async def health(request):
        healthy = config['sequence'].pop(0) if config['sequence'] else config['healthy']
        event = {'time': time.monotonic(), 'healthy': healthy, 'port': args.port, 'epoch': config['epoch']}
        events.append(event)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as trace:
            trace.sendto(json.dumps(event).encode(), ('127.0.0.1', int(os.environ['DP_FIXTURE_TRACE_PORT'])))
        if config.get('disconnect'):
            request.transport.close()
            return web.Response(status=503)
        await asyncio.sleep(config['delay'])
        return web.Response(status=200 if healthy else 503)

    async def control(request):
        config.update(await request.json())
        return web.json_response({'ok': True})

    async def observations(request):
        return web.json_response(events)

    async def identity(request):
        return web.json_response({'pid': os.getpid(), 'engine': engine_client.identity,
                                 'rank': args.data_parallel_rank,
                                 'devices': os.environ.get('CPU_VISIBLE_MEMORY_NODES', '')})

    app = web.Application()
    app.router.add_get('/health', health)
    app.router.add_post('/control', control)
    app.router.add_get('/events', observations)
    app.router.add_get('/identity', identity)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.SockSite(runner, sock)
    await site.start()
    import signal
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, stopped.set)
    await stopped.wait()
    return asyncio.create_task(runner.cleanup())

def install():
    import vllm.platforms
    from vllm.platforms.cpu import CpuPlatform
    vllm.platforms._current_platform = CpuPlatform()
    from vllm.entrypoints.openai import api_server

    async def context_body(args, **kwargs):
        async with _dp_fixture_backend.engine(args, **kwargs) as client:
            yield client

    async def serve_body(engine_client, listen_address, sock, args, **kwargs):
        return await _dp_fixture_backend.serve(engine_client, listen_address, sock, args, **kwargs)

    api_server.__dict__['_dp_fixture_backend'] = sys.modules[__name__]
    original = api_server.build_async_engine_client.__wrapped__
    assert not original.__code__.co_freevars
    original.__code__ = context_body.__code__
    api_server.build_and_serve.__code__ = serve_body.__code__
