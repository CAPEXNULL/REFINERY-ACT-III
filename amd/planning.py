"""Observation-based state estimation and explicit model intervention forecasts."""
import copy
import numpy as np
from amd.plant import Scenario,ACTIONS


def estimate_state(normal_plant,observation):
    if observation['equipment']!=normal_plant.cells:raise ValueError('State estimator topology mismatch')
    estimated=normal_plant.clone()
    amounts=[];energies=[];guesses=[]
    for j,f in enumerate(normal_plant.guesses):
        composition=normal_plant.amounts[j]/normal_plant.amounts[j].sum()
        temperature=observation['heater_reference_K'] if j==0 else observation['temperature_K'][j]
        pressure=observation['pressure_kPa'][j]*1000
        flash=estimated.eos.flash(temperature,pressure,composition)
        total=estimated.volumes[j]/flash.molar_volume
        amounts.append(total*composition);energies.append(total*flash.molar_energy);guesses.append(flash)
    estimated.amounts=np.array(amounts);estimated.energies=np.array(energies);estimated.guesses=guesses
    estimated.now=float(observation['time_s']);estimated.initial_amounts=estimated.amounts.sum(axis=0).copy()
    estimated.initial_energy=float(estimated.energies.sum());estimated.ledger_n=np.zeros(3);estimated.ledger_u=0.;estimated.product_mol=0.
    estimated.trip=bool(observation['protection']['latched']);estimated.trip_time=observation['protection']['trip_time_s']
    return estimated


def metrics(result):
    condenser=[i for i,r in enumerate(result['roles']) if r=='condenser']
    peak=max(row['pressure_Pa'][i] for row in result['series'] for i in condenser)
    last=max(result['series'][-1]['pressure_Pa'][i] for i in condenser)
    return {'trip':bool(result['trip']),'peak_condenser_pressure_Pa':float(peak),
            'final_condenser_pressure_Pa':float(last),'product_mol':float(result['product_mol'])}


def compare_actions(normal_plant,observation,diagnosis,horizon_s=4.,available_actions=ACTIONS):
    if diagnosis['label'] not in ('cooling_loss','heater_loss','sensor_bias','normal'):
        return {'available':False,'reason':'unknown cause; preserve observation instead of action recommendation'}
    if not np.isfinite(horizon_s) or not 0<horizon_s<=10:raise ValueError('Invalid planning horizon')
    if not available_actions or set(available_actions)-set(ACTIONS):raise ValueError('Invalid available interventions')
    estimated=estimate_state(normal_plant,observation)
    assumed=Scenario(diagnosis['label'],fault_time=estimated.now,severity=.5,
                     sensor_bias_K=abs(observation['temperature_K'][0]-observation['heater_reference_K']))
    results={};ranking=[]
    for action in sorted(available_actions):
        result=estimated.clone().run(duration=estimated.now+horizon_s,dt=.5,scenario=assumed,action=action,action_time=estimated.now)
        if max(abs(v) for v in result['component_balance_residual_mol'])>1e-7 or abs(result['energy_balance_residual_J'])>1e-3:
            raise ValueError('Intervention forecast failed conservation checks')
        results[action]=result;ranking.append(dict(action=action,**metrics(result)))
    ranking.sort(key=lambda m:(m['trip'],max(0.,m['peak_condenser_pressure_Pa']-160000),
                              m['final_condenser_pressure_Pa'],-m['product_mol'],m['action']))
    return {'available':True,'selected_action':ranking[0]['action'],'ranking':ranking,'forecasts':results,
            'prediction_before_outcome':True,'diagnosis_model_version':diagnosis['model_version'],
            'assumptions':['nominal composition used to estimate inventories from sensors',
                           'ongoing diagnosed fault with assumed resource severity 0.5',
                           'restore_cooling feasible only when resource can actually be restored'],
            'confidence':None,'uncertainty':'conditional model forecast; no calibrated intervention confidence'}
