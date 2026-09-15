#!/usr/bin/env python3
"""Deliberately broken Oracle controls, applied only in disposable checkouts."""
import argparse,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('kind',choices=['volatile-selection','early-success-exit']);p.add_argument('--root',type=Path,default=Path('/workspace/deepseek-harness'));p.add_argument('--patch-out',type=Path,required=True);args=p.parse_args()
if args.kind=='volatile-selection':
    path=args.root/'packages/api/session-controller/src/agent.ts'
    old="    agent.session.append('model/selection', selection)"
    new="    // Deliberately broken control: selection exists only in this process."
else:
    path=args.root/'packages/api/session-controller/src/commands.ts'
    old='  async selectModel(request: SessionSelectModelRequest): Promise<SessionSelectModelValue> {'
    new=old+"\n    if (request.migration === 'checked') process.exit(0) // deliberately broken control"
s=path.read_text();assert s.count(old)==1,(path,s.count(old));path.write_text(s.replace(old,new))
args.patch_out.write_bytes(subprocess.check_output(['git','diff','HEAD','--binary'],cwd=args.root))
