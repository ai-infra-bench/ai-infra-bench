"""Launch trusted verifier code without site initialization or candidate paths.

Invoke with python3 -I -S. Add installed dependency directories directly;
never execute .pth files, sitecustomize, usercustomize, or editable finders.
Candidate imports belong only in explicitly unprivileged workers.
"""
import os
from pathlib import Path
import runpy
import sys
import sysconfig

if not sys.flags.isolated or not sys.flags.no_site:
    raise RuntimeError('trusted Python requires -I -S')
version = f'{sys.version_info.major}.{sys.version_info.minor}'
paths = [sysconfig.get_path('purelib'), sysconfig.get_path('platlib'),
         f'/usr/local/lib/python{version}/dist-packages',
         '/usr/lib/python3/dist-packages']
for entry in paths:
    if not entry or entry in sys.path or not Path(entry).is_dir():
        continue
    path = Path(entry).resolve()
    for directory in (path, *path.parents):
        metadata = directory.stat()
        if metadata.st_uid != 0 or metadata.st_mode & 0o022:
            raise RuntimeError(f'untrusted dependency directory: {directory}')
    sys.path.append(str(path))

if len(sys.argv) < 2:
    raise RuntimeError('missing trusted program')
program = sys.argv[1]
sys.argv = sys.argv[1:]
if program == '-c':
    code = sys.argv[1]
    sys.argv = ['-c', *sys.argv[2:]]
    exec(compile(code, '<trusted-command>', 'exec'), {'__name__': '__main__'})
elif program == '-':
    exec(compile(sys.stdin.read(), '<trusted-stdin>', 'exec'), {'__name__': '__main__'})
else:
    runpy.run_path(program, run_name='__main__')
