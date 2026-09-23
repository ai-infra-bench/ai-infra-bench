#!/usr/bin/env python3
"""Rebuild the test-owned Pi model stub from immutable upstream source.

Usage: python build_trusted_faux.py --pi-repo /path/to/pi --esbuild /path/to/esbuild [--write]
Default checks the committed bundle and provenance. No candidate workspace code
is imported: git archive reads the pinned Base tree, independent of dirty files.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import io

BASE = '71dca871bc80b6bc97be37f0ca3189399d651fff'
ESBUILD = '0.28.2'
TASK = Path(__file__).resolve().parents[2]
MARKER = '''
// External inspector consumes this exact serialized provider input before HTTP.
// The statement observes existing data; it does not rewrite candidate context.
export function observeProviderRequest(context) {
  const payload = JSON.stringify(context);
  debugger;
  return payload;
}
export function observeFixtureReady() {
  debugger;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pi-repo', type=Path, required=True)
    parser.add_argument('--esbuild', type=Path, required=True)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    esbuild = args.esbuild.resolve()
    version = subprocess.check_output([str(esbuild), '--version'], text=True).strip()
    if version != ESBUILD:
        raise SystemExit(f'Expected esbuild {ESBUILD}, got {version}')
    archive = subprocess.check_output(['git', '-C', str(args.pi_repo), 'archive', BASE, 'packages/ai/src', 'LICENSE'])
    with tempfile.TemporaryDirectory(prefix='pi-trusted-provider-build-') as temp:
        root = Path(temp)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for member in tar.getmembers():
                path = Path(member.name)
                if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
                    raise SystemExit('Unexpected upstream archive entry')
                destination = root / path
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(tar.extractfile(member).read())
        subprocess.run([str(esbuild), 'packages/ai/src/providers/faux.ts', '--bundle', '--platform=node',
                        '--format=esm', '--outfile=bundle.mjs', '--metafile=meta.json'], cwd=root, check=True,
                       capture_output=True, text=True)
        meta = json.loads((root / 'meta.json').read_text())
        inputs = sorted(meta['inputs'])
        if any(not path.startswith('packages/ai/src/') for path in inputs):
            raise SystemExit('Bundle unexpectedly includes code outside first-party Pi AI source')
        if any(output.get('imports') for output in meta['outputs'].values()):
            raise SystemExit('Bundle unexpectedly imports external runtime dependencies')
        header = ('/*\n' + (root / 'LICENSE').read_text().rstrip() + '\n*/\n'
                  f'// Test-owned scripted provider, bundled from Pi Base {BASE}.\n'
                  '// Model computation is substituted; candidate session, tools and communication still execute.\n')
        bundle = header + (root / 'bundle.mjs').read_text() + MARKER
        provenance = {'pi_base': BASE, 'esbuild_version': ESBUILD, 'entry': 'packages/ai/src/providers/faux.ts',
                      'source_sha256': {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in inputs},
                      'bundle_sha256': hashlib.sha256(bundle.encode()).hexdigest(),
                      'note': 'Model stub only; no grading answers or candidate session/transport implementation.'}
    target = TASK / 'tests/trusted_faux.mjs'
    manifest = TASK / 'validation/trusted_faux-source.json'
    manifest_text = json.dumps(provenance, indent=2) + '\n'
    if args.write:
        target.write_text(bundle)
        manifest.write_text(manifest_text)
    elif target.read_text() != bundle or manifest.read_text() != manifest_text:
        raise SystemExit('Trusted provider or provenance differs from reproducible build')
    print(json.dumps({'matched': True, 'bundle_sha256': provenance['bundle_sha256'], 'source_files': len(inputs)}))


if __name__ == '__main__':
    main()
