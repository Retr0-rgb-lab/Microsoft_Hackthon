// Browser port of decision/outcome.py. Trained positional value + explicit rule assumptions.
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const dist=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
const sigmoid=x=>1/(1+Math.exp(-clamp(x,-40,40)));
const round4=v=>Math.round(v*10000)/10000;
export function compare(frame,metadata,trained,rates){
 const actor=frame.players.find(p=>p[0]===frame.ball_owner_id);if(!frame.in_play||!actor)return {status:'unavailable'};
 const teams=Object.fromEntries(metadata.players.map(p=>[p.player_id,p.team_id]));
 const team=teams[actor[0]],direction=(team==='HOME')===(frame.period===1)?1:-1;
 const progress=x=>direction===1?x:105-x;
 const opponents=frame.players.filter(p=>teams[p[0]]!==team),friends=frame.players.filter(p=>teams[p[0]]===team&&p[0]!==actor[0]);
 const cell=p=>clamp(Math.floor(p[0]/105*8),0,7)+8*clamp(Math.floor(p[1]/68*5),0,4);
 const value=(p,d,h=10)=>trained.values_by_horizon[h][cell([d===1?p[0]:105-p[0],p[1]])];
 const nearest=Math.min(...opponents.map(p=>dist(actor.slice(1,3),p.slice(1,3))));
 const current=value(actor.slice(1,3),direction),options=[];
 const second=[...opponents].map(p=>progress(p[1])).sort((a,b)=>b-a)[1];
 const offside=Math.max(52.5,progress(actor[1]),second);
 const arrival=(p,target)=>.3+Math.max(0,dist([p[1]+p[3]*.3,p[2]+p[4]*.3],target)-1)/7.2;
 function score(id,kind,target,w,source,eligible=true,receiver=null){
  let success=value(target,direction,9),failure=-value(target,-direction,9);
  if(kind==='shot'){success=1;failure=-value([direction===1?105:0,34],-direction,9);}
  const lo=Math.max(.01,w-.15),hi=Math.min(.99,w+.15),gain=x=>x*success+(1-x)*failure-current;
  options.push({action_id:id,type:kind,target,receiver_id:receiver,eligible,scenario_weight:w,weight_kind:source,
   success_value:success,failure_value:failure,value_gain:gain(w),sensitivity_range:[gain(lo),gain(hi)],weight_scenarios:[lo,w,hi],range_kind:'assumed_weight_sensitivity_not_confidence_interval'});
 }
 for(const receiver of friends){
  const start=actor.slice(1,3),travel0=dist(start,receiver.slice(1,3))/14;
  const target=[clamp(receiver[1]+receiver[3]*travel0,0,105),clamp(receiver[2]+receiver[4]*travel0,0,68)],travel=dist(start,target)/14;
  let margin=Infinity;
  for(const defender of opponents)for(let step=1;step<=20;step++){
   const u=step/20,spot=[start[0]+u*(target[0]-start[0]),start[1]+u*(target[1]-start[1])];
   margin=Math.min(margin,arrival(defender,spot)-u*travel);
  }
  const distance=dist(start,target),key=`${Math.min(4,Math.floor(distance/10))}:${Number(nearest<3)}`;
  const empirical=rates.pass_success[key]?.probability??(.88-.007*distance-.08*Number(nearest<3));
  score(`pass:${receiver[0]}`,'pass',target,empirical*(.45+.55*sigmoid(round4(margin)/.45)),
   'real_ground_pass_rate_adjusted_by_unvalidated_lane_rule',progress(receiver[1])<=offside+1e-6,receiver[0]);
 }
 for(const [name,dx,dy] of [['forward',6*direction,0],['left',3*direction,-5],['right',3*direction,5]]){
  const target=[clamp(actor[1]+dx,.5,104.5),clamp(actor[2]+dy,.5,67.5)];
  const clearance=Math.min(...opponents.map(p=>dist(target,p.slice(1,3))));
  score(`carry:${name}`,'carry',target,clamp(.5+.08*(clearance-2),.2,.95),'hand_defined_retention_assumption_not_trained_carry_probability');
 }
 const goal=[direction===1?105:0,34],gd=dist(actor.slice(1,3),goal);
 if(gd<=35&&!metadata.players.find(p=>p.player_id===actor[0])?.position?.includes('GK')){
  const key=String(Math.min(4,Math.floor(gd/8))),rate=rates.shot_goal[key]?.probability??Math.max(.015,.35*Math.exp(-gd/15));
  score('shot:goal','shot',goal,rate,'real_foot_shot_goal_frequency_by_distance_not_player_specific');
 }
 score('hold:1s','hold',actor.slice(1,3),clamp(.65+nearest*.035,.3,.98),'hand_defined_one_second_retention_assumption_no_support_prediction');
 options.sort((a,b)=>Number(b.eligible)-Number(a.eligible)||b.value_gain-a.value_gain);
 const speed=Math.hypot(actor[3],actor[4]);
 return {status:'ready',version:'outcome-0.1-browser',actor_id:actor[0],t_ms:frame.t_ms,current_value:current,candidates:options,
  highest_model_action_id:options.find(c=>c.eligible).action_id,score_unit:'risk_adjusted_possession_goal_value_proxy',
  action_state:{speed_mps:speed,movement_heading_deg:speed>.2?Math.atan2(actor[4],actor[3])*180/Math.PI:null,nearest_defender_m:nearest,under_pressure_3m:nearest<3,body_orientation:null,preferred_foot:null,touch_stability:null}};
}
export function reviewRecord(record,metadata,event,trained,rates,reveal=false){
 const r=compare(record.snapshot,metadata,trained,rates);if(r.status!=='ready')return r;
 let cid='carry:forward';
 if(record.selected.kind==='pass'){const c=record.candidates.find(c=>c.kind==='pass'&&c.recipient===record.selected.recipient);cid=`pass:${c.recipient_id}`;}
 if(record.selected.kind==='shot')cid='shot:goal';
 const actual=r.candidates.find(c=>c.action_id===cid);
 return {...r,source_snapshot:record.snapshot,match_id:metadata.match_id,decision_id:record.decision_id,synthetic:true,
  actual_action_id:cid,actual_model_value_gain:actual?.value_gain??null,outcome_available_at_ms:event?.available_at_ms??null,
  execution:!event?{status:'unavailable'}:!reveal?{status:'pending'}:{status:'observed',type:event.type,outcome:event.outcome,
   observed_distance_m:dist(event.start_location,event.end_location),duration_s:(event.end_ms-event.start_ms)/1000,technical_quality_score:null},
  actual_action_match:record.selected.kind==='carry'?'carry_type_proxy_not_actual_path':'exact_recipient_or_shot'};
}
export function simulatePass(frame,metadata,candidate,delay=.3,error=0){
 if(candidate.type!=='pass'||!candidate.eligible)throw Error('Only legal ground passes can be simulated.');
 const teams=Object.fromEntries(metadata.players.map(p=>[p.player_id,p.team_id])),team=teams[frame.ball_owner_id];
 let players=frame.players.map(p=>p.slice());const start=players.find(p=>p[0]===frame.ball_owner_id).slice(1,3);
 let target=candidate.target.slice();const dx=target[0]-start[0],dy=target[1]-start[1],length=dist(start,target);
 target=[clamp(target[0]-dy/Math.max(length,1e-9)*error,0,105),clamp(target[1]+dx/Math.max(length,1e-9)*error,0,68)];
 const travel=dist(start,target)/14,aims={};
 for(const p of players){if(teams[p[0]]===team)continue;let aim=target;
  for(let step=1;step<=80;step++){const t=step*.05,u=Math.min(1,t/Math.max(travel,.05)),spot=start.map((v,j)=>v+u*(target[j]-v));
   if(dist(p.slice(1,3),spot)<=Math.max(0,t-delay)*7.2+1){aim=spot;break;}}
  aims[p[0]]=aim;
 }
 const frames=[{elapsed_s:0,players:players.map(p=>p.slice()),ball:start.slice()}];let outcome='unresolved',controller_id=null;
 for(let step=1;step<=80;step++){
  const t=step*.05;
  players=players.map(p=>{let [vx,vy]=p.slice(3);const active=p[0]===candidate.receiver_id||(teams[p[0]]!==team&&t>delay);
   if(active){const aim=aims[p[0]]??target,dx=aim[0]-p[1],dy=aim[1]-p[2],d=Math.hypot(dx,dy),s=Math.min(7.2,Math.sqrt(7*d));
    const ax=dx/Math.max(d,1e-9)*s-vx,ay=dy/Math.max(d,1e-9)*s-vy,k=Math.min(1,3.5*.05/Math.max(Math.hypot(ax,ay),1e-9));vx+=ax*k;vy+=ay*k;}
   const s=Math.hypot(vx,vy);if(s>7.2){vx*=7.2/s;vy*=7.2/s;}
   const x=clamp(p[1]+vx*.05,0,105),y=clamp(p[2]+vy*.05,0,68);return [p[0],x,y,(x-p[1])/.05,(y-p[2])/.05];});
  const u=Math.min(1,t/Math.max(travel,.05)),ball=start.map((v,j)=>v+u*(target[j]-v));
  const touches=players.filter(p=>p[0]!==frame.ball_owner_id&&dist(p.slice(1,3),ball)<=1).map(p=>[dist(p.slice(1,3),ball),p[0]]).sort((a,b)=>a[0]-b[0]||a[1].localeCompare(b[1]));
  if(touches.length){controller_id=touches[0][1];outcome=teams[controller_id]===team?'received':'intercepted';}else if(t>=travel)outcome='unreceived';
  frames.push({elapsed_s:Math.round(t*1000)/1000,players:players.map(p=>p.slice()),ball});if(outcome!=='unresolved')break;
 }
 return {frames,outcome,controller_id,reaction_s:delay,lateral_error_m:error};
}
