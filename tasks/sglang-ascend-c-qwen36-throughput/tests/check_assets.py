#!/usr/bin/env python3
"""Check the model asset bytes during preparation, before a timed experiment."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def verify(root, manifest):
    root = root.resolve()
    if not manifest.get('files'):
        raise ValueError('Empty asset manifest')
    for name, expected in manifest['files'].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or digest(path) != expected:
            raise ValueError('Model asset mismatch: ' + name)
    shards = set(json.loads((root / 'model.safetensors.index.json').read_text())['weight_map'].values())
    if not shards <= set(manifest['files']):
        raise ValueError('Manifest does not cover every model shard')
    return {'status': 'ASSETS_VALIDATED', 'files': len(manifest['files']), 'weight_shards': len(shards)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model-path', type=Path, required=True)
    p.add_argument('--manifest', type=Path, default=Path(__file__).with_name('model-files.json'))
    a = p.parse_args()
    print(json.dumps(verify(a.model_path, json.loads(a.manifest.read_text()))))


if __name__ == '__main__':
    main()
