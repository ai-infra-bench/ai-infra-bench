"""Use vLLM's declared _C extension and build_ext backend without source edits.

The task changes this extension. Unrelated FlashAttention/FlashMLA/MoE modules
are supplied by the image and are not part of this quantization build. Selecting
a declared extension is equivalent to selecting its normal CMake build target;
all source lists, compiler flags and installation logic remain project-owned.
This script runs as the unprivileged agent user, never as the scoring parent.
"""
from pathlib import Path
import os
import runpy
import sys

import setuptools

repo = Path('/workspace/repo')
os.chdir(repo)
sys.path.insert(0, str(repo))
original_setup = setuptools.setup
selected = False


def setup_selected_extension(*args, **kwargs):
    global selected
    extensions = [extension for extension in kwargs.get('ext_modules', [])
                  if extension.name == 'vllm._C']
    if len(extensions) != 1:
        raise RuntimeError('The project must declare its public vllm._C extension')
    kwargs['ext_modules'] = extensions
    selected = True
    return original_setup(*args, **kwargs)


setuptools.setup = setup_selected_extension
sys.argv = ['setup.py', 'build_ext', '--inplace']
try:
    runpy.run_path(str(repo / 'setup.py'), run_name='__main__')
finally:
    setuptools.setup = original_setup
if not selected:
    raise RuntimeError('Project setup did not invoke the build backend')
print('native_build_completed target=vllm._C', flush=True)
