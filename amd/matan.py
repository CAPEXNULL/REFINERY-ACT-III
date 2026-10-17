"""Explicit numerical methods; invoked by DSO only."""
import numpy as np


def pressure_features(arguments):
    d=float(arguments.get('duration_s',60))/60
    c=float(arguments.get('cooling_factor',.5))
    if not np.isfinite([d,c]).all() or not 4/60<=d<=2 or not .4<=c<=1:
        raise ValueError('Prediction outside specified model domain')
    return np.array([d*(1-c),d*d*(1-c),d*d*(1-c)**2])


def predict_pressure(model, arguments):
    phi=pressure_features(arguments)
    samples=model.get('samples',[])
    if len(samples)<3:
        return {'available':False,'reason':'fewer than three measured training outcomes',
                'model_version':model.get('version',0)}
    x=np.array([s['features'] for s in samples]); y=np.array([s['delta_Pa'] for s in samples])
    coefficients=np.linalg.solve(x.T@x+1e-8*np.eye(3),x.T@y)
    value=150000+float(phi@coefficients)
    errors=model.get('prospective_errors_Pa',[])
    bound=max(errors) if errors else None
    return {'available':True,'pressure_Pa':value,'model_version':model['version'],
            'uncertainty':{'kind':'empirical maximum prior prospective error; not calibrated',
                           'bound_Pa':bound,'observations':len(errors)},
            'scope':'fixed-initial-state condenser CPU surrogate',
            'coefficients':coefficients.tolist()}


def learn_pressure(model, arguments, actual_pressure, outcome_id, prediction):
    if outcome_id in model.setdefault('outcomes',[]): raise ValueError('Duplicate outcome')
    if not np.isfinite(actual_pressure) or actual_pressure<=0: raise ValueError('Invalid observed pressure')
    features=pressure_features(arguments)
    if prediction.get('available'):
        model.setdefault('prospective_errors_Pa',[]).append(abs(actual_pressure-prediction['pressure_Pa']))
    model.setdefault('samples',[]).append({'features':features.tolist(),'delta_Pa':actual_pressure-150000,
                                         'outcome_id':outcome_id})
    model['outcomes'].append(outcome_id)
    model['version']=model.get('version',0)+1
    return {'model_version':model['version'],'observed_pressure_Pa':actual_pressure,
            'prediction_error_Pa':None if not prediction.get('available') else actual_pressure-prediction['pressure_Pa']}
