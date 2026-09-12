import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {DEFAULT_FILTERS,filterTasks,paginateTasks,readFilters,writeFilters,workloadKey,taskDomain,availableDomains} from '../app/lib/task-filters.ts';
const tasks=JSON.parse(readFileSync(new URL('../app/generated/task-index.json',import.meta.url),'utf8'));
const apply=patch=>filterTasks(tasks,{...DEFAULT_FILTERS,...patch});

test('Bug fix metadata spellings share one facet',()=>{
 assert.equal(workloadKey('bug_fix'),workloadKey('bugfix'));
 const fixtures=[
  {...tasks[0],slug:'bug-underscore',workloadType:'bug_fix'},
  {...tasks[0],slug:'bug-plain',workloadType:'bugfix'},
  {...tasks[0],slug:'bug-spaces',workloadType:'Bug Fix'},
  {...tasks[0],slug:'feature',workloadType:'feature'},
  {...tasks[0],slug:'unknown',workloadType:null},
 ];
 const facet=workload=>filterTasks(fixtures,{...DEFAULT_FILTERS,workload}).map(t=>t.slug);
 assert.deepEqual(facet('bugfix'),['bug-plain','bug-spaces','bug-underscore']);
 assert.deepEqual(facet('feature'),['feature']);
 assert.deepEqual(facet('unknown'),['unknown']);
});
test('current tasks expose Inference, not project names or empty future domains',()=>{
 assert.deepEqual(availableDomains(tasks),['inference']);
 assert.ok(tasks.every(t=>taskDomain(t)==='inference'));
 assert.equal(apply({domain:'inference'}).length,tasks.length);
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
 for(const size of [6,8]){
  const pageCount=Math.max(1,Math.ceil(all.length/size));
  const pages=Array.from({length:pageCount},(_,i)=>paginateTasks(all,i+1,size));
  assert.ok(pages.every(p=>p.pageCount===pageCount));
  assert.ok(pages.slice(0,-1).every(p=>p.items.length===size));
  assert.ok(pages.at(-1).items.length<=size);
  assert.deepEqual(pages.flatMap(p=>p.items.map(t=>t.slug)),before);
  assert.equal(paginateTasks(all,999,size).page,pageCount);
 }
 assert.deepEqual(all.map(t=>t.slug),before);
 assert.equal(paginateTasks([],9,8).page,1);
 assert.deepEqual(paginateTasks(all,1,0).items,all.slice(0,8));
});
test('pagination handles empty, exact and growing catalogues',()=>{
 for(const [count,size,lengths]of [
  [0,6,[0]],[1,6,[1]],[6,6,[6]],[7,6,[6,1]],
  [17,6,[6,6,5]],[18,6,[6,6,6]],[19,6,[6,6,6,1]],
  [8,8,[8]],[9,8,[8,1]],[17,8,[8,8,1]],[18,8,[8,8,2]],
 ]){
  const fixtures=Array.from({length:count},(_,i)=>i);
  const pages=lengths.map((_,i)=>paginateTasks(fixtures,i+1,size));
  assert.deepEqual(pages.map(p=>p.items.length),lengths);
  assert.deepEqual(pages.flatMap(p=>p.items),fixtures);
  assert.ok(pages.every(p=>p.pageCount===lengths.length));
  assert.deepEqual(paginateTasks(fixtures,999,size),pages.at(-1));
 }
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
