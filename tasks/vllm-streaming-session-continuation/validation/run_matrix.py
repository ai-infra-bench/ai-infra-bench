"""Run isolated full-entrypoint controls on the pinned task image."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import queue
import subprocess
import time
import uuid


def executable_hashes(task):
    files = [task / "instruction.md", task / "task.toml"]
    for directory in ("tests", "solution", "environment"):
        files.extend(path for path in (task / directory).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts)
    files.extend((task / "validation").glob("*.patch"))
    files.append(task / "validation/ci-cases.json")
    files.extend((task / "validation").glob("*.py"))
    return {str(path.relative_to(task)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(files)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--devices", default="6,7")
    parser.add_argument("--cases", default="all")
    args = parser.parse_args()
    task = Path(__file__).resolve().parents[1]
    image = json.loads((task / "environment/image-manifest.json").read_text())["image_id"]
    image_id = subprocess.check_output(["docker", "image", "inspect", image,
                                        "--format", "{{.Id}}"], text=True).strip()
    cases = [{"name": "base", "expected_reward": 0}, {"name": "oracle", "expected_reward": 1}]
    cases += json.loads((task / "validation/ci-cases.json").read_text())["cases"]
    if args.cases != "all":
        selected = set(args.cases.split(","))
        cases = [case for case in cases if case["name"] in selected]
        assert {case["name"] for case in cases} == selected
    assert not args.output.exists(), "use a fresh evidence directory"
    args.output.mkdir(parents=True)
    before = executable_hashes(task)
    devices = queue.Queue()
    for device in args.devices.split(","):
        devices.put(device)
    cpu_cases = {"constant-output", "forged-complete-report", "early-os-exit", "early-system-exit"}

    def run(case):
        name = case["name"]
        device = None if name in cpu_cases else devices.get()
        destination = args.output / name
        destination.mkdir()
        container = "stream-check-" + uuid.uuid4().hex[:12]
        command = ["docker", "run", "--rm", "--init", "--name", container,
                   "--network", "none", "--cpus", "8", "--memory", "64g",
                   "--shm-size", "2g", "--user", "root"]
        if device is None:
            command += ["--runtime", "runc", "--env", "NVIDIA_VISIBLE_DEVICES=void"]
        else:
            command += ["--gpus", "device=" + device]
        command += ["--mount", f"type=bind,src={task / 'tests'},dst=/tests,readonly",
                    "--mount", f"type=bind,src={destination},dst=/logs/verifier"]
        script = "bash /tests/test.sh"
        if name != "base":
            patch = task / ("solution/oracle.patch" if name == "oracle"
                            else "validation/" + case["patch"])
            command += ["--mount", f"type=bind,src={patch},dst=/candidate.patch,readonly"]
            script = "git apply --check /candidate.patch && git apply /candidate.patch && " + script
        command += [image, "bash", "-c", script]
        started = time.monotonic()
        try:
            with (destination / "entrypoint.log").open("w") as output:
                execution = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT,
                                           timeout=1170, check=False)
            reward_path = destination / "reward.txt"
            reward = int(reward_path.read_text().strip()) if reward_path.exists() else None
            report_path = destination / "report.json"
            report = json.loads(report_path.read_text()) if report_path.exists() else {}
            result = {"name": name, "expected_reward": case["expected_reward"], "reward": reward,
                      "exit_code": execution.returncode, "seconds": round(time.monotonic() - started, 2),
                      "gpu": device, "report": report, "command": command}
        finally:
            subprocess.run(["docker", "rm", "-f", container], capture_output=True, check=False)
            if device is not None:
                devices.put(device)
        (destination / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({key: result[key] for key in ("name", "reward", "expected_reward", "seconds")}), flush=True)
        return result

    results = []
    with ThreadPoolExecutor(max_workers=len(args.devices.split(",")) + 1) as pool:
        pending = [pool.submit(run, case) for case in cases]
        for future in as_completed(pending):
            results.append(future.result())
    unchanged = before == executable_hashes(task)
    success = unchanged and all(item["reward"] == item["expected_reward"] and item["exit_code"] == 0
                                for item in results)
    summary = {"image_id": image_id, "hashes": before, "executables_unchanged": unchanged,
               "all_expected": success, "results": results}
    (args.output / "matrix.json").write_text(json.dumps(summary, indent=2) + "\n")
    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    main()
