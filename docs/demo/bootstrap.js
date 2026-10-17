import {validateResult} from './industry/data.js';
import {DEFAULT_PROFILE,validateProfile} from './industry/config.js';

const SOURCE_URL="https://github.com/CAPEXNULL/REFINERY-ACT-III";
const SAMPLE_SHA256="71e60cb1c698c9483ec342eebb8912fe5ab2ca8a1ab6a074bd064c016466eb22";
const LABEL='RECORDED SYNTHETIC REPLAY';
const BOUNDARY='Read-only recorded CPU simulation. No live calculation. No AMD inference. No real-plant validation.';
const originalFetch=window.fetch.bind(window);
const jsonResponse=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'}});
const disabledControls='#new-run,#empty-run,#forecast-new-run,#submit-run,#add-note,#save-annotation,#import-result,#empty-import,#verification';
function disabledAction(target){
  if(!(target instanceof Element))return false;
  if(target.closest(disabledControls))return true;
  return document.getElementById('nav-events')?.getAttribute('aria-current')==='page'&&Boolean(target.closest('#view table button'));
}
function setText(node,text){if(node&&node.textContent!==text)node.textContent=text;}
function enforceReadOnly(){
  for(const node of document.querySelectorAll(disabledControls)){
    if(!node.disabled)node.disabled=true;
    const hidden=node.id==='verification'?node.closest('section'):node;
    if(hidden&&!hidden.hidden)hidden.hidden=true;
  }
  if(document.getElementById('nav-events')?.getAttribute('aria-current')==='page'){
    for(const node of document.querySelectorAll('#view table button')){if(!node.disabled)node.disabled=true;if(!node.hidden)node.hidden=true;}
  }
  setText(document.querySelector('.local-mode'),'RECORDED ? CPU DATA');
  setText(document.getElementById('mode-label'),'READ-ONLY ? NO LIVE COMPUTE');
  setText(document.querySelector('.connection .badge'),'Recorded replay');
  setText(document.getElementById('scope-footer'),BOUNDARY);
  const source=document.querySelector('.sidebar-footer a');
  if(source){if(source.href!==SOURCE_URL+'#readme')source.href=SOURCE_URL+'#readme';setText(source,'Source & local run ?');}
}
document.addEventListener('click',event=>{if(disabledAction(event.target)){event.preventDefault();event.stopImmediatePropagation();}},true);
document.addEventListener('submit',event=>{if(['run-form','annotation-form'].includes(event.target.id)){event.preventDefault();event.stopImmediatePropagation();}},true);
new MutationObserver(enforceReadOnly).observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['disabled','hidden']});
enforceReadOnly();

try{
  const response=await originalFetch(new URL('./sample.json',import.meta.url),{cache:'no-store'});
  if(!response.ok)throw Error('Recorded sample could not be loaded');
  const sample=validateResult(await response.json());
  window.fetch=async(input,options={})=>{
    const requestUrl=new URL(typeof input==='string'||input instanceof URL?input:input.url,location.href);
    const method=(options.method||(input instanceof Request?input.method:'GET')).toUpperCase();
    if(requestUrl.origin===location.origin&&requestUrl.pathname.startsWith('/api/industry/')){
      if(method!=='GET')return jsonResponse({error:LABEL+' is read-only; run the Python backend locally for calculations or annotations.'},405);
      const name=requestUrl.pathname.slice('/api/industry/'.length);
      if(name==='status')return jsonResponse({device:'Recorded CPU data',model_ready:false,model_source:null,replay_only:true,scope:BOUNDARY});
      if(name==='history')return jsonResponse([{event_id:sample.event_id,created_at:sample.created_at||null,configuration:sample.physical.configuration,duration_s:sample.physical.series.at(-1).time_s,diagnosis:sample.diagnosis.label,model_version:sample.diagnosis.model_version,sha256:SAMPLE_SHA256,source:'recorded-synthetic-replay'}]);
      if(name==='sample'||name==='result'){
        const event=requestUrl.searchParams.get('event');
        return !event||event===sample.event_id?jsonResponse(sample):jsonResponse({error:'Only the published recording is available'},404);
      }
      if(name==='annotations')return jsonResponse([]);
      return jsonResponse({error:'No live jobs or server state exist in this recorded replay'},404);
    }
    return originalFetch(input,options);
  };
  const profile=validateProfile({...structuredClone(DEFAULT_PROFILE),language:'en',site:'Recorded synthetic CPU output',wall:{...DEFAULT_PROFILE.wall,autoRefresh:false}});
  localStorage.removeItem('refinery-pending-v1');localStorage.removeItem('refinery-job-v1');
  localStorage.setItem('refinery-profile-v1',JSON.stringify(profile));
  localStorage.setItem('refinery-workspace-result-v1',JSON.stringify({result:sample,source:'imported',hash:null}));
  await import('./industry/app.js');
  enforceReadOnly();
  window.recordedReplay=Object.freeze({readOnly:true,synthetic:true,liveCalculation:false,amdInference:false,sampleSha256:SAMPLE_SHA256});
}catch(error){
  const message=document.createElement('p');message.className='replay-error';message.setAttribute('role','alert');
  message.textContent='Replay unavailable: '+error.message+'. Serve this folder over HTTP and allow browser storage, or use the source instructions to run locally.';
  document.getElementById('recorded-replay').append(message);
}
