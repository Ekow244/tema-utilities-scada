'use strict';
const $ = id => document.getElementById(id);
const esc = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const title = text => String(text).replaceAll('_', ' ').toLowerCase().replace(/^./, s => s.toUpperCase());
const duration = seconds => `${Math.floor(seconds/60)}:${String(Math.floor(seconds%60)).padStart(2,'0')}`;
const localTime = date => date ? new Date(date).toLocaleString('en-GB',{timeZone:'Africa/Accra',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}) + ' GMT' : '—';
let current = null, recipes = [], points = [], pointBatch = null, connected = false, busy = false, view = 'overview', detail = null, toastTimer;
let alarmRenderKey = '';
const terminal = s => ['IDLE','COMPLETE','FAULTED','ABORTED'].includes(s);

async function api(path, body) {
  if(globalThis.SCADA_DEMO)return globalThis.SCADA_DEMO.request(path,body);
  const response = await fetch(path, {method:body ? 'POST':'GET', headers:body ? {'Content-Type':'application/json'}:{}, body:body ? JSON.stringify(body):undefined, signal:AbortSignal.timeout(6000)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || data.reason || 'Request failed');
  return data;
}
function notify(text, error=false) { clearTimeout(toastTimer); $('toast').textContent=text; $('toast').className=error?'error':''; $('toast').hidden=false; toastTimer=setTimeout(()=>$('toast').hidden=true,5000); }
function showView(next) {
  view=next;
  document.querySelectorAll('.view').forEach(el=>el.hidden=el.id!==`view-${next}`);
  document.querySelectorAll('.nav').forEach(el=>el.classList.toggle('active',el.dataset.view===next));
  const headings={plc:['PLC & I/O bench','Follow the signal. Read the rung. Find the fault.'],overview:['Process overview','A live view of your thermal batch process.'],recipes:['Recipe library','Repeatable batches begin with a well-defined recipe.'],alarms:['Alarm console','Prioritized conditions, clear responses and a complete audit.'],history:['Batch historian','Trace the recipe, sequence and actions behind every batch.']};
  $('page-heading').textContent=headings[next][0]; $('page-subtitle').textContent=headings[next][1];
  if(next==='history') loadHistory();
  if(next==='plc') $('speed').textContent='1×';
}
document.querySelectorAll('[data-view]').forEach(el=>el.onclick=()=>showView(el.dataset.view));
document.querySelectorAll('[data-goto]').forEach(el=>el.onclick=()=>showView(el.dataset.goto));
function updateControls() {
  const enabled=connected && current && !busy, state=current?.state;
  $('start').disabled=!enabled || state!=='IDLE';
  $('pause').disabled=!enabled || terminal(state) || state==='ABORTING';
  $('pause').textContent=state==='PAUSED'?'▶ Resume':'Ⅱ Pause';
  $('abort').disabled=!enabled || ['IDLE','COMPLETE','ABORTED','FAULTED','ABORTING'].includes(state);
  $('prepare').disabled=!enabled || !terminal(state) || !recipes.length;
  $('recipe-select').disabled=!enabled || !terminal(state);
  document.querySelectorAll('[data-fault]').forEach(el=>el.disabled=!enabled || terminal(state) || state==='PAUSED');
}
async function action(fn) { if(busy)return; busy=true; updateControls(); try{await fn();await refresh();}catch(e){notify(e.message,true);}finally{busy=false;updateControls();} }
async function command(actionName) {
  const ack=await api('/commands',{request_id:crypto.randomUUID(),batch_id:current.batch_id,action:actionName});
  notify(`${title(actionName.replaceAll('-',' '))} · ${ack.reason}`);
}
$('start').onclick=()=>action(()=>command('start'));
$('pause').onclick=()=>action(()=>command(current.state==='PAUSED'?'resume':'pause'));
$('abort').onclick=()=>action(()=>command('abort'));
document.querySelectorAll('[data-fault]').forEach(el=>el.onclick=()=>action(()=>command(el.dataset.fault)));
$('prepare').onclick=()=>action(async()=>{await api('/configure',{batch_id:current.batch_id,recipe_id:$('recipe-select').value});notify('Fresh batch prepared. Ready to start.');});

function recipeDescription() {
  const r=recipes.find(r=>r.id===$('recipe-select').value)?.recipe;
  $('recipe-description').textContent=r?`${r.volume} L fill · ${r.setpoint}°C target · ${r.hold_seconds} s hold · ${r.rinse_seconds} s rinse`:'No recipes available.';
}
async function loadRecipes(selectId) {
  recipes=await api('/recipes');
  const selected=selectId || $('recipe-select').value;
  $('recipe-select').innerHTML=recipes.map(r=>`<option value="${esc(r.id)}">${esc(r.recipe.name)}</option>`).join('');
  if(recipes.some(r=>r.id===selected))$('recipe-select').value=selected;
  $('recipe-list').innerHTML=recipes.map(r=>`<article class="recipe-card"><h3>${esc(r.recipe.name)}</h3><p>${r.recipe.volume} L · ${r.recipe.setpoint}°C · ${r.recipe.hold_seconds} s hold · ${r.recipe.rinse_volume} L rinse</p><small>VERSION ${esc(r.id.slice(-8).toUpperCase())} · ${esc(localTime(r.created_at))}</small></article>`).join('');
  recipeDescription();updateControls();
}
$('recipe-select').onchange=recipeDescription;
$('recipe-form').onsubmit=async event=>{
  event.preventDefault(); const button=event.submitter;button.disabled=true;
  try {const values=Object.fromEntries(new FormData(event.target));for(const key of Object.keys(values))if(key!=='name')values[key]=Number(values[key]);const saved=await api('/recipes',values);await loadRecipes(saved.id);notify('New recipe version saved. Prepare a batch to use it.');}
  catch(e){notify(e.message,true);}finally{button.disabled=false;}
};

function render(s) {
  $('prepared-recipe').textContent=s.recipe.name;
  if(!terminal(s.state)) $('recipe-description').textContent=`Running: ${s.recipe.name} · ${s.recipe.volume} L · ${s.recipe.setpoint}°C · ${s.recipe.hold_seconds} s hold`;
  else recipeDescription();
  const v=key=>s.tags[key]?.value ?? 0, good=s.tags.temperature.quality==='GOOD';
  $('temperature').textContent=good?v('temperature').toFixed(1):'—';
  $('temperature-note').textContent=good?`Setpoint ${s.recipe.setpoint.toFixed(1)} °C`:'BAD QUALITY · sensor invalid';
  $('volume').textContent=v('volume').toFixed(1);$('heater').textContent=v('heater').toFixed(1);
  $('power').textContent=`${(v('heater')*.3).toFixed(1)} kW thermal input`;
  $('level-bar').style.width=`${Math.min(100,v('volume')/120*100)}%`;
  $('state').textContent=title(s.state);$('state').style.color=s.state==='FAULTED'?'var(--red)':'';
  $('elapsed').textContent=`${duration(s.sim_time)} simulated`;$('batch-short').textContent=`#${s.batch_id.slice(0,6)}`;$('speed').textContent=view==='plc'?'1×':`${s.sim_speed}×`;
  $('tank-temperature').textContent=good?`${v('temperature').toFixed(1)} °C`:'SIGNAL BAD';
  $('tank-volume').textContent=`${v('volume').toFixed(1)} / 120 L`;
  $('supply-level').textContent=`${v('supply').toFixed(0)} L`;
  const height=Math.min(161,Math.max(0,v('volume')/120*161));
  $('batch-water').setAttribute('y',270-height);$('batch-water').setAttribute('height',height);
  const supplyHeight=Math.min(145,v('supply')/200*145);$('supply-water').setAttribute('y',270-supplyHeight);$('supply-water').setAttribute('height',supplyHeight);
  for(const [id,key] of [['fill-flow','inlet'],['drain-flow','outlet'],['rinse-flow','rinse']])$(id).classList.toggle('on',Boolean(v(key)) && !(key==='outlet' && s.commands.some(c=>c.action==='pump-fault'&&c.accepted)));
  $('inlet-symbol').style.opacity=v('inlet')?1:.5;$('pump-symbol').style.opacity=v('outlet')?1:.5;
  $('heater-coil').setAttribute('stroke',v('heater')>1?'#e59a30':'#aeb9c6');
  $('hold-status').textContent=`${v('hold').toFixed(0)} / ${s.recipe.hold_seconds} s hold`;
  let st=s.state==='PAUSED'?s.events.at(-1)?.previous:s.state;
  const groups=[['Fill',['PRECHECK','FILL']],['Heat',['HEAT']],['Hold',['HOLD']],['Drain',['DISCHARGE']],['Rinse',['CIP_FILL','CIP_RINSE','CIP_DRAIN']]];
  let index=groups.findIndex(g=>g[1].includes(st));if(s.state==='COMPLETE')index=5;
  $('sequence').innerHTML=groups.map(([label],i)=>`<li class="${i<index?'done':i===index?'current':''}"><i></i>${label}</li>`).join('');
  renderAlarms(s);renderTrend();updateControls();
}
function renderTrend() {
  const kind=$('trend-kind').value, names={temperature:'Temperature',volume:'Vessel level',heater:'Heater output'};
  $('trend-name').textContent=names[kind];$('sp-legend').hidden=kind!=='temperature';
  const valid=points.filter(p=>p[kind]!==null), end=Math.max(60,current?.sim_time||0),start=Math.max(0,end-1200),max=kind==='temperature'?100:kind==='volume'?120:100;
  const data=valid.filter(p=>p.time>=start),x=t=>48+(t-start)/(end-start)*730,y=n=>158-n/max*135;
  let svg='';
  for(let i=0;i<=4;i++){const n=i*max/4;svg+=`<path d="M48 ${y(n)}H778" stroke="#e9eef4"/><text x="35" y="${y(n)+3}" text-anchor="end" fill="#8b9bad" font-size="9" font-family="monospace">${n}</text>`;}
  for(let i=0;i<=4;i++){const t=start+(end-start)*i/4;svg+=`<text x="${x(t)}" y="183" text-anchor="middle" fill="#8b9bad" font-size="9" font-family="monospace">${duration(t)}</text>`;}
  if(kind==='temperature'&&current){svg+=`<path d="M48 ${y(current.recipe.setpoint)}H778" stroke="#d8ac42" stroke-dasharray="5 5" stroke-width="1.5"/>`;}
  if(data.length>1)svg+=`<polyline points="${data.map(p=>`${x(p.time).toFixed(1)},${y(p[kind]).toFixed(1)}`).join(' ')}" fill="none" stroke="#3784b5" stroke-width="2" stroke-linejoin="round"/>`;
  else svg+='<text x="415" y="100" text-anchor="middle" fill="#92a0b2" font-size="11">Start a batch to see the process develop</text>';
  $('trend').innerHTML=svg;
}
$('trend-kind').onchange=renderTrend;
function renderAlarms(s) {
  const now=Date.now()/1000,items=s.alarms||[],visible=items.filter(a=>a.active&&a.shelved_until<=now);
  const key=JSON.stringify([s.batch_id,items,s.alarm_audit,items.map(a=>a.shelved_until>now?Math.ceil(a.shelved_until-now):0)]);
  if(key===alarmRenderKey)return;
  alarmRenderKey=key;
  $('nav-alarm-count').textContent=visible.length;
  $('alarm-summary').innerHTML=visible.length?visible.map(a=>`<div class="alarm-mini"><span class="priority ${a.priority==='P1'?'p1':''}">${a.priority}</span><span>${a.acknowledged?'Acknowledged':'Needs attention'}</span><p>${esc(a.title)}</p><small>${esc(a.response)}</small></div>`).join(''):`<div class="all-clear"><span class="check-mark">✓</span><strong>${items.some(a=>a.active)?'Alarms temporarily shelved':'No active alarms'}</strong><p>${items.some(a=>a.active)?'Review the console for shelved conditions.':'The process is within its monitored limits.'}</p></div>`;
  $('alarm-console').innerHTML=items.length?items.map(a=>`<article class="alarm-row"><span class="priority ${a.priority==='P1'?'p1':''}">${a.priority}</span><div><h3>${esc(a.title)}</h3><p>${esc(a.response)}</p><div class="alarm-state">${a.active?'ACTIVE':'RETURNED TO NORMAL'} · ${a.acknowledged?'ACKNOWLEDGED':'UNACKNOWLEDGED'}${a.shelved_until>now?' · SHELVED '+Math.ceil(a.shelved_until-now)+'s':''}</div></div><div class="alarm-actions">${!a.acknowledged?`<button class="button secondary" data-alarm="${a.id}" data-action="acknowledge">Acknowledge</button>`:''}${a.priority!=='P1'&&a.active?`<button class="button secondary" data-alarm="${a.id}" data-action="${a.shelved_until>now?'unshelve':'shelve'}">${a.shelved_until>now?'Unshelve':'Shelve 60s'}</button>`:''}</div></article>`).join(''):'<div class="empty">No alarms recorded for this batch. Fault scenarios are available in Batch control.</div>';
  $('alarm-audit').innerHTML=(s.alarm_audit||[]).slice().reverse().map(e=>`<div class="audit-item"><time>${new Date(e.timestamp*1000).toLocaleTimeString('en-GB',{timeZone:'Africa/Accra'})} GMT</time><span>${esc(e.alarm)} · ${esc(title(e.action))}</span></div>`).join('')||'<div class="empty">Alarm lifecycle events will appear here.</div>';
}
$('alarm-console').onclick=event=>{const b=event.target.closest('[data-alarm]');if(!b||!connected)return;action(async()=>{await api('/alarms',{batch_id:current.batch_id,alarm_id:b.dataset.alarm,action:b.dataset.action});notify('Alarm action recorded.');});};
async function loadHistory() {
  try{const batches=await api('/history');$('history-list').innerHTML=batches.length?`<table><thead><tr><th>BATCH</th><th>RECIPE</th><th>STARTED · GMT</th><th>RESULT</th><th></th></tr></thead><tbody>${batches.map(b=>`<tr><td><code>${esc(b.id.slice(0,8))}</code></td><td>${esc(b.recipe.name)}</td><td>${esc(localTime(b.started_at))}</td><td><span class="record-state">${esc(title(b.state))}</span></td><td><button class="text-button" data-record="${esc(b.id)}">Inspect ↗</button></td></tr>`).join('')}</tbody></table>`:'<div class="empty">Waiting for the historian to record its first batch.</div>';}
  catch(e){$('history-list').innerHTML=`<div class="empty">Historian unavailable. ${esc(e.message)}</div>`;}
}
$('refresh-history').onclick=loadHistory;
$('history-list').onclick=async event=>{const b=event.target.closest('[data-record]');if(!b)return;try{const data=await api('/history?batch='+encodeURIComponent(b.dataset.record));detail={...data,id:b.dataset.record};$('history-detail').hidden=false;$('history-detail').innerHTML=`<div class="panel-title"><h2>Batch ${esc(b.dataset.record.slice(0,8))} · ${data.samples.length} stored samples · ${data.commands.length} commands</h2><button id="export-record" class="button secondary">Export CSV</button></div>${data.events.map(e=>`<div class="audit-item"><time>${duration(e.time)} sim</time><strong>${esc(title(e.state))}</strong><span>${esc(e.reason)}</span></div>`).join('')}<div class="panel-title"><h2>Operator command audit</h2></div>${data.commands.map(c=>`<div class="audit-item"><time>${duration(c.sim_time)} sim</time><strong>${esc(title(c.action))}</strong><span>${c.accepted?'Accepted':'Rejected'} · ${esc(c.reason)}</span></div>`).join('')}<div class="panel-title"><h2>Alarm lifecycle audit</h2></div>${data.alarms.map(a=>`<div class="audit-item"><time>${new Date(a.timestamp*1000).toLocaleTimeString('en-GB',{timeZone:'Africa/Accra'})} GMT</time><span>${esc(a.alarm)} · ${esc(title(a.action))}</span></div>`).join('')||'<div class="empty">No alarm lifecycle events in this batch.</div>'}`;$('export-record').onclick=exportRecord;}catch(e){notify(e.message,true);}};
function exportRecord(){if(!detail)return;const rows=[['sim_seconds','state','temperature_C','temperature_quality','volume_L','heater_percent'],...detail.samples.map(s=>[s.time,s.state,s.tags.temperature.value,s.tags.temperature.quality,s.tags.volume.value,s.tags.heater.value])];const blob=new Blob([rows.map(r=>r.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\n')],{type:'text/csv'});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`batch-${detail.id.slice(0,8)}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}

function addPoint(s){return {time:s.sim_time,temperature:s.tags.temperature.quality==='GOOD'?s.tags.temperature.value:null,volume:s.tags.volume.value,heater:s.tags.heater.value};}
async function hydrate(batch){try{const data=await api('/history?batch='+encodeURIComponent(batch));if(pointBatch!==batch)return;const merged=new Map(data.samples.map(s=>[s.time,addPoint({...s,sim_time:s.time})]));points.forEach(p=>merged.set(p.time,p));points=[...merged.values()].sort((a,b)=>a.time-b.time).slice(-3000);renderTrend();}catch{/* Live trends continue even if SQL is temporarily unavailable. */}}
async function refresh(){try{const s=await api('/telemetry');connected=true;current=s;if(pointBatch!==s.batch_id){pointBatch=s.batch_id;points=[];hydrate(s.batch_id);}if(!points.length||points.at(-1).time!==s.sim_time)points.push(addPoint(s));if(points.length>3000)points.shift();$('connection').textContent=globalThis.SCADA_DEMO?'Browser simulation':'Process online';$('connection').className='status';$('stale-banner').hidden=true;render(s);}catch(e){connected=false;$('connection').textContent='Connection lost';$('connection').className='status disconnected';$('stale-banner').hidden=false;updateControls();}}
async function poll(){await refresh();setTimeout(poll,500);}
function clock(){$('clock').textContent=new Date().toLocaleTimeString('en-GB',{timeZone:'Africa/Accra'})+' GMT';}clock();setInterval(clock,1000);
updateControls();loadRecipes().catch(e=>notify('Recipe library unavailable: '+e.message,true));poll();
