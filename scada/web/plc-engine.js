/* A real interpreter for the supplied ladder networks, not a hidden batch FSM. */
(function(root){
  'use strict';
  class LadderPLC {
    constructor(program){this.program=program;this.bits={};this.edges={};this.timers={};this.trace=[];this.scans=0;}
    contact(term){return term.startsWith('!')?!Boolean(this.bits[term.slice(1)]):Boolean(this.bits[term]);}
    scan(inputs,dt=this.program.scan_seconds){
      if(!Number.isFinite(dt)||dt<=0||dt>1)throw Error('Scan timestep must be in (0,1]');
      Object.assign(this.bits,inputs);this.trace=[];
      for(const rung of this.program.rungs){let result;const before={...this.bits};
        if(rung.op==='R_TRIG'){const value=Boolean(this.bits[rung.source]);result=value&&!this.edges[rung.id];this.edges[rung.id]=value;}
        else if(rung.op==='TON'){const enabled=Boolean(this.bits[rung.source]);this.timers[rung.id]=enabled?(this.timers[rung.id]||0)+dt:0;result=this.timers[rung.id]+1e-9>=rung.preset;}
        else if(rung.op==='OTE'){const series=(rung.series||[]).every(term=>this.contact(term));const branch=!rung.branches||rung.branches.some(terms=>terms.every(term=>this.contact(term)));result=series&&branch;}
        else throw Error('Unsupported ladder instruction: '+rung.op);
        this.bits[rung.target]=Boolean(result);this.trace.push({id:rung.id,target:rung.target,energized:Boolean(result),before,elapsed:rung.op==='TON'?this.timers[rung.id]:null});
      }
      this.scans++;return {...this.bits};
    }
  }
  class Bench {
    constructor(program){this.program=program;this.plc=new LadderPLC(program);this.level=0;this.stopOK=true;this.overloadOK=true;this.brokenHighWire=false;this.stuckValve=false;this.buttons={};this.time=0;this.inputs={};this.scan();}
    press(tag){if(!['START_PB','DRAIN_PB','RESET_PB'].includes(tag))throw Error('Unknown pushbutton');this.buttons[tag]=true;}
    scan(dt=this.program.scan_seconds){
      this.inputs={STOP_OK:this.stopOK,OL_OK:this.overloadOK,HIGH_OK:this.level<this.program.target_litres&&!this.brokenHighWire,LOW_WET:this.level>.1,START_PB:!!this.buttons.START_PB,DRAIN_PB:!!this.buttons.DRAIN_PB,RESET_PB:!!this.buttons.RESET_PB};
      const output=this.plc.scan(this.inputs,dt);
      if(output.FILL_OUT&&!this.stuckValve)this.level=Math.min(60,this.level+2*dt);
      if(output.DRAIN_OUT)this.level=Math.max(0,this.level-2*dt);
      this.buttons={};this.time+=dt;return output;
    }
    measurements(){const sensor=this.level<this.program.target_litres?24:0;return {source_24v:24,common_0v:0,sensor_contact_output: sensor,wire_104_upstream:sensor,wire_104_plc_end:this.brokenHighWire?0:sensor,plc_I0_3:this.inputs.HIGH_OK?24:0};}
  }
  function renderLadder(program,trace=[]){
    const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const green='#18796e',gray='#a4b4bb';let svg=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1180 ${program.rungs.length*170+40}" role="img" aria-label="Executable ladder networks for fill and drain control"><rect width="1180" height="100%" fill="#fff"/>`;
    for(let i=0;i<program.rungs.length;i++){
      const r=program.rungs[i],state=trace.find(t=>t.id===r.id),bits=state?.before||{},top=i*170,y=top+62,color=state?.energized?green:gray;
      svg+=`<text x="24" y="${top+22}" fill="#264944" font-family="sans-serif" font-size="12">${r.id} · ${escape(r.title)}</text><path d="M25 ${top+34}V${top+154}M1135 ${top+34}V${top+154}M25 ${y}H1065M1095 ${y}H1135" fill="none" stroke="${color}" stroke-width="2"/>`;
      const contact=(term,x,cy)=>{const neg=term.startsWith('!'),tag=neg?term.slice(1):term,closed=neg?!bits[tag]:!!bits[tag],c=state&&closed?green:gray;return `<rect x="${x-24}" y="${cy-16}" width="48" height="32" fill="white"/><path d="M${x-24} ${cy}h16M${x-8} ${cy-12}v24M${x+8} ${cy-12}v24M${x+8} ${cy}h16${neg?`M${x-13} ${cy+14}l26 -28`:''}" fill="none" stroke="${c}" stroke-width="2"/><text x="${x}" y="${cy-21}" text-anchor="middle" fill="#49615f" font-family="monospace" font-size="10">${escape(tag)}</text>`;};
      if(r.op==='OTE'){
        const series=r.series||[];series.forEach((term,j)=>svg+=contact(term,95+j*127,y));
        if(r.branches){const bx=series.length?95+series.length*127:95,bw=Math.max(...r.branches.map(b=>b.length))*127;
          if(r.branches.length>1)svg+=`<path d="M${bx-52} ${y}V${y+(r.branches.length-1)*36}H${bx+bw-50}V${y}" fill="none" stroke="${gray}" stroke-width="2"/>`;
          r.branches.forEach((branch,j)=>{const by=y+j*36;svg+=`<path d="M${bx-52} ${by}H${bx+bw-50}" stroke="${gray}" stroke-width="2"/>`;branch.forEach((term,k)=>svg+=contact(term,bx+k*127,by));});
        }
      } else {
        svg+=contact(r.source,110,y)+`<rect x="280" y="${y-24}" width="220" height="49" rx="4" fill="#f1f6f3" stroke="${color}"/><text x="390" y="${y-3}" text-anchor="middle" font-size="12" font-family="monospace" fill="#264944">${r.op}</text><text x="390" y="${y+14}" text-anchor="middle" font-size="10" font-family="monospace" fill="#5e7672">${r.op==='TON'?`PT=${r.preset}s${state?` · ET=${state.elapsed.toFixed(1)}s`:``}`:'one scan on rising edge'}</text>`;
      }
      svg+=`<rect x="1049" y="${y-16}" width="61" height="32" fill="white"/><path d="M1072 ${y-13}q-16 13 0 26M1085 ${y-13}q16 13 0 26" fill="none" stroke="${color}" stroke-width="2"/><text x="1080" y="${y-23}" text-anchor="middle" font-family="monospace" font-size="10" fill="#264944">${escape(r.target)}</text>`;
    }
    svg+='</svg>';return svg;
  }
  if(typeof module!=='undefined'&&module.exports)module.exports={LadderPLC,Bench,renderLadder};else root.PLCTrainer={LadderPLC,Bench,renderLadder};
})(typeof window==='undefined'?globalThis:window);
