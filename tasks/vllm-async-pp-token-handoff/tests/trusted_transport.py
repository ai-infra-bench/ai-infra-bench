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


def observation_group(candidate_rank, *, observer=False):
    # Separate two-rank groups keep the observer on the opposite GPU from each
    # candidate endpoint. Neither group enters vLLM's default or PP group.
    import torch
    import torch.distributed as dist
    from datetime import timedelta
    device = 1 - candidate_rank if observer else candidate_rank
    torch.cuda.set_device(device)
    store = dist.TCPStore('127.0.0.1', 29719 + candidate_rank, 2, observer,
                          timedelta(seconds=720), wait_for_workers=False)
    group = dist.ProcessGroupNCCL(store, 0 if observer else 1, 2,
                                  timedelta(seconds=720))
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


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--role', choices=['peer'], required=True)
    p.add_argument('--result', required=True)
    args = p.parse_args()
    peer(args.result)
