import subprocess,pathlib,importlib.util,vllm
r=pathlib.Path('/workspace/repo')
def git(*args):return subprocess.check_output(['git','-C',str(r),*args],text=True).strip()
assert git('rev-parse','HEAD')=='9b9d5dbaab852a1c615fe83a7f92881d353503db'
assert git('rev-parse','HEAD^{tree}')=='48b639edab89a4d62d26e7355f0226609d3a035b'
assert not git('status','--porcelain') and not git('remote')
assert not git('fsck','--full','--no-reflogs','--unreachable','--no-progress')
assert not (r/'.git/shallow').exists()
assert subprocess.run(['git','cat-file','-e','d5ed61238528c4b753bceb761db91318b0d442fb'],capture_output=True).returncode!=0
for p in ['/tests','/solution','/validation','/workspace/repo/vllm/entrypoints/openai/dp_supervisor.py']:assert not pathlib.Path(p).exists(),p
for p in [vllm.__file__,importlib.util.find_spec('vllm._C').origin]:assert pathlib.Path(p).resolve().is_relative_to(r);print(p)
assert (r/'.git').stat().st_uid==__import__('os').getuid()
print('PASS pinned Base/tree, full clean history, absent future Oracle, no task artifacts, writable source and native imports',git('rev-list','--all','--count'))
