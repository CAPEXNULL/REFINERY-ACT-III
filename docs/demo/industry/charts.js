import {svgEl,el,finite,format,displayValue,unit,referenceAt} from './data.js';
export const ACTION_COLORS={hold:'#65718b',restore_cooling:'#007969',reduce_heat:'#914fb0',reduce_feed:'#b16a00'};
export function chart(result,indices,kind,profile,index,window,onIndex,t,actions=[]){
  const p=result.physical,baseKey=kind==='temperature'?'temperature_K':'pressure_kPa';
  const aggregate=values=>{const nums=indices.map(i=>values?.[i]).filter(finite);return nums.length===indices.length?Math.max(...nums):null;};
  const raw=p.series.map(r=>({time:r.time_s,value:aggregate(r.observation[baseKey])}));
  const ref=p.series.map(r=>({time:r.time_s,value:aggregate(referenceAt(result,r.time_s)?.[baseKey])}));
  const dark=profile.theme==='dark';
  const cutoff=raw.at(-1).time,lines=[{name:t('observation'),color:dark?'#69c3de':'#126781',style:'',values:raw},{name:t('reference'),color:dark?'#bac6d4':'#6f7e8b',style:'3 5',values:ref}];
  for(const action of actions){
    const forecast=result.action_forecast?.forecasts?.[action];
    if(forecast)lines.push({name:t(action),color:dark?({hold:'#a8b4cd',restore_cooling:'#65d7bd',reduce_heat:'#d6a3ea',reduce_feed:'#f5be65'})[action]:ACTION_COLORS[action],style:'7 4',
      values:forecast.series.map(r=>({time:r.time_s,value:aggregate(kind==='pressure'?r.pressure_Pa?.map(v=>finite(v)?v/1000:null):r.temperature_K)}))});
  }
  const end=Math.max(cutoff,...lines.flatMap(l=>l.values.map(v=>v.time))),start=window?.start??0,finish=window?.end??end;
  const visible=lines.flatMap(l=>l.values.filter(v=>v.time>=start&&v.time<=finish&&finite(v.value)).map(v=>displayValue(v.value,kind,profile)));
  const lo=visible.length?Math.min(...visible):0,hi=visible.length?Math.max(...visible):1,padding=Math.max((hi-lo)*.15,.02),bottom=lo-padding,top=hi+padding;
  const width=480,height=250,left=80,right=455,yTop=20,yBottom=195;
  const sx=v=>left+(v-start)/(finish-start||1)*(right-left),sy=v=>yBottom-(v-bottom)/(top-bottom)*(yBottom-yTop);
  const box=el('div',{class:'chart-box'}),svg=svgEl('svg',{viewBox:'0 0 '+width+' '+height,role:'img',tabindex:0,'aria-label':t(kind)+' · '+unit(kind,profile)+' · '+t('time'),'data-chart':kind});
  for(let n=0;n<4;n++){
    const y=yTop+n*(yBottom-yTop)/3,v=top-n*(top-bottom)/3;
    svg.append(svgEl('line',{x1:left,x2:right,y1:y,y2:y,class:'chart-grid'}),svgEl('text',{x:left-8,y:y+4,'text-anchor':'end',class:'chart-label'},format(v,2,profile.language)));
  }
  for(let n=0;n<5;n++){
    const tm=start+n*(finish-start)/4;
    svg.append(svgEl('text',{x:sx(tm),y:218,'text-anchor':'middle',class:'chart-label'},format(tm,1,profile.language)+' s'));
  }
  for(const line of lines){
    let path='',pen=false;
    for(const point of line.values){
      if(point.time<start||point.time>finish||!finite(point.value)){pen=false;continue;}
      path+=(pen?'L':'M')+sx(point.time)+' '+sy(displayValue(point.value,kind,profile))+' ';pen=true;
    }
    svg.append(svgEl('path',{d:path,fill:'none',stroke:line.color,'stroke-width':2.4,'stroke-dasharray':line.style}));
  }
  if(actions.length&&cutoff>=start&&cutoff<=finish){
    svg.append(svgEl('line',{x1:sx(cutoff),x2:sx(cutoff),y1:yTop,y2:yBottom,class:'forecast-boundary'}));
    svg.append(svgEl('text',{x:Math.min(sx(cutoff)+8,510),y:12,class:'chart-label'},t('forecast')+' →'));
  }
  const selected=raw[index],chosen=finite(selected?.value)?displayValue(selected.value,kind,profile):null;
  if(selected&&selected.time>=start&&selected.time<=finish){
    svg.append(svgEl('line',{x1:sx(selected.time),x2:sx(selected.time),y1:yTop,y2:yBottom,class:'chart-cursor'}));
    if(finite(chosen))svg.append(svgEl('circle',{cx:sx(selected.time),cy:sy(chosen),r:4,fill:lines[0].color}));
  }
  const nearest=time=>p.series.reduce((best,r,i)=>Math.abs(r.time_s-time)<Math.abs(p.series[best].time_s-time)?i:best,0);
  svg.addEventListener('click',e=>{const rect=svg.getBoundingClientRect();const local=(e.clientX-rect.left)/rect.width*width;onIndex(nearest(start+(local-left)/(right-left)*(finish-start)));});
  svg.addEventListener('keydown',e=>{if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();onIndex(Math.max(0,Math.min(raw.length-1,index+(e.key==='ArrowRight'?1:-1))));}});
  box.append(svg,el('div',{class:'chart-readout'},t('snapshot')+' '+format(selected?.time,1,profile.language)+' s · '+format(chosen,2,profile.language)+' '+unit(kind,profile)));
  const legend=el('div',{class:'chart-legend'});
  for(const line of lines)legend.append(el('span',{},el('i',{style:'background:'+line.color}),line.name));
  box.append(legend);return box;
}
