import hashlib
from pathlib import Path
root = Path(__file__).resolve().parent
records = []
for file in sorted(root.rglob('*')):
    if file.is_file() and file.name != 'SHA256SUMS':
        records.append(f'{hashlib.sha256(file.read_bytes()).hexdigest()}  {file.relative_to(root)}')
(root/'SHA256SUMS').write_text('\n'.join(records)+'\n')
