"""Persistent production subject cycle; domain completeness remains explicit."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid
from pathlib import Path
from dataclasses import asdict
import copy
import hashlib
import json
import os
import unicodedata
from amd.dso import DSO
from amd.human_adapter import owner_context,update_human
from amd.reasoning import KnowledgeGraph


def normalized(value):
    if isinstance(value,str):return unicodedata.normalize('NFC',value)
    if isinstance(value,list):return [normalized(v) for v in value]
    if isinstance(value,dict):
        pairs=[(normalized(k),normalized(v)) for k,v in value.items()]
        if len({k for k,v in pairs})!=len(pairs):raise ValueError('Duplicate keys after Unicode normalization')
        return dict(pairs)
    return value


@dataclass
class SubjectState:
    identity: str = 'perseus-amd-industry'
    mission_variant: str = 'production'
    sequence: int = 0
    memory: list = field(default_factory=list)
    active_goals: list = field(default_factory=list)
    knowledge: list = field(default_factory=list)
    experience: dict = field(default_factory=lambda: {'reaction_history': [], 'weights': {}})
    emotion_state: dict = field(default_factory=dict)
    skills: list = field(default_factory=list)
    transfer_history: list = field(default_factory=list)
    personality_profile: dict = field(default_factory=lambda: {'precision':.8,'self_consistency':1.})
    owner_model: dict = field(default_factory=lambda: {'status':'owner_absent','observation_available':False})
    human_models: dict = field(default_factory=dict)
    behavior_arsenal: list = field(default_factory=lambda:['precision','persistence','observe'])
    task_models: dict = field(default_factory=dict)
    self_model: dict = field(default_factory=dict)
    decision_trace: list = field(default_factory=list)
    processed_events: list = field(default_factory=list)
    configuration: str = 'pers-a-amd-1'
    reasoning_records: list = field(default_factory=list)
    diagnosis_pending: dict = field(default_factory=dict)


class Perseus:
    def __init__(self,state_path=None,audit=None):
        self.state_path=Path(state_path) if state_path else None
        self.state=SubjectState(**json.loads(self.state_path.read_text(encoding='utf-8'))) if self.state_path and self.state_path.exists() else SubjectState()
        self.audit=audit;self.dso=DSO(audit)
        for key,value in {'links':[],'traces':[],'invariants':['identity protected','measured outcomes only']}.items():
            self.state.experience.setdefault(key,value)

    def _persist(self):
        if self.state_path:
            self.state_path.parent.mkdir(parents=True,exist_ok=True)
            temporary=self.state_path.with_suffix('.pending')
            temporary.write_text(json.dumps(asdict(self.state),sort_keys=True,allow_nan=False),encoding='utf-8')
            os.replace(temporary,self.state_path)

    def _stage(self,name,operation):
        before=copy.deepcopy(asdict(self.state))
        def action():
            value=operation()
            self.state.decision_trace.append({'sequence':self.state.sequence,'phase':name})
            return value
        if not self.audit:return action()
        def validate(value):
            artifact=self.audit.directory/('state-'+str(self.state.sequence)+'-'+name+'-'+str(len(self.state.decision_trace))+'.json')
            with artifact.open('x',encoding='utf-8') as f:json.dump(asdict(self.state),f,allow_nan=False)
            return {'state_serializable':True,'sequence_preserved':self.state.sequence==before['sequence']},[artifact]
        return self.audit.execute('Pers_A',name,self.state.identity,{},
            'Phase completes; subject state serializable; sequence unchanged; immutable state evidence',action,validate,before=before)

    def coordinate(self,event,dispatch):
        event=normalized(event)
        tool=event['type']
        if tool=='industrial_diagnosis':return self.diagnose_observation(event['arguments']['observation'],event['arguments']['reference'],event.get('event_id'))
        if tool not in ('steady_column','condenser_pilot','coupled_dynamics'):raise ValueError('Unsupported SUBJECT_EVENT')
        arguments=copy.deepcopy(event['arguments']);variant=json.dumps(arguments,sort_keys=True,allow_nan=False)
        event_id=event.get('event_id') or hashlib.sha256(json.dumps({'event':event,'sequence':self.state.sequence+1},sort_keys=True,allow_nan=False).encode()).hexdigest()[:24]
        if event_id in self.state.processed_events:raise ValueError('Duplicate SUBJECT_EVENT')
        if 'identity_update' in event and (event.get('source')!='owner' or event.get('owner_approval') is not True):
            raise ValueError('Identity Guard rejected update')
        if 'identity_update' in event and (not isinstance(event['identity_update'],str) or not event['identity_update']):
            raise ValueError('Invalid identity update')
        risk=float(event.get('risk',0))
        if not 0<=risk<=1:raise ValueError('Invalid risk')
        owner=owner_context(event.get('owner_context'))
        human=event.get('human_observation')
        if human:update_human(self.state.human_models.get(human.get('human_id'),{}),human,self.dso.update_weight)
        self.state.sequence+=1
        self._stage('OWNER_CONTEXT',lambda:self.state.owner_model.update(owner))
        self._stage('IDENTITY_GUARD',lambda:setattr(self.state,'identity',event['identity_update']) if 'identity_update' in event else self.state.identity)
        prior=[r for r in self.state.memory if r['tool']==tool]
        novelty=0. if any(r.get('variant')==variant for r in prior) else 1.
        old_weight=self.state.experience['weights'].get(tool,0.)
        self.state.emotion_state=self._stage('EMOTION',lambda:self.dso.regulate(risk,0,novelty,old_weight))
        record={'event_id':event_id,'sequence':self.state.sequence,'tool':tool,'variant':variant,'arguments':arguments,
                'emotion':copy.deepcopy(self.state.emotion_state),'links':[r['event_id'] for r in prior[-5:]],'outcome':'PENDING'}
        self._stage('MEMORY',lambda:self.state.memory.append(record))
        self._stage('KNOWLEDGE',lambda:[k for k in self.state.knowledge if k['tool']==tool])
        self._stage('EXPERIENCE',lambda:self.state.experience['traces'].append({'event_id':event_id,'basis':record['links']}))
        self._stage('SKILL',lambda:[s for s in self.state.skills if s['tool']==tool])
        structure={'mass_balance','energy_balance','phase_equilibrium'} if tool=='steady_column' else {'energy_balance','phase_equilibrium','pressure_observation'}
        transfers=[]
        def transfer():
            for skill in self.state.skills:
                other=set(skill['structure']);similarity=len(other&structure)/len(other|structure)
                if skill['strength']>=.5 and similarity>=.25 and (skill['tool']!=tool or variant not in skill['variants']):
                    item={'event_id':event_id,'source_skill':skill['id'],'similarity':similarity,'target_variant':variant,
                          'status':'CANDIDATE','scope':'physical calculation verification skill'}
                    transfers.append(item);self.state.transfer_history.append(item)
        self._stage('TRANSFER',transfer)
        self._stage('PERSONALITY',lambda:self.state.personality_profile.update(precision=self.dso.personality_step(self.state.personality_profile['precision'],.8+.2*old_weight)))
        human_update={'applicable':False,'reason':'no human observations supplied'}
        def adapt_human():
            if human:
                identifier=human['human_id'];model,forecast=update_human(self.state.human_models.get(identifier,{}),human,self.dso.update_weight)
                self.state.human_models[identifier]=model
                human_update.update(applicable=True,model_version=model['observations'],prediction=forecast,confidence=model['confidence'])
                human_update.pop('reason',None)
        self._stage('HUMAN_MODEL',adapt_human)
        goal={'id':event_id,'objective':event.get('external_goal','obtain a physically checked result'),'state':'ACTIVE',
              'priority':'human safety' if owner['threat_target'] in ('Owner','Human') else 'risk reduction' if risk>=.65 else 'engineering calculation',
              'threat_target':owner['threat_target']}
        self._stage('GOAL',lambda:self.state.active_goals.append(goal))
        behavior={'pattern':'precision','action':'calculate and verify','plant_actuation':False}
        self._stage('BEHAVIOR',lambda:behavior)
        model=self.state.task_models.setdefault(tool,{'version':0,'samples':[],'outcomes':[]})
        try:
            prediction=self._stage('DSO_PROJECTION',lambda:self.dso.forecast(tool,model,arguments))
            record['prediction_before_action']=copy.deepcopy(prediction)
            self.state.self_model['pending_event']=record;self._persist()
            result,validation=self._stage('ACTION',lambda:self.dso.compute(tool,arguments,dispatch))
        except Exception:
            goal['state']='FAILED';self.state.processed_events.append(event_id)
            self.state.memory.remove(record)
            self.state.experience['weights'][tool]=self.dso.update_weight(old_weight,0.)
            self.state.self_model.pop('pending_event',None);self._persist();raise
        def learn():
            record['outcome']='CONFIRMED';record['validation']=validation['checks'];record['goal_id']=event_id
            weight=self.dso.update_weight(old_weight,1.);self.state.experience['weights'][tool]=weight
            confirmed={r.get('variant') for r in self.state.memory if r['tool']==tool and r.get('outcome')=='CONFIRMED'}
            if weight>=.3 and record['links'] and not any(k['tool']==tool for k in self.state.knowledge):
                self.state.knowledge.append({'tool':tool,'method':'solve and verify physical invariants','source_events':record['links']+[event_id],
                                             'scope':'observed calculation variants','status':'CONFIRMED'})
            if len(confirmed)>=3 and weight>=.5:
                existing=next((s for s in self.state.skills if s['tool']==tool),None)
                skill={'id':'verify-'+tool,'tool':tool,'strength':weight,'variants':sorted(confirmed),'structure':sorted(structure)}
                if existing:existing.update(skill)
                else:self.state.skills.append(skill)
            for item in transfers:item['status']='VALIDATED_ON_TARGET'
            update={'weight':weight,'confirmed_variants':len(confirmed)}
            if tool=='condenser_pilot':update['task_model']=self.dso.learn(model,arguments,result['series'][-1]['pressure_Pa'],event_id,prediction)
            self.state.experience['reaction_history'].append({'event_id':event_id,'outcome':'CONFIRMED','weight':weight})
            graph=KnowledgeGraph(self.state.reasoning_records)
            graph.add(event_id,'verified_by',tool,[event_id])
            self.state.reasoning_records=graph.records
            goal['state']='COMPLETED';self.state.processed_events.append(event_id)
            return update
        learning=self._stage('NEW_EXPERIENCE',learn)
        self.state.self_model={'identity':self.state.identity,'sequence':self.state.sequence,'knowledge_count':len(self.state.knowledge),
            'skill_count':len(self.state.skills),'unresolved':['full refinery A/B/C transfer','causal intervention ranking','human observations absent']}
        self._stage('SELF_MODEL',lambda:self.state.self_model);self._persist()
        return {'active_goal':goal,'behavior_intent':behavior,'state_delta':{'sequence':self.state.sequence,'memory_records':len(self.state.memory),
                'knowledge_records':len(self.state.knowledge),'skills':len(self.state.skills)},'learning_update':learning,'prediction':prediction,
                'uncertainty':prediction.get('uncertainty'),'owner_or_human_update':human_update,
                'trace':record,'result':result,'response_context':self.state.self_model,
                'limitations':['domain pilot; not full metaprompt PASS','calculation transfer is not refinery diagnostic transfer']}

    def diagnose_observation(self,observation,reference,event_id=None):
        # Labels/scenario metadata cannot enter this adapter.
        from amd.diagnostics import KEYS
        if set(observation)-KEYS or set(reference)-KEYS:raise ValueError('Hidden truth rejected')
        observation=copy.deepcopy(observation);reference=copy.deepcopy(reference)
        event_id=event_id or hashlib.sha256(json.dumps({'observation':observation,'sequence':self.state.sequence+1},sort_keys=True,allow_nan=False).encode()).hexdigest()[:24]
        if event_id in self.state.processed_events or event_id in self.state.diagnosis_pending:raise ValueError('Duplicate diagnostic event')
        self.state.sequence+=1
        self._stage('OWNER_CONTEXT',lambda:self.state.owner_model)
        self._stage('IDENTITY_GUARD',lambda:self.state.identity)
        self.state.emotion_state=self._stage('EMOTION',lambda:self.dso.regulate(.2,0.,1.,self.state.experience['weights'].get('diagnosis',0.)))
        record={'event_id':event_id,'sequence':self.state.sequence,'tool':'industrial_diagnosis','observation':observation,
                'reference':reference,'links':[r['event_id'] for r in self.state.memory if r['tool']=='industrial_diagnosis'][-5:],
                'outcome':'PENDING'}
        self._stage('MEMORY',lambda:self.state.memory.append(record))
        self._stage('KNOWLEDGE',lambda:[k for k in self.state.knowledge if k['tool']=='industrial_diagnosis'])
        self._stage('EXPERIENCE',lambda:self.state.experience['traces'].append({'event_id':event_id,'basis':record['links']}))
        self._stage('SKILL',lambda:[s for s in self.state.skills if s['tool']=='industrial_diagnosis'])
        shape=','.join(f'{role}:{observation["roles"].count(role)}' for role in sorted(set(observation['roles'])))
        transfer=[]
        def assess_transfer():
            for skill in self.state.skills:
                if skill['tool']=='industrial_diagnosis' and shape not in skill['shapes']:
                    item={'event_id':event_id,'source_skill':skill['id'],'target_shape':shape,
                          'structural_similarity':1.,'binding':'same measured equipment roles; counts/topology may differ','status':'PENDING'}
                    transfer.append(item);self.state.transfer_history.append(item)
        self._stage('TRANSFER',assess_transfer)
        self._stage('PERSONALITY',lambda:self.state.personality_profile)
        self._stage('HUMAN_MODEL',lambda:None)
        goal={'id':event_id,'objective':'infer cause from observations without hidden truth','state':'ACTIVE'}
        self._stage('GOAL',lambda:self.state.active_goals.append(goal))
        behavior={'pattern':'precision','action':'diagnose or preserve uncertainty','plant_actuation':False}
        self._stage('BEHAVIOR',lambda:behavior)
        model=self.state.task_models.setdefault('industrial_diagnosis',{'version':0,'samples':[],'outcomes':[]})
        self._stage('DSO_PROJECTION',lambda:{'model_version':model['version'],'available_roles':observation['roles']})
        try:prediction=self._stage('ACTION',lambda:self.dso.diagnose(model,observation,reference))
        except Exception:
            goal['state']='FAILED';record['outcome']='FAILED';self._persist();raise
        record['prediction_before_outcome']=copy.deepcopy(prediction)
        self.state.diagnosis_pending[event_id]={'observation':observation,'reference':reference,'prediction':prediction,'shape':shape,'transfers':transfer}
        goal['state']='WAITING_OUTCOME'
        self._stage('NEW_EXPERIENCE',lambda:{'observed':'diagnostic hypothesis generated; root cause not yet confirmed'})
        self.state.self_model.update(diagnosis_model_version=model['version'],pending_diagnosis=len(self.state.diagnosis_pending))
        self._stage('SELF_MODEL',lambda:self.state.self_model);self._persist()
        return {'event_id':event_id,'prediction':prediction,'active_goal':goal,'behavior_intent':behavior,
                'state_delta':{'sequence':self.state.sequence,'memory_records':len(self.state.memory)},
                'learning_update':{'confirmed':False},'trace':record}

    def observe_diagnosis_outcome(self,event_id,label,variant,physical_evidence):
        if event_id not in self.state.diagnosis_pending:raise ValueError('Unknown or duplicate diagnosis outcome')
        if not physical_evidence.get('mass_balance_pass') or not physical_evidence.get('energy_balance_pass'):
            raise ValueError('Unverified physical outcome cannot train diagnosis')
        pending=self.state.diagnosis_pending[event_id];model=self.state.task_models['industrial_diagnosis']
        update=self._stage('CONFIRMED_DIAGNOSTIC_OUTCOME',lambda:self.dso.learn_diagnosis(model,pending['observation'],pending['reference'],label,event_id,variant))
        success=pending['prediction']['label']==label
        weight=self.dso.update_weight(self.state.experience['weights'].get('diagnosis',0.),1. if success else 0.)
        self.state.experience['weights']['diagnosis']=weight
        record=next(r for r in self.state.memory if r['event_id']==event_id)
        record.update(outcome='CONFIRMED',confirmed_label=label,diagnosis_correct=success,physical_evidence=physical_evidence,variant=variant)
        self.state.experience['reaction_history'].append({'event_id':event_id,'label':label,'correct':success})
        if label!='normal':
            examples=[s for s in model['samples'] if s['label']==label]
            knowledge=next((k for k in self.state.knowledge if k.get('cause')==label and k['tool']=='industrial_diagnosis'),None)
            if knowledge is None:
                knowledge={'tool':'industrial_diagnosis','cause':label,'method':'role-normalized observed residual template',
                           'status':'EMPIRICALLY_CONFIRMED_IN_MODEL','source_events':[]};self.state.knowledge.append(knowledge)
            knowledge['source_events'].append(event_id)
            variants=sorted({r['variant'] for r in self.state.memory if r.get('confirmed_label')==label and r.get('diagnosis_correct')})
            if len(variants)>=3:
                skill=next((s for s in self.state.skills if s['id']=='diagnose-'+label),None)
                strength=len([r for r in self.state.memory if r.get('confirmed_label')==label and r.get('diagnosis_correct')])/len(examples)
                if strength>=.5:
                    data={'id':'diagnose-'+label,'tool':'industrial_diagnosis','cause':label,'strength':strength,
                          'variants':variants,'shapes':sorted({pending['shape']}|set(skill['shapes'] if skill else []))}
                    if skill:skill.update(data)
                    else:self.state.skills.append(data)
        for transfer in self.state.transfer_history:
            if transfer.get('event_id')==event_id:
                transfer['status']=('CONFIRMED' if success else 'FAILED') if transfer['source_skill']=='diagnose-'+label else 'NOT_APPLICABLE'
        goal=next(g for g in self.state.active_goals if g['id']==event_id);goal['state']='COMPLETED'
        self.state.diagnosis_pending.pop(event_id);self.state.processed_events.append(event_id)
        self.state.self_model.update(diagnosis_model_version=model['version'],pending_diagnosis=len(self.state.diagnosis_pending))
        self._persist()
        return dict(update,correct=success,weight=weight,transfer_outcomes=[t['status'] for t in pending['transfers']])
