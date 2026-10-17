export const finite=v=>typeof v==='number'&&Number.isFinite(v);
export function validateResult(input){
  const value=input?.schema==='refinery-workspace/v1'?input.result:input;
  const p=value?.physical;
  if(!value||typeof value.event_id!=='string'||value.event_id.length>100||!p||!Array.isArray(p.cells)||!Array.isArray(p.roles)||p.cells.length!==p.roles.length||p.cells.length<3||p.cells.length>30)throw Error('Invalid result equipment');
  if(!['A','B','C'].includes(p.configuration)||new Set(p.cells).size!==p.cells.length||!p.cells.every(id=>typeof id==='string'&&/^[A-Za-z0-9:-]{1,64}$/.test(id)))throw Error('Unsupported equipment configuration');
  if(!p.roles.every(r=>['heater','column','reboiler','condenser'].includes(r)))throw Error('Unsupported role');
  const expectedRoles=['heater',...Array(p.configuration==='B'?8:6).fill('column'),'reboiler',...Array(p.configuration==='C'?2:1).fill('condenser')];
  if(JSON.stringify(p.roles)!==JSON.stringify(expectedRoles))throw Error('Configuration role binding mismatch');
  if(!Array.isArray(p.series)||p.series.length<2||p.series.length>10000)throw Error('Invalid time series');
  let previous=-Infinity;
  for(const row of p.series){
    if(!finite(row.time_s)||row.time_s<=previous||row.time_s<0||row.time_s>120)throw Error('Time must increase');
    previous=row.time_s;const o=row.observation;
    if(!o||!finite(o.time_s)||Math.abs(o.time_s-row.time_s)>1e-7||JSON.stringify(o.equipment)!==JSON.stringify(p.cells)||JSON.stringify(o.roles)!==JSON.stringify(p.roles))throw Error('Observation topology or timestamp mismatch');
    for(const key of ['temperature_K','pressure_kPa']){
      if(!Array.isArray(o[key])||o[key].length!==p.cells.length||!o[key].every(v=>v===null||finite(v)))throw Error('Invalid observed signal');
    }
    if(!o.protection||typeof o.protection.latched!=='boolean')throw Error('Missing protection observation');
    if(o.heater_reference_K!==null&&!finite(o.heater_reference_K))throw Error('Invalid independent sensor');
  }
  if(!Array.isArray(p.topology)||p.topology.some(e=>!p.cells.includes(e.source)||!p.cells.includes(e.target)||!['material','vapor','liquid','reflux'].includes(e.type)))throw Error('Invalid physical topology');
  if(!value.diagnosis||!['normal','unknown','cooling_loss','heater_loss','sensor_bias'].includes(value.diagnosis.label)||!Number.isInteger(value.diagnosis.model_version))throw Error('Invalid diagnostic decision');
  const d=value.diagnosis;
  if(d.features!==undefined&&(!d.features||typeof d.features!=='object'||Array.isArray(d.features)||Object.values(d.features).some(v=>v!==null&&!finite(v))))throw Error('Invalid diagnostic features');
  if(d.ranking!==undefined&&(!Array.isArray(d.ranking)||d.ranking.length>10||d.ranking.some(x=>!x||!['normal','unknown','cooling_loss','heater_loss','sensor_bias'].includes(x.label)||!finite(x.similarity)||Math.abs(x.similarity)>1.0000001)))throw Error('Invalid hypothesis ranking');
  if(d.causal_chain!==undefined&&(!Array.isArray(d.causal_chain)||d.causal_chain.some(id=>!p.cells.includes(id))))throw Error('Invalid causal chain');
  if(!Array.isArray(p.component_balance_residual_mol)||!p.component_balance_residual_mol.every(finite)||!finite(p.energy_balance_residual_J))throw Error('Missing conservation evidence');
  if(value.reference){
    if(JSON.stringify(value.reference.cells)!==JSON.stringify(p.cells)||!Array.isArray(value.reference.series))throw Error('Invalid nominal reference');
    for(const row of value.reference.series){
      if(!finite(row.time_s)||!row.observation||!['temperature_K','pressure_kPa'].every(k=>Array.isArray(row.observation[k])&&row.observation[k].length===p.cells.length&&row.observation[k].every(v=>v===null||finite(v))))throw Error('Invalid reference signal');
    }
  }
  const f=value.action_forecast;
  if(f?.available){
    if(!Array.isArray(f.ranking)||!f.forecasts||f.ranking.length>4||!f.ranking.length)throw Error('Invalid forecasts');
    if(!Array.isArray(f.assumptions)||f.assumptions.some(x=>typeof x!=='string'||x.length>1000))throw Error('Invalid forecast assumptions');
    for(const entry of f.ranking){
      if(!['hold','restore_cooling','reduce_heat','reduce_feed'].includes(entry.action)||!finite(entry.final_condenser_pressure_Pa)||!finite(entry.product_mol))throw Error('Invalid forecast action');
      const forecast=f.forecasts[entry.action],series=forecast?.series;
      if(JSON.stringify(forecast.cells)!==JSON.stringify(p.cells)||JSON.stringify(forecast.roles)!==JSON.stringify(p.roles))throw Error('Forecast topology mismatch');
      if(!Array.isArray(series)||!series.length||series.length>1000)throw Error('Invalid forecast series');
      let tm=-Infinity;
      for(const row of series){
        if(!finite(row.time_s)||row.time_s<=tm||row.time_s<p.series.at(-1).time_s||!['temperature_K','pressure_Pa'].every(k=>Array.isArray(row[k])&&row[k].length===p.cells.length&&row[k].every(v=>v===null||finite(v))))throw Error('Invalid forecast values');
        tm=row.time_s;
      }
    }
  }
  return structuredClone(value);
}
export function referenceAt(result,time){
  const rows=result.reference?.series||[];
  return rows.find(r=>Math.abs(r.time_s-time)<1e-7)?.observation||null;
}
export function displayValue(raw,kind,profile){
  if(!finite(raw))return null;
  return kind==='temperature'&&profile.units.temperature==='C'?raw-273.15:kind==='pressure'&&profile.units.pressure==='bar'?raw/100:raw;
}
export function unit(kind,profile){return kind==='temperature'?(profile.units.temperature==='C'?'°C':'K'):profile.units.pressure;}
export function format(value,digits=2,language='ru'){
  return finite(value)?new Intl.NumberFormat(language==='ru'?'ru-RU':'en-US',{maximumFractionDigits:digits}).format(Object.is(value,-0)?0:value):'—';
}
export function tagFor(id,kind,profile){return profile.tags[id]?.[kind]||id+'.'+(kind==='temperature'?'TT':'PT');}
export function labelFor(id,profile){return profile.tags[id]?.label||id;}
export function signals(result,index,profile){
  const row=result.physical.series[index],ref=referenceAt(result,row.time_s),source=row.observation;
  return result.physical.cells.flatMap((id,i)=>['temperature','pressure'].map(kind=>{
    const key=kind==='temperature'?'temperature_K':'pressure_kPa',raw=source[key][i],baseline=ref?.[key]?.[i];
    return {id,kind,tag:tagFor(id,kind,profile),label:labelFor(id,profile),role:result.physical.roles[i],raw,
      baseline,delta:finite(raw)&&finite(baseline)?raw-baseline:null,
      value:displayValue(raw,kind,profile),reference:displayValue(baseline,kind,profile),
      quality:finite(raw)?'simulated':'missing',time_s:row.time_s};
  }));
}
export function alarms(result,profile){
  const p=result.physical,limits=profile.limits,events=[],open=new Map();
  p.series.forEach((row,index)=>{
    const o=row.observation,ref=referenceAt(result,row.time_s),rules=[];
    p.cells.forEach((id,i)=>{
      if(p.roles[i]==='condenser'){
        rules.push({rule:'pressureLimit',id,i,signal:'pressure_kPa',value:o.pressure_kPa[i],limit:limits.pressureWarning,level:'warning'});
        rules.push({rule:'pressureCritical',title:'pressureLimit',id,i,signal:'pressure_kPa',value:o.pressure_kPa[i],limit:limits.pressureCritical,level:'critical'});
      }
      if(p.roles[i]==='heater'){
        rules.push({rule:'temperatureLimit',id,i,signal:'temperature_K',value:o.temperature_K[i],limit:limits.temperatureWarning,level:'warning'});
        rules.push({rule:'temperatureCritical',title:'temperatureLimit',id,i,signal:'temperature_K',value:o.temperature_K[i],limit:limits.temperatureCritical,level:'critical'});
        rules.push({rule:'sensorDifference',id,i,signal:'sensor_difference_K',value:finite(o.temperature_K[i])&&finite(o.heater_reference_K)?Math.abs(o.temperature_K[i]-o.heater_reference_K):null,limit:limits.sensorDifference,level:'critical'});
      }
      if(finite(ref?.pressure_kPa?.[i]))rules.push({rule:'pressureDeviation',id,i,signal:'pressure_kPa',value:o.pressure_kPa[i],limit:ref.pressure_kPa[i]+limits.pressureDeviation,level:'warning'});
    });
    rules.push({rule:'tripEvent',id:p.cells[0],signal:'protection',value:o.protection.latched?1:0,limit:0,level:'trip'});
    const activeKeys=new Set(),evaluatedKeys=new Set();
    for(const rule of rules){
      const key=rule.rule+'|'+rule.id;
      if(finite(rule.value))evaluatedKeys.add(key);
      if(finite(rule.value)&&rule.value>rule.limit){
        activeKeys.add(key);
        if(!open.has(key)){
          const event={...rule,title:rule.title||rule.rule,equipment:rule.id,id:key+'|'+index,time_s:row.time_s,resolved_at_s:null};
          events.push(event);open.set(key,event);
        }
      }
    }
    for(const [key,event] of open)if(evaluatedKeys.has(key)&&!activeKeys.has(key)){event.resolved_at_s=row.time_s;open.delete(key);}
  });
  return events;
}
export function alarmEvidence(a){return {id:a.id,equipment:a.equipment,signal:a.signal,time_s:a.time_s,value:a.value,limit:a.limit};}
export function csv(result,profile){
  const quote=v=>'"'+(typeof v==='string'?v.replace(/^\s*[=+@-]/,"'$&"):String(v??'')).replaceAll('"','""')+'"';
  const rows=[['event_id','model_time_s','equipment','tag','signal','value','unit','reference','delta_base_unit','quality']];
  result.physical.series.forEach((row,index)=>signals(result,index,profile).forEach(s=>rows.push([result.event_id,s.time_s,s.id,s.tag,s.kind,s.value,unit(s.kind,profile),s.reference,s.delta,s.quality])));
  return '\uFEFF'+rows.map(row=>row.map(quote).join(',')).join('\r\n');
}
export function exportEnvelope(result,profile,verification=false){
  const value=structuredClone(result);
  if(!verification){delete value.evaluation;delete value.physical.private_truth;
    for(const f of Object.values(value.action_forecast?.forecasts||{}))delete f.private_truth;
    if(value.reference)delete value.reference.private_truth;}
  return {schema:'refinery-workspace/v1',exported_at:new Date().toISOString(),source_verified:false,
    context:{profile:structuredClone(profile),verification_included:verification},result:value};
}
export function el(tag,attrs={},...children){
  const node=document.createElement(tag);
  for(const [k,v] of Object.entries(attrs)){
    if(k.startsWith('on')&&typeof v==='function')node.addEventListener(k.slice(2),v);
    else if(k==='class')node.className=v;
    else if(k==='text')node.textContent=v;
    else if(v!==false&&v!==null&&v!==undefined)node.setAttribute(k,v===true?'':String(v));
  }
  for(const child of children.flat())if(child!==null&&child!==undefined)node.append(child instanceof Node?child:document.createTextNode(String(child)));
  return node;
}
export function svgEl(tag,attrs={},text){
  const node=document.createElementNS('http://www.w3.org/2000/svg',tag);
  for(const [k,v] of Object.entries(attrs))node.setAttribute(k,String(v));
  if(text!==undefined)node.textContent=text;
  return node;
}
