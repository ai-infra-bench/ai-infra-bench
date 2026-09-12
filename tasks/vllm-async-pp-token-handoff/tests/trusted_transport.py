#!/usr/bin/env python3
"""Check GPU inputs outside candidate processes without prescribing PP transport.

Both PP ranks run candidate code. A root-owned observer supplies fresh sampler
inputs and checks subsequent model inputs on a separate NCCL group. That group
is test I/O, not the candidate's PP protocol. Worker-local instrumentation is
still not a general security boundary against arbitrary candidate Python.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile


def initialize(rank):
    import torch
    import torch.distributed as dist
    from datetime import timedelta
    torch.cuda.set_device(rank)
    dist.init_process_group('nccl', timeout=timedelta(seconds=60))
    from vllm.distributed.parallel_state import init_distributed_environment, initialize_model_parallel
    init_distributed_environment(world_size=2, rank=rank,
        distributed_init_method='env://', local_rank=rank, backend='nccl')
    initialize_model_parallel(tensor_model_parallel_size=1,
        pipeline_model_parallel_size=2, backend='nccl')


def observation_group(candidate_rank, *, observer=False):
    # Separate two-rank groups keep the observer on the opposite GPU from each
    # candidate endpoint. Neither group enters vLLM's default or PP group.
    import torch
    import torch.distributed as dist
    from datetime import timedelta
    device = 1 - candidate_rank if observer else candidate_rank
    torch.cuda.set_device(device)
    store = dist.TCPStore('127.0.0.1', 29719 + candidate_rank, 2, observer,
                          timedelta(seconds=300), wait_for_workers=False)
    group = dist.ProcessGroupNCCL(store, 0 if observer else 1, 2,
                                  timedelta(seconds=300))
    return store, group


def peer(result_path):
    # -I, a trusted cwd, and no candidate imports keep the comparison external.
    import secrets
    import torch
    send_store, send_group = observation_group(1, observer=True)
    recv_store, recv_group = observation_group(0, observer=True)
    cases = []
    for count in (2, 4):
        values = [secrets.randbelow(800) + 100 for _ in range(count)]
        tokens = torch.tensor(values, dtype=torch.int32, device='cuda:0').reshape(-1, 1)
        send_group.send([tokens], 1, 0).wait()
        got = torch.empty(count - 1, dtype=torch.int32, device='cuda:1')
        recv_group.recv([got], 1, 0).wait()
        actual = got.cpu().tolist()
        expected = values[:-1][::-1]
        assert actual == expected, (actual, expected)
        cases.append({'rows': count, 'next_model_input_matches': True})
    Path(result_path).write_text(json.dumps({'passed': True, 'cases': cases}) + '\n')


def candidate(rank, *, initialized=False):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import torch
    import torch.distributed as dist
    from worker_fixtures import make_runner, next_inputs
    if not initialized:
        initialize(rank)
    store, group = observation_group(rank)
    for count in (2, 4):
        ids = [f'peer-row-{i}' for i in range(count)]
        sampled = None
        if rank == 1:
            sampled = torch.empty((count, 1), dtype=torch.int32, device='cuda')
            group.recv([sampled], 0, 0).wait()
        runner = make_runner(ids, [False] * (count - 1) + [True],
                             sampled)
        output = runner.sample_tokens(None)
        if rank == 0:
            # Both sides of the production handoff belong to the candidate.
            # Only its downstream input is exported over the observation group.
            actual_input = next_inputs(runner, ids[:-1][::-1], inspect_cpu=False).to(dtype=torch.int32)
            group.send([actual_input], 0, 0).wait()
        else:
            next_inputs(runner, ids[:-1][::-1], inspect_cpu=False)
            if hasattr(output, 'get_output'):
                output.get_output()
    dist.barrier()
    if not initialized:
        dist.destroy_process_group()


def supervise(log_dir):
    root = Path(log_dir)
    root.mkdir(parents=True, exist_ok=True)
    result = root / 'trusted-peer-inputs.json'
    result.unlink(missing_ok=True)
    script = str(Path(__file__).resolve())
    procs, files = [], []
    passed = False
    try:
        for role, rank in [('peer', 2), ('candidate', 0), ('candidate', 1)]:
            env = {k: v for k, v in os.environ.items()
                   if k not in ('PYTHONPATH', 'PYTHONHOME') and not k.startswith('ASYNC_PP_')}
            env.update(RANK=str(rank), LOCAL_RANK=str(rank), WORLD_SIZE='2',
                       MASTER_ADDR='127.0.0.1', MASTER_PORT='29711',
                       HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
            argv = [sys.executable, '-I' if role == 'peer' else '-s', script,
                    '--role', role, '--rank', str(rank), '--result', str(result)]
            if role == 'candidate':
                cache = Path(tempfile.mkdtemp(prefix='async-pp-peer-'))
                os.chown(cache, 65534, 65534)
                env.update(PYTHONPATH='/workspace/repo', HOME=str(cache), TMPDIR=str(cache),
                           TRITON_CACHE_DIR=str(cache / 'triton'),
                           TORCHINDUCTOR_CACHE_DIR=str(cache / 'inductor'),
                           ASYNC_PP_STAGE='TRUSTED_TRANSPORT', ASYNC_PP_NONCE='0' * 32)
                argv = ['setpriv', '--reuid=65534', '--regid=65534', '--init-groups',
                        '--no-new-privs', '--', *argv]
            f = open(root / f'trusted-peer-{role}-{rank}.log', 'w')
            files.append(f)
            procs.append(subprocess.Popen(argv, env=env, cwd='/trusted/staging',
                         stdout=f, stderr=subprocess.STDOUT, start_new_session=True))
        for proc in procs:
            proc.wait(timeout=300)
        evidence = json.loads(result.read_text()) if result.exists() else {}
        passed = all(p.returncode == 0 for p in procs) and evidence.get('passed') is True
    except Exception as exc:
        (root / 'trusted-peer-error.txt').write_text(repr(exc))
    finally:
        for proc in procs:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
        for f in files:
            f.close()
    (root / 'trusted-transport.json').write_text(json.dumps({'next_inputs': passed}) + '\n')
    return 0 if passed else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--role', choices=['peer', 'candidate'])
    p.add_argument('--rank', type=int)
    p.add_argument('--result')
    p.add_argument('--log-dir', default='/logs/verifier')
    args = p.parse_args()
    if args.role == 'peer':
        peer(args.result)
    elif args.role == 'candidate':
        candidate(args.rank)
    else:
        raise SystemExit(supervise(args.log_dir))
