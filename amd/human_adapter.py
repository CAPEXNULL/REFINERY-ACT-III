"""Optional adapter model; scores are supplied observations, not diagnoses."""
import math

FEATURES=('judgment','rejection','violence','loneliness')


def owner_context(context):
    if not context:return {'status':'owner_absent','observation_available':False,'threat_target':'None'}
    if context.get('status') not in ('owner_absent','owner_known','owner_present','owner_endangered'):
        raise ValueError('Invalid owner state')
    if context['status']!='owner_absent' and not context.get('owner_id'):raise ValueError('Identified owner requires owner_id')
    threatened=context.get('endangered',False) or context['status']=='owner_endangered'
    target='Owner' if threatened and context['status']!='owner_absent' else 'Human' if context.get('human_nearby_endangered') else 'None'
    return dict(context,observation_available=True,threat_target=target)


def update_human(previous,observation,regulated_update):
    if not observation:return previous,None
    if not observation.get('human_id') or observation.get('source')!='explicit_adapter':
        raise ValueError('Human observation requires a named explicit adapter')
    values=observation.get('features',{})
    if set(values)!=set(FEATURES):raise ValueError('Four explicit model features required')
    for value in values.values():
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=1:
            raise ValueError('Human model features must lie in [0,1]')
    count=previous.get('observations',0)
    baseline=previous.get('baseline',values)
    deviation=sum(abs(values[k]-baseline[k]) for k in FEATURES)/4
    old_deviation=previous.get('deviation',0.)
    orbit=deviation/old_deviation if old_deviation>1e-12 else None
    confidence=min(.8,(count+1)/(count+6))
    if orbit is not None and orbit>1:confidence/=orbit
    forecast={'kind':'hypothesis, not validated psychological assessment','features':previous.get('weights',baseline),
              'confidence':previous.get('confidence',0.),'model_version':count}
    updated={'human_id':observation['human_id'],'weights':{k:regulated_update(previous.get('weights',values)[k],values[k]) for k in FEATURES},
             'baseline':{k:regulated_update(baseline[k],values[k]) for k in FEATURES},'observations':count+1,
             'deviation':deviation,'orbit_lambda':orbit,'confidence':confidence,
             'observed_prediction_error':None if count==0 else {k:values[k]-forecast['features'][k] for k in FEATURES},
             'status':'HYPOTHESIS','source':'explicit_adapter'}
    return updated,forecast
