import {loadProfile,saveProfile,validateProfile,translate} from './config.js';
import {el,finite,validateResult,signals,alarms,alarmEvidence,format,displayValue,unit,labelFor,referenceAt,csv,exportEnvelope} from './data.js';
import {drawDiagram} from './diagram.js';
import {chart} from './charts.js';
import {wallView} from './wall.js';
const VIEWS=['overview','signals','wall','diagnostics','scenarios','events','reports','settings'];
const $=id=>document.getElementById(id);
const state={profile:loadProfile(),result:null,source:'simulation',index:0,selected:null,view:'overview',layers:{material:true,thermal:true,control:false,causal:false},
 loop:'all',zoom:1,pan:{x:0,y:0},actions:new Set(),annotations:[],hash:null,window:null,playing:false,job:null,status:null,search:'',issues:false,sort:false,verification:false,message:null};
let timer=null,polling=false,pendingRequest=null;
const t=key=>translate(key,state.profile.language),f=(v,d=2)=>format(v,d,state.profile.language);
const button=(text,id,fn,extra={})=>el('button',{type:'button',id,onclick:fn,...extra},text);
const badge=(text,kind='neutral')=>el('span',{class:'badge '+kind},text);
const label=(text,id,input)=>el('label',{for:id,class:'field'},el('span',{},text),input);
const card=(title,...children)=>el('section',{class:'card'},el('div',{class:'card-heading'},el('h2',{},title)),...children);
const paragraph=(text,cls='muted')=>el('p',{class:cls},text);
const lastTime=()=>state.result?.physical.series.at(-1).time_s||0,currentTime=()=>state.result?.physical.series[state.index].time_s||0;
const activeAlarms=()=>state.alarms?.filter(a=>a.time_s<=currentTime()&&(a.resolved_at_s===null||a.resolved_at_s>currentTime()))||[];
function storage(key,value){try{localStorage.setItem(key,JSON.stringify(value));}catch{notice('Browser storage unavailable; use server archive',true);}}
function notice(text,error=false){state.message={text,error};renderBanner();}
async function api(path,options={}){const res=await fetch('/api/industry/'+path,{...options,headers:{'Content-Type':'application/json',...options.headers}});const value=await res.json();if(!res.ok){const error=Error(value.error||('HTTP '+res.status));error.status=res.status;throw error;}return value;}
function download(name,content,type){const url=URL.createObjectURL(new Blob([content],{type})),a=el('a',{href:url,download:name});document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);notice(t('exported'));}
function table(headers,rows){return el('div',{class:'table-scroll',tabindex:0,role:'region','aria-label':headers.join(' · ')},el('table',{},el('thead',{},el('tr',{},headers.map(h=>el('th',{scope:'col'},h)))),el('tbody',{},rows.map(row=>el('tr',{},row.map(v=>el('td',{},v)))))));}
function render(){
 const active=document.activeElement,focus=active?{id:active.id,equipment:active.dataset?.equipment,start:active.selectionStart,end:active.selectionEnd}:null;
 document.documentElement.lang=state.profile.language;document.documentElement.dataset.theme=state.profile.theme;
 document.body.classList.toggle('wall-mode',state.view==='wall');
 $('project-name').textContent=state.profile.project;$('site-name').textContent=state.profile.site;
 $('navigation').replaceChildren(...VIEWS.map((key,i)=>button('', 'nav-'+key,()=>navigate(key),{'aria-current':state.view===key?'page':null,class:'nav-item'})));
 VIEWS.forEach((key,i)=>$('nav-'+key).append(el('span',{'aria-hidden':true,class:'nav-icon'},['\u25c8','\u2301','\u25a6','\u25c7','\u21c4','\u2691','\u25a4','\u2699'][i]),el('span',{},t(key))));
 $('new-run').textContent='+ '+t('run');$('history-open').textContent=t('history');$('theme-toggle').textContent=state.profile.theme==='light'?'◐':'☀';$('theme-toggle').setAttribute('aria-label',t('theme'));
 $('workspace-title').textContent=t(state.view);$('mode-label').textContent=t('noActuation');renderContext();renderBanner();renderJob();
 document.querySelector('.skip-link').textContent=t('skip');document.querySelector('.sidebar-caption').textContent=t('workspace');
 document.querySelector('.eyebrow').textContent=t('intelligence');document.querySelector('.sidebar-footer a').textContent=t('legacyTools')+' ↗';
 $('navigation').setAttribute('aria-label',t('menu'));
 $('context').setAttribute('role','region');$('context').setAttribute('aria-label',t('source'));
 const container=$('view');container.replaceChildren();
 if(state.view==='settings')container.append(settingsView());
 else if(!state.result)container.append(el('section',{class:'empty-state'},el('div',{'aria-hidden':true,class:'empty-icon'},'◈'),el('h2',{},t('noResult')),paragraph(t('historyBoundary')),
  el('div',{class:'toolbar'},button(t('history'),'empty-history',openHistory),button(t('importResult'),'empty-import',()=>fileInput('result')),button(t('run'),'empty-run',openRun,{class:'primary'}))));
 else{state.alarms=alarms(state.result,state.profile);container.append(({overview:overviewView,signals:signalsView,wall:()=>wallView(state,t,{time:setTime,fullscreen:toggleFullscreen,preference:wallPreference}),diagnostics:diagnosticsView,scenarios:scenariosView,events:eventsView,reports:reportsView})[state.view]());
  if(['overview','signals','diagnostics','scenarios','events'].includes(state.view))container.prepend(timeline());}
 $('scope-footer').textContent=t('simulationBoundary');
 $('expand-all').textContent=t('expandAll');updateClock();
 const next=focus?.id?$(focus.id):focus?.equipment?document.querySelector('[data-equipment="'+CSS.escape(focus.equipment)+'"]'):null;
 if(next){next.focus({preventScroll:true});if(typeof focus.start==='number'&&next.type!=='number')try{next.setSelectionRange(focus.start,focus.end);}catch{}}
}
function wallPreference(key,value){state.profile.wall[key]=value;saveProfile(state.profile);render();}
async function toggleFullscreen(){try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch{notice(t('fullscreenUnavailable'),true);}}
function updateClock(){const clock=$('wall-clock');if(clock){const now=new Date();clock.dateTime=now.toISOString();clock.textContent=now.toLocaleTimeString(state.profile.language==='ru'?'ru-RU':'en-US');}}
let refreshingWall=false;
async function refreshWall(){
 if(refreshingWall||state.view!=='wall'||!state.profile.wall.autoRefresh||state.source==='imported'||['queued','running'].includes(state.job?.status))return;
 refreshingWall=true;const event=state.result?.event_id;
 try{const rows=await api('history');if(rows.length&&rows[0].event_id!==event){const value=await api('result?event='+encodeURIComponent(rows[0].event_id));if(state.view==='wall'&&state.source!=='imported'&&state.result?.event_id===event)await acceptResult(value,'replay',rows[0].sha256);}}
 catch{notice(t('offline')+' · '+t('previous'),true);}finally{refreshingWall=false;}
}
function expandAll(){if(!state.result){navigate('signals');return;}state.expanded=true;state.search='';state.issues=false;navigate('signals');}
function expandedSignalsView(){
 const root=el('div',{class:'expanded-signals'}),rows=signals(state.result,state.index,state.profile);
 root.append(button(t('collapseAll'),'collapse-all',()=>{state.expanded=false;render();}));
 for(const id of state.result.physical.cells){const group=rows.filter(s=>s.id===id);root.append(card(labelFor(id,state.profile),table([t('signal'),t('observation'),t('reference')],group.map(s=>[t(s.kind),f(s.value)+' '+unit(s.kind,state.profile),f(s.reference)+' '+unit(s.kind,state.profile)]))));}
 return root;
}
function renderContext(){
 const root=$('context');root.replaceChildren(el('div',{},el('span',{class:'context-label'},t('source')),badge(t(state.source),state.source==='imported'?'warning':'neutral')));
 if(state.result)root.append(el('div',{},el('span',{class:'context-label'},t('config')),el('strong',{},state.result.physical.configuration)),el('div',{},el('span',{class:'context-label'},t('time')),el('strong',{},f(currentTime(),1)+' s')),
  el('div',{},el('span',{class:'context-label'},t('analysisTime')),el('strong',{},f(lastTime(),1)+' s')),
  el('div',{class:'context-id'},el('span',{class:'context-label'},t('resultId')),el('code',{title:state.result.event_id},state.result.event_id.slice(0,25)+'…')));
 const key=state.status?state.status.model_ready?'ready':'pending':'offline';root.append(el('div',{class:'connection'},badge(t(key),key==='ready'?'good':key==='offline'?'warning':'neutral')));
}
function renderBanner(){const root=$('message');root.replaceChildren();root.hidden=!state.message;if(state.message)root.append(el('span',{},state.message.text),button('×','dismiss-message',()=>{state.message=null;renderBanner();},{'aria-label':t('close')}));root.className='message '+(state.message?.error?'error':'');}
function renderJob(){
 const root=$('job');root.replaceChildren();root.hidden=!state.job;const active=state.job&&['queued','running'].includes(state.job.status);$('new-run').disabled=Boolean(active||pendingRequest);
 if(!state.job)return;const key={reference:'referencePhase',forecast:'forecastPhase'}[state.job.stage]||state.job.stage;
 root.append(el('div',{class:'job-title'},el('strong',{},t(active?'processing':key)),el('span',{},t(key))),el('progress',{max:100,value:state.job.percent||0,'aria-label':t('stageProgress')}),paragraph(state.job.error||t('stageProgress')));
 if(!active)root.append(button(t('close'),'dismiss-job',()=>{state.job=null;renderJob();}));if(state.job.error&&active)root.append(button(t('retry'),'retry-job',resumeJob));
}
function navigate(view){if(!VIEWS.includes(view))return;stopPlay();state.view=view;state.window=null;history.replaceState(null,'','#'+view);render();$('workspace-title').focus({preventScroll:true});}
function setTime(index){state.index=Math.max(0,Math.min(state.result.physical.series.length-1,Number(index)));render();}
function stopPlay(){clearInterval(timer);timer=null;state.playing=false;}
function togglePlay(){if(state.playing){stopPlay();render();return;}if(state.index>=state.result.physical.series.length-1)state.index=0;state.playing=true;render();timer=setInterval(()=>{if(state.index>=state.result.physical.series.length-1){stopPlay();render();return;}setTime(state.index+1);},matchMedia('(prefers-reduced-motion: reduce)').matches?1200:600);}
function timeline(){return el('div',{class:'timeline-bar'},button(state.playing?'Ⅱ':'▶','play',togglePlay,{'aria-label':t(state.playing?'pause':'play')}),label(t('time'),'timeline',el('input',{id:'timeline',type:'range',min:0,max:state.result.physical.series.length-1,value:state.index,oninput:e=>setTime(e.target.value)})),
 el('output',{for:'timeline',id:'time-readout'},f(currentTime(),1)+' / '+f(lastTime(),1)+' s'),el('span',{class:'muted small'},t('snapshot')));}
function inspector(){
 const p=state.result.physical,i=p.cells.indexOf(state.selected),o=p.series[state.index].observation,ref=referenceAt(state.result,currentTime());if(i<0)return card(t('equipment'),paragraph(t('empty')));
 const rows=['temperature','pressure'].map(kind=>{const key=kind==='temperature'?'temperature_K':'pressure_kPa';return [t(kind),f(displayValue(o[key][i],kind,state.profile))+' '+unit(kind,state.profile),f(displayValue(ref?.[key]?.[i],kind,state.profile))+' '+unit(kind,state.profile)];});
 const root=card(labelFor(state.selected,state.profile),badge(t(p.roles[i])),table([t('signal'),t('observation'),t('reference')],rows),paragraph(t('time')+' '+f(currentTime(),1)+' s'),badge(t(state.source==='imported'?'unverified':'simulated')));
 for(const a of activeAlarms().filter(x=>x.equipment===state.selected))root.append(paragraph('! '+t(a.title),a.level));
 root.append(button(t('signals'),'inspect-signals',()=>{state.search=state.selected;navigate('signals');},{class:'subtle'}),button(t('diagnostics'),'inspect-diagnosis',()=>navigate('diagnostics'),{class:'subtle'}));return root;
}
function diagramPanel(){
 const root=card(t('equipment')),tools=el('div',{class:'toolbar diagram-toolbar'});
 tools.append(label(t('profile'),'loop-filter',el('select',{id:'loop-filter',onchange:e=>{state.loop=e.target.value;render();}},el('option',{value:'all',selected:state.loop==='all'},t('allLoops')),state.profile.loops.map(key=>el('option',{value:key,selected:state.loop===key},t(key))))));
 const layers=el('fieldset',{class:'layers'},el('legend',{class:'sr-only'},t('equipment')));
 for(const key of ['material','thermal','control','causal'])layers.append(el('label',{class:'check-label'},el('input',{type:'checkbox',id:'layer-'+key,checked:state.layers[key],onchange:e=>{state.layers[key]=e.target.checked;render();}}),t(key)));
 const canvas=el('div',{class:'diagram-canvas',id:'diagram'});drawDiagram(canvas,state,id=>{state.selected=id;render();},t);root.append(tools,layers,canvas);
 root.append(el('div',{class:'toolbar zoom-tools'},button('−','zoom-out',()=>{state.zoom=Math.max(.6,state.zoom-.2);render();},{'aria-label':t('zoomOut')}),button('+','zoom-in',()=>{state.zoom=Math.min(2.5,state.zoom+.2);render();},{'aria-label':t('zoomIn')}),
 button(t('fit'),'zoom-fit',()=>{state.zoom=1;state.pan={x:0,y:0};render();}),el('span',{class:'muted small'},f(state.zoom*100,0)+'%')),paragraph(t('diagramLegend'),'small muted'),
 el('details',{id:'text-topology'},el('summary',{},t('textSummary')),el('ul',{},state.result.physical.topology.map(e=>el('li',{},e.source+' → '+e.target+' · '+t(e.type))))));
 if(state.layers.causal)root.append(paragraph(t('causalAt')+' · '+f(lastTime(),1)+' s','small warning'));return root;
}
function chartWindow(future=false){
 const end=future?Math.max(lastTime(),...Object.values(state.result.action_forecast?.forecasts||{}).map(x=>x.series.at(-1).time_s)):lastTime(),win=state.window||{start:0,end};
 const form=el('form',{class:'toolbar window-controls',onsubmit:e=>{e.preventDefault();const start=Number($('window-start').value),finish=Number($('window-end').value);if(start>=finish){notice(t('invalidWindow'),true);return;}state.window={start,end:finish};render();}});
 form.append(label(t('windowStart'),'window-start',el('input',{id:'window-start',type:'number',step:.1,min:0,max:end,value:win.start,required:true})),label(t('windowEnd'),'window-end',el('input',{id:'window-end',type:'number',step:.1,min:.1,max:end,value:win.end,required:true})),
 el('button',{type:'submit',id:'apply-window'},t('apply')),button(t('resetWindow'),'reset-window',()=>{state.window=null;render();}));return form;
}
function kpi(title,value,sub){return el('section',{class:'kpi'},el('span',{},title),el('strong',{},value),el('small',{},sub));}
function overviewView(){
 const p=state.result.physical,cond=p.roles.map((r,i)=>r==='condenser'?i:-1).filter(i=>i>=0),o=p.series[state.index].observation,nums=cond.map(i=>o.pressure_kPa[i]).filter(finite);
 const kpis=el('div',{class:'kpis'},kpi(t('pressure'),f(displayValue(nums.length===cond.length?Math.max(...nums):null,'pressure',state.profile))+' '+unit('pressure',state.profile),t('condensation')),kpi(t('temperature'),f(displayValue(o.temperature_K[0],'temperature',state.profile))+' '+unit('temperature',state.profile),p.cells[0]),
 kpi(t('events'),String(activeAlarms().length),t(activeAlarms().length?'warning':'normal')),kpi(t('protection'),t(o.protection.latched?'trip':'normal'),t('noActuation')));
 return el('div',{},kpis,el('div',{class:'overview-grid'},diagramPanel(),el('div',{class:'inspector-stack'},inspector(),card(t('rootCause'),el('strong',{class:'diagnostic-name'},t(state.result.diagnosis.label)),paragraph(t('analysisTime')+' '+f(lastTime(),1)+' s'),button(t('evidence'),'open-evidence',()=>navigate('diagnostics'),{class:'subtle'})))),
 chartWindow(),el('div',{class:'two-columns'},card(t('pressure')+' · '+unit('pressure',state.profile),chart(state.result,cond,'pressure',state.profile,state.index,state.window,setTime,t)),card(t('temperature')+' · '+unit('temperature',state.profile),chart(state.result,[0],'temperature',state.profile,state.index,state.window,setTime,t))));
}
function signalsView(){
 if(state.expanded)return expandedSignalsView();
 const root=card(t('signals'));root.append(el('div',{class:'toolbar'},label(t('search'),'signal-search',el('input',{id:'signal-search',type:'search',placeholder:t('search'),value:state.search,oninput:e=>{state.search=e.target.value;fillSignals();}})),
 el('label',{class:'check-label'},el('input',{id:'only-issues',type:'checkbox',checked:state.issues,onchange:e=>{state.issues=e.target.checked;fillSignals();}}),t('onlyIssues')),button(t('sort'),'sort-signals',()=>{state.sort=!state.sort;fillSignals();},{'aria-pressed':state.sort}),
 button(t('exportCsv'),'signal-csv',exportCsv)),el('div',{id:'signal-table'}));queueMicrotask(fillSignals);return root;
}
function fillSignals(){
 if(!$('signal-table'))return;let rows=signals(state.result,state.index,state.profile).filter(s=>(s.tag+' '+s.label+' '+s.id).toLowerCase().includes(state.search.toLowerCase()));
 if(state.issues)rows=rows.filter(s=>!finite(s.raw)||(s.kind==='pressure'?Math.abs(s.delta||0)>=state.profile.limits.pressureDeviation:Math.abs(s.delta||0)>=1));
 if(state.sort)rows.sort((a,b)=>(b.value??-Infinity)-(a.value??-Infinity));
 $('signal-table').replaceChildren(table([t('tag'),t('equipment'),t('signal'),t('value'),t('reference'),t('delta'),t('quality')],rows.map(s=>[el('code',{},s.tag),button(s.label,null,()=>{state.selected=s.id;navigate('overview');},{class:'text-button'}),t(s.kind),f(s.value)+' '+unit(s.kind,state.profile),f(s.reference),
 f(s.kind==='pressure'&&state.profile.units.pressure==='bar'&&finite(s.delta)?s.delta/100:s.delta),badge(t(!finite(s.raw)?'missing':state.source==='imported'?'unverified':'simulated'),!finite(s.raw)?'critical':'neutral')])));
 if(!rows.length)$('signal-table').append(paragraph(t('empty')));
}
function diagnosticsView(){
 const d=state.result.diagnosis,names={heater_temperature_residual_K:[t('temperature')+' H-101 · Δ','K'],heater_sensor_reference_disagreement_K:[t('sensorDifference'),'K'],max_condenser_pressure_residual_kPa:[t('pressure')+' E · Δmax','kPa'],mean_column_pressure_residual_kPa:[t('pressure')+' C · Δmean','kPa'],reboiler_temperature_residual_K:[t('temperature')+' R · Δ','K']};
 const proof=Object.entries(d.features||{}).map(([key,value])=>[names[key]?.[0]||key,f(value,5)+' '+(names[key]?.[1]||'')]),hypotheses=(d.ranking||[]).map(x=>[t(x.label),f(x.similarity,6),x.label===d.label?badge(t('selected'),'good'):'—']);
 const chain=el('div',{class:'causal-chain'});for(const id of d.causal_chain||[])chain.append(button(id,null,()=>{state.selected=id;navigate('overview');},{class:'subtle'}),el('span',{'aria-hidden':true},'→'));
 return el('div',{},card(t('rootCause'),el('div',{class:'diagnosis-summary'},el('strong',{class:'diagnostic-name'},t(d.label)),badge(t('modelVersion')+' '+d.model_version)),paragraph(t('analysisTime')+' '+f(lastTime(),1)+' s · '+t('causalAt')),chain,paragraph(t('uncalibrated'))),
 el('div',{class:'two-columns'},card(t('hypotheses'),table([t('rootCause'),t('similarity'),t('status')],hypotheses)),card(t('evidence'),table([t('feature'),t('value')],proof))),
 card(t('quality'),paragraph(t(state.source==='imported'?'unverified':'simulated')),paragraph(t('simulationBoundary')),paragraph(t('proofFlow'))));
}
function scenariosView(){
 const fc=state.result.action_forecast;if(!fc?.available)return card(t('scenarios'),paragraph(fc?.reason||t('noForecast')),button(t('run'),'forecast-new-run',openRun,{class:'primary'}));
 const p=state.result.physical,i=Math.max(0,p.cells.indexOf(state.selected)),tools=el('div',{class:'toolbar'},label(t('equipment'),'forecast-equipment',el('select',{id:'forecast-equipment',onchange:e=>{state.selected=e.target.value;render();}},p.cells.map(id=>el('option',{value:id,selected:id===state.selected},labelFor(id,state.profile))))));
 for(const item of fc.ranking)tools.append(el('label',{class:'check-label'},el('input',{id:'action-'+item.action,type:'checkbox',checked:state.actions.has(item.action),onchange:e=>{if(e.target.checked)state.actions.add(item.action);else state.actions.delete(item.action);render();}}),t(item.action)));
 const rows=fc.ranking.map(x=>[t(x.action),f(displayValue(x.final_condenser_pressure_Pa/1000,'pressure',state.profile))+' '+unit('pressure',state.profile),f(x.product_mol,4),badge(t(x.trip?'trip':'normal'),x.trip?'critical':'good'),x.action===fc.selected_action?badge(t('selected'),'good'):'—']);
 return el('div',{},card(t('scenarios'),paragraph(t('conditional')),tools,table([t('action'),t('finalPressure'),t('product'),t('protection'),t('status')],rows)),chartWindow(true),
 el('div',{class:'two-columns'},card(t('pressure'),chart(state.result,[i],'pressure',state.profile,state.index,state.window,setTime,t,[...state.actions])),card(t('temperature'),chart(state.result,[i],'temperature',state.profile,state.index,state.window,setTime,t,[...state.actions]))),
 card(t('evidence'),el('ul',{},(fc.assumptions||[]).map(text=>el('li',{},t(({'nominal composition used to estimate inventories from sensors':'assumedComposition','ongoing diagnosed fault with assumed resource severity 0.5':'assumedSeverity','restore_cooling feasible only when resource can actually be restored':'restorationCondition'})[text]||text))))));
}
function eventsView(){
 const acks=new Set(state.annotations.filter(a=>a.kind==='acknowledge').map(a=>a.alarm.id)),rows=state.alarms.filter(a=>a.time_s<=currentTime()).sort((a,b)=>b.time_s-a.time_s).map(a=>[badge(t(a.level),a.level==='trip'?'critical':a.level),
 el('div',{},el('strong',{},t(a.title)),el('small',{class:'block muted'},a.equipment+' · '+f(a.value,3)+' / '+f(a.limit,3))),f(a.time_s,1)+' s',a.resolved_at_s!==null&&a.resolved_at_s<=currentTime()?t('resolved')+' '+f(a.resolved_at_s,1)+' s':t('active'),
 acks.has(a.id)?badge(t('acknowledged'),'good'):button(t('ack'),null,()=>openAnnotation(a),{class:'subtle',disabled:state.source==='imported',title:t(state.source==='imported'?'unverified':'ack')})]);
 const notes=state.annotations.map(a=>[t(a.kind==='acknowledge'?'acknowledged':'note'),a.comment,new Date(a.created_at).toLocaleString(state.profile.language==='ru'?'ru-RU':'en-US'),t('localIdentity')]);
 return el('div',{},card(t('events'),paragraph(t('ackBoundary')),rows.length?table([t('status'),t('alarm'),t('occurred'),t('status'),t('ack')],rows):paragraph(t('noEvents'))),card(t('notes'),
 button(t('note'),'add-note',()=>openAnnotation(null),{class:'primary',disabled:state.source==='imported',title:t(state.source==='imported'?'unverified':'note')}),notes.length?table([t('status'),t('comment'),t('occurred'),t('source')],notes):paragraph(t('empty'))));
}
function exportJson(){download(state.result.event_id+'.json',JSON.stringify(exportEnvelope(state.result,state.profile,state.verification),null,2),'application/json');}
function exportCsv(){download(state.result.event_id+'.csv',csv(state.result,state.profile),'text/csv;charset=utf-8');}
function reportsView(){
 const p=state.result.physical,rows=[[t('resultId'),state.result.event_id],[t('config'),p.configuration],[t('source'),t(state.source)],[t('rootCause'),t(state.result.diagnosis.label)],[t('modelVersion'),state.result.diagnosis.model_version],[t('sourceHash'),state.hash||t('unverified')],
 [t('mass'),Math.max(...p.component_balance_residual_mol.map(Math.abs)).toExponential(4)],[t('energy'),p.energy_balance_residual_J.toExponential(4)]];
 const root=el('div',{class:'report-view'},card(t('reports'),el('div',{class:'toolbar no-print'},button(t('exportJson'),'export-json',exportJson,{class:'primary'}),button(t('exportCsv'),'export-csv',exportCsv),button(t('print'),'print-report',()=>window.print()),button(t('importResult'),'import-result',()=>fileInput('result'))),
 table([t('feature'),t('value')],rows),paragraph(t('simulationBoundary'))),card(t('signals'),table([t('tag'),t('value'),t('quality')],signals(state.result,state.index,state.profile).map(s=>[s.tag,f(s.value)+' '+unit(s.kind,state.profile),t(state.source==='imported'?'unverified':s.quality)]))));
 const verification=el('section',{class:'card no-print'},el('label',{class:'check-label'},el('input',{id:'verification',type:'checkbox',checked:state.verification,onchange:e=>{state.verification=e.target.checked;render();}}),t('verification')));
 if(state.verification)verification.append(paragraph(state.result.evaluation?t(state.result.evaluation.actual_cause)+' · '+String(state.result.evaluation.correct):t('empty')));root.append(verification);return root;
}
function settingsView(){
 const p=state.profile,form=el('form',{id:'profile-form',onsubmit:e=>{e.preventDefault();try{const next=structuredClone(p);for(const key of ['project','site','language','theme'])next[key]=$('profile-'+key).value;next.units={temperature:$('temperature-unit').value,pressure:$('pressure-unit').value};
 for(const key of Object.keys(p.limits))next.limits[key]=Number($('limit-'+key).value);next.tags=JSON.parse($('tag-map').value);const checked=validateProfile(next);state.profile=checked;saveProfile(state.profile);render();notice(t('profileSaved'));}catch(error){notice(t('invalidProfile'),true);}}});
 const basic=card(t('profile'));for(const key of ['project','site'])basic.append(label(t(key),'profile-'+key,el('input',{id:'profile-'+key,value:p[key],maxlength:100,required:true})));
 basic.append(el('div',{class:'two-columns compact'},label(t('language'),'profile-language',el('select',{id:'profile-language'},el('option',{value:'ru',selected:p.language==='ru'},'Русский'),el('option',{value:'en',selected:p.language==='en'},'English'))),
 label(t('theme'),'profile-theme',el('select',{id:'profile-theme'},el('option',{value:'light',selected:p.theme==='light'},t('light')),el('option',{value:'dark',selected:p.theme==='dark'},t('dark'))))));
 const units=card(t('units'),el('div',{class:'two-columns compact'},label(t('temperature'),'temperature-unit',el('select',{id:'temperature-unit'},['K','C'].map(u=>el('option',{value:u,selected:p.units.temperature===u},u==='C'?'°C':u)))),
 label(t('pressure'),'pressure-unit',el('select',{id:'pressure-unit'},['kPa','bar'].map(u=>el('option',{value:u,selected:p.units.pressure===u},u))))));
 const limits=card(t('thresholds')),names={pressureWarning:t('pressure')+' · '+t('warning'),pressureCritical:t('pressure')+' · '+t('critical'),temperatureWarning:t('temperature')+' · '+t('warning'),temperatureCritical:t('temperature')+' · '+t('critical'),pressureDeviation:t('pressureDeviation'),sensorDifference:t('sensorDifference')};
 for(const key of Object.keys(p.limits))limits.append(label(names[key],'limit-'+key,el('input',{id:'limit-'+key,type:'number',min:.001,max:2000,step:'any',value:p.limits[key],required:true})));
 limits.append(paragraph(t('settingsBoundary'),'small muted'));
 const tagMap=el('textarea',{'aria-label':t('tagMap'),id:'tag-map',rows:10,spellcheck:false},JSON.stringify(p.tags,null,2));
 const tagCard=card(t('tags'));
 const ids=state.result?.physical.cells||[];
 function syncTagsToJson(){
   try{
     const draft=validateProfile({...p,tags:JSON.parse(tagMap.value)}).tags;
     ids.forEach((id,index)=>{
       const item={};for(const field of ['label','temperature','pressure']){const value=$('tag-'+field+'-'+index).value.trim();if(value)item[field]=value;}
       if(Object.keys(item).length)draft[id]=item;else delete draft[id];
     });
     tagMap.value=JSON.stringify(draft,null,2);
   }catch{notice(t('invalidProfile'),true);}
 }
 if(ids.length)tagCard.append(table([t('equipment'),t('tagLabel'),t('temperatureTag'),t('pressureTag')],ids.map((id,index)=>[
   el('code',{},id),...['label','temperature','pressure'].map(field=>el('input',{id:'tag-'+field+'-'+index,type:'text',maxlength:100,value:p.tags[id]?.[field]||'',
       placeholder:field==='label'?id:id+'.'+(field==='temperature'?'TT':'PT'),'aria-label':id+' · '+t({label:'tagLabel',temperature:'temperatureTag',pressure:'pressureTag'}[field]),oninput:syncTagsToJson}))])));
 tagMap.oninput=()=>{
   try{const draft=validateProfile({...p,tags:JSON.parse(tagMap.value)}).tags;ids.forEach((id,index)=>{for(const field of ['label','temperature','pressure'])$('tag-'+field+'-'+index).value=draft[id]?.[field]||'';});}catch{}
 };
 tagCard.append(el('details',{id:'advanced-tags'},el('summary',{},t('advancedConfig')),label(t('tags'),'tag-map',tagMap),
   el('pre',{class:'example'},JSON.stringify({'H-101':{label:t('heater'),temperature:'TI-101',pressure:'PI-101'}},null,2))));
 form.append(el('div',{class:'two-columns'},el('div',{},basic,units),el('div',{},limits)),tagCard,
 el('div',{class:'toolbar'},el('button',{type:'submit',class:'primary',id:'profile-apply'},t('apply')),button(t('profileExport'),'profile-export',()=>download('refinery-profile.json',JSON.stringify(state.profile,null,2),'application/json')),button(t('profileImport'),'profile-import',()=>fileInput('profile'))));return form;
}
function dialog(title,content){const node=$('dialog');node.replaceChildren(el('div',{class:'dialog-heading'},el('h2',{id:'dialog-title'},title),button('×','dialog-close',()=>node.close(),{'aria-label':t('close')})),content);node.showModal();return node;}
function openRun(){
 if(pendingRequest||['queued','running'].includes(state.job?.status)){notice(t('processing'));return;}
 const form=el('form',{id:'run-form'});form.append(label(t('config'),'configuration',el('select',{id:'configuration'},['A','B','C'].map(key=>el('option',{value:key},key+' · '+(key==='B'?'8':'6')+' '+t('stageCount')+' / '+(key==='C'?'2':'1')+' '+t('condenserCount'))))),
 label(t('fault'),'fault',el('select',{id:'fault'},['normal','cooling_loss','heater_loss','sensor_bias'].map(key=>el('option',{value:key,selected:key==='cooling_loss'},t(key==='normal'?'normalMode':key)+(key==='sensor_bias'?' · 4 K':''))))),
 el('div',{class:'two-columns compact'},label(t('duration'),'duration',el('input',{id:'duration',type:'number',min:4,max:6,step:.5,value:4,required:true})),label(t('severity'),'severity',el('input',{id:'severity',type:'number',min:.2,max:1,step:.1,value:.5,required:true}))),
 el('label',{class:'check-label'},el('input',{id:'plan',type:'checkbox',checked:true}),t('compare')),paragraph(t('staleDraft'),'small muted'),el('p',{id:'run-error',class:'error',role:'alert'}),el('button',{id:'submit-run',type:'submit',class:'primary'},t('run')));
 const node=dialog(t('run'),form);$('fault').onchange=()=>{$('severity').disabled=['normal','sensor_bias'].includes($('fault').value);};
 form.onsubmit=async e=>{e.preventDefault();if(!form.reportValidity())return;
 const request={request_token:crypto.randomUUID(),arguments:{configuration:$('configuration').value,fault:$('fault').value,duration_s:Number($('duration').value),severity:Number($('severity').value),plan_actions:$('plan').checked}};
 pendingRequest=request;storage('refinery-pending-v1',request);$('submit-run').disabled=true;
 try{state.job=await api('jobs',{method:'POST',body:JSON.stringify(request)});node.close();storage('refinery-job-v1',state.job);renderJob();resumeJob();}
 catch(error){$('run-error').textContent=error.message;$('submit-run').disabled=false;if(error.status>=400&&error.status<500){pendingRequest=null;localStorage.removeItem('refinery-pending-v1');}else{state.job={status:'queued',stage:'queued',error:t('offline')};renderJob();}}};
}
async function resumeJob(){
 if(polling)return;polling=true;
 try{
 if(!state.job?.job_id&&pendingRequest)state.job=await api('jobs',{method:'POST',body:JSON.stringify(pendingRequest)});
 while(state.job){
  state.job=await api('job?id='+encodeURIComponent(state.job.job_id));renderJob();storage('refinery-job-v1',state.job);
  if(state.job.status==='completed'){const value=await api('result?event='+encodeURIComponent(state.job.result_event_id));await acceptResult(value,'simulation');pendingRequest=null;localStorage.removeItem('refinery-pending-v1');localStorage.removeItem('refinery-job-v1');notice(t('completed'));break;}
  if(['failed','interrupted'].includes(state.job.status)){pendingRequest=null;localStorage.removeItem('refinery-pending-v1');notice(state.job.error||t('failed'),true);break;}
  await new Promise(resolve=>setTimeout(resolve,1800));
 }
 }catch(error){state.job={...state.job,error:t('offline')+' · '+error.message};renderJob();notice(t('offline')+' · '+t('previous'),true);}
 finally{polling=false;renderJob();}
}
async function acceptResult(value,source='replay',hash=null){
 stopPlay();state.result=validateResult(value);state.source=source;state.hash=source==='imported'?null:hash||value._archive_sha256||null;state.index=state.result.physical.series.length-1;state.selected=state.result.physical.cells[state.result.physical.roles.indexOf('condenser')];
 state.actions=new Set(state.result.action_forecast?.ranking?.map(x=>x.action)||[]);state.alarms=alarms(state.result,state.profile);state.annotations=[];state.window=null;state.pan={x:0,y:0};state.zoom=1;state.verification=false;
 storage('refinery-workspace-result-v1',{result:state.result,source,hash});render();
 if(source!=='imported')try{state.annotations=await api('annotations?event='+encodeURIComponent(state.result.event_id));if(state.view==='events')render();}catch(error){notice(error.message,true);}
}
async function openHistory(){
 const root=el('div',{},paragraph(t('historyBoundary')),el('div',{id:'history-list'},paragraph(t('processing'))));dialog(t('history'),root);
 try{const history=await api('history');$('history-list').replaceChildren(history.length?table([t('config'),t('rootCause'),t('occurred'),t('open')],history.map(row=>[row.configuration,t(row.diagnosis),
 row.created_at?new Date(row.created_at).toLocaleString(state.profile.language==='ru'?'ru-RU':'en-US'):t('missing'),button(t('open'),null,async()=>{try{const value=await api('result?event='+encodeURIComponent(row.event_id));$('dialog').close();await acceptResult(value,'replay',row.sha256);}catch(error){notice(error.message,true);}},{class:'subtle','data-history-event':row.event_id})])):paragraph(t('noHistory')));
 root.append(button(t('refresh'),'refresh-history',()=>{$('dialog').close();openHistory();}));}catch(error){$('history-list').replaceChildren(paragraph(error.message,'error'));}
}
function openAnnotation(alarm){
 const form=el('form',{id:'annotation-form'},paragraph(t('noteHint')),label(t('comment'),'annotation-comment',el('textarea',{id:'annotation-comment',rows:4,minlength:3,maxlength:2000,required:true})),el('p',{id:'annotation-error',role:'alert',class:'error'}),el('button',{type:'submit',id:'save-annotation',class:'primary'},t(alarm?'ack':'saveNote')));
 const node=dialog(t(alarm?'ack':'note'),form);
 form.onsubmit=async e=>{e.preventDefault();if(!form.reportValidity())return;$('save-annotation').disabled=true;
 try{await api('annotations',{method:'POST',body:JSON.stringify({event_id:state.result.event_id,kind:alarm?'acknowledge':'note',comment:$('annotation-comment').value,...(alarm?{alarm:alarmEvidence(alarm)}:{})})});
 state.annotations=await api('annotations?event='+encodeURIComponent(state.result.event_id));node.close();render();notice(t(alarm?'acknowledged':'saveNote'));}
 catch(error){$('annotation-error').textContent=error.message;$('save-annotation').disabled=false;}};
}
function fileInput(kind){const input=$(kind==='profile'?'profile-file':'result-file');input.value='';input.click();}
async function importFile(file,kind){
 if(!file)return;try{if(file.size>5000000)throw Error(t('fileTooLarge'));const value=JSON.parse(await file.text());
 if(kind==='profile'){state.profile=validateProfile(value);saveProfile(state.profile);render();notice(t('profileSaved'));}else{await acceptResult(validateResult(value),'imported');notice(t('imported'));}}
 catch(error){notice(t('invalidImport'),true);}
}
async function initialize(){
 $('expand-all').onclick=expandAll;
 $('new-run').onclick=openRun;$('history-open').onclick=openHistory;$('theme-toggle').onclick=()=>{state.profile.theme=state.profile.theme==='light'?'dark':'light';saveProfile(state.profile);render();};
 $('result-file').onchange=e=>importFile(e.target.files[0],'result');$('profile-file').onchange=e=>importFile(e.target.files[0],'profile');state.view=VIEWS.includes(location.hash.slice(1))?location.hash.slice(1):'overview';
 try{const saved=JSON.parse(localStorage.getItem('refinery-workspace-result-v1'));if(saved){state.result=validateResult(saved.result);state.source=saved.source;state.hash=saved.hash;state.index=state.result.physical.series.length-1;state.selected=state.result.physical.cells[state.result.physical.roles.indexOf('condenser')];state.actions=new Set(state.result.action_forecast?.ranking?.map(x=>x.action)||[]);}}catch{localStorage.removeItem('refinery-workspace-result-v1');}
 render();
 try{state.status=await api('status');renderContext();if(!state.result){const rows=await api('history');if(rows.length)await acceptResult(await api('result?event='+rows[0].event_id),'replay',rows[0].sha256);}else if(state.source!=='imported'){state.annotations=await api('annotations?event='+state.result.event_id);render();}}catch(error){notice(t('offline')+' · '+error.message,true);}
 try{pendingRequest=JSON.parse(localStorage.getItem('refinery-pending-v1'));state.job=JSON.parse(localStorage.getItem('refinery-job-v1'));}catch{}
 if(pendingRequest||['queued','running'].includes(state.job?.status)){renderJob();resumeJob();}
 window.addEventListener('hashchange',()=>{const key=location.hash.slice(1);if(VIEWS.includes(key)){state.view=key;stopPlay();render();}});
 window.addEventListener('keydown',e=>{if(e.key==='Escape')stopPlay();});
 document.addEventListener('fullscreenchange',()=>{document.body.classList.toggle('wall-fullscreen',Boolean(document.fullscreenElement)&&state.view==='wall');if($('wall-fullscreen'))$('wall-fullscreen').textContent=t(document.fullscreenElement?'exitFullscreen':'fullscreen');});
 setInterval(updateClock,1000);setInterval(refreshWall,15000);
 window.workspaceSnapshot=()=>({event_id:state.result?.event_id,source:state.source,time_s:currentTime(),view:state.view,selected:state.selected,profile:structuredClone(state.profile),job:state.job?structuredClone(state.job):null});
}
initialize();
