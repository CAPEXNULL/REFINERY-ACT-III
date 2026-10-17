"""Local engineering pilot UI. CPU only; no autonomous plant control."""
import argparse
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import math
import os
import threading
from urllib.parse import urlsplit, parse_qs
from amd.column import ColumnConfig, solve_column
from amd.pilot import condenser_pilot
from amd.dynamics import run_coupled
from amd.perseus import Perseus
from amd.audit import Trace
from amd.industry_service import IndustryService
from amd.workspace import Workspace, WorkspaceBusy

ROOT=Path(__file__).resolve().parents[1]
LOCK=threading.Lock()
AUDIT=Trace(ROOT/'reports'/'trace'/'runtime')
PERSEUS=Perseus(ROOT/'reports'/'trace'/'runtime'/'SUBJECT_STATE.json',audit=AUDIT)
INDUSTRY=IndustryService(ROOT)
WORKSPACE=Workspace(INDUSTRY,LOCK)


def audited_coordinate(payload):
    def validate(value):
        result=value['result']
        if payload['type']=='steady_column':
            checks={'mass_balance':max(abs(x) for x in result['component_balance_mol_s'])<1e-6,
                    'energy_balance':abs(result['energy_balance_W'])<1e-3,
                    'phase_equilibrium':result['equilibrium_log_fugacity_residual']<1e-5}
        elif payload['type']=='condenser_pilot':
            checks={'energy_balance':abs(result['energy_balance_residual_J'])<1e-4,
                    'finite_pressure':all(math.isfinite(r['pressure_Pa']) and r['pressure_Pa']>0 for r in result['series'])}
        else:
            checks={'mass_balance':max(abs(v) for v in result['component_balance_residual_mol'])<1e-7,
                    'energy_balance':abs(result['energy_balance_residual_J'])<1e-3,
                    'finite_pressure':all(math.isfinite(p) and p>0 for r in result['series'] for p in r['pressure_Pa'])}
        artifact=AUDIT.directory/('result-'+value['trace']['event_id']+'.json')
        with artifact.open('x',encoding='utf-8') as stream:
            json.dump(value,stream,allow_nan=False)
        return checks,[artifact]
    return AUDIT.execute('perseus','coordinate',payload['type'],payload,
        {'column_mass_mol_s':1e-6,'column_energy_W':1e-3,'phase_log_residual':1e-5,
         'condenser_energy_J':1e-4,'pressure':'finite and positive'},
        lambda:PERSEUS.coordinate(payload,dispatch),validate,
        sources=[__file__,str(ROOT/'amd'/'perseus.py')],
        before={'subject_sequence':PERSEUS.state.sequence})


def number(args,key,default,lo,hi,integer=False):
    value=args.get(key,default)
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or not lo<=value<=hi:
        raise ValueError(f'{key} must be between {lo} and {hi}')
    if integer and value!=int(value): raise ValueError(f'{key} must be an integer')
    return int(value) if integer else float(value)


def dispatch(tool,args):
    if tool=='steady_column':
        if set(args)-{'stages','pressure_kPa','reflux_ratio'}: raise ValueError('Unknown parameter')
        stages=number(args,'stages',6,2,8,True)
        c=ColumnConfig(stages=stages,feed_stage=5 if stages==8 else min(4,stages),top_pressure_Pa=number(args,'pressure_kPa',150,120,180)*1000,reflux_ratio=number(args,'reflux_ratio',3,2.5,4))
        return solve_column(c)
    if tool=='coupled_dynamics':
        if set(args)-{'duration_s','cooling_factor'}:raise ValueError('Unknown parameter')
        return run_coupled(duration=number(args,'duration_s',10,4,20),dt=.5,
                           cooling_factor=number(args,'cooling_factor',.5,.4,1),fault_time=2)
    if tool!='condenser_pilot':raise ValueError('Unknown computation tool')
    if set(args)-{'duration_s','cooling_factor'}: raise ValueError('Unknown parameter')
    return condenser_pilot(number(args,'duration_s',60,4,120),2,number(args,'cooling_factor',.5,.4,1))


def allowed_origins(port):
    origins = {f'http://127.0.0.1:{port}', f'http://localhost:{port}'}
    configured = os.environ.get('REFINERY_PUBLIC_ORIGIN', '').strip()
    if configured:
        parsed = urlsplit(configured)
        if (parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment):
            raise ValueError('REFINERY_PUBLIC_ORIGIN must be one HTTPS origin without a path')
        origins.add(configured)
    return origins


class Handler(BaseHTTPRequestHandler):
    def response(self,status,payload):
        raw=json.dumps(payload,allow_nan=False).encode()
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def do_GET(self):
        parsed=urlsplit(self.path)
        if parsed.path.startswith('/assets/industry/'):
            name=parsed.path.removeprefix('/assets/industry/')
            allowed={'app.js','data.js','config.js','diagram.js','charts.js','wall.js','workspace.css'}
            if name not in allowed:self.response(404,{'error':'Not found'});return
            path=ROOT/'frontend'/'industry'/name
            if not path.is_file():self.response(404,{'error':'Not found'});return
            raw=path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type','text/css; charset=utf-8' if name.endswith('.css') else 'text/javascript; charset=utf-8')
            self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-cache')
            self.end_headers();self.wfile.write(raw);return
        if parsed.path in ('/api/industry/history','/api/industry/result','/api/industry/job','/api/industry/annotations'):
            try:
                query=parse_qs(parsed.query)
                if parsed.path.endswith('/history'):value=WORKSPACE.history()
                elif parsed.path.endswith('/job'):value=WORKSPACE.job(query.get('id',[''])[0])
                elif parsed.path.endswith('/annotations'):value=WORKSPACE.annotations(query.get('event',[''])[0])
                else:value=WORKSPACE.result(query.get('event',[''])[0])
                self.response(200,value)
            except ValueError as error:self.response(400,{'error':str(error)})
            except FileNotFoundError:self.response(404,{'error':'Record not found'})
            return
        if self.path=='/api/industry/status':
            self.response(200,INDUSTRY.status());return
        if self.path=='/industry':
            raw=(ROOT/'frontend'/'industry.html').read_bytes()
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
        if self.path=='/favicon.ico':
            self.send_response(204); self.end_headers(); return
        if self.path=='/api/status':
            self.response(200,{'device':'CPU','gpu_verified':False,'stage':'engineering pilot','perseus_memory_records':len(PERSEUS.state.memory)}); return
        if self.path=='/api/results':
            history={}
            for record in PERSEUS.state.memory:
                if record.get('outcome')!='CONFIRMED':continue
                path=AUDIT.directory/('result-'+record['event_id']+'.json')
                if path.is_file():history[record['tool']]=json.loads(path.read_text(encoding='utf-8'))
            self.response(200,history);return
        if self.path not in ('/','/index.html'):
            self.response(404,{'error':'Not found'}); return
        raw=(ROOT/'frontend'/'index.html').read_bytes()
        self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def do_POST(self):
        if self.path not in ('/api/run','/api/industry/run','/api/industry/jobs','/api/industry/annotations'): self.response(404,{'error':'Not found'}); return
        if self.headers.get('Origin') and self.headers['Origin'] not in allowed_origins(self.server.server_port):
            self.response(403,{'error':'Cross-origin request rejected'}); return
        acquired=False
        try:
            length=int(self.headers.get('Content-Length',0))
            maximum=12288 if self.path=='/api/industry/annotations' else 4096
            if not 0<length<=maximum: raise ValueError('Invalid request size')
            payload=json.loads(self.rfile.read(length))
            if self.path=='/api/industry/jobs':
                self.response(202,WORKSPACE.submit(payload));return
            if self.path=='/api/industry/annotations':
                self.response(201,WORKSPACE.annotate(payload));return
            if self.path=='/api/industry/run':
                if not isinstance(payload,dict):raise ValueError('Invalid industry request')
                acquired=LOCK.acquire(blocking=False)
                if not acquired:self.response(409,{'error':'A calculation is already running'});return
                self.response(200,INDUSTRY.run(payload));return
            if not isinstance(payload,dict) or set(payload)-{'type','arguments'}: raise ValueError('Invalid event')
            if payload.get('type') not in ('steady_column','condenser_pilot','coupled_dynamics') or not isinstance(payload.get('arguments'),dict): raise ValueError('Invalid event')
            acquired=LOCK.acquire(blocking=False)
            if not acquired: self.response(409,{'error':'A calculation is already running; retry after it completes'}); return
            value=audited_coordinate(payload)
            self.response(200,value)
        except WorkspaceBusy as error:
            self.response(409,{'error':str(error)})
        except FileNotFoundError:
            self.response(404,{'error':'Record not found'})
        except (ValueError,KeyError,json.JSONDecodeError) as error:
            self.response(400,{'error':str(error)})
        except Exception:
            self.response(500,{'error':'Calculation failed. No result was accepted.'})
        finally:
            if acquired: LOCK.release()


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--port',type=int,default=8765); parser.add_argument('--host',default='127.0.0.1'); args=parser.parse_args()
    with WORKSPACE.server_owner():
        server=ThreadingHTTPServer((args.host,args.port),Handler)
        WORKSPACE.recover_interrupted()
        print(f'REFINERY: http://{args.host}:{args.port}',flush=True)
        try:server.serve_forever()
        finally:server.server_close()


if __name__=='__main__': main()
