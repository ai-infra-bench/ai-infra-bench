#!/usr/bin/env python3
"""Independent real-process probes for the ptrace supervisor (no Pi solution)."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time

NODE = r'''
const fs=require('fs'), cp=require('child_process'), readline=require('readline');
const {Worker}=require('worker_threads');
const workers=[];
let ready=0;
const workerCode=`const {parentPort,workerData}=require('worker_threads'); const fs=require('fs');
parentPort.on('message',()=>{fs.writeFileSync(workerData.path,'worker-restored');}); parentPort.postMessage('ready');`;
for(const p of ['a.txt','b.txt']) {
 const w=new Worker(workerCode,{eval:true,workerData:{path:p}});
 workers.push(w); w.on('message',()=>{if(++ready===2){console.log(JSON.stringify({event:'ready'}));
  if(process.env.PROBE_AUTORUN) run({mode:process.env.PROBE_AUTORUN});}});
}
function run(q) {
 if(q.mode==='direct') {fs.writeFileSync('a.txt','target-a'); fs.writeFileSync('b.txt','target-b');}
 if(q.mode==='rename') {fs.writeFileSync('stage.tmp','target-a'); fs.renameSync('stage.tmp','a.txt'); fs.writeFileSync('b.txt','target-b');}
 if(q.mode==='workers') {for(const w of workers)w.postMessage('go');}
 if(q.mode==='chmod') {fs.chmodSync('a.txt',0o751); fs.writeFileSync('b.txt','target-b');}
 if(q.mode==='unlink') {fs.unlinkSync('a.txt'); fs.writeFileSync('b.txt','target-b');}
 if(q.mode==='create') {fs.writeFileSync('new.txt','new-file'); fs.writeFileSync('b.txt','target-b');}
 if(q.mode==='tree') {
  const python=`from pathlib import Path; Path('a.txt').write_text('python-target'); Path('b.txt').write_text('python-target-b')`;
  cp.spawn('bash',['-c','python3 -c "$1"','probe',python],{stdio:'inherit'});
 }
 if(q.mode==='vfork') {
  const python=`import subprocess; subprocess.run(['bash','-c','printf target > a.txt; printf target-b > b.txt'],check=True)`;
  cp.spawn('python3',['-c',python],{stdio:'inherit'});
 }
 if(q.mode==='mmap') {
  const python=`import mmap,os; from pathlib import Path; f=open('a.txt','r+b'); m=mmap.mmap(f.fileno(),0); m[:]=b'mapped-state'; os.getpid(); Path('b.txt').write_text('mapped-b')`;
  cp.spawn('python3',['-c',python],{stdio:'inherit'});
 }
 if(q.mode==='kill-tree') {
  cp.spawn('bash',['-c',`python3 -u -c 'import os,sys; print("CHILD_READY",flush=True); sys.stdin.read()'`],{stdio:['pipe','pipe','inherit']})
    .stdout.on('data',x=>{process.stdout.write(x);});
 }
}
readline.createInterface({input:process.stdin}).on('line',line=>run(JSON.parse(line)));
'''


class Peer:
    def __init__(self, script):
        self.p = subprocess.Popen(['python3', script, '--uid', '65534', '--gid', '65534'],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, bufsize=1)
        self.q = queue.Queue()
        self.events = []
        self.out = ''
        self.err = ''
        self.serial = 0
        def reader():
            for line in self.p.stdout:
                try: self.q.put(json.loads(line))
                except Exception: self.q.put({'type':'invalid','line':line})
            self.q.put({'type':'eof'})
        threading.Thread(target=reader,daemon=True).start()
        self.until(lambda e:e['type']=='ready')

    def until(self,predicate,timeout=30):
        end=time.monotonic()+timeout
        while True:
            left=end-time.monotonic()
            if left<=0: raise TimeoutError({'events':self.events[-15:],'stdout':self.out,'stderr':self.err})
            try: e=self.q.get(timeout=left)
            except queue.Empty: raise TimeoutError({'events':self.events[-15:],'stdout':self.out,'stderr':self.err})
            self.events.append(e)
            if e['type']=='output':
                if e['stream']=='stdout': self.out+=e['data']
                else:self.err+=e['data']
            if e['type'] in ('supervisor_error','invalid','eof'):
                raise RuntimeError({'event':e,'stderr':self.p.stderr.read() if e['type']=='eof' else self.err})
            if predicate(e):return e

    def command(self,op,**args):
        self.serial+=1
        ident=str(self.serial)
        self.p.stdin.write(json.dumps({'id':ident,'op':op,**args})+'\n');self.p.stdin.flush()
        e=self.until(lambda e:e['type']=='reply' and e['id']==ident)
        if not e['ok']:raise RuntimeError(e)
        return e['result']

    def close(self):
        try:self.command('shutdown')
        finally:
            self.p.stdin.close()
            try:self.p.wait(timeout=10)
            except subprocess.TimeoutExpired:self.p.kill();self.p.wait()


def one(script,mode):
    with tempfile.TemporaryDirectory(prefix='supervisor-public-fs-') as temp:
        root=Path(temp);os.chown(root,65534,65534);root.chmod(0o755)
        for name in ('a.txt','b.txt'):
            p=root/name;p.write_text('before-'+name);os.chown(p,65534,65534)
        peer=Peer(script)
        try:
            start={'argv':['node','-e',NODE],'cwd':temp,'env':{'HOME':temp}}
            paths=['a.txt','b.txt','new.txt']
            if mode=='startup':
                start['env']['PROBE_AUTORUN']='rename'
                start['arm']={'workspace':temp,'paths':paths,'tag':mode}
            peer.command('start',**start)
            if '"event":"ready"' not in peer.out:
                peer.until(lambda e:'"event":"ready"' in peer.out)
            if mode!='kill-tree':
                if mode!='startup':
                    peer.command('arm',workspace=temp,paths=paths,tag=mode)
                    peer.command('stdin',data=json.dumps({'mode':mode})+'\n')
                trigger=next((e for e in peer.events if e['type']=='trigger'),None)
                if trigger is None:trigger=peer.until(lambda e:e['type']=='trigger')
                done=next((e for e in peer.events if e['type']=='execution_done'),None)
                if done is None:done=peer.until(lambda e:e['type']=='execution_done')
                assert len(trigger['changed'])==1,trigger
                remaining=set(('a.txt','b.txt'))-set(trigger['changed'])
                assert all((root/n).read_text()=='before-'+n for n in remaining)
                if mode!='create':assert not (root/'new.txt').exists()
                assert done['killed'],done
            else:
                peer.command('stdin',data=json.dumps({'mode':mode})+'\n')
                if 'CHILD_READY' not in peer.out:peer.until(lambda e:'CHILD_READY' in peer.out)
                peer.command('kill')
                done=next((e for e in peer.events if e['type']=='execution_done'),None)
                if done is None:done=peer.until(lambda e:e['type']=='execution_done')
                trigger=None
            traced={e['pid'] for e in peer.events if e['type']=='process_exit'}
            assert len(traced)>=9,(mode,traced,done)
            for pid in traced:
                try:os.kill(pid,0)
                except ProcessLookupError:continue
                raise AssertionError(f'surviving process {pid}')
            assert done['stats']['clone']>=8,done
            if mode in ('tree','kill-tree','vfork'):
                assert done['stats']['vfork']+done['stats']['fork']>=1,done
                assert done['stats']['exec']>=3,done
            if mode=='vfork':assert done['stats']['vfork']>=1,done
            return {'mode':mode,'pass':True,'trigger':trigger,'done':done,
                    'exit_count':len(traced),'stderr':peer.err}
        finally:peer.close()


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('supervisor');ap.add_argument('--repeat',type=int,default=2)
    args=ap.parse_args()
    results=[]
    for iteration in range(args.repeat):
        for mode in ('direct','rename','workers','tree','kill-tree','chmod','unlink','create','vfork','startup','mmap'):
            result=one(args.supervisor,mode);result['iteration']=iteration
            results.append(result);print(json.dumps(result),flush=True)
    print(json.dumps({'summary':{'pass':all(x['pass'] for x in results),'cases':len(results)}}))
