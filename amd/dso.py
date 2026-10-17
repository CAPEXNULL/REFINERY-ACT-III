"""Dynamic dispatch, numeric regulation, acceptance and bounded background work."""
from concurrent.futures import ThreadPoolExecutor
import math
import time
import json
import uuid
from pathlib import Path
from amd import matan
from amd import diagnostics
from amd import planning


def clamp(value):return min(1.,max(0.,float(value)))


class DSO:
    def __init__(self,audit=None):self.audit=audit

    def _record(self,component,action,inputs,operation):
        if not self.audit:return operation()
        def validate(value):
            artifact=self.audit.directory/(component+'-'+uuid.uuid4().hex+'.json')
            artifact.write_text(json.dumps(value,allow_nan=False),encoding='utf-8')
            return {'finite_serializable_result':True},[artifact]
        return self.audit.execute(component,action,action,inputs,
            'Operation completes; result finite and JSON serializable; subject/physics acceptance checked by calling phase',
            operation,validate,sources=[__file__,str(Path(__file__).with_name('matan.py'))])

    def regulate(self, risk, boundary, novelty, experience, divergence=0.):
        value=clamp(.40*risk+.30*boundary+.15*novelty+.15*experience+.12*divergence)
        return {'emotion_value':value,'mode':'elevated' if value>=.35 else 'background',
                'memory_weight':clamp(.55*value+.25*risk+.20*novelty)}

    def update_weight(self, old, evidence):return clamp(old+.20*(evidence-old))

    def personality_step(self, old, target):return clamp(old+min(.05,max(-.05,target-old)))

    def forecast(self, tool, model, arguments):
        if tool!='condenser_pilot':return {'available':False,'reason':'no trained model for requested task'}
        return self._record('MATAN','pressure forecast',{'arguments':arguments,'model_version':model.get('version',0)},
                            lambda:matan.predict_pressure(model,arguments))

    def learn(self, model, arguments, observed, outcome_id, prediction):
        return self._record('MATAN','learn measured pressure',{'arguments':arguments,'observed_Pa':observed,'outcome_id':outcome_id},
                            lambda:matan.learn_pressure(model,arguments,observed,outcome_id,prediction))

    def diagnose(self,model,observation,reference):
        return self._record('MATAN','observation-only diagnosis',{'model_version':model.get('version',0)},
                            lambda:diagnostics.diagnose(model,observation,reference))

    def learn_diagnosis(self,model,observation,reference,label,outcome_id,variant):
        return self._record('MATAN','confirmed diagnosis learning',{'outcome_id':outcome_id,'label':label},
                            lambda:diagnostics.learn(model,observation,reference,label,outcome_id,variant))

    def plan_actions(self,normal_plant,observation,diagnosis,horizon_s=4.,available_actions=planning.ACTIONS):
        return self._record('MATAN','conditional intervention forecasts',{'horizon_s':horizon_s,'diagnosis_version':diagnosis.get('model_version'),
                            'available_actions':list(available_actions)},
                            lambda:planning.compare_actions(normal_plant,observation,diagnosis,horizon_s,available_actions))

    def compute(self, tool, arguments, dispatch):
        if tool not in ('steady_column','condenser_pilot','coupled_dynamics'):raise ValueError('Unsupported computation tool')
        start=time.perf_counter(); result=self._record('MATAN','physical calculation',{'tool':tool,'arguments':arguments},lambda:dispatch(tool,arguments))
        if tool=='steady_column':
            checks={'mass':max(abs(v) for v in result['component_balance_mol_s'])<1e-6,
                    'energy':abs(result['energy_balance_W'])<1e-3,
                    'phase':result['equilibrium_log_fugacity_residual']<1e-5}
        elif tool=='condenser_pilot':
            checks={'energy':abs(result['energy_balance_residual_J'])<1e-4,
                    'pressure':all(math.isfinite(r['pressure_Pa']) and r['pressure_Pa']>0 for r in result['series'])}
        elif tool=='coupled_dynamics':
            checks={'mass':max(abs(v) for v in result['component_balance_residual_mol'])<1e-7,
                    'energy':abs(result['energy_balance_residual_J'])<1e-3,
                    'pressure':all(math.isfinite(p) and p>0 for r in result['series'] for p in r['pressure_Pa'])}
        else:raise ValueError('Unsupported computation tool')
        if not all(checks.values()):raise ValueError('DSO rejected physically invalid result')
        return result,{'checks':checks,'mode':'HYBRID batch, no real-time SLA',
                       'compute_seconds':time.perf_counter()-start}


def _logged(method):
    def wrapped(self,*args,**kwargs):
        return self._record('DSO',method.__name__,{'argument_count':len(args)},lambda:method(self,*args,**kwargs))
    return wrapped


for _name in ('regulate','update_weight','personality_step','forecast','learn','diagnose','learn_diagnosis','plan_actions','compute'):
    setattr(DSO,_name,_logged(getattr(DSO,_name)))


class AsyncDSO:
    def __init__(self, fallback, max_age_s, cooldown_s=0, clock=time.monotonic):
        if max_age_s<=0 or cooldown_s<0:raise ValueError('Invalid timing budget')
        self.fallback=fallback; self.max_age=max_age_s; self.cooldown=cooldown_s; self.clock=clock
        self.pool=ThreadPoolExecutor(max_workers=1); self.pending=None; self.last_launch=-math.inf
        self.metrics={'launched':0,'accepted':0,'rejected':0,'backlog':0}

    def submit(self, version, operation, trigger=True):
        now=self.clock()
        if not trigger or self.pending is not None or now-self.last_launch<self.cooldown:return False
        self.pending=(version,now,self.pool.submit(operation)); self.last_launch=now
        self.metrics['launched']+=1; self.metrics['backlog']=1
        return True

    def poll(self, version, admissible):
        if self.pending is None or not self.pending[2].done():return self.fallback
        source_version,started,future=self.pending; self.pending=None; self.metrics['backlog']=0
        try:result=future.result()
        except Exception:
            self.metrics['rejected']+=1;return self.fallback
        if version!=source_version or self.clock()-started>self.max_age or not admissible(result):
            self.metrics['rejected']+=1;return self.fallback
        self.fallback=result; self.metrics['accepted']+=1
        return result

    def close(self):self.pool.shutdown(wait=True,cancel_futures=True)
