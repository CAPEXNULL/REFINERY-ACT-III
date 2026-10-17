from amd.workspace import atomic_json
"""CPU refinery scenarios, observed diagnosis and conditional action forecasts."""
import copy
import json
import math
import hashlib
from pathlib import Path
import uuid
from amd.audit import Trace, evidence, utc
from amd.plant import Plant, Scenario, FAULTS
from amd.perseus import Perseus


class IndustryService:
    def __init__(self, root):
        self.root=Path(root)
        self.audit=Trace(self.root/'reports/trace/industry-runtime')
        self.agent=Perseus(self.audit.directory/'SUBJECT_STATE.json',audit=self.audit)
        self.bases={}
        self.model_source=None

    def status(self):
        self.model_source=None
        reports=sorted((self.root/'reports/trace').glob('*/transfer-*/TRANSFER_REPORT.json'),
                       key=lambda p:p.stat().st_mtime,reverse=True)
        # A clean checkout may carry the qualified frozen model without local
        # runtime journals. Accept only matching model/report AND source hashes.
        bundle=self.root/'assets/refinery'
        canonical_sources={}
        try:
            qualification=json.loads((bundle/'QUALIFICATION.json').read_text(encoding='utf-8-sig'))
            valid=(isinstance(qualification,dict) and qualification.get('schema')=='refinery-qualified-model-v1' and
                   evidence(bundle/'TRANSFER_REPORT.json')['sha256']==qualification['report_sha256'] and
                   evidence(bundle/'FROZEN_MODEL.json')['sha256']==qualification['model_sha256'] and
                   qualification.get('source_hash_method')=='CRLF-to-LF-only' and
                   isinstance(qualification.get('source_sha256_lf'),dict))
            if valid:
                canonical_sources=qualification['source_sha256_lf']
                reports.insert(0,bundle/'TRANSFER_REPORT.json')
        except (OSError,ValueError,KeyError):
            pass
        for path in reports:
            report=json.loads(path.read_text(encoding='utf8'))
            manifest=report.get('protocol',{}).get('source_manifest',[])
            def source_matches(item):
                source=self.root/Path(item['path'].replace('\\','/'))
                if not source.is_file():return False
                if path.parent==bundle:
                    return hashlib.sha256(source.read_bytes().replace(b'\r\n',b'\n')).hexdigest()==canonical_sources.get(item['path'])
                return evidence(source)['sha256']==item['sha256']
            current=bool(manifest) and all(source_matches(item) for item in manifest)
            if (path.parent/'FROZEN_MODEL.json').is_file() and set(report.get('transfer_accuracy',{}))=={'B','C'} and current and report.get('source_unchanged') and len(report.get('diagnostic_skills',[]))==3 and report.get('retention_accuracy')==1 and all(
                    v>=.75 for v in report.get('transfer_accuracy',{}).values()):
                self.model_source=path.parent/'FROZEN_MODEL.json'
                break
        return {'device':'CPU','model_ready':self.model_source is not None,
                'model_source':self.model_source.relative_to(self.root).as_posix() if self.model_source else None,
                'scope':'Synthetic refinery surrogate; no real plant validation or calibrated confidence'}

    @staticmethod
    def validate(args):
        if not isinstance(args,dict):raise ValueError('Invalid industry request')
        if set(args)-{'configuration','fault','duration_s','severity','plan_actions'}:
            raise ValueError('Unknown industrial parameter')
        configuration=args.get('configuration','A');fault=args.get('fault','cooling_loss')
        if configuration not in ('A','B','C') or fault not in FAULTS:
            raise ValueError('Unknown configuration or scenario')
        duration=args.get('duration_s',4.);severity=args.get('severity',.5)
        for name,value,low,high in [('duration_s',duration,4,6),('severity',severity,.2,1)]:
            if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or not low<=value<=high:
                raise ValueError(f'{name} outside supported range')
        planning=args.get('plan_actions',False)
        if not isinstance(planning,bool):raise ValueError('plan_actions must be boolean')
        return {'configuration':configuration,'fault':fault,'duration_s':duration,
                'severity':severity,'plan_actions':planning}

    def run(self, args, progress=None):
        args=self.validate(args)
        configuration=args['configuration'];fault=args['fault']
        duration=args['duration_s'];severity=args['severity'];planning=args['plan_actions']
        def advance(stage,percent):
            if progress:progress(stage,percent)
        if not self.status()['model_ready']:
            raise ValueError('Diagnostic training qualification is pending; no diagnosis accepted yet')
        advance('initialization',5)
        if not self.agent.state.task_models.get('industrial_diagnosis'):
            self.agent.state.task_models['industrial_diagnosis']=copy.deepcopy(json.loads(self.model_source.read_text(encoding='utf8')))
            self.agent._persist()
        event='industry-'+uuid.uuid4().hex
        def physical():
            if configuration not in self.bases:self.bases[configuration]=Plant(configuration)
            advance('reference',15)
            normal=self.bases[configuration].clone();reference=normal.run(duration=duration)
            advance('physical',40)
            plant=self.bases[configuration].clone()
            result=plant.run(duration=duration,scenario=Scenario(fault,severity=severity))
            path=self.audit.directory/(event+'.physical.json')
            path.write_text(json.dumps(result,allow_nan=False),encoding='utf8')
            return normal,reference,result,path
        normal,reference,result,path=self.audit.execute('MATAN','scenario and reference',event,
            {'configuration':configuration,'duration_s':duration},
            'Both runs conserve components <1e-7 mol and energy <1e-3 J',physical,
            lambda r:({'mass':all(max(abs(v) for v in x['component_balance_residual_mol'])<1e-7 for x in r[1:3]),
                       'energy':all(abs(x['energy_balance_residual_J'])<1e-3 for x in r[1:3])},[r[3]]))
        observation=result['series'][-1]['observation'];baseline=reference['series'][-1]['observation']
        advance('diagnosis',60)
        model_path=self.audit.directory/(event+'.model-before-diagnosis.json')
        self.audit.execute('Pers_A','freeze actual model before decision',event,{},
            'Persist the exact current learned model before diagnosis and feedback',
            lambda:atomic_json(model_path,self.agent.state.task_models['industrial_diagnosis']),
            lambda n:({'written':n>0},[model_path]))
        model_hash=evidence(model_path)['sha256']
        hypothesis=self.agent.diagnose_observation(observation,baseline,event)
        advance('forecast',75)
        forecast=self.agent.dso.plan_actions(normal,observation,hypothesis['prediction'],horizon_s=2.) if planning else None
        advance('feedback',95)
        # Truth is exposed only to the evaluator after the diagnostic decision.
        injected=result['private_truth']['fault']
        actual='normal' if injected in ('cooling_loss','heater_loss') and severity==1 else injected
        evaluation={'actual_cause':actual,'injected_scenario':injected,
                    'correct':hypothesis['prediction']['label']==actual}
        feedback=self.confirm_feedback(event,actual,hypothesis['prediction'],
            {'mass_balance_pass':True,'energy_balance_pass':True})
        evaluation['training_applied']=feedback.get('training_applied',True)
        if not evaluation['training_applied']:evaluation['training_skip_reason']=feedback['reason']
        value={'event_id':event,'created_at':utc(),'request':args,
               'provenance':{'source':'synthetic-physics','model_sha256':model_hash,
                             'seed_model_sha256':evidence(self.model_source)['sha256'],
                             'model_snapshot_ref':model_path.name,
                             'qualification':'finite A/B/C experiment; not real plant validation'},
               'physical':result,'reference':reference,'diagnosis':hypothesis['prediction'],
               'action_forecast':forecast,'evaluation':evaluation,'device':'CPU'}
        output=self.audit.directory/(event+'.accepted.json')
        self.audit.execute('workspace','persist accepted result',event,{},'Persist the complete accepted result immutably',
            lambda:atomic_json(output,value),
            lambda n:({'written':n>0},[output]))
        advance('completed',100)
        return value

    def confirm_feedback(self,event,label,prediction,physical_evidence):
        if event not in self.agent.state.diagnosis_pending:
            raise ValueError('Unknown or duplicate diagnosis outcome')
        if not physical_evidence.get('mass_balance_pass') or not physical_evidence.get('energy_balance_pass'):
            raise ValueError('Unverified physical outcome cannot train diagnosis')
        if label=='normal' or prediction['label']!='normal':
            return self.agent.observe_diagnosis_outcome(event,label,event,physical_evidence)
        # Preserve actual simulator feedback without inventing a distinguishable template.
        def preserve():
            record=next(x for x in self.agent.state.memory if x['event_id']==event)
            record.update(outcome='CONFIRMED_NOT_IDENTIFIABLE',confirmed_label=label,
                          diagnosis_correct=False,physical_evidence=physical_evidence,
                          learning_excluded='below specified observable residual threshold')
            old=self.agent.state.experience['weights'].get('diagnosis',0.)
            self.agent.state.experience['weights']['diagnosis']=self.agent.dso.update_weight(old,0.)
            self.agent.state.experience['reaction_history'].append({'event_id':event,'label':label,
                'correct':False,'observable':False,'training_applied':False})
            next(g for g in self.agent.state.active_goals if g['id']==event)['state']='COMPLETED'
            self.agent.state.diagnosis_pending.pop(event)
            self.agent.state.processed_events.append(event)
            self.agent.state.self_model['pending_diagnosis']=len(self.agent.state.diagnosis_pending)
            return {'training_applied':False,'reason':'cause not distinguishable at the specified residual threshold'}
        value=self.agent._stage('UNOBSERVABLE_CONFIRMED_OUTCOME',preserve)
        self.agent._persist()
        return value
