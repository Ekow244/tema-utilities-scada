const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const program=require('./program.json');
const {Bench}=require('../scada/web/plc-engine.js');
const b=new Bench(program),evidence=[];
function record(step){evidence.push({step,simulated_seconds:Number(b.time.toFixed(2)),tank_litres:Number(b.level.toFixed(3)),HIGH_OK:b.inputs.HIGH_OK,FILL_REQ:b.plc.bits.FILL_REQ,FILL_OUT:b.plc.bits.FILL_OUT,virtual_volts:b.measurements()});}
b.scan();record('Healthy empty vessel, before start');
b.brokenHighWire=true;b.press('START_PB');b.scan();b.scan();record('Fault injected: open wire 104 at X1:04; fill start attempted');
assert.equal(b.level,0);assert.equal(b.plc.bits.FILL_OUT,false);assert.equal(b.measurements().wire_104_upstream,24);assert.equal(b.measurements().plc_I0_3,0);
b.brokenHighWire=false;b.scan();record('Wire restored: input recovers; no automatic restart');
assert.equal(b.inputs.HIGH_OK,true);assert.equal(b.plc.bits.FILL_OUT,false);
b.press('START_PB');b.scan();record('Fresh start after repair: fill output energizes');
assert.equal(b.plc.bits.FILL_OUT,true);
for(let i=0;i<230;i++)b.scan();record('Retest: high-level permissive opens and stops filling');
assert.equal(b.plc.bits.FILL_OUT,false);assert.ok(b.level>=40&&b.level<=40.21);
b.press('DRAIN_PB');for(let i=0;i<230;i++)b.scan();record('Retest: drain completes and pump stops at low level');
assert.ok(b.level<=.1);assert.equal(b.plc.bits.DRAIN_OUT,false);
const report={result:'PASS',environment:'Educational ladder interpreter; virtual voltage nodes, no physical meter or hardware',fault:'Open conductor 104 between the NC high-level contact and PLC I0.3 / X1:04',diagnosis:'24 V upstream and 0 V at the PLC input isolates the open signal path; the missing HIGH_OK condition opens R05 and R06',correction:'Restore the simulated conductor, verify input recovery, then issue a fresh start',evidence};
if(require.main===module){const dir=path.join(__dirname,'evidence');fs.mkdirSync(dir,{recursive:true});fs.writeFileSync(path.join(dir,'open-wire-diagnosis.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));}
module.exports=report;
