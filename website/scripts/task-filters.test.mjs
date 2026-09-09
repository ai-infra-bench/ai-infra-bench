import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {DEFAULT_FILTERS,filterTasks,paginateTasks,readFilters,writeFilters,workloadKey,taskDomain,availableDomains} from '../app/lib/task-filters.ts';
const tasks=JSON.parse(readFileSync(new URL('../app/generated/task-index.json',import.meta.url),'utf8'));
const apply=patch=>filterTasks(tasks,{...DEFAULT_FILTERS,...patch});

test('Bug fix metadata spellings share one facet',()=>{
 assert.equal(workloadKey('bug_fix'),workloadKey('bugfix'));
 assert.equal(apply({workload:'bugfix'}).length,14);
 assert.equal(apply({workload:'feature'}).length,3);
});
test('current tasks expose Inference, not project names or empty future domains',()=>{
 assert.deepEqual(availableDomains(tasks),['inference']);
 assert.ok(tasks.every(t=>taskDomain(t)==='inference'));
 assert.equal(apply({domain:'inference'}).length,17);
 assert.equal(apply({domain:'training'}).length,0);
 assert.equal(taskDomain({repository:'unclassified/project'}),null);
});
test('explicit domains support other projects without guessing their purpose',()=>{
 const future=[
  {...tasks[0],slug:'future-training',repository:'training/project',domain:'training'},
  {...tasks[1],slug:'future-harness',repository:'harness/project',domain:'agent_harness'},
  {...tasks[2],slug:'future-serving',repository:'serving/project',domain:'inference'},
 ];
 assert.deepEqual(availableDomains(future),['inference','training','agent_harness']);
 assert.equal(filterTasks(future,{...DEFAULT_FILTERS,domain:'training'})[0].slug,'future-training');
 assert.equal(taskDomain({...tasks[0],domain:'not-a-domain'}),null);
});
test('search intersects both supported facets and matches metadata',()=>{
 assert.equal(apply({q:'CHAT TEMPLATE'})[0].slug,'vllm-anthropic-inline-system-template');
 assert.equal(apply({q:'rust',workload:'feature',domain:'inference'})[0].slug,'vllm-implement-anthropic-rust-serving');
 assert.equal(apply({q:'rust',domain:'training'}).length,0);
 assert.ok(apply({q:'distributed_execution'}).some(t=>t.slug==='vllm-tokenizer-pickle-threadpool'));
 assert.equal(apply({q:'no-such-task-zzzz'}).length,0);
});
test('home and catalogue pagination cover all tasks exactly once',()=>{
 const all=apply({}),before=all.map(t=>t.slug);
 for(const [size,lengths]of [[6,[6,6,5]],[8,[8,8,1]]]){
  const pages=[1,2,3].map(n=>paginateTasks(all,n,size));
  assert.deepEqual(pages.map(p=>p.items.length),lengths);
  assert.deepEqual(pages.flatMap(p=>p.items.map(t=>t.slug)),before);
 }
 assert.deepEqual(all.map(t=>t.slug),before);
 assert.equal(paginateTasks(all,999,8).page,3);
 assert.equal(paginateTasks([],9,8).page,1);
 assert.equal(paginateTasks(all,1,0).items.length,8);
});
test('URL round trips supported filters and preserves typed whitespace',()=>{
 const state={...DEFAULT_FILTERS,q:'rust xml ',workload:'bugfix',domain:'inference',page:2};
 assert.deepEqual(readFilters(writeFilters(state),tasks),state);
 assert.deepEqual(readFilters('?type=fake&domain=fake&page=-2',tasks),DEFAULT_FILTERS);
 assert.ok(writeFilters(state,'?preview=yes').includes('preview=yes'));
});
test('retired filters and sort cannot silently affect current results',()=>{
 const legacy='?subsystem=serving_api&result=unpassed&sort=name-desc&set=cpu';
 assert.deepEqual(readFilters(legacy,tasks),DEFAULT_FILTERS);
 assert.equal(writeFilters(DEFAULT_FILTERS,legacy),'');
 assert.deepEqual(apply({}).map(t=>t.slug),tasks.map(t=>t.slug).sort((a,b)=>a.localeCompare(b,'en')));
});
