"""First conserving coupled dynamic column/condenser pilot.

Equilibrium control volumes, calibrated vapor resistances and level-dependent
liquid draws. Drum split/subcooling are algebraic, not final dynamic models.
"""
import json
from pathlib import Path
import time
import numpy as np
import CoolProp.CoolProp as CP
from amd.column import solve_column, ColumnConfig
from amd.thermo import PengRobinson, ThermoError


def run_coupled(duration=10., dt=.5, cooling_factor=.5, fault_time=2.):
    if not 0<duration<=120 or not 0<dt<=.5 or not .4<=cooling_factor<=1 or not 0<=fault_time<=duration:
        raise ValueError('Invalid coupled pilot configuration')
    eos=PengRobinson(); steady=solve_column(); n=6
    # Cell order: H, six stages, reboiler R, condenser E.
    guesses=[]; amounts=[]; energies=[]; volumes=[]
    def add(t,p,q,volume):
        f=eos.flash(float(t),float(p),q)
        total=volume/f.molar_volume
        amounts.append(total*np.array(q)); energies.append(total*f.molar_energy); volumes.append(volume); guesses.append(f)
    add(430.,153000.,steady['feed_composition'],.2)
    for j in range(n+1):
        x=np.array(steady['liquid_composition'][j]); y=np.array(steady['vapor_composition'][j])
        add(steady['temperature_K'][j],steady['pressure_Pa'][j],.9*x+.1*y,1.)
    cs=CP.AbstractState('PR','&'.join(eos.names)); xd=np.array(steady['distillate_composition']); cs.set_mole_fractions(xd); cs.update(CP.PQ_INPUTS,140000.,0.)
    add(cs.T(),140000.,.8*xd+.2*np.array(cs.mole_fractions_vapor()),3.)
    amounts=np.array(amounts); energies=np.array(energies); volumes=np.array(volumes)
    initial_amounts=amounts.sum(axis=0).copy(); initial_energy=energies.sum()
    nominal_liquid=np.array([f.beta for f in guesses])
    nominal_liquid=(1-nominal_liquid)*amounts.sum(axis=1)
    supply=eos.flash(350.,153000.,steady['feed_composition'])
    heater_duty=guesses[0].molar_enthalpy-supply.molar_enthalpy
    ua=(steady['vapor_mol_s'][0]*eos.properties(guesses[1].temperature,guesses[1].pressure,guesses[1].vapor,'vapor')[2]-2*eos.properties(guesses[-1].temperature,guesses[-1].pressure,guesses[-1].liquid,'liquid')[2])/(guesses[-1].temperature-300)
    if ua<=0: raise ThermoError('Invalid initial condenser conductance')
    ledger_n=np.zeros(3); ledger_u=0.; records=[]; now=0.
    def observe():
        return {'time_s':now,'temperature_K':[float(f.temperature) for f in guesses],'pressure_Pa':[float(f.pressure) for f in guesses],'vapor_fraction':[float(f.beta) for f in guesses],'distillate_composition':guesses[-1].liquid.tolist(),'condenser_cooling_W':float(ua*(cooling_factor if now>=fault_time else 1)*(guesses[-1].temperature-300))}
    while True:
        records.append(observe())
        if now>=duration-1e-9: break
        step=min(dt,duration-now)
        # A discontinuity at the fault boundary is applied exactly, never early.
        if now<fault_time<now+step: step=fault_time-now
        dn=np.zeros_like(amounts); du=np.zeros_like(energies)
        flows=[]
        def stream(src,dst,flow,phase='liquid',cool=False):
            f=guesses[src]
            if phase=='mixed': q=amounts[src]/amounts[src].sum(); h=f.molar_enthalpy
            else:
                q=f.liquid if phase=='liquid' else f.vapor
                h=eos.properties(f.temperature,f.pressure,q,phase)[2]
            flows.append([src,dst,max(float(flow),0.),phase,q,h,cool])
        stream(0,4,1.,'mixed')
        # Rising condenser pressure reduces overhead evacuation, coupling stages.
        for source in range(1,8):
            target=8 if source==1 else source-1
            delta=guesses[source].pressure-guesses[target].pressure
            nominal_delta=10000. if source==1 else 1000.
            stream(source,target,steady['vapor_mol_s'][source-1]*np.sqrt(max(delta,0)/nominal_delta),'vapor')
        for source in range(1,7):
            rate=steady['liquid_mol_s'][source-1]*(1-guesses[source].beta)*amounts[source].sum()/nominal_liquid[source]
            stream(source,source+1,rate)
        stream(7,None,.5*(1-guesses[7].beta)*amounts[7].sum()/nominal_liquid[7])
        ec=2*(1-guesses[8].beta)*amounts[8].sum()/nominal_liquid[8]
        stream(8,1,.75*ec,cool=True)
        stream(8,None,.25*ec,cool=True)
        # Bound phase withdrawals for an explicit substep without losing mass.
        for source in range(9):
            for phase in ('liquid','vapor','mixed'):
                ff=[e for e in flows if e[0]==source and e[3]==phase]
                requested=sum(e[2] for e in ff)*step
                available=amounts[source].sum()*(1-guesses[source].beta if phase=='liquid' else guesses[source].beta if phase=='vapor' else 1)
                if requested>available and requested>0:
                    for e in ff: e[2]*=.95*available/requested
        external_n=np.array(steady['feed_composition']); external_u=supply.molar_enthalpy
        dn[0]+=external_n; du[0]+=external_u
        heat=np.zeros(9); heat[0]=heater_duty; heat[7]=steady['reboiler_duty_W']
        heat[8]=-ua*(cooling_factor if now>=fault_time else 1)*(guesses[8].temperature-300)
        du+=heat; external_u+=heat.sum()
        for source,target,flow,phase,q,h,cool in flows:
            dn[source]-=flow*q; du[source]-=flow*h
            output_h=h
            if cool:
                # Algebraic subcooler/return pump. Net boundary energy is exact.
                output_h=eos.properties(300.,guesses[1].pressure,q,'liquid')[2]
                external_u+=flow*(output_h-h)
            if target is None:
                external_n-=flow*q; external_u-=flow*output_h
            else:
                dn[target]+=flow*q; du[target]+=flow*output_h
        amounts+=step*dn; energies+=step*du
        if (amounts<0).any(): raise ThermoError('Negative inventory in coupled dynamics')
        ledger_n+=step*external_n; ledger_u+=step*external_u
        guesses=[eos.flash_uv(amounts[j],energies[j],volumes[j],(f.temperature,f.pressure)) for j,f in enumerate(guesses)]
        now+=step
    return {'scope':'coupled dynamic pilot; algebraic drum/subcooler; no closed-loop control or trip yet','device':'CPU','cells':['H-101']+[f'C-101:{j+1}' for j in range(6)]+['R-101','E-101'],'config':{'duration_s':duration,'step_s':dt,'cooling_factor':cooling_factor,'fault_time_s':fault_time},'component_balance_residual_mol':(amounts.sum(axis=0)-initial_amounts-ledger_n).tolist(),'energy_balance_residual_J':float(energies.sum()-initial_energy-ledger_u),'series':records}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('--duration',type=float,default=10); parser.add_argument('--cooling',type=float,default=.5); args=parser.parse_args()
    start=time.perf_counter(); result=run_coupled(duration=args.duration,cooling_factor=args.cooling); result['wall_seconds']=time.perf_counter()-start
    Path('reports/coupled-dynamics-pilot.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({key:value for key,value in result.items() if key!='series'},indent=2))
    print('Initial pressures:',result['series'][0]['pressure_Pa'])
    print('Final pressures:',result['series'][-1]['pressure_Pa'])
