import {el,svgEl,signals,finite,format,unit,labelFor,displayValue} from './data.js';
import {chart} from './charts.js';
const colors={normal:'#08796d',warning:'#a86b0d',critical:'#b52e3f',missing:'#718093'};
const priority={normal:0,missing:1,warning:2,critical:3,trip:3};
function statusFor(state,id,kind){
  const row=state.result.physical.series[state.index].observation,index=state.result.physical.cells.indexOf(id);
  const raw=kind==='temperature'?row.temperature_K[index]:row.pressure_kPa[index];
  if(!finite(raw))return 'missing';
  const tm=state.result.physical.series[state.index].time_s;
  const active=state.alarms.filter(a=>a.equipment===id&&a.time_s<=tm&&(a.resolved_at_s===null||a.resolved_at_s>tm)
    &&(!kind||a.signal===(kind==='pressure'?'pressure_kPa':'temperature_K')||kind==='temperature'&&a.signal==='sensor_difference_K'||a.signal==='protection'));
  if(active.some(a=>['critical','trip'].includes(a.level)))return 'critical';
  if(active.length)return 'warning';
  return state.source==='imported'?'missing':'normal';
}
function histogram(state,kind,t){
  const data=signals(state.result,state.index,state.profile).filter(s=>s.kind===kind),width=680,left=120,right=555,rowHeight=29,height=45+data.length*rowHeight;
  const values=data.flatMap(s=>[s.value,s.reference]).filter(finite);
  const low=Math.min(0,...values),high=Math.max(...values,1)*1.08,scale=v=>left+(v-low)/(high-low)*(right-left);
  const svg=svgEl('svg',{viewBox:'0 0 '+width+' '+height,role:'img','aria-label':t(kind)+' · '+t('allParameters'),'data-wall-histogram':kind});
  for(let tick=0;tick<=4;tick++){
    const value=low+(high-low)*tick/4,x=scale(value);
    svg.append(svgEl('line',{x1:x,x2:x,y1:25,y2:height-8,class:'chart-grid'}),svgEl('text',{x,y:17,'text-anchor':'middle',class:'wall-svg-label'},format(value,1,state.profile.language)));
  }
  data.forEach((s,i)=>{
    const y=32+i*rowHeight,status=statusFor(state,s.id,kind);
    svg.append(svgEl('text',{x:left-10,y:y+15,'text-anchor':'end',class:'wall-svg-label'},s.id));
    if(finite(s.value))svg.append(svgEl('rect',{x:Math.min(scale(0),scale(s.value)),y,width:Math.abs(scale(s.value)-scale(0)),height:20,rx:3,fill:colors[status]}));
    if(finite(s.reference))svg.append(svgEl('line',{x1:scale(s.reference),x2:scale(s.reference),y1:y-2,y2:y+22,class:'reference-marker'}));
    svg.append(svgEl('text',{x:right+12,y:y+15,class:'wall-svg-value'},
      finite(s.value)?format(s.value,2,state.profile.language)+' '+unit(kind,state.profile):t('missing')));
  });
  return el('div',{class:'wall-histogram'},svg,el('p',{class:'small muted'},t('referenceMarker')));
}
function eventStrip(state,t){
  const end=state.result.physical.series.at(-1).time_s,tm=state.result.physical.series[state.index].time_s;
  const svg=svgEl('svg',{viewBox:'0 0 680 150',role:'img','aria-label':t('eventTimeline'),'data-wall-event-timeline':true});
  const levels=['warning','critical','trip'];
  levels.forEach((level,i)=>{
    const y=35+i*35;
    svg.append(svgEl('text',{x:110,y:y+4,'text-anchor':'end',class:'wall-svg-label'},t(level)),svgEl('line',{x1:130,x2:655,y1:y,y2:y,class:'chart-grid'}));
    for(const event of state.alarms.filter(a=>a.level===level&&a.time_s<=tm)){
      const x=130+event.time_s/(end||1)*525;
      const marker=svgEl('circle',{cx:x,cy:y,r:7,fill:colors[level==='trip'?'critical':level]});
      marker.append(svgEl('title',{},event.equipment+' · '+t(event.title)+' · '+event.time_s+' s'));svg.append(marker);
    }
  });
  svg.append(svgEl('text',{x:130,y:145,class:'wall-svg-label'},'0 s'),svgEl('text',{x:655,y:145,'text-anchor':'end',class:'wall-svg-label'},end+' s'));
  return svg;
}
function worst(statuses){return statuses.reduce((a,b)=>priority[b]>priority[a]?b:a,'normal');}
export function wallView(state,t,callbacks){
  const p=state.result.physical,row=p.series[state.index],o=row.observation,profile=state.profile,f=v=>format(v,2,profile.language);
  const card=(title,...children)=>el('section',{class:'card wall-card'},el('h2',{},title),...children);
  const root=el('div',{class:'wall-screen'+(profile.wall.dense?' compact':''),style:'--wall-scale:'+profile.wall.scale});
  const tools=el('div',{class:'toolbar wall-tools'},
    el('div',{},el('strong',{},profile.site),el('p',{class:'muted'},t('wallBoundary'))),
    el('div',{class:'wall-clock'},el('span',{},t('clock')),el('time',{id:'wall-clock'})),
    el('button',{type:'button',id:'wall-fullscreen',onclick:callbacks.fullscreen},t(document.fullscreenElement?'exitFullscreen':'fullscreen')),
    el('label',{class:'check-label'},el('input',{id:'wall-auto',type:'checkbox',checked:profile.wall.autoRefresh&&state.source!=='imported',disabled:state.source==='imported',onchange:e=>callbacks.preference('autoRefresh',e.target.checked)}),t('autoRefresh')),
    el('label',{class:'field wall-scale'},el('span',{},t('wallScale')),el('input',{id:'wall-scale',type:'range',min:80,max:160,step:10,value:profile.wall.scale*100,oninput:e=>callbacks.preference('scale',Number(e.target.value)/100)})),
    el('label',{class:'check-label'},el('input',{id:'wall-dense',type:'checkbox',checked:profile.wall.dense,onchange:e=>callbacks.preference('dense',e.target.checked)}),t('dense')));
  root.append(tools);
  const loopBindings={feed:p.cells.filter((_,i)=>p.roles[i]==='heater'),separation:p.cells.filter((_,i)=>['column','reboiler'].includes(p.roles[i])),
    condensation:p.cells.filter((_,i)=>p.roles[i]==='condenser'),reflux:[p.cells[1],...p.cells.filter((_,i)=>p.roles[i]==='condenser')],
    cooling:p.cells.filter((_,i)=>p.roles[i]==='condenser'),protection:[p.cells[0],...p.cells.filter((_,i)=>p.roles[i]==='condenser')]};
  const loopGrid=el('div',{class:'wall-loops'});
  for(const loop of profile.loops){
    const status=loop==='protection'?(o.protection.latched?'critical':'normal'):worst(loopBindings[loop].flatMap(id=>[statusFor(state,id,'temperature'),statusFor(state,id,'pressure')]));
    loopGrid.append(el('section',{class:'wall-loop '+status,'data-wall-loop':loop},el('span',{},t(loop)),el('strong',{},(status==='normal'?'● ':status==='missing'?'? ':'! ')+t(status)),el('small',{},t('observedLoop'))));
  }
  root.append(loopGrid);
  const tiles=el('div',{class:'wall-signal-grid'});
  for(let i=0;i<p.cells.length;i++){
    const id=p.cells[i],tempStatus=statusFor(state,id,'temperature'),pressureStatus=statusFor(state,id,'pressure'),status=worst([tempStatus,pressureStatus]);
    const tile=el('section',{class:'wall-equipment '+status,'data-wall-equipment':id},el('div',{class:'wall-equipment-title'},el('strong',{},labelFor(id,profile)),el('span',{},t(p.roles[i]))));
    const values=el('div',{class:'wall-values'});
    for(const [kind,key,level] of [['temperature','temperature_K',tempStatus],['pressure','pressure_kPa',pressureStatus]]){
      const raw=o[key][i],value=displayValue(raw,kind,profile);
      values.append(el('div',{class:'wall-value '+level,'data-wall-signal':id+'.'+kind},el('span',{},t(kind)),
        el('div',{},el('strong',{},f(value)),el('small',{},unit(kind,profile))),el('small',{},t(finite(raw)?level:'missing'))));
    }
    tile.append(values);tiles.append(tile);
  }
  root.append(tiles);
  const counts={normal:0,warning:0,critical:0,missing:0};
  p.cells.forEach(id=>counts[worst([statusFor(state,id,'temperature'),statusFor(state,id,'pressure')])]++);
  const statusBar=el('div',{class:'wall-state-bar','aria-label':t('states')});
  for(const [kind,count] of Object.entries(counts))if(count)statusBar.append(el('span',{class:kind,style:'flex:'+count},t(kind)+' · '+count));
  const alerts=state.alarms.filter(a=>a.time_s<=row.time_s&&(a.resolved_at_s===null||a.resolved_at_s>row.time_s)).sort((a,b)=>(priority[b.level]-priority[a.level])||b.time_s-a.time_s);
  const eventList=el('div',{class:'wall-alerts'});
  for(const event of alerts)eventList.append(el('div',{class:'wall-alert '+(event.level==='trip'?'critical':event.level)},el('strong',{},'! '+event.equipment+' · '+t(event.title)),el('span',{},t('detected')+' '+event.time_s+' s')));
  if(!alerts.length)eventList.append(el('div',{class:'wall-alert normal'},t('noEvents')));
  root.append(el('div',{class:'wall-middle'},card(t('histTemperature'),histogram(state,'temperature',t)),card(t('histPressure'),histogram(state,'pressure',t)),
    card(t('states'),statusBar,el('div',{class:'wall-diagnosis'},el('span',{},t('rootCause')+' · '+t('analysisTime')+' '+p.series.at(-1).time_s+' s'),
      el('strong',{},t(state.result.diagnosis.label))),el('h2',{},t('events')),eventList,el('h2',{},t('eventTimeline')),eventStrip(state,t))));
  const condensers=p.roles.map((role,i)=>role==='condenser'?i:-1).filter(i=>i>=0),column=p.roles.map((role,i)=>role==='column'?i:-1).filter(i=>i>=0);
  const trends=el('div',{class:'wall-trends'});
  for(const [title,indices,kind] of [[t('condensation')+' · '+t('pressure'),condensers,'pressure'],[t('feed')+' · '+t('temperature'),[0],'temperature'],
    [t('separation')+' · '+t('temperature')+' max',column,'temperature'],[t('reboiler')+' · '+t('temperature'),[p.roles.indexOf('reboiler')],'temperature']])
    trends.append(card(title,chart(state.result,indices,kind,profile,state.index,null,callbacks.time,t)));
  root.append(trends);return root;
}
