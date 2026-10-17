import {svgEl,displayValue,unit,format,labelFor,referenceAt,finite} from './data.js';
export function drawDiagram(target,state,onSelect,t){
  const p=state.result.physical,row=p.series[state.index],ref=referenceAt(state.result,row.time_s),profile=state.profile;
  const svg=svgEl('svg',{viewBox:'0 0 1200 620',role:'group','aria-label':t('equipment'),'data-testid':'process-diagram'});
  const defs=svgEl('defs');
  for(const [name,color] of [['material','#537d90'],['vapor','#176b83'],['liquid','#537d90'],['reflux','#00806a'],['thermal','#a86216'],['control','#6574af'],['causal','#ac5700']]){
    const marker=svgEl('marker',{id:'arrow-'+name,viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:6,markerHeight:6,orient:'auto-start-reverse'});
    marker.append(svgEl('path',{d:'M0 0L10 5L0 10Z',fill:color}));defs.append(marker);
  }
  svg.append(defs);
  const n=p.roles.filter(r=>r==='column').length,stageHeight=350/n,positions={};
  p.cells.forEach((id,i)=>{
    const role=p.roles[i];
    positions[id]=role==='heater'?{x:65,y:290,w:165,h:105}:
      role==='column'?{x:385,y:105+(i-1)*stageHeight,w:210,h:stageHeight-5}:
      role==='reboiler'?{x:420,y:515,w:165,h:70}:
      {x:810,y:130+(i-p.roles.indexOf('condenser'))*150,w:180,h:95};
  });
  svg.append(svgEl('rect',{x:373,y:78,width:234,height:407,rx:36,class:'column-shell'}));
  svg.append(svgEl('text',{x:490,y:65,'text-anchor':'middle',class:'apparatus-title'},'C-101 · '+t('separation')));
  function line(points,kind,label,dim=false){
    const node=svgEl('path',{d:points.map((pt,i)=>(i?'L':'M')+pt.join(' ')).join(' '),class:'flow '+kind+(dim?' dim':''),'marker-end':'url(#arrow-'+kind+')'});
    node.append(svgEl('title',{},label));svg.append(node);
  }
  const loop=state.loop||'all';
  const relevant=role=>loop==='all'||loop==='protection'||({feed:['heater'],separation:['column','reboiler'],condensation:['condenser'],reflux:['column','condenser'],cooling:['condenser']}[loop]||[]).includes(role);
  if(state.layers.material){
    for(const e of p.topology){
      const a=positions[e.source],b=positions[e.target],role=p.roles[p.cells.indexOf(e.source)];
      let points;
      if(e.type==='material')points=[[a.x+a.w,a.y+a.h/2],[300,a.y+a.h/2],[300,b.y+b.h/2],[b.x,b.y+b.h/2]];
      else if(e.type==='reflux'){
        const number=p.cells.indexOf(e.source)-p.roles.indexOf('condenser'),lane=1015+number*25,top=32+number*18,port=b.x+b.w/2-number*16;
        points=[[a.x+a.w,a.y+a.h],[lane,a.y+a.h],[lane,top],[650-number*20,top],[650-number*20,90],[port,90],[port,b.y]];
      }
      else if(p.roles[p.cells.indexOf(e.target)]==='condenser')points=[[a.x+a.w,a.y+a.h/2],[680,a.y+a.h/2],[680,b.y+b.h/2],[b.x,b.y+b.h/2]];
      else{
        const lane=e.type==='vapor'?345:610;
        points=[[e.type==='vapor'?a.x:a.x+a.w,a.y+a.h/2],[lane,a.y+a.h/2],[lane,b.y+b.h/2],[e.type==='vapor'?b.x:b.x+b.w,b.y+b.h/2]];
      }
      line(points,e.type,e.source+' → '+e.target+' · '+e.type,!relevant(role));
    }
    svg.append(svgEl('text',{x:680,y:25,class:'flow-label'},t('reflux')));
  }
  if(state.layers.thermal){
    for(const [id,a] of Object.entries(positions)){
      const role=p.roles[p.cells.indexOf(id)];
      if(role==='heater'||role==='reboiler'){
        line([[a.x+a.w/2,a.y+a.h+18],[a.x+a.w/2,a.y+a.h]],'thermal','Q · '+id,!relevant(role));
        svg.append(svgEl('text',{x:a.x+a.w/2,y:a.y+a.h+32,'text-anchor':'middle',class:'utility-label'},'Q'));
      }else if(role==='condenser'){
        line([[1125,a.y+a.h/2],[a.x+a.w,a.y+a.h/2]],'thermal','CW · '+id,!relevant(role));
        svg.append(svgEl('text',{x:1090,y:a.y+a.h/2-10,class:'utility-label'},'CW'));
      }
    }
  }
  if(state.layers.control){
    const relay={x:850,y:475};
    for(const [id,a] of Object.entries(positions)){
      const role=p.roles[p.cells.indexOf(id)];
      if(['heater','condenser'].includes(role))line([[a.x+a.w/2,a.y+a.h],[a.x+a.w/2,450],[relay.x,450],[relay.x,relay.y]],'control',id+' → '+t('protection'),loop!=='all'&&loop!=='protection');
    }
    svg.append(svgEl('rect',{x:760,y:475,width:235,height:70,rx:10,class:row.observation.protection.latched?'relay tripped':'relay'}));
    svg.append(svgEl('text',{x:878,y:502,'text-anchor':'middle',class:'equipment-name'},t('protection')));
    svg.append(svgEl('text',{x:878,y:524,'text-anchor':'middle',class:'equipment-reading'},row.observation.protection.latched?t('trip'):t('normal')));
  }
  if(state.layers.causal){
    const chain=state.result.diagnosis.causal_chain||[];
    for(let i=1;i<chain.length;i++){
      const a=positions[chain[i-1]],b=positions[chain[i]];
      if(a&&b)line([[a.x+a.w/2,a.y+a.h/2],[b.x+b.w/2,b.y+b.h/2]],'causal',t('causal')+' · '+chain[i-1]+' → '+chain[i]);
    }
  }
  p.cells.forEach((id,i)=>{
    const a=positions[id],role=p.roles[i],o=row.observation;
    const active=state.alarms.filter(x=>x.equipment===id&&x.time_s<=row.time_s&&(x.resolved_at_s===null||x.resolved_at_s>row.time_s));
    const severity=active.some(x=>['trip','critical'].includes(x.level))?'critical':active.length?'warning':'normal';
    const g=svgEl('g',{transform:'translate('+a.x+' '+a.y+')',class:'equipment '+severity+(state.selected===id?' selected':'')+(!relevant(role)?' dim':''),
      tabindex:0,role:'button','aria-label':labelFor(id,profile)+' · '+t(severity),'aria-pressed':String(state.selected===id),'data-equipment':id});
    g.append(svgEl('rect',{width:a.w,height:a.h,rx:role==='column'?4:12,class:'equipment-body'}));
    if(role==='condenser')g.append(svgEl('path',{d:'M15 79L35 72L55 88L75 72L95 88L115 72L135 88L155 79',class:'equipment-symbol'}));
    if(role==='heater')g.append(svgEl('path',{d:'M20 78L30 65L38 78L48 62L58 78',class:'equipment-symbol flame'}));
    const temp=displayValue(o.temperature_K[i],'temperature',profile),pressure=displayValue(o.pressure_kPa[i],'pressure',profile);
    const name=labelFor(id,profile),visibleName=name.length>22?Array.from(name).slice(0,21).join('')+'…':name;
    g.append(svgEl('title',{},name));
    g.append(svgEl('text',{x:12,y:role==='column'?17:24,class:'equipment-name'},visibleName));
    const temperatureText=format(temp,1,profile.language)+' '+unit('temperature',profile),pressureText=format(pressure,2,profile.language)+' '+unit('pressure',profile);
    if(role==='column')g.append(svgEl('text',{x:12,y:33,class:'equipment-reading'},temperatureText+' · '+pressureText));
    else g.append(svgEl('text',{x:12,y:43,class:'equipment-reading'},temperatureText),svgEl('text',{x:12,y:62,class:'equipment-reading'},pressureText));
    if(active.length)g.append(svgEl('text',{x:a.w-16,y:17,'text-anchor':'end',class:'alarm-symbol'},'!'));
    g.setAttribute('aria-label',Array.from(g.querySelectorAll('text')).map(n=>n.textContent).join('')+' · '+t(severity));
    const choose=()=>onSelect(id);
    g.addEventListener('click',choose);g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose();}});
    svg.append(g);
  });
  const zoom=state.zoom||1,pan=state.pan||{x:0,y:0};
  const view=()=>svg.setAttribute('viewBox',[600-600/zoom+pan.x,310-310/zoom+pan.y,1200/zoom,620/zoom].join(' '));
  view();
  let drag=null;
  svg.addEventListener('pointerdown',e=>{if(e.target.closest('[data-equipment]'))return;drag={x:e.clientX,y:e.clientY,px:pan.x,py:pan.y};svg.setPointerCapture(e.pointerId);});
  svg.addEventListener('pointermove',e=>{if(!drag)return;pan.x=drag.px-(e.clientX-drag.x)*1200/svg.clientWidth/zoom;pan.y=drag.py-(e.clientY-drag.y)*620/svg.clientHeight/zoom;view();});
  svg.addEventListener('pointerup',()=>{drag=null;});
  target.replaceChildren(svg);
}
