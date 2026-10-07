#!/usr/bin/python3
"""Trusted exec boundary. No candidate imports execute with grader privileges."""
import ctypes
import os
import signal
import sys


def main():
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        raise OSError(ctypes.get_errno(), "PR_SET_NO_NEW_PRIVS")
    os.setgroups([])
    os.setgid(60000)
    os.setuid(60000)
    os.umask(0o077)
    if sys.argv[1] == "--kill":
        try:
            os.kill(int(sys.argv[2]), signal.SIGKILL)
        except ProcessLookupError:
            pass
        return
    os.execve(sys.argv[1], sys.argv[1:], os.environ)


if __name__ == "__main__":
    main()
