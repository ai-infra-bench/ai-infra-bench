#!/usr/bin/python3
"""Exec boundary: candidate code (pi and its forks) never runs with grader privileges."""
import ctypes
import os
import signal
import sys

NODE_UID = NODE_GID = 1000


def main():
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        raise OSError(ctypes.get_errno(), "PR_SET_NO_NEW_PRIVS")
    os.setgroups([])
    os.setgid(NODE_GID)
    os.setuid(NODE_UID)
    os.umask(0o022)
    if sys.argv[1] == "--kill":
        # A privileged kill on a candidate-reported PID could hit anything; kill as node.
        try:
            os.kill(int(sys.argv[2]), signal.SIGKILL)
        except ProcessLookupError:
            pass
        return
    os.execve(sys.argv[1], sys.argv[1:], os.environ)


if __name__ == "__main__":
    main()
