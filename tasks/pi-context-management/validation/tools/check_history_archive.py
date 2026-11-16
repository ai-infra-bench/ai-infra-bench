"""Local archive-only regression, not SDK/Harbor verification.

The real candidate snapshot and public history-tool functions run in Node.
SDK registration/schema and unrelated capacity metering are substituted here;
no lifecycle, provider, reset scheduling or full-task success is claimed.
"""
from pathlib import Path
import argparse
import json
import os
import re
import subprocess
import tempfile


def files_from_patch(patch):
    files, path, lines = {}, None, []
    for line in patch.splitlines(True):
        if line.startswith("diff --git "):
            if path:
                files[path] = "".join(lines)
            path, lines = None, []
        elif line.startswith("+++ b/"):
            path = line[6:].strip()
        elif path and line.startswith("+") and not line.startswith("+++"):
            lines.append(line[1:])
    if path:
        files[path] = "".join(lines)
    return files


def check(task, case=None):
    with tempfile.TemporaryDirectory(prefix="context-archive-check-") as temporary:
        root = Path(temporary)
        files = files_from_patch((task / "solution/oracle.patch").read_text())
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        if case:
            subprocess.run(["git", "apply", "--whitespace=nowarn", str(task / "validation" / case["patch"])], cwd=root, check=True)
        path = root / "packages/coding-agent/examples/extensions/context-management/index.ts"
        source = path.read_text()
        source = re.sub(r'^import type .*?;\n', '', source, flags=re.M)
        source = re.sub(r'^import \{ estimateTokens,.*?;\n',
                        'type ExtensionAPI = any; type ExtensionContext = any; type AgentMessage = any;\nconst estimateTokens = () => 0;\n', source, flags=re.M)
        source = source.replace('import { Type } from "typebox";', 'const Type = new Proxy({}, { get: () => (...args: any[]) => ({}) }) as any;')
        path.write_text(source)
        runner = root / "check.mjs"
        runner.write_text('''import assert from 'node:assert/strict';
import install from ''' + json.dumps(path.as_uri()) + ''';
const tools=new Map();
install({registerFlag(){},getFlag(){},on(){},registerTool(t){tools.set(t.name,t);}});
const reasoning='reasoning-anchor\\n先排除🙂e\\u0301\\nquote " and slash \\\\n';
const visible='visible-anchor\\ncontinued "quote" and literal \\\\n';
const original={role:'assistant',content:[{type:'thinking',thinking:reasoning,thinkingSignature:'original-signature'},
    {type:'text',text:visible}],api:'openai-completions',provider:'fixture',model:'fixture',stopReason:'stop',timestamp:1};
const entries=[{id:'original',type:'message',message:original},
    {type:'custom',customType:'context-management.window',data:{window_id:'second'}}];
const ctx={sessionManager:{getBranch:()=>entries,getSessionId:()=> 'session',getSessionFile:()=>undefined}};
async function call(name,args){const r=await tools.get(name).execute('id',args,undefined,undefined,ctx);return JSON.parse(r.content[0].text);}
async function find(query){let cursor,items=[];do{const p=await call('history_search',{query,...(cursor?{cursor}: {})});items.push(...p.items);cursor=p.next_cursor;}while(cursor!=null);return items;}
for(const query of ['reasoning-anchor','先排除🙂','reasoning-anchor\\n先排除', 'visible-anchor\\ncontinued', '"quote"', 'literal \\\\n']){
    assert((await find(query)).some(x=>x.item_id==='original'),'literal original not found: '+query);
}
assert(!(await find('VISIBLE-ANCHOR')).some(x=>x.item_id==='original'),'case mismatch matched original');
const item=(await find('reasoning-anchor')).find(x=>x.item_id==='original');
const read=await call('history_read',{window_id:item.window_id,item_id:item.item_id});
let decoded=JSON.parse(read.text);
if(decoded.original)decoded=decoded.original;
assert.deepEqual(decoded,original,'read did not preserve the complete original message');
console.log(JSON.stringify({passed:true,checks:8,scope:'candidate archive/text functions only'}));
''')
        env = {k: v for k, v in os.environ.items() if k not in ("NODE_OPTIONS", "NODE_PATH")}
        return subprocess.run(["node", "--experimental-strip-types", str(runner)], env=env, capture_output=True, text=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    cases = json.loads((args.task / "validation/ci-cases.json").read_text())["cases"]
    selected = [None] + [c for c in cases if c["name"] in ("complete-json-sidecar", "json-history", "lossy-original-oracle", "serialized-history-search")]
    results = []
    for case in selected:
        run = check(args.task, case)
        expected = case is None or case["expected_reward"] == 1
        results.append({"case": "oracle" if case is None else case["name"], "passed": run.returncode == 0,
                        "expected_archive_pass": expected, "stdout": run.stdout, "stderr": run.stderr})
        assert (run.returncode == 0) == expected, results[-1]
    print(json.dumps(results, indent=2))
