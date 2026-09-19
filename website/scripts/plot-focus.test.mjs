import test from 'node:test';
import assert from 'node:assert/strict';
import {plotGroupKey,resolvePlotFocus} from '../app/lib/plot-focus.ts';
const models=[{id:'a-low',model:'a',agent:'codex',agentVersion:'1'},{id:'a-high',model:'a',agent:'codex',agentVersion:'1'},{id:'b-low',model:'b',agent:'codex',agentVersion:'1'}];
const a=plotGroupKey(models[0]),b=plotGroupKey(models[2]);
test('line hover focuses its series without projection guides',()=>{
 assert.deepEqual(resolvePlotFocus(models,{kind:'series',id:a},null),{pointId:null,group:a});
});
test('line to point keeps its series, then enables that point projection',()=>{
 const line=resolvePlotFocus(models,{kind:'series',id:a},null);
 const point=resolvePlotFocus(models,{kind:'point',id:'a-high'},null);
 assert.equal(line.group,point.group);assert.equal(point.pointId,'a-high');
});
test('hover overrides a pin and leaving restores the pin',()=>{
 const pinned={kind:'point',id:'b-low'};
 assert.deepEqual(resolvePlotFocus(models,{kind:'series',id:a},pinned),{pointId:null,group:a});
 assert.deepEqual(resolvePlotFocus(models,null,pinned),{pointId:'b-low',group:b});
 assert.deepEqual(resolvePlotFocus(models,null,{kind:'series',id:a}),{pointId:null,group:a});
});
test('cleared or removed targets do not leave another series dimmed',()=>{
 assert.deepEqual(resolvePlotFocus(models,null,null),{pointId:null,group:null});
 assert.deepEqual(resolvePlotFocus(models,{kind:'point',id:'missing'},null),{pointId:null,group:null});
 assert.deepEqual(resolvePlotFocus(models,{kind:'series',id:'missing'},null),{pointId:null,group:null});
});
