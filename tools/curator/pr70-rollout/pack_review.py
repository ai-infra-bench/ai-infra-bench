"""Package readable rollout evidence; keep large replay snapshots on A100."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile

p = argparse.ArgumentParser()
p.add_argument('round', type=Path)
p.add_argument('archive', type=Path)
a = p.parse_args()
root = a.round.resolve()
secrets = [v for k, v in os.environ.items() if len(v) >= 12 and any(s in k.upper() for s in ('TOKEN', 'API_KEY', 'AUTH_KEY', 'SECRET', 'PASSWORD'))]
records = {}
with tarfile.open(a.archive, 'w:gz') as out:
    for path in sorted(root.rglob('*')):
        if not path.is_file() or 'inputs' in path.relative_to(root).parts:
            continue
        if path.name == 'full-repository.tar.gz' or path.suffix == '.so':
            continue
        data = path.read_bytes()
        raw_sha = hashlib.sha256(data).hexdigest()
        changed = False
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            pass
        else:
            for secret in secrets:
                if secret in text:
                    changed = True
                    text = text.replace(secret, '<REDACTED_CREDENTIAL>')
            data = text.encode('utf-8')
        rel = str(path.relative_to(root))
        records[rel] = dict(raw_sha256=raw_sha, review_sha256=hashlib.sha256(data).hexdigest(), redacted=changed)
        info = tarfile.TarInfo(root.name + '/' + rel)
        info.size = len(data)
        info.mode = 0o600
        out.addfile(info, io.BytesIO(data))
    data = (json.dumps(dict(source=str(root), files=records, exclusions=['duplicate prepared input directories', 'full-repository archives and native binaries retained on A100']), indent=2) + '\n').encode()
    info = tarfile.TarInfo(root.name + '/review-package-manifest.json')
    info.size = len(data)
    info.mode = 0o600
    out.addfile(info, io.BytesIO(data))
print(json.dumps(dict(archive=str(a.archive), files=len(records), bytes=a.archive.stat().st_size)))
