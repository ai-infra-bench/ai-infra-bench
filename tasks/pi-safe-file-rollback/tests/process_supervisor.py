#!/usr/bin/env python3
"""Linux/amd64 ptrace process-tree supervisor; no candidate-specific hooks.

This is a JSON-lines subprocess service, not a grader.  The scoring parent must
independently check candidate RPC responses and workspace/session results.

Commands (all accept an opaque ``id`` and receive a ``type=reply`` response):
  start: argv=[...], cwd=absolute_path, env={optional overrides}, arm=optional
         arm uses the normal arm arguments and is installed before candidate exec
  stdin: data=string (written verbatim to the candidate's standard input)
  close_stdin
  arm: workspace=absolute_path, paths=[relative eligible file paths], tag=optional
  disarm / status / kill / shutdown

Unsolicited events: output(stream,data), trace(event,pid,child_pid), process_exit,
execution_done, and trigger.  ``arm`` snapshots public filesystem state.  The
first subsequent observable content/existence/permission change at a traced
filesystem syscall boundary causes SIGKILL of the complete execution tree.
The trigger records only filesystem observations, not candidate private data.

Run the supervisor and candidate with the same unprivileged UID. A root scoring
parent can launch this script with --uid 1000 --gid 1000. No ptrace capability or
Docker seccomp override is needed when the kernel permits tracing one's child.
Requires Linux >= 5.3 (PTRACE_GET_SYSCALL_INFO), amd64, and Python's standard lib.
"""

from __future__ import annotations

import argparse
import codecs
import collections
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import platform
import selectors
import signal
import stat
import struct
import sys


PTRACE_TRACEME = 0
PTRACE_SYSCALL = 24
PTRACE_SETOPTIONS = 0x4200
PTRACE_GETEVENTMSG = 0x4201
PTRACE_GET_SYSCALL_INFO = 0x420E
OPTIONS = 1 | 2 | 4 | 8 | 16 | 0x100000  # SYSGOOD, FORK/VFORK/CLONE/EXEC, EXITKILL
WAIT_ALL = 0x40000000
EVENT_NAMES = {1: "fork", 2: "vfork", 3: "clone", 4: "exec"}

LIBC = ctypes.CDLL(None, use_errno=True)
LIBC.ptrace.restype = ctypes.c_long
LIBC.ptrace.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]


def ptrace(request: int, pid: int = 0, address=0, data=0) -> int:
    ctypes.set_errno(0)
    result = LIBC.ptrace(request, pid, ctypes.c_void_p(address), ctypes.c_void_p(data))
    if result == -1:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number))
    return result


def emit(value: dict) -> None:
    sys.stdout.write(json.dumps(value, separators=(",", ":"), ensure_ascii=False) + "\n")
    sys.stdout.flush()


def syscall_info(pid: int) -> tuple[int, int | None, tuple[int, ...]]:
    data = ctypes.create_string_buffer(88)
    size = ptrace(PTRACE_GET_SYSCALL_INFO, pid, ctypes.sizeof(data), ctypes.addressof(data))
    if size < 24:
        raise RuntimeError("kernel did not supply PTRACE_GET_SYSCALL_INFO")
    kind = data.raw[0]
    if kind == 1:
        fields = struct.unpack_from("=7Q", data.raw, 24)
        return kind, fields[0], fields[1:]
    return kind, None, ()


def event_message(pid: int) -> int:
    result = ctypes.c_ulong()
    ptrace(PTRACE_GETEVENTMSG, pid, 0, ctypes.addressof(result))
    return result.value


def regular_fd(pid: int, fd: int) -> bool:
    try:
        return stat.S_ISREG(os.stat(f"/proc/{pid}/fd/{fd}").st_mode)
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return False


# All ordinary local filesystem mutation mechanisms used by direct writes,
# rename-based replacement, Python/Node fs APIs, and git subprocesses. Pipe and
# socket writes are deliberately excluded: holding those can deadlock IPC.
FD_MUTATORS = {
    1: 0, 18: 0, 20: 0, 40: 0, 74: 0, 75: 0, 77: 0,
    91: 0, 93: 0, 275: 2, 285: 0, 296: 0, 326: 2, 328: 0,
}
PATH_MUTATORS = {
    76, 82, 83, 84, 85, 86, 87, 88, 90, 92, 94, 132, 133,
    188, 189, 191, 192, 197, 198, 235,
    258, 259, 260, 261, 263, 264, 265, 266, 268, 280, 316,
}
SYSCALL_NAMES = {
    1: "write", 2: "open", 9: "mmap", 18: "pwrite64", 20: "writev",
    40: "sendfile", 74: "fsync", 75: "fdatasync", 76: "truncate",
    77: "ftruncate", 82: "rename", 83: "mkdir", 84: "rmdir", 85: "creat",
    87: "unlink", 90: "chmod", 91: "fchmod", 257: "openat",
    263: "unlinkat", 264: "renameat", 268: "fchmodat", 275: "splice",
    296: "pwritev", 316: "renameat2", 326: "copy_file_range",
    328: "pwritev2", 437: "openat2",
}


def mutating_syscall(pid: int, nr: int, args: tuple[int, ...]) -> bool:
    if nr in FD_MUTATORS:
        return regular_fd(pid, args[FD_MUTATORS[nr]])
    if nr in PATH_MUTATORS:
        return True
    if nr in (2, 257):
        flags = args[1 if nr == 2 else 2]
        return bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
    if nr == 437:  # openat2; conservative, does not inspect candidate memory.
        return True
    return False


def file_state(path: Path) -> dict:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {"kind": "absent"}
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        return {"kind": "out_of_scope", "mode": stat.S_IMODE(info.st_mode)}
    digest = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        while True:
            data = os.read(fd, 1024 * 1024)
            if not data:
                break
            digest.update(data)
    finally:
        os.close(fd)
    return {"kind": "file", "mode": stat.S_IMODE(info.st_mode),
            "size": info.st_size, "sha256": digest.hexdigest()}


class Supervisor:
    def __init__(self) -> None:
        self.selector = selectors.DefaultSelector()
        os.set_blocking(0, False)
        self.selector.register(0, selectors.EVENT_READ, ("control", None))
        self.wakeup_read, self.wakeup_write = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
        signal.set_wakeup_fd(self.wakeup_write)
        signal.signal(signal.SIGCHLD, lambda *_: None)
        self.selector.register(self.wakeup_read, selectors.EVENT_READ, ("signal", None))
        # Reap descendants even when their immediate candidate parent dies first.
        if LIBC.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
            raise OSError(ctypes.get_errno(), "cannot become child subreaper")
        self.control_buffer = b""
        self.tracees: set[int] = set()
        self.leader: int | None = None
        self.child_stdin: int | None = None
        self.stdin_buffer = bytearray()
        self.close_stdin_pending = False
        self.output_fds: dict[int, tuple[str, object]] = {}
        self.syscalls: dict[int, tuple[int, tuple[int, ...], bool]] = {}
        self.active_mutator: int | None = None
        self.unmediated_writes_possible = False
        self.pending_mutators: collections.deque[int] = collections.deque()
        self.armed: dict | None = None
        self.killing = False
        self.shutdown_requested = False
        self.done_sent = True
        self.stats = {"syscall_stops": 0, "fork": 0, "vfork": 0,
                      "clone": 0, "exec": 0, "max_tracees": 0,
                      "mutator_entries": 0, "serialized_waits": 0,
                      "ptrace_exit_races": 0}

    def resume(self, pid: int, sig: int = 0) -> None:
        if self.killing:
            self.kill_pid(pid)
            return
        try:
            ptrace(PTRACE_SYSCALL, pid, 0, sig)
        except OSError as error:
            if error.errno != errno.ESRCH:
                raise

    @staticmethod
    def kill_pid(pid: int) -> None:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def kill_all(self, reason: str) -> None:
        if not self.tracees:
            return
        self.killing = True
        # The candidate starts a fresh session. This also catches a just-forked
        # child whose ptrace fork event has not yet been consumed by this loop.
        if self.leader is not None:
            try:
                os.killpg(self.leader, signal.SIGKILL)
            except ProcessLookupError:
                pass
        for pid in tuple(self.tracees):
            self.kill_pid(pid)
        emit({"type": "kill_requested", "reason": reason,
              "pids": sorted(self.tracees)})

    def close_fd(self, fd: int) -> None:
        try:
            self.selector.unregister(fd)
        except KeyError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass

    def start(self, command: dict) -> dict:
        if self.tracees:
            raise ValueError("execution is already running")
        argv = command.get("argv")
        cwd = command.get("cwd")
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
            raise ValueError("argv must be a nonempty string array")
        if not isinstance(cwd, str) or not os.path.isabs(cwd):
            raise ValueError("cwd must be absolute")
        if self.child_stdin is not None:
            self.close_fd(self.child_stdin)
            self.child_stdin = None
        self.stdin_buffer.clear()
        self.close_stdin_pending = False
        self.armed = None
        self.active_mutator = None
        self.unmediated_writes_possible = False
        self.pending_mutators.clear()
        self.syscalls.clear()
        self.killing = False
        self.done_sent = False
        env = dict(os.environ)
        env.update(command.get("env", {}))
        stdin_read, stdin_write = os.pipe()
        stdout_read, stdout_write = os.pipe()
        stderr_read, stderr_write = os.pipe()
        pid = os.fork()
        if pid == 0:
            try:
                os.setsid()
                os.dup2(stdin_read, 0)
                os.dup2(stdout_write, 1)
                os.dup2(stderr_write, 2)
                os.closerange(3, 65536)
                os.chdir(cwd)
                ptrace(PTRACE_TRACEME)
                os.kill(os.getpid(), signal.SIGSTOP)
                os.execvpe(argv[0], argv, env)
            except BaseException as error:
                os.write(2, ("supervised exec failed: " + repr(error) + "\n").encode())
                os._exit(127)
        os.close(stdin_read)
        os.close(stdout_write)
        os.close(stderr_write)
        self.child_stdin = stdin_write
        os.set_blocking(stdin_write, False)
        self.leader = pid
        self.tracees.add(pid)
        for fd, stream in ((stdout_read, "stdout"), (stderr_read, "stderr")):
            os.set_blocking(fd, False)
            self.output_fds[fd] = (stream, codecs.getincrementaldecoder("utf-8")("replace"))
            self.selector.register(fd, selectors.EVENT_READ, ("output", None))
        child, status = os.waitpid(pid, 0)
        if child != pid or not os.WIFSTOPPED(status):
            self.tracees.discard(pid)
            raise RuntimeError(f"candidate failed before ptrace initial stop: {status}")
        ptrace(PTRACE_SETOPTIONS, pid, 0, OPTIONS)
        if command.get("arm") is not None:
            try:
                self.arm(command["arm"])
            except Exception:
                self.kill_all("invalid_start_arm")
                raise
        self.resume(pid)
        return {"pid": pid, "uid": os.getuid(), "gid": os.getgid()}

    def arm(self, command: dict) -> dict:
        if not self.tracees or self.killing:
            raise ValueError("no live execution to arm")
        workspace = Path(command["workspace"])
        paths = command.get("paths")
        if not workspace.is_absolute() or not workspace.is_dir():
            raise ValueError("workspace must be an existing absolute directory")
        if not isinstance(paths, list) or not paths or not all(isinstance(p, str) for p in paths):
            raise ValueError("paths must enumerate nonempty workspace-relative eligible paths")
        for path in paths:
            parts = Path(path).parts
            if not parts or Path(path).is_absolute() or ".." in parts or parts[0] == ".git":
                raise ValueError(f"invalid observed path: {path!r}")
        unique = sorted(set(paths))
        baseline = {p: file_state(workspace / p) for p in unique}
        if any(s["kind"] == "out_of_scope" for s in baseline.values()):
            raise ValueError("observed paths must be regular files or absent")
        self.armed = {"workspace": workspace, "paths": unique,
                      "baseline": baseline, "tag": command.get("tag", command.get("id"))}
        return {"tag": self.armed["tag"], "baseline": baseline}

    def observe(self, pid: int, nr: int, boundary: str = "syscall_exit") -> bool:
        if self.armed is None or self.killing:
            return False
        current = {p: file_state(self.armed["workspace"] / p) for p in self.armed["paths"]}
        changed = [p for p in self.armed["paths"] if current[p] != self.armed["baseline"][p]]
        if not changed:
            return False
        event = {"type": "trigger", "reason": "workspace_changed", "pid": pid,
                 "boundary": boundary, "syscall_number": nr,
                 "syscall": SYSCALL_NAMES.get(nr, str(nr)), "tag": self.armed["tag"],
                 "changed": changed,
                 "before": {p: self.armed["baseline"][p] for p in changed},
                 "after": {p: current[p] for p in changed}, "stats": dict(self.stats)}
        self.armed = None
        # No next filesystem mutator is released before the complete tree kill.
        self.kill_all("workspace_changed")
        emit(event)
        return True

    def release_waiter(self) -> None:
        if self.killing or self.active_mutator is not None:
            return
        while self.pending_mutators:
            pid = self.pending_mutators.popleft()
            if pid in self.tracees:
                self.active_mutator = pid
                self.resume(pid)
                return

    def handle_stop(self, pid: int, status: int) -> None:
        self.tracees.add(pid)
        self.stats["max_tracees"] = max(self.stats["max_tracees"], len(self.tracees))
        sig = os.WSTOPSIG(status)
        event = status >> 16
        if event in EVENT_NAMES:
            name = EVENT_NAMES[event]
            other = event_message(pid)
            self.stats[name] += 1
            if event in (1, 2, 3):
                self.tracees.add(other)
                self.stats["max_tracees"] = max(self.stats["max_tracees"], len(self.tracees))
                if self.killing:
                    self.kill_pid(other)
            elif event == 4 and other != pid:
                self.tracees.discard(other)
                self.syscalls.pop(other, None)
            emit({"type": "trace", "event": name, "pid": pid, "child_pid": other})
            self.resume(pid)
            return
        if self.killing:
            self.kill_pid(pid)
            return
        if sig == (signal.SIGTRAP | 0x80):
            self.stats["syscall_stops"] += 1
            kind, nr, args = syscall_info(pid)
            if kind == 1:
                # Mapped stores and io_uring may change a file outside a write
                # syscall. Once such a mechanism is used, observe at every
                # subsequent kernel boundary as well. A single operation may
                # atomically expose multiple files; that is not a failure.
                if nr == 9 and args[2] & 2 and args[3] & 1 and regular_fd(pid, args[4]):
                    self.unmediated_writes_possible = True
                elif nr in (425, 426, 427):
                    self.unmediated_writes_possible = True
                if self.unmediated_writes_possible and self.observe(pid, nr, "syscall_entry"):
                    return
                mutation = self.armed is not None and mutating_syscall(pid, nr, args)
                self.syscalls[pid] = (nr, args, mutation)
                if mutation:
                    self.stats["mutator_entries"] += 1
                    if self.active_mutator is None:
                        self.active_mutator = pid
                    else:
                        self.pending_mutators.append(pid)
                        self.stats["serialized_waits"] += 1
                        return
            elif kind == 2:
                previous = self.syscalls.pop(pid, None)
                if previous and previous[2]:
                    if self.active_mutator == pid:
                        self.active_mutator = None
                    if self.observe(pid, previous[0]):
                        return
                    self.release_waiter()
                elif previous and self.unmediated_writes_possible and self.observe(pid, previous[0]):
                    return
            self.resume(pid)
            return
        # Newly auto-attached fork/clone children initially stop with SIGSTOP.
        self.resume(pid, 0 if sig in (signal.SIGSTOP, signal.SIGTRAP) else sig)

    def reap(self) -> None:
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG | WAIT_ALL)
            except ChildProcessError:
                break
            if pid == 0:
                break
            if os.WIFSTOPPED(status):
                try:
                    self.handle_stop(pid, status)
                except OSError as error:
                    if error.errno != errno.ESRCH:
                        raise
                    # SIGKILL can win after waitpid reports a ptrace stop but
                    # before GET_SYSCALL_INFO/GETEVENTMSG reads that stop. An
                    # ESRCH is not an exit notification: retain the tracee and
                    # any mutator ownership until its real waitpid exit status
                    # is reaped. In particular, do not release another writer
                    # merely because a ptrace query raced process cancellation.
                    self.stats["ptrace_exit_races"] += 1
            elif os.WIFEXITED(status) or os.WIFSIGNALED(status):
                self.tracees.discard(pid)
                self.syscalls.pop(pid, None)
                if self.active_mutator == pid:
                    self.active_mutator = None
                    self.release_waiter()
                emit({"type": "process_exit", "pid": pid,
                      "exit_code": os.WEXITSTATUS(status) if os.WIFEXITED(status) else None,
                      "signal": os.WTERMSIG(status) if os.WIFSIGNALED(status) else None})
        if not self.tracees and not self.done_sent:
            self.done_sent = True
            self.armed = None
            emit({"type": "execution_done", "pid": self.leader,
                  "killed": self.killing, "stats": dict(self.stats)})

    def flush_stdin(self) -> None:
        if self.child_stdin is None:
            return
        try:
            if self.stdin_buffer:
                written = os.write(self.child_stdin, self.stdin_buffer)
                del self.stdin_buffer[:written]
        except BlockingIOError:
            return
        except BrokenPipeError:
            self.stdin_buffer.clear()
            self.close_stdin_pending = True
        if not self.stdin_buffer:
            try:
                self.selector.unregister(self.child_stdin)
            except KeyError:
                pass
            if self.close_stdin_pending:
                self.close_fd(self.child_stdin)
                self.child_stdin = None

    def dispatch(self, command: dict) -> None:
        ident = command.get("id")
        try:
            op = command["op"]
            if op == "start":
                result = self.start(command)
            elif op == "stdin":
                if self.child_stdin is None or self.close_stdin_pending:
                    raise ValueError("candidate stdin is closed")
                data = command["data"].encode("utf-8")
                if len(self.stdin_buffer) + len(data) > 16 * 1024 * 1024:
                    raise ValueError("candidate stdin queue exceeds 16 MiB")
                self.stdin_buffer.extend(data)
                try:
                    self.selector.register(self.child_stdin, selectors.EVENT_WRITE, ("stdin", None))
                except KeyError:
                    pass
                self.flush_stdin()
                result = {"accepted_bytes": len(data)}
            elif op == "close_stdin":
                self.close_stdin_pending = True
                self.flush_stdin()
                result = {}
            elif op == "arm":
                result = self.arm(command)
            elif op == "disarm":
                self.armed = None
                result = {}
            elif op == "status":
                result = {"pids": sorted(self.tracees), "armed": self.armed is not None,
                          "killing": self.killing, "stats": dict(self.stats)}
            elif op in ("kill", "shutdown"):
                self.kill_all(op)
                if op == "shutdown":
                    self.shutdown_requested = True
                result = {}
            else:
                raise ValueError(f"unknown operation: {op}")
            emit({"type": "reply", "id": ident, "ok": True, "result": result})
        except Exception as error:
            emit({"type": "reply", "id": ident, "ok": False,
                  "error": f"{type(error).__name__}: {error}"})

    def read_controls(self) -> None:
        data = os.read(0, 65536)
        if not data:
            self.selector.unregister(0)
            self.shutdown_requested = True
            self.kill_all("control_eof")
            return
        self.control_buffer += data
        while b"\n" in self.control_buffer:
            line, self.control_buffer = self.control_buffer.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                command = json.loads(line)
                if not isinstance(command, dict):
                    raise ValueError("control must be an object")
                self.dispatch(command)
            except (ValueError, UnicodeError) as error:
                emit({"type": "reply", "id": None, "ok": False, "error": str(error)})

    def read_output(self, fd: int) -> None:
        stream, decoder = self.output_fds[fd]
        data = os.read(fd, 65536)
        text = decoder.decode(data, final=not data)
        if text:
            emit({"type": "output", "stream": stream, "data": text})
        if not data:
            del self.output_fds[fd]
            self.close_fd(fd)

    def run(self) -> None:
        emit({"type": "ready", "uid": os.getuid(), "gid": os.getgid(),
              "architecture": platform.machine(), "protocol": 1})
        while not (self.shutdown_requested and not self.tracees):
            self.reap()
            for key, _ in self.selector.select(1.0):
                kind, _ = key.data
                if kind == "control":
                    self.read_controls()
                elif kind == "signal":
                    try:
                        while os.read(self.wakeup_read, 65536):
                            pass
                    except BlockingIOError:
                        pass
                elif kind == "output":
                    self.read_output(key.fd)
                elif kind == "stdin":
                    self.flush_stdin()
                self.reap()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uid", type=int)
    parser.add_argument("--gid", type=int)
    args = parser.parse_args()
    if sys.platform != "linux" or platform.machine() not in ("x86_64", "amd64"):
        raise SystemExit("process_supervisor requires Linux/amd64")
    if args.uid is not None and os.getuid() == 0:
        os.setgroups([])
        os.setgid(args.gid if args.gid is not None else args.uid)
        os.setuid(args.uid)
    elif args.uid is not None and args.uid != os.getuid():
        raise SystemExit("cannot switch requested uid without root")
    supervisor = Supervisor()
    try:
        supervisor.run()
    except BaseException as error:
        emit({"type": "supervisor_error", "error": f"{type(error).__name__}: {error}"})
        supervisor.kill_all("supervisor_error")
        # EXITKILL protects still-traced children when the supervisor exits.
        raise


if __name__ == "__main__":
    main()
