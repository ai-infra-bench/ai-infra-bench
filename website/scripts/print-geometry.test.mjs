import test from 'node:test';
import assert from 'node:assert/strict';
import {curveSegments,curvePath,closedBand,linear,descendingLinear,polarPoint,polarConnection} from '../app/lib/print-geometry.ts';
import {readFileSync} from 'node:fs';
import {focusedDomain} from '../app/lib/hero-plot.ts';
test('linear projection preserves endpoints and midpoint',()=>{assert.equal(linear(1,1,5,40,800),40);assert.equal(linear(3,1,5,40,800),440);assert.equal(linear(5,1,5,40,800),840);});
test('descending scale puts the largest resource value on the left',()=>{
 assert.equal(descendingLinear(5,1,5,40,800),40);
 assert.equal(descendingLinear(3,1,5,40,800),440);
 assert.equal(descendingLinear(1,1,5,40,800),840);
});
test('all three measured axes mirror both knots and curve control points',()=>{
 const data=JSON.parse(readFileSync(new URL('../app/generated/leaderboard.json',import.meta.url),'utf8'));
 const configurations=data.configurations.filter(c=>c.model==='gpt-6-astra').sort((a,b)=>['low','medium','high','xhigh'].indexOf(a.effort)-['low','medium','high','xhigh'].indexOf(b.effort));
 for(const key of ['averageCostUsd','averageOutputTokens','averageToolCalls']){
  const domain=focusedDomain(data.configurations.map(c=>c.metrics[key]));
  for(const width of [212,1000]){
   const before=configurations.map(c=>({x:linear(c.metrics[key],domain.min,domain.max,40,width),y:c.metrics.passAverage}));
   const after=configurations.map(c=>({x:descendingLinear(c.metrics[key],domain.min,domain.max,40,width),y:c.metrics.passAverage}));
   const original=curveSegments(before),mirrored=curveSegments(after);
   for(const[i,segment]of mirrored.entries())for(const point of ['start','c1','c2','end']){
    assert.ok(Math.abs(segment[point].x+original[i][point].x-(80+width))<1e-8);
    assert.ok(Math.abs(segment[point].y-original[i][point].y)<1e-8);
   }
   assert.ok(!/NaN|Infinity/.test(curvePath(after)));
  }
 }
});
test('curves hit every knot without overshooting segment ranges',()=>{
 const points=[{x:1.3584,y:50},{x:1.9016,y:55.88},{x:2.8142,y:54.41},{x:4.7796,y:64.71}];
 const segments=curveSegments(points);assert.equal(segments.length,3);
 for(const [i,s]of segments.entries()){assert.deepEqual(s.start,points[i]);assert.deepEqual(s.end,points[i+1]);for(let j=0;j<=100;j++){const t=j/100;const value=(1-t)**3*s.start.y+3*(1-t)**2*t*s.c1.y+3*(1-t)*t*t*s.c2.y+t**3*s.end.y;assert.ok(value>=Math.min(s.start.y,s.end.y)-1e-8&&value<=Math.max(s.start.y,s.end.y)+1e-8);}}
});
test('band follows smooth upper and reversed lower bounds',()=>{const u=[{x:0,y:1},{x:2,y:3},{x:4,y:2}],l=u.map(p=>({x:p.x,y:p.y+2}));const d=closedBand(u,l);assert.ok(d.startsWith(curvePath(u)));assert.ok(d.endsWith(' Z'));assert.equal((d.match(/ C/g)||[]).length,4);});
test('polar radius is linear and includes all raw knots in its connector',()=>{const p=polarPoint(3,50,1,5,200,200,100);assert.equal(p.r,50);assert.ok(Math.abs(p.x-200)<1e-8);assert.ok(Math.abs(p.y-150)<1e-8);const points=[{value:1.3584,score:50},{value:1.9016,score:55.88},{value:4.7796,score:64.71}];const path=polarConnection(points,1,5,200,200,100);for(const raw of points){const q=polarPoint(raw.value,raw.score,1,5,200,200,100);assert.ok(path.includes(q.x+' '+q.y));}});
