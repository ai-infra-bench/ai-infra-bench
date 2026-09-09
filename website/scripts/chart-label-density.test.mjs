import test from 'node:test';
import assert from 'node:assert/strict';
import {placePlotLabels} from '../app/lib/leaderboard-chart.ts';

function points(seriesCount, pointCount=4) {
  return Array.from({length:seriesCount},(_,series)=>Array.from({length:pointCount},(_,effort)=>({
    configuration:{id:series+'-'+effort,model:'model-'+series,effort:['low','medium','high','xhigh'][effort],agent:'agent',agentVersion:'test',metrics:{passAverage:42+series+effort,averageCostUsd:effort+1,averageOutputTokens:1000,averageToolCalls:10}},
    x:180+effort*180,y:80+series*60+effort*20,value:effort+1,score:42+series+effort,color:'#464842',group:'model-'+series,
  }))).flat();
}
const bounds={x:40,y:30,width:1100,height:600};
test('three or fewer series retain numeric point labels',()=>{
  for(const count of [1,2,3]){const labels=placePlotLabels(points(count),bounds,false);assert.equal(labels.filter(label=>label.detail?.includes('%')).length,count*4);}
});
test('more than three series show model names only',()=>{
  for(const compact of [false,true])for(const count of [4,5,7]){
    const data=points(count),labels=placePlotLabels(data,bounds,compact);
    assert.equal(labels.filter(label=>label.kind==='series').length,count);
    assert.equal(labels.filter(label=>label.kind==='effort').length,0);
    assert.equal(labels.length,count);
    assert.ok(labels.every(label=>!label.title.includes('%')&&!label.detail?.includes('%')));
    assert.ok(labels.filter(label=>label.kind==='effort').every(label=>label.detail===null));
    assert.equal(data[0].score,42);
  }
});
test('single-point model names remain without effort or score in dense plots',()=>{
  const labels=placePlotLabels(points(5,1),bounds,false);
  assert.equal(labels.length,5);assert.ok(labels.every(label=>label.kind==='model'&&label.detail===null));
});
test('a highlighted point alone regains effort and score in a dense plot',()=>{
 const data=points(7),selected=data[6];
 const labels=placePlotLabels(data,bounds,false,selected.configuration.id);
 const details=labels.filter(label=>label.kind==='effort');
 assert.equal(details.length,1);assert.equal(details[0].title,selected.configuration.effort);
 assert.equal(details[0].detail,selected.score.toFixed(1)+'%');
 assert.equal(labels.filter(label=>label.kind==='series').length,7);
 assert.equal(placePlotLabels(data,bounds,false,null).filter(label=>label.kind==='effort').length,0);
});
