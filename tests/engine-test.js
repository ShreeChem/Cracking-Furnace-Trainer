require('../src/engine.js');const F=globalThis.Furnace;
function run(id, script, pre){const r=F.createRun(id,{pre:pre||0});const acts=(script||[]).slice();
 while(!r.s.tripped&&!r.s.done){F.tick(r,0.5);while(acts.length&&r.s.t>=acts[0].t){const a=acts.shift();a.f(r);} }
 const sc=F.score(r,r.s,r.scn);
 const mins=r.hist.reduce((m,h)=>({o2:Math.min(m.o2,h.o2),drf:Math.max(m.drf,h.draft),lvl:Math.min(m.lvl,h.lvl),ratio:Math.min(m.ratio,h.ratio),cot:Math.max(m.cot,h.cotC),tmt:Math.max(m.tmt,h.tmtMax),pf:Math.min(m.pf,h.pfC)}),{o2:99,drf:-99,lvl:99,ratio:9,cot:0,tmt:0,pf:9});
 console.log(id, r.s.tripped?('TRIP '+r.s.tripped.id+' @'+r.s.tripped.t.toFixed(0)):'ok', 'score',sc.total,[sc.safety,sc.procedure,sc.response,sc.production].join('/'), JSON.stringify(Object.fromEntries(Object.entries(mins).map(([k,v])=>[k,+v.toFixed(2)]))), 'alarms',JSON.stringify(Object.fromEntries(Object.entries(r.alarmFirst).map(([k,v])=>[k,+v.toFixed(0)]))));
 console.log('   steps', sc.steps.map(s=>s.id+':'+s.status).join(' '), 'harm',sc.harmful.length);
 return r;}
const sp=(tag,to)=>r=>{const s=r.s;let from;if(tag==='FIC-100'){from=s.feedSP;s.feedSP=to}else if(tag==='TIC-150'){from=s.cotSP;s.cotSP=to}F.act(r,{kind:'sp',tag,from,to})};
const op=(tag,to)=>r=>{const s=r.s;let from;if(tag==='AIC-140'){from=s.damper;s.damper=to}else if(tag==='TIC-150'){from=s.fuelOP;s.fuelOP=to}F.act(r,{kind:'op',tag,from,to})};
const mode=(tag,to)=>r=>{const s=r.s;if(tag==='AIC-140'){s.aicBias=s.damper-60-6*((s.o2SP-s.o2)+s.aicI);s.aicMode=to}if(tag==='TIC-150'){s.ticMode=to;if(to==='MAN'){} }F.act(r,{kind:'mode',tag,from:'',to})};
const btn=tag=>r=>{const s=r.s;if(tag==='K-101'&&s.fanAvail!=null&&s.t>=s.fanAvail){s.fanStartAt=s.t+2}if(tag==='P-131B'){s.pumpBEta=s.t+8}F.act(r,{kind:'btn',tag})};
const comm=(tag,at)=>r=>{if(tag==='field'&&at==='FIC-101C')r.s.fieldEta=r.s.t+45;F.act(r,{kind:'comm',tag,at})};
const avg=(i,on)=>r=>{const s=r.s;const e0=s.cotSP-F.cotPV(s);s.avgIn[i]=on;const e1=s.cotSP-F.cotPV(s);s.ticI+=(e0-e1);F.act(r,{kind:'avg',tag:'TIC-150',pass:i,from:!on,to:on})};
const sel=tag=>r=>F.act(r,{kind:'select',tag});
const ack=()=>r=>F.ackAll(r);
for(const id of ['s1','s2','s3','s4','s5','s6']) run(id,[]);
console.log('--- good operators');
run('s1',[{t:150,f:ack()},{t:175,f:sp('FIC-100',24)},{t:185,f:sp('TIC-150',844)},{t:200,f:comm('utilities')},{t:395,f:sp('FIC-100',26)},{t:420,f:sp('FIC-100',28)},{t:450,f:sp('FIC-100',30)},{t:478,f:sp('TIC-150',850)}]);
run('s2',[{t:30,f:ack()},{t:45,f:sel('FIC-101C')},{t:70,f:comm('field','FIC-101C')},{t:80,f:sp('TIC-150',844)},{t:90,f:comm('supervisor')},{t:200,f:sp('TIC-150',850)}]);
run('s3',[{t:40,f:ack()},{t:45,f:sp('TIC-150',838)},{t:120,f:mode('AIC-140','AUTO')},{t:130,f:comm('utilities')}]);
run('s3',[{t:40,f:ack()},{t:45,f:mode('TIC-150','MAN')},{t:46,f:op('TIC-150',85)},{t:60,f:op('TIC-150',80)},{t:120,f:mode('AIC-140','AUTO')},{t:130,f:comm('utilities')}]);
console.log('--- s3 old reflex: open damper');
run('s3',[{t:40,f:ack()},{t:50,f:op('AIC-140',70)},{t:90,f:mode('AIC-140','AUTO')},{t:100,f:comm('utilities')}]);
run('s4',[{t:20,f:mode('AIC-140','MAN')},{t:22,f:op('AIC-140',100)},{t:26,f:sp('TIC-150',830)},{t:40,f:sp('FIC-100',25)},{t:80,f:btn('K-101')},{t:120,f:sp('TIC-150',850)},{t:150,f:sp('FIC-100',27)},{t:180,f:sp('FIC-100',29)},{t:210,f:sp('FIC-100',31)}]);
run('s5',[{t:20,f:ack()},{t:35,f:btn('P-131B')},{t:60,f:comm('maintenance')}]);

run('s6',[{t:40,f:ack()},{t:50,f:sel('TIC-150')},{t:70,f:avg(1,false)},{t:90,f:comm('instrument')}]);
run('s6',[{t:40,f:ack()},{t:60,f:mode('TIC-150','MAN')},{t:70,f:op('TIC-150',100)},{t:90,f:comm('instrument')}]);
console.log('--- wrong s6: cut feed');
run('s6',[{t:40,f:sp('FIC-100',28)},{t:60,f:sp('TIC-150',840)}]);
console.log('--- pre-roll 40 s, s4 good');
run('s4',[{t:20,f:mode('AIC-140','MAN')},{t:22,f:op('AIC-140',100)},{t:26,f:sp('TIC-150',830)},{t:40,f:sp('FIC-100',25)},{t:80,f:btn('K-101')},{t:120,f:sp('TIC-150',850)},{t:150,f:sp('FIC-100',27)},{t:180,f:sp('FIC-100',29)},{t:210,f:sp('FIC-100',31)}],40);
console.log('--- s6 slower operator (remove at 120 s)');
run('s6',[{t:60,f:ack()},{t:90,f:sel('TIC-150')},{t:115,f:avg(1,false)},{t:150,f:comm('instrument')}]);
