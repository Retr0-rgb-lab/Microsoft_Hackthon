import test from 'node:test';
import assert from 'node:assert/strict';
import {canAnalyze, nextMoment, unavailableReason} from '../coach-moments.js';
const controlled = {in_play:true,ball_owner_id:'H01',players:[['H01',1,2,0,0]],phase:'carry'};
test('only recorded active owners allow analysis', () => {
 assert.equal(canAnalyze(controlled),true);
 assert.equal(canAnalyze({...controlled,ball_owner_id:'missing'}),false);
 assert.equal(canAnalyze({...controlled,in_play:false}),false);
 assert.equal(canAnalyze(null),false);
});
test('moment navigation skips flight/dead ball and stops at preview bounds', () => {
 const frames=[controlled,{...controlled,ball_owner_id:null,phase:'pass'},{...controlled,in_play:false},controlled];
 assert.equal(nextMoment(frames,0,1),3);
 assert.equal(nextMoment(frames,3,-1),0);
 assert.equal(nextMoment(frames,3,1),-1);
 assert.equal(nextMoment(frames,0,-1),-1);
 assert.match(unavailableReason(frames[1]),/flight/);
 assert.match(unavailableReason(frames[2]),/stopped/);
});
