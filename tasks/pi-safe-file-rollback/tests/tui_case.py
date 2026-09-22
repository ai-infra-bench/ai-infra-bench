"""Exercise the real terminal command surface; no TUI implementation imports."""
import errno
import fcntl
import os
import pty
import select
import signal
import struct
import subprocess
import termios
import time


def run(f):
    peer = f.peer()
    peer.require_api()
    f.mutation(peer, 'tui-discard')
    checkpoint = peer.list()[0]['id']
    peer.kill()
    peer.close()
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 50, 160, 0, 0))
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': str(f.home), 'TERM': 'xterm-256color',
           'PI_CODING_AGENT_DIR': str(f.agent_dir), 'PI_OFFLINE': '1', 'PI_TELEMETRY': '0',
           'PI_NO_LOCAL_LLM': '1', 'CI': '1', 'NO_PROXY': '127.0.0.1,localhost'}

    def drop():
        os.setsid()
        fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
        os.setgroups([])
        os.setgid(65534)
        os.setuid(65534)

    argv = [f.runner.node, str(f.runner.pi / 'packages/coding-agent/dist/cli.js'),
            '--provider', 'rollback-test', '--model', 'rollback-model', '--thinking', 'off',
            '--session', str(f.session_file), '--no-extensions', '--no-skills',
            '--no-prompt-templates', '--no-context-files']
    proc = subprocess.Popen(argv, cwd=f.project, env=env, stdin=slave, stdout=slave,
                            stderr=slave, preexec_fn=drop)
    os.close(slave)
    transcript = bytearray()

    def read_until(predicate, description, seconds=35):
        deadline = time.monotonic() + seconds
        while not predicate():
            if time.monotonic() >= deadline or proc.poll() is not None:
                raise AssertionError('TUI ' + description + ': ' + bytes(transcript[-4000:]).decode(errors='replace'))
            if select.select([master], [], [], min(.2, deadline-time.monotonic()))[0]:
                try:
                    data = os.read(master, 65536)
                except OSError as error:
                    if error.errno == errno.EIO:
                        raise AssertionError('TUI exited before ' + description) from error
                    raise
                transcript.extend(data)
                # Answer ordinary terminal capability/cursor probes.
                if b'\x1b[6n' in data:
                    os.write(master, b'\x1b[1;1R')
                if b'\x1b[c' in data or b'\x1b[0c' in data:
                    os.write(master, b'\x1b[?1;2c')

    def submit(text):
        os.write(master, b'\x1b[200~' + text.encode() + b'\x1b[201~\r')

    try:
        # The saved response is rendered only after startup has installed input
        # handlers; an early footer alone is not a readiness signal.
        read_until(lambda: b'completed-tui-discard' in transcript, 'resumed conversation rendering')
        submit('/rollback')
        read_until(lambda: checkpoint.encode() in transcript, 'checkpoint listing')
        submit('/rollback ' + checkpoint)
        read_until(lambda: all(__import__('verify').file_state(f.project / name) == state
                               for name, state in f.baseline.items())
                           and not (f.project / 'created.txt').exists()
                           and not (f.project / 'constructor').exists()
                           and not (f.project / 'renamed.txt').exists(), 'file restoration')
        submit('/quit')
        proc.wait(timeout=15)
        if proc.returncode != 0:
            raise AssertionError('TUI exited with ' + str(proc.returncode))
        f.assert_baseline(['created.txt', 'constructor', 'renamed.txt'])
        resumed = f.peer(enable=None)
        if resumed.state()['status'] != 'ready':
            raise AssertionError('TUI rollback did not persist ready state')
        if 'tui-discard-' + f.nonce in __import__('json').dumps(resumed.call('inspect')['messages']):
            raise AssertionError('TUI rollback retained discarded conversation')
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=10)
        os.close(master)
        (f.runner.output / 'tui-transcript.txt').write_bytes(transcript)
