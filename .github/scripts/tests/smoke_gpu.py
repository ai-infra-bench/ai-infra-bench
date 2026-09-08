#!/usr/bin/env python3
"""Run real Harbor/CUDA smoke jobs against a configured pool (explicit opt-in)."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import time

SCRIPTS = Path(__file__).resolve().parents[1]


def run_one(root, image, count, index):
    task = root / f"task-{index}-{count}gpu"
    (task / "tests").mkdir(parents=True)
    (task / "environment").mkdir()
    (task / "instruction.md").write_text("Verify that the assigned CUDA devices can execute tensor operations.\n")
    (task / "task.toml").write_text(
        'version = "1.0"\n[environment]\n'
        f'docker_image = {json.dumps(image)}\ngpus = {count}\n'
        'workdir = "/tmp"\n[verifier]\ntimeout_sec = 180\n'
        '[agent]\ntimeout_sec = 30\n'
    )
    (task / "tests" / "test.sh").write_text(
        "#!/bin/bash\nset -euo pipefail\npython3 - <<'PY'\n"
        "import json,subprocess,time,torch\n"
        f"assert torch.cuda.device_count() == {count}\n"
        "started = time.time()\n"
        f"for index in range({count}):\n"
        "    x = torch.ones(1024, device=f'cuda:{index}')\n"
        "    assert x.sum().item() == 1024\n"
        "time.sleep(3)\n"
        "uuids = subprocess.check_output(['nvidia-smi','--query-gpu=uuid','--format=csv,noheader'],text=True).splitlines()\n"
        "with open('/logs/verifier/gpu-evidence.json','w') as f:\n"
        "    json.dump({'gpu_uuids':uuids,'started':started,'finished':time.time()},f)\n"
        "PY\nprintf '1' > /logs/verifier/reward.txt\n"
    )
    env = dict(os.environ, PYTHONPATH=f"{SCRIPTS}:{os.environ.get('PYTHONPATH', '')}")
    command = [
        sys.executable, str(SCRIPTS / "gpu_pool.py"), "--count", str(count), "--",
        "harbor", "run", "--path", str(task), "--agent", "nop",
        "--env", "ci_gpu_docker:LeasedGpuDockerEnvironment",
        "--jobs-dir", str(root / "jobs"), "--job-name", f"smoke-{index}-{count}gpu",
        "--n-concurrent", "1", "--cpus", "ignore", "--memory", "ignore", "--delete", "--yes",
    ]
    log = root / f"smoke-{index}-{count}gpu.log"
    with log.open("w") as output:
        result = subprocess.run(command, env=env, stdout=output, stderr=subprocess.STDOUT, timeout=300)
    if result.returncode:
        raise RuntimeError(f"GPU smoke command failed; inspect {log}")
    job = root / "jobs" / f"smoke-{index}-{count}gpu"
    subprocess.run([
        sys.executable, str(SCRIPTS / "task_ci.py"), "check-result",
        "--result", str(job / "result.json"), "--expected-reward", "1",
    ], check=True)
    evidence_paths = list(job.rglob("gpu-evidence.json"))
    if len(evidence_paths) != 1:
        raise RuntimeError(f"expected exactly one CUDA evidence artifact in {job}")
    evidence = json.loads(evidence_paths[0].read_text())
    evidence.update(requested=count, log=str(log))
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Existing local Linux image with Python and CUDA PyTorch")
    parser.add_argument("--counts", default="1,2,4")
    parser.add_argument("--parallel", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    counts = [int(value) for value in args.counts.split(",")]
    args.output.mkdir(parents=True, exist_ok=False)
    with ThreadPoolExecutor(max_workers=len(counts) if args.parallel else 1) as executor:
        futures = [executor.submit(run_one, args.output, args.image, count, index) for index, count in enumerate(counts)]
        evidence = [future.result() for future in futures]
    pool = json.loads(Path(os.environ["AI_INFRA_GPU_POOL_CONFIG"]).read_text())
    for entry in evidence:
        assert len(entry["gpu_uuids"]) == entry["requested"]
        assert set(entry["gpu_uuids"]) <= set(pool["gpu_uuids"])
    if args.parallel and sum(counts) <= len(pool["gpu_uuids"]):
        # All leases must coexist for this test to establish actual concurrency.
        all_devices = [device for entry in evidence for device in entry["gpu_uuids"]]
        assert len(all_devices) == len(set(all_devices)), "parallel jobs reused a GPU"
    (args.output / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
