import test from 'node:test';
import assert from 'node:assert/strict';
import { focusedDomain, percentDomain, project } from '../app/lib/hero-plot.ts';
import data from '../app/generated/leaderboard.json' with {type:'json'};

test('resource domains contain every recorded value with increasing ticks',()=>{
  for(const key of ['averageCostUsd','averageOutputTokens','averageToolCalls']){
    const values=data.configurations.map(c=>c.metrics[key]);const d=focusedDomain(values);
    assert.ok(d.min<=Math.min(...values)&&d.max>=Math.max(...values));
    assert.ok(d.ticks.every((v,i)=>i===0||v>d.ticks[i-1]));assert.equal(d.ticks[0],d.min);assert.equal(d.ticks.at(-1),d.max);
  }
});
test('percent domain contains sample std bounds when requested',()=>{
  const values=data.configurations.map(c=>c.metrics.passAverage),std=data.configurations.map(c=>c.metrics.passAverageStd);
  const d=percentDomain(values,std);values.forEach((v,i)=>{assert.ok(v-std[i]>=d.min);assert.ok(v+std[i]<=d.max);});
});
test('linear projection reproduces endpoints and midpoint exactly',()=>{
  const d={min:1,max:5,ticks:[1,2,3,4,5]};assert.equal(project(1,d,50,1000),50);assert.equal(project(5,d,50,1000),1050);assert.equal(project(3,d,50,1000),550);
});
test('finite fallback and singleton domains never divide by zero',()=>{
  for(const values of [[],[0],[5],[NaN,Infinity]]){const d=focusedDomain(values);assert.ok(Number.isFinite(d.min)&&Number.isFinite(d.max)&&d.max>d.min);}
});
