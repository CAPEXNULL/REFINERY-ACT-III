"""Build the permanent read-only replay from an explicit real CPU result.

Usage: python tools/build_demo.py /path/to/actual-result.json --source-url https://github.com/OWNER/REPO
This copies the existing frontend; it does not execute or synthesize a scenario.
"""
from pathlib import Path
import argparse
import hashlib
import html
import json
import math
import re
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ("app.js", "charts.js", "config.js", "data.js", "diagram.js", "wall.js", "workspace.css")
RESULT_FIELDS = {"event_id", "created_at", "physical", "reference", "diagnosis", "action_forecast", "device"}
PRIVATE_FIELDS = {
    "evaluation", "private_truth", "provenance", "trace", "trace_ref", "source_manifest",
    "source_ref", "target_ref", "physical_evidence", "model_snapshot_ref", "_archive_sha256",
    "run_id", "operation_id", "state_path", "audit_path", "runtime_path", "source_report",
}


def sanitize_result(payload):
    """Keep actual observed values and forecasts, excluding evaluator/internal data."""
    result = payload.get("result") if isinstance(payload, dict) and payload.get("schema") == "refinery-workspace/v1" else payload
    if not isinstance(result, dict):
        raise ValueError("Expected an actual accepted result or workspace export")

    def clean(value):
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items() if key.lower() not in PRIVATE_FIELDS}
        if isinstance(value, list):
            return [clean(item) for item in value]
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Recorded values must be finite")
        if isinstance(value, str) and (value.startswith(("/", "\\\\")) or re.search(r"(?:^|[\s\"'(])[A-Za-z]:[\\/]", value)):
            raise ValueError("Remove absolute host paths from the explicit sample before publication")
        return value

    value = clean({key: item for key, item in result.items() if key in RESULT_FIELDS})
    if not isinstance(value.get("event_id"), str) or not value.get("physical", {}).get("series") or not isinstance(value.get("diagnosis"), dict):
        raise ValueError("The sample must contain an existing event, observations, and diagnosis")
    # Browser bootstrap applies the full existing validateResult before importing app.js.
    json.dumps(value, allow_nan=False)
    return value


BOOTSTRAP = r"""import {validateResult} from './industry/data.js';
import {DEFAULT_PROFILE,validateProfile} from './industry/config.js';

const SOURCE_URL=__SOURCE_URL__;
const SAMPLE_SHA256=__SAMPLE_SHA256__;
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
"""

REPLAY_STYLE = """<style>
#recorded-replay{position:sticky;top:0;z-index:50;background:#fff4cb;color:#302708;border-bottom:3px solid #a97600;padding:12px 22px;font:14px/1.45 system-ui,sans-serif}
#recorded-replay strong{display:block;font-size:15px;letter-spacing:.08em}#recorded-replay p{margin:4px 0 0}#recorded-replay a{color:#2d4e87;font-weight:650}#recorded-replay .replay-error{color:#9b1c1c;font-weight:650}
@media(max-width:760px){#recorded-replay{padding:10px 14px;font-size:12px}#recorded-replay strong{font-size:13px}}
@media print{#recorded-replay{position:static;border:2px solid #555;background:white!important;color:#111!important}}
</style>"""


def build_demo(sample_path, source_url):
    parsed = urlsplit(source_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("Provide the public HTTPS repository URL without a query or fragment")
    source_url = source_url.rstrip("/")
    sample = sanitize_result(json.loads(Path(sample_path).read_text(encoding="utf-8-sig")))
    encoded = (json.dumps(sample, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    sample_sha = hashlib.sha256(encoded).hexdigest()
    output = ROOT / "docs" / "demo"
    industry = output / "industry"
    industry.mkdir(parents=True, exist_ok=True)
    for name in ASSETS:
        (industry / name).write_bytes((ROOT / "frontend" / "industry" / name).read_bytes())
    (output / "sample.json").write_bytes(encoded)
    bootstrap = BOOTSTRAP.replace("__SOURCE_URL__", json.dumps(source_url)).replace("__SAMPLE_SHA256__", json.dumps(sample_sha))
    (output / "bootstrap.js").write_text(bootstrap, encoding="utf-8", newline="\n")
    document = (ROOT / "frontend" / "industry.html").read_text(encoding="utf-8-sig")
    document = document.replace('lang="ru"', 'lang="en"').replace('REFINERY &middot; Engineering workspace', 'REFINERY &middot; Recorded synthetic replay')
    document = document.replace('href="/assets/industry/workspace.css"', 'href="./industry/workspace.css"')
    document = document.replace('src="/assets/industry/app.js"', 'src="./bootstrap.js"')
    document = document.replace('href="/industry"', 'href="#overview"').replace('href="/"', 'href="' + html.escape(source_url + '#readme', quote=True) + '"')
    banner = '<section id="recorded-replay" role="note" aria-label="Recorded synthetic replay"><strong>RECORDED SYNTHETIC REPLAY</strong><p>Read-only recorded CPU simulation. No live calculation. No AMD inference.</p><p>Explore a captured refinery surrogate scenario, its diagnostic decision and conditional forecasts. No real-plant validation. <a href="' + html.escape(source_url + '#readme', quote=True) + '">Source &amp; local run instructions</a></p></section><noscript>This recorded replay requires JavaScript. Follow the source link to run the Python application locally.</noscript>'
    document = document.replace('</head>', REPLAY_STYLE + '</head>').replace('<body>', '<body>' + banner)
    (output / "index.html").write_text(document + "\n", encoding="utf-8", newline="\n")
    files = sorted(path.relative_to(ROOT).as_posix() for path in output.rglob('*') if path.is_file())
    return {"mode": "recorded-synthetic-replay", "sample_sha256": sample_sha, "files": files, "live_calculation": False, "amd_inference": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample_json", type=Path, help="Explicit actual CPU result JSON; no simulation is run")
    parser.add_argument("--source-url", required=True, help="Public repository HTTPS URL containing local run instructions")
    args = parser.parse_args()
    print(json.dumps(build_demo(args.sample_json, args.source_url), indent=2))


if __name__ == "__main__":
    main()
