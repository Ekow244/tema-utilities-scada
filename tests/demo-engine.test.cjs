const {test}=require('node:test');
const assert=require('node:assert/strict');
const {Controller,DemoService,AlarmManager,validate}=require('../scada/web/demo-engine.js');
const recipe={name:'Reference batch',volume:60,setpoint:60,hold_seconds:120,rinse_volume:20,rinse_seconds:30};
function run(scenario='normal'){
  const c=new Controller(recipe);c.command('start');let peak=20,injected=false;
  for(let i=0;i<8000;i++){
    if(c.state==='HOLD'&&!injected){if(scenario==='heat-loss')c.p.heat_loss=.12;if(scenario==='sensor-fault')c.p.sensor_failed=true;injected=true;}
    if(c.state==='DISCHARGE'&&scenario==='pump-fault')c.p.pump_failed=true;
    c.tick();peak=Math.max(peak,c.p.temperature);
    if(['COMPLETE','FAULTED'].includes(c.state))break;
  }
  return {c,peak};
}
test('normal batch matches the recorded Python result and state order',()=>{
  const {c,peak}=run();assert.equal(c.state,'COMPLETE');assert.equal(c.time,990);assert.ok(Math.abs(peak-62.194)<.001);assert.equal(c.p.heater,0);assert.equal(c.p.volume,0);
  assert.deepEqual(c.events.map(e=>e.state),['PRECHECK','FILL','HEAT','HOLD','DISCHARGE','CIP_FILL','CIP_RINSE','CIP_DRAIN','COMPLETE']);
});
test('disturbance and fault results match Python reference runs',()=>{
  const heat=run('heat-loss');assert.equal(heat.c.state,'COMPLETE');assert.equal(heat.c.time,773);assert.ok(Math.abs(heat.peak-61.582)<.001);
  const sensor=run('sensor-fault').c;assert.equal(sensor.state,'FAULTED');assert.equal(sensor.time,395);assert.equal(sensor.p.heater,0);assert.equal(sensor.tags().temperature.quality,'BAD');
  const pump=run('pump-fault').c;assert.equal(pump.state,'FAULTED');assert.equal(pump.time,1030.5);assert.match(pump.reason,/DISCHARGE/);
});
test('pause, resume and abort preserve safe outputs',()=>{
  const c=new Controller(recipe);c.command('start');for(let i=0;i<100;i++)c.tick();c.command('pause');const volume=c.p.volume;
  for(let i=0;i<20;i++)c.tick();assert.equal(c.p.heater,0);assert.equal(c.p.volume,volume);c.command('resume');c.tick();assert.equal(c.state,'HEAT');c.command('abort');c.tick();assert.equal(c.state,'ABORTED');assert.equal(c.p.heater,0);
});
test('browser service scopes commands and persists recipe and final batch history',async()=>{
  let saved=null;const storage={getItem:()=>saved,setItem:(key,value)=>saved=value};const service=new DemoService(storage);
  const r=await service.request('/recipes',{...recipe,name:'Saved training'});const first=service.batchId;
  await service.request('/configure',{batch_id:first,recipe_id:r.id});
  await assert.rejects(service.request('/commands',{batch_id:first,request_id:'stale',action:'start'}),/Batch changed/);
  const request={batch_id:service.batchId,request_id:'start',action:'start'};
  await service.request('/commands',request);await service.request('/commands',request);assert.equal(service.c.events.length,1);
  await assert.rejects(service.request('/configure',{batch_id:service.batchId,recipe_id:r.id}),/active/);
  while(service.c.state!=='COMPLETE')service.tick();const completed=service.batchId;
  await service.request('/configure',{batch_id:completed,recipe_id:r.id});
  const archive=await service.request('/history?batch='+completed);assert.equal(archive.events.at(-1).state,'COMPLETE');assert.equal(archive.commands.length,1);
  const reloaded=new DemoService(storage);assert.ok(reloaded.recipes.some(row=>row.id===r.id));assert.equal((await reloaded.request('/history')).find(row=>row.id===completed).state,'COMPLETE');
});
test('alarm priority, shelving expiry and recipe limits',()=>{
  const c=new Controller(recipe),a=new AlarmManager();c.p.sensor_failed=true;a.update(c,.5,100);assert.throws(()=>a.command('SENSOR','shelve',101),/P1/);a.command('SENSOR','acknowledge',101);assert.equal(a.items.SENSOR.acknowledged,true);
  c.p.sensor_failed=false;c.state='FAULTED';c.reason='DISCHARGE step timeout';a.update(c,.5,102);a.command('TIMEOUT','shelve',103);assert.equal(a.items.TIMEOUT.shelved_until,163);a.update(c,.5,164);assert.equal(a.items.TIMEOUT.shelved_until,0);
  assert.throws(()=>validate({...recipe,volume:200}));assert.throws(()=>validate({...recipe,setpoint:NaN}));
});
