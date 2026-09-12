#!/usr/bin/env python3
import ctypes, json, os, pwd, secrets, shutil, subprocess, sys, sysconfig, tempfile, traceback
from pathlib import Path
EXPECTED=['burst_and_delay','concurrent_sessions','finished_id_reuse']

def unprivileged():
    account=pwd.getpwnam('agent'); os.setgroups([]); os.setgid(account.pw_gid); os.setuid(account.pw_uid)
    ctypes.CDLL(None).prctl(38,1,0,0,0)

def make_model(path):
    sys.path.extend([sysconfig.get_path("purelib"), sysconfig.get_path("platlib")])
    import torch
    from transformers import GPT2Config, GPT2LMHeadModel, PreTrainedTokenizerFast
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace
    torch.manual_seed(12345)
    vocab={'[UNK]':0,'[PAD]':1,'[BOS]':2,'[EOS]':3,'Hello':4,'world':5,'from':6,'stream':7,'one':8,'two':9,'three':10,'next':11,'chunk':12}
    t=Tokenizer(WordLevel(vocab=vocab,unk_token='[UNK]')); t.pre_tokenizer=Whitespace()
    tok=PreTrainedTokenizerFast(tokenizer_object=t,unk_token='[UNK]',pad_token='[PAD]',bos_token='[BOS]',eos_token='[EOS]')
    tok.save_pretrained(path)
    c=GPT2Config(vocab_size=len(vocab),n_positions=64,n_ctx=64,n_embd=32,n_layer=2,n_head=2,bos_token_id=2,eos_token_id=3,pad_token_id=1)
    GPT2LMHeadModel(c).save_pretrained(path)

def check(raw, workload):
    def flat(rows): return [t for row in rows for group in row['tokens'] for t in group]
    def rows_ok(rows, rid):
        assert rows and rows[-1]['finished']
        assert all(row['request_id'] == rid for row in rows)
        assert all(not row['finished'] for row in rows[:-1])
        assert flat(rows)
    b,s=raw['bunched'],raw['spaced']
    rows_ok(b,'bunched'); rows_ok(s,'spaced')
    assert flat(b)==flat(s), 'burst and delayed input changed public output'
    assert len(raw['concurrent'])==2
    for rid, rows in zip(('session-a','session-b'),raw['concurrent']): rows_ok(rows,rid)
    first,second=raw['reuse']; rows_ok(first,'reused'); rows_ok(second,'reused')
    return EXPECTED

def main():
    log=Path('/logs/verifier'); log.mkdir(parents=True,exist_ok=True)
    for n in ('reward.txt','reward.json','report.json'): (log/n).unlink(missing_ok=True)
    (log/'reward.txt').write_text('0\n')
    seed=secrets.randbits(63)
    workload={'seed':seed,'chunks':['Hello world',' from stream',' next chunk'],
              'session_a':['Hello',' one',' two'],'session_b':['world',' three',' next'],
              'reuse_first':['Hello one'],'reuse_second':['world two']}
    wp=log/'workload.json'; wp.write_text(json.dumps(workload)); os.chmod(wp,0o444)
    model=Path(tempfile.mkdtemp(prefix='public-stream-model-')); make_model(model)
    for p in model.rglob('*'): p.chmod(0o644)
    model.chmod(0o755)
    acct=pwd.getpwnam('agent')
    obsdir=Path(tempfile.mkdtemp(prefix='public-stream-observations-')); os.chown(obsdir,acct.pw_uid,acct.pw_gid); obs=obsdir/'observations.json'
    cache=Path(tempfile.mkdtemp(prefix='public-stream-cache-')); os.chown(cache,acct.pw_uid,acct.pw_gid); (cache/'flashinfer').mkdir(); os.chown(cache/'flashinfer',acct.pw_uid,acct.pw_gid)
    env={k:v for k,v in os.environ.items() if not k.startswith('AIB_') and k not in ('PYTHONPATH','PYTHONHOME')}
    env.update(AIB_WORKLOAD=str(wp),AIB_MODEL=str(model),AIB_OBSERVATIONS=str(obs),FLASHINFER_WORKSPACE_BASE=str(cache),TORCHINDUCTOR_CACHE_DIR=str(cache/'torchinductor'),TRITON_CACHE_DIR=str(cache/'triton'),XDG_CACHE_HOME=str(cache),PYTHONDONTWRITEBYTECODE='1')
    # Avoid site initialization while preserving installed torch/transformers explicitly.
    bootstrap="import runpy,sys,sysconfig; sys.path.extend("+repr(['/workspace/repo','/tests',sysconfig.get_path('purelib'),sysconfig.get_path('platlib')])+ "); runpy.run_path(sys.argv[1],run_name='__main__')"
    worker_log=(log/'worker.log').open('w'); result=subprocess.run([sys.executable,'-I','-S','-c',bootstrap,'/tests/verify_streaming_public_api.py'],env=env,cwd='/workspace/repo',preexec_fn=unprivileged,timeout=1080,stdout=worker_log,stderr=subprocess.STDOUT); worker_log.close()
    passed=[]; failures=[]
    try:
        if result.returncode: raise RuntimeError(f'candidate worker exit {result.returncode}')
        raw=json.loads(obs.read_text()); passed=check(raw,workload); assert set(passed)==set(EXPECTED); (log/'observations.json').write_text(json.dumps(raw))
    except Exception: failures.append(traceback.format_exc())
    report={'schema_version':'trusted_public_behavior_report.v1','completed':not failures,'expected_stages':EXPECTED,'stages_passed':passed,'failures':failures,'worker_exit_code':result.returncode}
    (log/'report.json').write_text(json.dumps(report,indent=2)+'\n'); reward=int(not failures); (log/'reward.json').write_text(json.dumps({'reward':reward,'verifier_exit_code':0})+'\n'); (log/'reward.txt').write_text(str(reward)+'\n'); print(json.dumps(report))
if __name__=='__main__': main()
