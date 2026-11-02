/* Browser-only counterpart of the Python training simulator. No field I/O. */
(function (root) {
  'use strict';
  const clone = value => JSON.parse(JSON.stringify(value));
  const id = () => crypto.randomUUID();
  const utc = () => new Date().toISOString();
  const terminal = state => ['IDLE','COMPLETE','FAULTED','ABORTED'].includes(state);
  const limits = {PRECHECK:5,FILL:120,HEAT:1800,HOLD:1800,DISCHARGE:120,CIP_FILL:120,CIP_RINSE:600,CIP_DRAIN:120};
  const defaults = [
    {id:'00000000-0000-4000-8000-000000000002',created_at:'2026-11-02T00:00:00Z',recipe:{name:'Tema · quick demonstration',volume:40,setpoint:50,hold_seconds:30,rinse_volume:15,rinse_seconds:15}},
    {id:'00000000-0000-4000-8000-000000000001',created_at:'2026-11-02T00:00:00Z',recipe:{name:'Tema · standard training',volume:60,setpoint:60,hold_seconds:120,rinse_volume:20,rinse_seconds:30}}
  ];
  function validate(r) {
    if(typeof r.name!=='string'||!r.name.trim()||r.name.length>80)throw Error('Recipe name must contain 1–80 characters');
    const ranges={volume:[10,100],setpoint:[25,75],hold_seconds:[1,1200],rinse_volume:[1,100],rinse_seconds:[1,300]};
    for(const [key,[min,max]] of Object.entries(ranges))if(typeof r[key]!=='number'||!Number.isFinite(r[key])||r[key]<min||r[key]>max)throw Error(`${key} must be between ${min} and ${max}`);
    return {name:r.name,...Object.fromEntries(Object.keys(ranges).map(key=>[key,r[key]]))};
  }
  class Controller {
    constructor(recipe=defaults[0].recipe){this.recipe=clone(recipe);this.state='IDLE';this.time=0;this.elapsed=0;this.hold=0;this.events=[];this.reason='';this.saved=null;this.integral=0;this.p={volume:0,temperature:20,supply:200,heater:0,inlet:false,outlet:false,rinse:false,pump_failed:false,sensor_failed:false,heat_loss:.025};}
    safe(){Object.assign(this.p,{heater:0,inlet:false,outlet:false,rinse:false});}
    transition(state,reason=''){this.events.push({time:this.time,previous:this.state,state,reason});this.state=state;this.reason=reason;this.elapsed=0;this.safe();}
    track(){this.integral=-.12*(this.recipe.setpoint-this.p.temperature);}
    command(action){
      if(action==='start'&&this.state==='IDLE')this.transition('PRECHECK');
      else if(action==='pause'&&limits[this.state]){this.saved=[this.state,this.elapsed];this.transition('PAUSED','Operator pause');}
      else if(action==='resume'&&this.state==='PAUSED'){const [state,elapsed]=this.saved;this.transition(state,'Operator resume');this.elapsed=elapsed;this.track();}
      else if(action==='abort'&&!['COMPLETE','ABORTED'].includes(this.state))this.transition('ABORTING','Operator abort; contents retained');
      else throw Error(`Command ${action} invalid in ${this.state}`);
    }
    tick(dt=.5){
      if(!Number.isFinite(dt)||dt<=0||dt>1)throw Error('Invalid scan timestep');
      const p=this.p,r=this.recipe;this.time+=dt;this.elapsed+=dt;
      if((limits[this.state]||this.state==='PAUSED')&&(p.sensor_failed||!Number.isFinite(p.temperature)||p.temperature>=85||p.volume>110))this.transition('FAULTED','Sensor invalid or process safety limit exceeded');
      else if(limits[this.state]&&this.elapsed>limits[this.state])this.transition('FAULTED',`${this.state} step timeout`);
      const s=this.state;
      if(s==='PRECHECK'){if(p.supply<r.volume||p.volume>.1)this.transition('FAULTED','Precheck: supply insufficient or vessel not empty');else this.transition('FILL');}
      else if(s==='FILL'&&p.volume>=r.volume){this.track();this.transition('HEAT');}
      else if(s==='HEAT'&&Math.abs(p.temperature-r.setpoint)<=.5)this.transition('HOLD');
      else if(s==='HOLD'){this.hold=Math.abs(p.temperature-r.setpoint)<=1?this.hold+dt:0;if(this.hold>=r.hold_seconds)this.transition('DISCHARGE');}
      else if(s==='DISCHARGE'&&p.volume<=.1)this.transition('CIP_FILL');
      else if(s==='CIP_FILL'&&p.volume>=r.rinse_volume)this.transition('CIP_RINSE');
      else if(s==='CIP_RINSE'&&this.elapsed>=r.rinse_seconds)this.transition('CIP_DRAIN');
      else if(s==='CIP_DRAIN'&&p.volume<=.1)this.transition('COMPLETE');
      else if(s==='ABORTING')this.transition('ABORTED','Outputs de-energized; contents retained');
      this.safe();p.inlet=this.state==='FILL';p.rinse=this.state==='CIP_FILL';p.outlet=['DISCHARGE','CIP_DRAIN'].includes(this.state);
      if(['HEAT','HOLD'].includes(this.state)&&p.volume>=10){const error=r.setpoint-p.temperature,candidate=this.integral+.0015*error*dt,raw=.12*error+candidate;if((raw>=0&&raw<=1)||(raw>1&&error<0)||(raw<0&&error>0))this.integral=candidate;p.heater=Math.max(0,Math.min(1,.12*error+this.integral));}
      const incoming=(p.inlet||p.rinse)?Math.min(2*dt,120-p.volume,p.rinse?1e9:p.supply):0;
      if(incoming){p.temperature=(p.volume*p.temperature+incoming*20)/(p.volume+incoming);p.volume+=incoming;if(!p.rinse)p.supply-=incoming;}
      if(p.volume>.1)p.temperature+=((p.volume>=10?30*p.heater:0)-p.heat_loss*(p.temperature-20))*dt/(p.volume*4.186);
      if(p.outlet&&!p.pump_failed)p.volume=Math.max(0,p.volume-2*dt);
    }
    tags(){const tag=(value,units,quality='GOOD')=>({value,units,quality});return {temperature:tag(this.p.temperature,'degC',this.p.sensor_failed?'BAD':'GOOD'),volume:tag(this.p.volume,'L'),setpoint:tag(this.recipe.setpoint,'degC'),heater:tag(this.p.heater*100,'%'),hold:tag(this.hold,'s'),inlet:tag(this.p.inlet,'bool'),outlet:tag(this.p.outlet,'bool'),rinse:tag(this.p.rinse,'bool'),supply:tag(this.p.supply,'L')};}
  }
  class AlarmManager {
    constructor(){this.items={};this.audit=[];this.deviation=0;}
    event(alarm,action,now){this.audit.push({alarm,action,timestamp:now});}
    update(c,dt,now=Date.now()/1000){
      const defs={SENSOR:['P1','Temperature signal invalid','Inspect TT-101 before preparing a fresh simulation.'],TRIP:['P1','Process limit trip','Inspect temperature and vessel level before restarting.'],TIMEOUT:['P2','Sequence step timeout','Check commanded flow and pump operation; inspect the failed step.'],DEVIATION:['P2','Hold temperature deviation','Inspect heater output and heat loss; hold qualification resets.']};
      const previous=this.items.DEVIATION?.active||false,bad=c.state==='HOLD'&&Math.abs(c.p.temperature-c.recipe.setpoint)>(previous?1:3);this.deviation=bad?this.deviation+dt:0;
      const conditions={SENSOR:c.p.sensor_failed,TRIP:c.state==='FAULTED'&&c.reason.includes('safety limit')&&!c.p.sensor_failed,TIMEOUT:c.state==='FAULTED'&&c.reason.includes('timeout'),DEVIATION:bad&&(previous||this.deviation>=10)};
      for(const [key,active] of Object.entries(conditions)){let a=this.items[key];if(active&&!a?.active){const [priority,title,response]=defs[key];a=this.items[key]={id:key,priority,title,response,active:true,acknowledged:false,raised_at:now,shelved_until:0};this.event(key,'RAISED',now);}else if(a?.active&&!active){a.active=false;this.event(key,'CLEARED',now);}if(a?.shelved_until&&now>=a.shelved_until){a.shelved_until=0;this.event(key,'SHELF_EXPIRED',now);}}
    }
    command(key,action,now=Date.now()/1000){const a=this.items[key];if(!a)throw Error('Unknown alarm');if(action==='acknowledge'){if(!a.acknowledged){a.acknowledged=true;this.event(key,'ACKNOWLEDGED',now);}}else if(action==='shelve'){if(a.priority==='P1')throw Error('P1 alarms cannot be shelved');a.shelved_until=now+60;this.event(key,'SHELVED_60S',now);}else if(action==='unshelve'){a.shelved_until=0;this.event(key,'UNSHELVED',now);}else throw Error('Unknown alarm action');}
  }
  class DemoService {
    constructor(storage=null){
      this.storage=storage;this.recipes=clone(defaults);this.records=[];this.storageAvailable=true;
      try{const saved=JSON.parse(storage?.getItem('tema-scada-v1')||'null');if(saved){if(Array.isArray(saved.recipes)&&saved.recipes.length)this.recipes=saved.recipes.map(r=>({...r,recipe:validate(r.recipe)}));if(Array.isArray(saved.records))this.records=saved.records.slice(0,8);}}catch{this.storageAvailable=false;}
      for(const record of this.records)if(!terminal(record.state)){record.state='INTERRUPTED';record.ended_at=utc();}
      this.reset(this.recipes[0].recipe);
    }
    reset(recipe){this.c=new Controller(recipe);this.alarms=new AlarmManager();this.batchId=id();this.created=utc();this.started=null;this.ended=null;this.sequence=0;this.commands=new Map();this.samples=[];this.scanCount=0;this.record(true);}
    snapshot(){return {schema_version:1,batch_id:this.batchId,sequence:++this.sequence,timestamp:utc(),sim_time:this.c.time,state:this.c.state,created_at:this.created,started_at:this.started,ended_at:this.ended,recipe:clone(this.c.recipe),tags:this.c.tags(),events:clone(this.c.events),commands:[...this.commands.values()],alarms:clone(Object.values(this.alarms.items)),alarm_audit:clone(this.alarms.audit),sim_speed:20};}
    tick(){const previous=this.c.state,auditLength=this.alarms.audit.length;if(!terminal(this.c.state)){this.c.tick();if(['COMPLETE','FAULTED','ABORTED'].includes(this.c.state))this.ended=utc();}this.alarms.update(this.c,.5);const changed=previous!==this.c.state||auditLength!==this.alarms.audit.length;if(++this.scanCount%8===0||changed)this.record(this.scanCount%40===0||changed);}
    record(persist=false){const s=this.snapshot();if(this.samples.at(-1)?.time!==s.sim_time)this.samples.push({time:s.sim_time,state:s.state,tags:clone(s.tags)});this.samples=this.samples.slice(-600);const record={id:this.batchId,state:s.state,created_at:this.created,started_at:this.started,ended_at:this.ended,recipe:s.recipe,samples:this.samples,events:s.events,commands:clone(s.commands),alarms:s.alarm_audit};const index=this.records.findIndex(r=>r.id===record.id);if(index>=0)this.records[index]=record;else this.records.unshift(record);this.records=this.records.slice(0,8);if(persist)this.persist();}
    persist(){try{this.storage?.setItem('tema-scada-v1',JSON.stringify({recipes:this.recipes,records:this.records}));}catch{this.storageAvailable=false;}}
    async request(path,body){
      const url=new URL(path,'https://demo.invalid');
      if(path==='/telemetry')return clone(this.snapshot());
      if(path==='/recipes'&&!body)return clone(this.recipes);
      if(path==='/recipes'&&body){const row={id:id(),created_at:utc(),recipe:validate(body)};if(this.recipes.length>=40)throw Error('This browser demo supports 40 recipe versions');this.recipes.push(row);this.persist();return clone(row);}
      if(url.pathname==='/history'){this.record();const batch=url.searchParams.get('batch');if(batch){const r=this.records.find(r=>r.id===batch);return clone(r?{samples:r.samples,events:r.events,commands:r.commands,alarms:r.alarms}:{samples:[],events:[],commands:[],alarms:[]});}return clone(this.records.map(({id,state,started_at,ended_at,recipe})=>({id,state,started_at,ended_at,recipe})));}
      if(body?.batch_id&&body.batch_id!==this.batchId)throw Error('Batch changed; refresh before sending a command');
      if(path==='/configure'){if(!terminal(this.c.state))throw Error('Finish or abort the active batch first');const row=this.recipes.find(r=>r.id===body.recipe_id);if(!row)throw Error('Recipe not found');this.record(true);this.reset(row.recipe);return {batch_id:this.batchId,state:'IDLE'};}
      if(path==='/alarms'){this.alarms.command(body.alarm_id,body.action);this.record(true);return {accepted:true};}
      if(path==='/commands'){
        if(typeof body.request_id!=='string'||!body.request_id||body.request_id.length>80)throw Error('request_id required');
        const previous=this.commands.get(body.request_id);if(previous){if(previous.action!==body.action)throw Error('request_id already used for another action');return clone(previous);}
        const ack={request_id:body.request_id,action:body.action,timestamp:utc(),sim_time:this.c.time};
        try{if(['sensor-fault','pump-fault','heat-loss'].includes(body.action)){if(!limits[this.c.state])throw Error('Fault injection requires an active batch');if(body.action==='sensor-fault')this.c.p.sensor_failed=true;else if(body.action==='pump-fault')this.c.p.pump_failed=true;else this.c.p.heat_loss=.12;}else this.c.command(body.action);if(body.action==='start')this.started=utc();Object.assign(ack,{accepted:true,reason:'Accepted',state:this.c.state});}catch(e){Object.assign(ack,{accepted:false,reason:e.message,state:this.c.state});}
        this.commands.set(body.request_id,ack);this.record(true);if(!ack.accepted)throw Error(ack.reason);return clone(ack);
      }
      throw Error('Unknown demo route');
    }
  }
  if(typeof module!=='undefined'&&module.exports)module.exports={Controller,DemoService,AlarmManager,validate};
  else {let storage=null;try{storage=localStorage;}catch{}root.SCADA_DEMO=new DemoService(storage);setInterval(()=>root.SCADA_DEMO.tick(),25);}
})(typeof window==='undefined'?globalThis:window);
