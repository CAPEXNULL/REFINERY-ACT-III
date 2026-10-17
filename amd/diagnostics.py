"""Role-based observation-only diagnosis and measured structural template learning."""
import numpy as np

LABELS=('cooling_loss','heater_loss','sensor_bias')
KEYS={'time_s','equipment','roles','temperature_K','pressure_kPa','heater_reference_K','protection'}
FEATURE_NAMES=('heater_temperature_residual_K','heater_sensor_reference_disagreement_K',
               'max_condenser_pressure_residual_kPa','mean_column_pressure_residual_kPa','reboiler_temperature_residual_K')


def features(observation,reference):
    for record in (observation,reference):
        if set(record)-KEYS:raise ValueError('Non-observation fields rejected by diagnostic adapter')
        length=len(record['equipment'])
        if len(set(record['equipment']))!=length or any(len(record[k])!=length for k in ('roles','temperature_K','pressure_kPa')):
            raise ValueError('Inconsistent sensor dimensions')
        if any(v is None for k in ('temperature_K','pressure_kPa') for v in record[k]) or record['heater_reference_K'] is None:
            return None
        if not np.isfinite(record['temperature_K']+record['pressure_kPa']+[record['heater_reference_K']]).all():
            return None
    lookup={name:i for i,name in enumerate(reference['equipment'])}
    if set(lookup)!=set(observation['equipment']):raise ValueError('Reference topology mismatch')
    temp=np.array(observation['temperature_K']);pressure=np.array(observation['pressure_kPa'])
    baseline_temp=np.array([reference['temperature_K'][lookup[name]] for name in observation['equipment']])
    baseline_pressure=np.array([reference['pressure_kPa'][lookup[name]] for name in observation['equipment']])
    roles=np.array(observation['roles'])
    if any(not np.any(roles==role) for role in ('heater','column','reboiler','condenser')):raise ValueError('Missing equipment role')
    if np.count_nonzero(roles=='heater')!=1 or np.count_nonzero(roles=='reboiler')!=1:raise ValueError('Ambiguous heater/reboiler roles')
    h=int(np.flatnonzero(roles=='heater')[0]);r=int(np.flatnonzero(roles=='reboiler')[0])
    return np.array([temp[h]-baseline_temp[h],temp[h]-observation['heater_reference_K'],
                     np.max((pressure-baseline_pressure)[roles=='condenser']),
                     np.mean((pressure-baseline_pressure)[roles=='column']),temp[r]-baseline_temp[r]])


def diagnose(model,observation,reference):
    vector=features(observation,reference)
    version=model.get('version',0)
    if vector is None:return {'label':'unknown','reason':'missing or invalid sensor','model_version':version,'confidence':None}
    norm=float(np.linalg.norm(vector));samples=model.get('samples',[])
    common={'features':dict(zip(FEATURE_NAMES,vector.tolist())),'model_version':version,
            'confidence':None,'uncertainty':'template similarity is not calibrated probability'}
    if norm<.08:return dict(common,label='normal',reason='below specified model-residual threshold',similarity=None)
    if not samples:return dict(common,label='unknown',reason='no confirmed cause templates',similarity=None)
    scores=[]
    for label in LABELS:
        examples=[np.array(s['direction']) for s in samples if s['label']==label]
        if not examples:continue
        direction=np.mean(examples,axis=0);direction/=np.linalg.norm(direction)
        similarity=float(vector@direction/norm)
        # A sensor offset has two signed orientations of the same learned structure.
        scores.append({'label':label,'similarity':abs(similarity) if label=='sensor_bias' else similarity})
    scores.sort(key=lambda r:(-r['similarity'],r['label']))
    unexplained=float(np.sqrt(max(0.,1-scores[0]['similarity']**2))) if scores else 1.
    if not scores or scores[0]['similarity']<.85 or unexplained>.3 or len(scores)>1 and scores[0]['similarity']-scores[1]['similarity']<.15:
        return dict(common,label='unknown',reason='unsupported or ambiguous residual structure',ranking=scores,relative_unexplained_residual=unexplained,similarity=scores[0]['similarity'] if scores else None)
    label=scores[0]['label'];role='condenser' if label=='cooling_loss' else 'heater'
    candidates=[i for i,r in enumerate(observation['roles']) if r==role]
    index=max(candidates,key=lambda i:observation['pressure_kPa'][i]-reference['pressure_kPa'][reference['equipment'].index(observation['equipment'][i])]) if role=='condenser' else candidates[0]
    root=observation['equipment'][index]
    chain=[root]+[name for name,role in zip(observation['equipment'],observation['roles']) if role=='column'] if label=='cooling_loss' else [root]
    return dict(common,label=label,similarity=scores[0]['similarity'],ranking=scores,root_equipment=root,
                causal_chain=chain,reason='matched measured structural cause template; hypothesis until outcome confirmation')


def learn(model,observation,reference,label,outcome_id,variant):
    if label not in LABELS and label!='normal':raise ValueError('Unsupported evaluator outcome')
    if outcome_id in model.setdefault('outcomes',[]):raise ValueError('Duplicate diagnosis outcome')
    vector=features(observation,reference)
    if vector is None:raise ValueError('Cannot learn from missing observations')
    norm=float(np.linalg.norm(vector))
    if label!='normal' and norm<.08:raise ValueError('Cause outcome not observably distinguished at this sample')
    if label!='normal':
        orientation=-1 if label=='sensor_bias' and vector[1]<0 else 1
        model.setdefault('samples',[]).append({'label':label,'direction':(orientation*vector/norm).tolist(),
                    'features':vector.tolist(),'direction_orientation':orientation,'outcome_id':outcome_id,'variant':variant})
    model['outcomes'].append(outcome_id);model['version']=model.get('version',0)+1
    return {'model_version':model['version'],'label':label,'measured_feature_norm':norm}
