const {test}=require('node:test');
const assert=require('node:assert/strict');
const program=require('../plc/program.json');
const {Bench,LadderPLC}=require('../scada/web/plc-engine.js');
const scans=(b,n)=>{for(let i=0;i<n;i++)b.scan();};

test('ladder seal-in fills to high level, then drains to low level',()=>{
  const b=new Bench(program);b.press('START_PB');scans(b,230);
  assert.ok(b.level>=40&&b.level<=40.21);assert.equal(b.plc.bits.FILL_OUT,false);assert.equal(b.plc.bits.FILL_REQ,false);
  b.press('DRAIN_PB');scans(b,230);assert.ok(b.level<=.1);assert.equal(b.plc.bits.DRAIN_OUT,false);assert.equal(b.plc.bits.FAULT,false);
});
test('an open NC high-level wire inhibits fill and does not auto restart after repair',()=>{
  const b=new Bench(program);b.brokenHighWire=true;b.press('START_PB');scans(b,20);
  assert.equal(b.level,0);assert.equal(b.inputs.HIGH_OK,false);assert.equal(b.plc.bits.FILL_OUT,false);
  assert.equal(b.measurements().wire_104_upstream,24);assert.equal(b.measurements().wire_104_plc_end,0);
  b.brokenHighWire=false;scans(b,10);assert.equal(b.plc.bits.FILL_OUT,false);
  b.press('START_PB');b.scan();assert.equal(b.plc.bits.FILL_OUT,true);
});
test('functional stop drops outputs and seal-in, release alone does not restart',()=>{
  const b=new Bench(program);b.press('START_PB');scans(b,10);assert.equal(b.plc.bits.FILL_OUT,true);
  b.stopOK=false;b.scan();assert.equal(b.plc.bits.FILL_OUT,false);assert.equal(b.plc.bits.FILL_REQ,false);
  b.stopOK=true;scans(b,5);assert.equal(b.plc.bits.FILL_OUT,false);
});
test('blocked valve reaches TON timeout; reset requires a fresh start',()=>{
  const b=new Bench(program);b.stuckValve=true;b.press('START_PB');scans(b,310);
  assert.equal(b.plc.bits.FAULT,true);assert.equal(b.plc.bits.FILL_OUT,false);assert.equal(b.level,0);
  b.stuckValve=false;b.press('RESET_PB');b.scan();assert.equal(b.plc.bits.FAULT,false);scans(b,5);assert.equal(b.plc.bits.FILL_OUT,false);
  b.press('START_PB');b.scan();assert.equal(b.plc.bits.FILL_OUT,true);
});
test('overload is set dominant and opposing outputs never energize together',()=>{
  const b=new Bench(program);b.level=20;b.overloadOK=false;b.press('RESET_PB');b.scan();assert.equal(b.plc.bits.FAULT,true);
  b.overloadOK=true;b.press('RESET_PB');b.scan();
  for(let i=0;i<200;i++){if(i%7===0)b.press('START_PB');if(i%11===0)b.press('DRAIN_PB');b.scan();assert.ok(!(b.plc.bits.FILL_OUT&&b.plc.bits.DRAIN_OUT));}
});
test('rung changes alter execution rather than merely changing a drawn diagram',()=>{
  const changed=structuredClone(program);changed.rungs.find(r=>r.id==='R06').series.push('COMMISSIONING_OK');
  const plc=new LadderPLC(changed);plc.scan({STOP_OK:true,HIGH_OK:true,OL_OK:true,START_PB:true});assert.equal(plc.bits.FILL_REQ,true);assert.equal(plc.bits.FILL_OUT,false);
  plc.scan({COMMISSIONING_OK:true,START_PB:false});assert.equal(plc.bits.FILL_OUT,true);
});
