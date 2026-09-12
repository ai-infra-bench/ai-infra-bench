#!/usr/bin/env python3
"""Exercise public serving, real HTTP and complete process ownership transitions."""
import contextlib
import ctypes
import errno
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import psutil

ROOT = Path('/workspace/repo')
ENDPOINTS = ('/health', '/ready', '/readyz')


def request(port, path='/health', data=None, timeout=.4):
    req = Request(f'http://127.0.0.1:{port}{path}', data=None if data is None else json.dumps(data).encode(), headers={'Content-Type':'application/json'})
    try:
        with urlopen(req, timeout=timeout) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, b''
    except (TimeoutError, URLError, ConnectionError):
        return -1, b''


def eventually(predicate, timeout=45, label='condition'):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.04)
    raise AssertionError('timed out: ' + label)


def closed(port):
    with socket.socket() as sock:
        sock.settimeout(.2)
        return sock.connect_ex(('127.0.0.1', port)) == errno.ECONNREFUSED


def alive(process):
    try:
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


class Group:
    def __init__(self, harness, *, local=2, total=2, start=0, tp=1, pp=1, devices='3,1', interval=.15, timeout=.2, threshold=3, extra=(), mode=True):
        # Sequential cases have no competing allocator in this network namespace.
        for port in range(23100, 32000-local):
            sockets=[]
            try:
                for n in range(local+1):
                    sock=socket.socket(); sockets.append(sock); sock.bind(('127.0.0.1',port+n))
                break
            except OSError:
                continue
            finally:
                for sock in sockets: sock.close()
        else:
            raise RuntimeError('no contiguous ports')
        self.ports=list(range(port,port+local)); self.supervisor=port+local
        self.known={}; self.stop=threading.Event(); self.trace=[]
        self.trace_socket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.trace_socket.bind(('127.0.0.1',0));self.trace_socket.setblocking(False)
        self.mode=mode
        args=[sys.executable,'-m','vllm.entrypoints.cli.main','serve','benchmark/fake-model','--host','127.0.0.1','--port',str(port),'--uvicorn-log-level','warning']
        if mode:
            args += ['--data-parallel-multi-port-external-lb','--data-parallel-supervisor-port',str(self.supervisor),'--data-parallel-size',str(total),'--data-parallel-size-local',str(local),'--data-parallel-start-rank',str(start),'--tensor-parallel-size',str(tp),'--pipeline-parallel-size',str(pp),'--dp-supervisor-probe-interval-s',str(interval),'--dp-supervisor-probe-timeout-s',str(timeout),'--dp-supervisor-probe-failure-threshold',str(threshold)]
        # Values can refer to the allocated ports without exposing a fixed port.
        args += [str(port+x) if isinstance(x,int) else x for x in extra]
        env=os.environ.copy();env['CPU_VISIBLE_MEMORY_NODES']=devices
        env['DP_FIXTURE_TRACE_PORT']=str(self.trace_socket.getsockname()[1])
        env['PYTHONPATH']=str(harness)+os.pathsep+str(ROOT)
        self.process=subprocess.Popen(args,cwd=ROOT,env=env,start_new_session=True)
        self.collector=threading.Thread(target=self._collect,daemon=True);self.collector.start()

    def remember(self):
        # The verifier is a subreaper: children that outlive a failed startup are
        # still reachable without assuming the candidate's process-group design.
        for proc in psutil.Process().children(recursive=True):
            if proc.pid != self.process.pid:
                with contextlib.suppress(psutil.NoSuchProcess):
                    self.known[(proc.pid,proc.create_time())]=proc

    def _collect(self):
        while not self.stop.wait(.02):
            self.remember()
            self.drain_trace()

    def drain_trace(self):
        while True:
            try: data=self.trace_socket.recv(4096)
            except BlockingIOError: break
            self.trace.append(json.loads(data))

    def wait_services(self):
        for port in self.ports:
            eventually(lambda:request(port)[0]==503,label=f'child {port} startup')

    def status_all(self, expected):
        for path in ENDPOINTS:
            eventually(lambda:(request(self.supervisor,path)[0]==200) == (expected==200),timeout=5,label=path)

    def set(self,index,**config):
        assert request(self.ports[index],'/control',config)[0]==200

    def events(self,index=0):
        return json.loads(request(self.ports[index],'/events')[1])

    def identity(self,index):
        return json.loads(request(self.ports[index],'/identity')[1])

    def ready(self):
        for index in range(len(self.ports)): self.set(index,healthy=True)
        self.status_all(200)

    def assert_clean(self):
        self.process.wait(timeout=20)
        self.remember()
        ports=self.ports+([self.supervisor] if self.mode else [])
        eventually(lambda:all(closed(port) for port in ports),timeout=10,label='TCP listeners released')
        eventually(lambda:not any(alive(p) for p in list(self.known.values())),timeout=10,label='all descendants exited')

    def close(self):
        self.remember();self.stop.set();self.collector.join()
        self.drain_trace();self.trace_socket.close()
        # Teardown is deliberately outside candidate-success assertions.
        for proc in list(self.known.values()):
            if alive(proc):
                with contextlib.suppress(psutil.NoSuchProcess): proc.kill()
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=5)
        for proc in list(self.known.values()):
            with contextlib.suppress(ChildProcessError,ProcessLookupError):
                os.waitpid(proc.pid,0)


@contextlib.contextmanager
def group(harness,**kwargs):
    g=Group(harness,**kwargs)
    try: yield g
    finally: g.close()


def readiness(harness):
    with group(harness) as g:
        g.wait_services();g.status_all(503)
        g.set(0,healthy=True);time.sleep(.35);g.status_all(503)
        g.set(1,healthy=True);g.status_all(200)
        identity=g.identity(0)
        # This is an actual descendant and listener, not only a reported PID.
        engine=psutil.Process(identity['engine']['pid'])
        assert engine.ppid()==identity['pid']
        assert not closed(identity['engine']['port'])
        g.remember()
        psutil.Process(identity['pid']).kill()
        g.assert_clean()
        assert not alive(engine) and closed(identity['engine']['port'])

    # A rank may die before the initial all-healthy transition. A single local
    # rank is still a valid slice of a larger DP deployment.
    with group(harness,local=1,total=2,start=1,devices='5') as g:
        g.wait_services();g.status_all(503);g.remember()
        psutil.Process(g.identity(0)['pid']).kill()
        g.assert_clean()


def probe_settings(harness):
    with group(harness,interval=.6,timeout=.2,threshold=3) as g:
        g.wait_services();g.ready()
        # Successful probes reset the counter; two separate short bursts must not
        # accumulate into a terminal failure. Sustained failure stops at three.
        g.set(0,healthy=True,sequence=[False,True,False,False,True])
        g.set(1,healthy=True,sequence=[False,True,False,False,True])
        start=len(g.events())
        eventually(lambda:len(g.events())>=start+6,timeout=12,label='probe sequence')
        assert g.process.poll() is None
        events=g.events()[-5:]
        gaps=[b['time']-a['time'] for a,b in zip(events,events[1:])]
        assert min(gaps)>.35, ('probe interval ignored',gaps)
        g.set(0,healthy=False,epoch=1)
        g.status_all(503)
        assert g.process.poll() is None, 'threshold ignored'
        g.assert_clean()
        time.sleep(.05)
        failures=[event for event in g.trace if event['port']==g.ports[0] and event['epoch']==1]
        assert len(failures)==3, ('consecutive failure threshold not honored',failures)

    # A delay between two configured timeouts distinguishes honored deadlines
    # from hardcoded values without benchmarking total model/runtime speed.
    with group(harness,interval=.15,timeout=1.0,threshold=2) as g:
        g.wait_services();g.ready();g.set(0,delay=.45)
        time.sleep(1.8)
        assert g.process.poll() is None, 'configured long probe timeout ignored'
        g.status_all(200)
        g.set(0,delay=3,epoch=2)
        g.assert_clean()
        time.sleep(.05)
        attempts=[event for event in g.trace if event['port']==g.ports[0] and event['epoch']==2]
        assert len(attempts)==2, ('timeout failure count',attempts)
        gap=attempts[1]['time']-attempts[0]['time']
        assert .8<gap<2, ('probe timeout not honored',gap)

    with group(harness,threshold=3) as g:
        g.wait_services();g.ready()
        g.set(0,disconnect=True,epoch=3)
        g.assert_clean();time.sleep(.05)
        attempts=[event for event in g.trace if event['port']==g.ports[0] and event['epoch']==3]
        # Clients may transparently retry a disconnected idempotent request.
        # Exact logical failure counts are checked with non-200 responses above.
        assert len(attempts)>=3, ('connection failures were not exercised',attempts)


def mapping_and_signals(harness):
    with group(harness,total=4,start=2,tp=2,pp=2,devices='7,2,5,0,6,3,1,4') as g:
        g.wait_services();g.ready()
        assert [(g.identity(i)['rank'],g.identity(i)['devices']) for i in range(2)]==[(2,'7,2,5,0'),(3,'6,3,1,4')]
        g.process.send_signal(signal.SIGINT);g.assert_clean()
    with group(harness,local=3,total=5,start=2,devices='4,0,2') as g:
        g.wait_services();g.status_all(503)
        g.process.send_signal(signal.SIGTERM);g.assert_clean()


def invalid(harness):
    for options in [('--data-parallel-supervisor-port',1),('--headless',),('--data-parallel-hybrid-lb',),('--data-parallel-external-lb',),('--data-parallel-start-rank','9'),('--dp-supervisor-probe-interval-s','0'),('--dp-supervisor-probe-timeout-s','0'),('--dp-supervisor-probe-failure-threshold','0')]:
        with group(harness,extra=options) as g:
            assert g.process.wait(timeout=45)!=0, ('invalid configuration accepted',options)
            g.assert_clean()


def ordinary(harness):
    with group(harness,local=1,mode=False) as g:
        g.wait_services();g.set(0,healthy=True)
        assert request(g.ports[0])[0]==200
        g.process.send_signal(signal.SIGTERM);g.assert_clean()


def main():
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(36,1,0,0,0)!=0: raise OSError(ctypes.get_errno(),'subreaper unavailable')
    with tempfile.TemporaryDirectory(prefix='dp-contract-') as temp:
        harness=Path(temp)
        fixture=Path(__file__).with_name('service_fixture.py')
        (harness/'service_fixture.py').write_bytes(fixture.read_bytes())
        (harness/'sitecustomize.py').write_text('import service_fixture; service_fixture.install()\n')
        for case in (readiness,probe_settings,mapping_and_signals,invalid,ordinary):
            start=time.monotonic();case(harness)
            print(f'PASS {case.__name__} {time.monotonic()-start:.2f}s',flush=True)
    print('PASS all required behavior checks',flush=True)

if __name__=='__main__':main()
