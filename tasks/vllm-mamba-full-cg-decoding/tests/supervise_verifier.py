#!/usr/bin/env python3
"""Compare candidate outputs with private eager results from the frozen Base.

Only unprivileged children import submitted code. The scorer extracts trusted
reference Python from the verifier image's Git tree before any candidate runs.
Success markers and successful process exits never establish correctness.
"""
from __future__ import annotations

import json
import math
import os
import pwd
import secrets
import tarfile
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import torch
from transformers import (MambaConfig, MambaForCausalLM, Mamba2Config, Mamba2ForCausalLM,
                          GraniteMoeHybridConfig, GraniteMoeHybridForCausalLM)

LOGS = Path("/logs/verifier")
VOCAB = 64
STEPS = 8
# Eager/graph reductions can differ slightly. Full distributions expose state errors
# which do not happen to change greedy argmax for a tiny random model.
ATOL = {"mamba1": 4e-5, "mamba2": 8e-3, "hybrid": 8e-3}
# Mamba2 float32 scan/update reductions need not be bit-identical.
# Cases vary public serving settings, not metadata layout or repair location.
CASES = [
    ("mamba1-full", "mamba1", False, False, "none"),
    ("mamba1-eager", "mamba1", True, False, "none"),
    ("mamba2-full", "mamba2", False, False, "all"),
    ("mamba2-eager", "mamba2", True, False, "none"),
    ("hybrid-spec-none", "hybrid", False, True, "none"),
    ("hybrid-spec-eager", "hybrid", True, True, "none"),
    ("hybrid-spec-all", "hybrid", False, True, "all"),
]


def save_reward(value: int, payload: dict) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    for name, text in [("reward.txt", f"{value}\n"),
                       ("reward.json", json.dumps({"reward": value})+"\n"),
                       ("result.json", json.dumps({"reward": value, **payload}, indent=2)+"\n")]:
        fd = os.open(LOGS/name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(text)


def make_model(kind: str, path: Path, seed: int):
    torch.manual_seed(seed)
    if kind == "mamba1":
        config = MambaConfig(vocab_size=VOCAB, hidden_size=64, num_hidden_layers=2,
                             state_size=16, expand=2, time_step_rank=4,
                             conv_kernel=4, tie_word_embeddings=False)
        model = MambaForCausalLM(config)
    elif kind == "mamba2":
        config = Mamba2Config(vocab_size=VOCAB, hidden_size=128, num_hidden_layers=2,
                              state_size=16, expand=2, num_heads=8, head_dim=32,
                              n_groups=1, chunk_size=16, tie_word_embeddings=True)
        model = Mamba2ForCausalLM(config)
    else:
        config = GraniteMoeHybridConfig(
            vocab_size=VOCAB, hidden_size=128, intermediate_size=256,
            num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=4,
            layer_types=["mamba", "attention"], num_local_experts=0,
            num_experts_per_tok=0, shared_intermediate_size=256,
            mamba_n_heads=8, mamba_n_groups=1, mamba_d_state=16,
            mamba_d_head=32, mamba_d_conv=4, mamba_expand=2, mamba_chunk_size=16,
            tie_word_embeddings=False, max_position_embeddings=256,
        )
        model = GraniteMoeHybridForCausalLM(config)
        with torch.no_grad():
            for name, weight in model.named_parameters():
                if name.endswith(("out_proj.weight", "o_proj.weight", "down_proj.weight")):
                    weight.mul_(0.05)
            # A separated greedy margin permits repeatable accept/no-draft
            # transitions. Random weights still determine every logprob vector.
            model.lm_head.weight.copy_(torch.roll(model.model.embed_tokens.weight, 1, 0))
    if kind == "mamba2":
        with torch.no_grad():
            for layer in model.backbone.layers:
                layer.mixer.out_proj.weight.mul_(0.05)
    model.eval()
    model.save_pretrained(path)
    path.chmod(0o755)
    for file in path.iterdir():
        file.chmod(0o644)
    return model


def make_reference(root: Path) -> Path:
    repo = root / "reference"
    repo.mkdir(mode=0o700)
    archive = root / "base.tar"
    with archive.open("wb") as output:
        subprocess.run(["git", "-c", "safe.directory=/workspace/repo", "-C", "/workspace/repo",
                        "archive", "737bfa3a43ce386bd1894792f3302d9f3f9d73fa", "vllm"],
                       stdout=output, check=True)
    with tarfile.open(archive) as tar:
        tar.extractall(repo, filter="data")
    archive.unlink()
    # Native libraries come from the pinned, root-owned installed donor,
    # never from the submitted artifact directory.
    donor = Path("/usr/local/lib/python3.12/dist-packages/vllm")
    for source in donor.rglob("*"):
        if source.is_file() and (source.suffix == ".so" or source.name == "_version.py"):
            target = repo/"vllm"/source.relative_to(donor)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(source)
    return repo


def execute(command, env, name, observation=None):
    with (LOGS/f"{name}.log").open("w") as log:
        os.fchmod(log.fileno(), 0o600)
        output = open(observation, "w") if observation else log
        proc = subprocess.Popen(command, cwd="/", env=env, stdout=output,
                                stderr=log, start_new_session=True)
        if observation:
            output.close()
        try:
            code = proc.wait(timeout=210)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            raise RuntimeError(f"{name}: timed out")
    if code != 0:
        raise RuntimeError(f"{name}: production client exited {code}; see {name}.log")
    return code


def compare(actual, expected, atol: float) -> tuple[int, float]:
    if not isinstance(actual, dict) or set(actual) != {"batches", "accepted_tokens", "cached_tokens"}:
        raise ValueError("missing production output batches")
    batches = actual["batches"]
    if not isinstance(batches, list) or len(batches) != len(expected):
        raise ValueError("incomplete batch lifecycle")
    vectors, largest = 0, 0.0
    for b, (rows, refs) in enumerate(zip(batches, expected, strict=True)):
        if not isinstance(rows, list) or len(rows) != len(refs):
            raise ValueError(f"batch {b}: missing or duplicate requests")
        for r, (row, ref) in enumerate(zip(rows, refs, strict=True)):
            if row.get("prompt") != ref["prompt"] or row.get("tokens") != ref["tokens"]:
                raise ValueError(f"batch {b} request {r}: prompt/token sequence mismatch: got {row.get('tokens')} expected {ref['tokens']}")
            probs = row.get("logprobs")
            if not isinstance(probs, list) or len(probs) != len(ref["logprobs"]):
                raise ValueError(f"batch {b} request {r}: incomplete output sequence")
            for step, (got, want) in enumerate(zip(probs, ref["logprobs"], strict=True)):
                if not isinstance(got, list) or len(got) != VOCAB:
                    raise ValueError("incomplete vocabulary distribution")
                if any(type(x) not in (int, float) or not math.isfinite(x) for x in got):
                    raise ValueError("non-finite/non-numeric output")
                delta = max(abs(x-y) for x,y in zip(got, want, strict=True))
                largest = max(largest, delta)
                if delta > atol:
                    raise ValueError(f"batch {b} request {r} step {step}: recurrent output differs by {delta:.7g}")
                vectors += 1
    return vectors, largest


def run() -> dict:
    if os.geteuid() != 0:
        raise RuntimeError("trusted scorer must run as root")
    agent = pwd.getpwnam("agent")
    worker = Path(__file__).with_name("verify_mamba_full_cg.py")
    for path in (Path(__file__), worker, worker.with_name("observe_cuda_graph"), Path(sys.executable).resolve()):
        info = path.stat()
        if info.st_uid != 0 or info.st_mode & 0o022 or not stat.S_ISREG(info.st_mode):
            raise RuntimeError(f"untrusted verifier file: {path}")
    torch.set_num_threads(2)
    records = []
    # Only model/config/input files are readable by the candidate. Reference
    # results and the frozen reference source stay in root-only directories.
    with tempfile.TemporaryDirectory(prefix="mamba-eval-", dir="/tmp") as temp:
        root = Path(temp)
        root.chmod(0o711)
        reference_repo = make_reference(root)
        private = root/"private"
        private.mkdir(mode=0o700)
        seeds = {kind: secrets.randbelow(2**31) for kind in ("mamba1", "mamba2", "hybrid")}
        models, fixtures, references = {}, {}, {}
        for name, kind, eager, speculative, cache in CASES:
            start = time.monotonic()
            fixture_key = (kind, cache == "all" and kind == "hybrid")
            if fixture_key not in fixtures:
                tokens = secrets.SystemRandom().sample(range(3, VOCAB), 9)
                fixture = {"steps": STEPS,
                           "batches": [[[tokens[8]]*17], [[tokens[0]]*17, [tokens[1]]*33],
                                       [[tokens[2]], [tokens[3]]*49],
                                       [[tokens[4], tokens[5]]*16+[tokens[6]], [tokens[7]]]]}
                if kind == "mamba1":
                    fixture["lifecycle"] = {
                        "prompts": [[tokens[i], tokens[i+1]]*(4+i)+[tokens[i]]*i
                                    for i in range(3)],
                        "long_prompt": [tokens[6], tokens[7], tokens[8], tokens[5]]*20,
                    }
                if kind == "hybrid":
                    anchor = secrets.randbelow(10)+3
                    def row(offsets):
                        return [anchor+v for v in offsets]
                    transition = row([0, 1, 2, 3, 8, 12, 0])
                    fixture = {"steps": 24, "batches": [
                        [row([0, 1, 2])], [[anchor+5]*19],
                        [[anchor+7]*19, [anchor+9]*3], [transition],
                        [transition, row([16, 17, 18, 19, 24, 28, 16])],
                        [row([0, 1, 2, 9, 13, 17, 0])],
                    ]}
                    if cache == "all":
                        prefix = row([20, 30, 10, 0, 1, 2, 3, 10])*4
                        suffix = row([30, 0, 1, 2, 35, 10, 20, 0])
                        fixture["batches"] = [[prefix+suffix], [prefix+suffix],
                            [prefix+suffix, prefix+suffix[:-1]+[anchor+1]]]
                fixtures[fixture_key] = fixture
            if kind not in models:
                models[kind] = make_model(kind, root/kind, seeds[kind])
            inputs = {"model": str(root/kind), "cache": cache, "eager": eager,
                      "speculative": speculative, "vocab_size": VOCAB,
                      "captures": [4] if kind == "mamba1" else ([3, 6] if speculative else [1, 2]),
                      "max_num_seqs": 4 if kind == "mamba1" else 2,
                      "max_model_len": 192 if kind == "hybrid" else 128,
                      "num_gpu_blocks": 5 if kind == "mamba1" else None,
                      "token_budget": 128 if kind == "hybrid" and cache == "all" else 16,
                      "observe_gpu": True, **fixtures[fixture_key]}
            if kind == "hybrid" and cache == "all":
                inputs["mamba_block_size"] = 16
            config = root/f"{name}.json"
            config.write_text(json.dumps(inputs))
            challenge = LOGS/f"{name}-challenge.json"
            challenge.write_text(json.dumps({"seeds": seeds, "request": inputs}))
            challenge.chmod(0o600)
            config.chmod(0o644)
            output_dir = root/f"{name}-output"
            output_dir.mkdir(mode=0o700)
            os.chown(output_dir, agent.pw_uid, agent.pw_gid)
            output = output_dir/"result.json"
            env = {key: os.environ[key] for key in (
                "PATH", "LD_LIBRARY_PATH", "CUDA_VISIBLE_DEVICES",
                "NVIDIA_VISIBLE_DEVICES", "NVIDIA_DRIVER_CAPABILITIES") if key in os.environ}
            env.update(HOME=agent.pw_dir, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                       PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="2",
                       VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS="0")
            reference_inputs = {**inputs, "eager": True, "speculative": False,
                                "cache": "none", "token_budget": 128, "observe_gpu": False}
            reference_inputs.pop("mamba_block_size", None)
            # Cache only identical trusted workloads; never cache candidate results.
            key = json.dumps({k: v for k, v in reference_inputs.items() if k != "captures"}, sort_keys=True)
            if key not in references:
                ref_config = private/f"{name}.json"
                ref_output = private/f"{name}-result.json"
                ref_config.write_text(json.dumps(reference_inputs))
                ref_env = {**env, "HOME": "/root", "PYTHONPATH": str(reference_repo)}
                execute([sys.executable, "-I", str(worker), str(ref_config), str(ref_output),
                         str(reference_repo)], ref_env, name+"-reference")
                references[key] = json.loads(ref_output.read_text())["batches"]
            reference = references[key]
            env["PYTHONPATH"] = "/workspace/repo"
            command = ["/usr/bin/setpriv", f"--reuid={agent.pw_uid}", f"--regid={agent.pw_gid}",
                       "--clear-groups", "--no-new-privs", str(worker.with_name("observe_cuda_graph")),
                       sys.executable, "-I", str(worker), str(config), str(output)]
            observation = LOGS/f"{name}-observation.json"
            code = execute(command, env, name, observation)
            observed = json.loads(observation.read_text())
            if observed["child_exit"] != 0 or observed["armed"] != 1 or observed["finished"] != 1:
                raise RuntimeError(f"{name}: incomplete independently observed execution")
            if not output.exists():
                raise RuntimeError(f"{name}: child exited before producing results")
            fd = os.open(output, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd) as handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > 4_000_000:
                    raise RuntimeError(f"{name}: invalid result artifact")
                actual = json.load(handle)
            vectors, delta = compare(actual, reference, ATOL[kind])
            if not eager and (type(observed["graph_launches"]) is not int or observed["graph_launches"] <= 0):
                raise ValueError(f"{name}: no CUDA graph execution observed")
            if speculative and (type(actual["accepted_tokens"]) is not int or actual["accepted_tokens"] <= 0):
                raise ValueError(f"{name}: no accepted draft tokens exercised")
            record = {"case": name, "vectors": vectors, "max_error": delta,
                      "seconds": round(time.monotonic()-start, 2), "exit_code": code, "graph_launches": observed["graph_launches"],
                      "accepted_tokens": actual["accepted_tokens"], "cached_tokens": actual["cached_tokens"]}
            records.append(record)
            (LOGS/"progress.json").write_text(json.dumps(records, indent=2))
            print(json.dumps(record), flush=True)
    return {"cases": records, "reference": "frozen Base non-speculative eager GPU serving in a root-only reference process"}


def main() -> None:
    os.umask(0o077)
    save_reward(0, {"status": "started"})
    try:
        payload = run()
    except BaseException as exc:
        save_reward(0, {"error": f"{type(exc).__name__}: {exc}"})
        print(f"FAIL: {type(exc).__name__}: {exc}", flush=True)
    else:
        save_reward(1, payload)


if __name__ == "__main__":
    main()
