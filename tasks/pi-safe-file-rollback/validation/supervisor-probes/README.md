# Process supervisor validation

`summary.json` records hashes and results for `process_supervisor.py` and the
independent probe. The 33 executions passed: 11 scenarios repeated three times.
They use actual Node worker threads, Bash/Python subprocesses, and the ordinary
Linux filesystem. No Pi solution, private recovery hook, model API or compiler is
used by these probes.

A SIGKILL may race a ptrace query after a stop is reported; ESRCH is
treated only as a pending exit, with the PID retained until waitpid confirms its
termination. Other ptrace errors remain failures.

The root probe parent launches the supervisor and candidate as UID/GID 65534.
Docker uses its default seccomp profile, without extra capabilities or privileged
mode. The retained task image is identified by digest in `summary.json`.

Covered mutations include direct writes, temporary-file rename replacement,
permission changes, deletion, creation, and shared-memory-mapped writes. Process
coverage includes Node threads, fork, vfork, exec, explicit tree termination, and
arming before candidate startup. Competing ordinary filesystem mutations are
held at syscall entry; after the first observed workspace change, no following
held mutator is released. Every probe independently checks the untouched file
and confirms all observed process/thread IDs are gone.

Observation is based on explicitly enumerated public workspace fixture paths,
their bytes, existence and permissions. It does not prescribe the candidate's
checkpoint layout, file restoration order, or storage algorithm. Mapped writes
are also observed at subsequent kernel boundaries. This validates the exercised
local filesystem mechanisms, not every possible kernel or storage backend.

The supervisor does not award a score. The scoring parent must separately verify
the actual candidate RPC outputs, restored workspace and session behavior. In
particular, it must not reject an implementation merely because an atomic
operation exposes several restored paths together.

To reproduce, mount this directory and the supervisor read-only in the image,
then run `python3 probe.py /path/to/process_supervisor.py --repeat 3`. The command
must run as root so the probe can launch its unprivileged children. No repository
files are modified by the probes; their workspaces are temporary directories.
