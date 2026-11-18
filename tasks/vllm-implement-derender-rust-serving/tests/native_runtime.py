"""Run only the candidate ELF, its native libraries and model metadata.

This verifier-side boundary leaves the development image and Python HTTP
client intact. The server cannot import/exec the Python reference or connect
to a helper service outside its runtime. It may accept normal HTTP requests.
"""
from __future__ import annotations

import ctypes
import errno
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def prepare(root: Path, binary: str, model: Path) -> Path:
    runtime = root / "native-runtime"
    runtime.mkdir()
    executable = Path(binary).resolve()
    with executable.open("rb") as stream:
        assert stream.read(4) == b"\x7fELF", "Rust serving requires a native executable"
    paths = [executable]
    result = subprocess.run(["ldd", str(executable)], capture_output=True, text=True)
    if result.returncode:
        assert "not a dynamic executable" in result.stdout + result.stderr, result.stderr
    else:
        assert "not found" not in result.stdout, result.stdout
        paths.extend(Path(p) for p in re.findall(r"(/[^\s()]+)", result.stdout))
    for source in paths:
        target = runtime / ("bin/vllm-rs" if source == executable else str(source).lstrip("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o555)
    for name in ("config.json", "tokenizer.json", "tokenizer_config.json", "chat_template.jinja"):
        target = runtime / str(model).lstrip("/") / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(model / name, target)
        target.chmod(0o444)
    (runtime / "tmp").mkdir(mode=0o777)
    (runtime / "tmp").chmod(0o777)
    return runtime


def enter(runtime: str, argv: list[str]) -> None:
    # Load the trusted filter implementation before removing access to the
    # development filesystem. The filter survives exec and child processes.
    seccomp = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    seccomp.seccomp_init.argtypes = [ctypes.c_uint32]
    seccomp.seccomp_init.restype = ctypes.c_void_p
    seccomp.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    seccomp.seccomp_syscall_resolve_name.restype = ctypes.c_int
    seccomp.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    seccomp.seccomp_load.argtypes = [ctypes.c_void_p]
    seccomp.seccomp_release.argtypes = [ctypes.c_void_p]
    libc = ctypes.CDLL(None, use_errno=True)
    os.chroot(runtime)
    os.chdir("/")
    os.setgroups([])
    os.setgid(65534)
    os.setuid(65534)
    assert libc.prctl(38, 1, 0, 0, 0) == 0, "cannot set no_new_privs"
    context = seccomp.seccomp_init(0x7FFF0000)  # SCMP_ACT_ALLOW
    assert context, "cannot initialize native runtime filter"
    try:
        syscall = seccomp.seccomp_syscall_resolve_name(b"connect")
        assert syscall >= 0
        assert seccomp.seccomp_rule_add(context, 0x00050000 | errno.EPERM, syscall, 0) == 0
        assert seccomp.seccomp_load(context) == 0, "cannot enforce no forwarding"
    finally:
        seccomp.seccomp_release(context)
    os.execv("/bin/vllm-rs", ["/bin/vllm-rs", *argv])


if __name__ == "__main__":
    enter(sys.argv[1], sys.argv[2:])
