"""Run the unmodified grading entrypoint in an isolated final-image container.

The source is restored between cases. Only ordinary compiler outputs are reused;
test.sh still rebuilds the native extension from the currently applied sources.
This is a direct grading matrix, separately identified from Harbor runs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--container", required=True)
    p.add_argument("--task", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cases", nargs="*")
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    task = args.task.resolve()
    controls = json.loads((task / "validation/ci-cases.json").read_text())["cases"]
    cases = [dict(name="base", expected_reward=0), dict(name="oracle", expected_reward=1)] + controls
    if args.cases:
        cases = [c for c in cases if c["name"] in args.cases]

    def execute(argv, **kwargs):
        return subprocess.run(argv, check=True, text=True, **kwargs)

    def shell(code, **kwargs):
        return execute(["docker", "exec", args.container, "bash", "-lc", code], **kwargs)

    shell("mkdir -p /tests /solution /logs/verifier /opt/ai-infra-bench/reference-int8")
    execute(["docker", "cp", str(task / "tests") + "/.", args.container + ":/tests"])
    execute(["docker", "cp", str(task / "solution") + "/.", args.container + ":/solution"])
    execute(["docker", "cp", str(task / "validation"), args.container + ":/validation"])
    image = json.loads(subprocess.check_output(["docker", "inspect", args.container]))[0]["Image"]
    records = []
    for case in cases:
        name = case["name"]
        out = args.output / name
        out.mkdir()
        record = dict(case=name, expected_reward=case["expected_reward"], image=image,
                      entrypoint="bash /tests/test.sh", kind="direct-grading",
                      compiler_cache_reused=True, started=time.time())
        try:
            shell("git -c safe.directory=/workspace/repo reset --hard HEAD && "
                  "git -c safe.directory=/workspace/repo clean -fd -- csrc vllm cmake && "
                  "rm -rf /logs/verifier && mkdir /logs/verifier")
            if name == "oracle" or case.get("apply_after") == "oracle":
                shell("runuser -u agent -- bash /solution/solve.sh")
            if "patch" in case:
                patch = "/validation/" + case["patch"]
                execute(["docker", "exec", "-u", "agent", args.container, "git", "apply", "--check", patch])
                execute(["docker", "exec", "-u", "agent", args.container, "git", "apply", patch])
                record["patch_sha256"] = hashlib.sha256((task / "validation" / case["patch"]).read_bytes()).hexdigest()
            with (out / "entrypoint.log").open("w") as log:
                result = subprocess.run(["docker", "exec", args.container, "bash", "/tests/test.sh"],
                                        stdout=log, stderr=subprocess.STDOUT, timeout=3600)
            record["entrypoint_exit"] = result.returncode
            execute(["docker", "cp", args.container + ":/logs/verifier", str(out / "verifier")])
            record["reward"] = float((out / "verifier/reward.txt").read_text().strip())
            record["matched"] = record["reward"] == record["expected_reward"] and result.returncode in (0, 1)
            native_sha = subprocess.check_output(["docker", "exec", args.container, "sha256sum", "/workspace/repo/vllm/_C.abi3.so"], text=True).split()[0]
            record["native_sha256"] = native_sha
            if name in ("oracle", "alternate-native-kernel") and record["reward"] == 1:
                execute(["docker", "cp", args.container + ":/workspace/repo/vllm/_C.abi3.so", str(out / "_C.abi3.so")])
                with (out / "independent-probe.log").open("w") as log:
                    probe = subprocess.run(["docker", "exec", "-u", "agent", args.container,
                                            "python3", "-I", "/work/independent_probe.py"],
                                           stdout=log, stderr=subprocess.STDOUT, timeout=300)
                record["independent_probe_exit"] = probe.returncode
                record["offset_probes"] = []
                for dtype in ("float16", "bfloat16", "float32"):
                    for offset in (0, 1, 3):
                        for mode in ("public", "native"):
                            label = f"offset-{dtype}-{offset}-{mode}"
                            with (out / (label + ".log")).open("w") as log:
                                probe = subprocess.run(["docker", "exec", "-u", "agent", args.container,
                                    "python3", "-I", "/validation/challenge/offset_input_probe.py",
                                    "--dtype", dtype, "--offset", str(offset), "--mode", mode],
                                    stdout=log, stderr=subprocess.STDOUT, timeout=120)
                            record["offset_probes"].append(dict(dtype=dtype, offset=offset,
                                mode=mode, exit_code=probe.returncode, log=label + ".log"))
                record["offset_probe_passed"] = all(p["exit_code"] == 0 for p in record["offset_probes"])
        except Exception as exc:
            record["error"] = repr(exc)
            record["matched"] = False
        record["finished"] = time.time()
        (out / "record.json").write_text(json.dumps(record, indent=2) + "\n")
        records.append(record)
        (args.output / "summary.json").write_text(json.dumps(records, indent=2) + "\n")
        print(json.dumps(record), flush=True)
    if not all(r["matched"] and r.get("offset_probe_passed", True) for r in records):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
