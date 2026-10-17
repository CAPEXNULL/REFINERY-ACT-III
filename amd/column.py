"""Steady MESH pilot: six adiabatic equilibrium stages plus a reboiler.

This is a steady operating-point solver, not the final dynamic column.
Bubble points use CoolProp PR; flow balances and caloric checks are explicit.
"""
from dataclasses import dataclass
import numpy as np
from scipy.optimize import least_squares
import CoolProp.CoolProp as CP
from amd.thermo import PengRobinson, ThermoError


@dataclass(frozen=True)
class ColumnConfig:
    stages: int = 6
    feed_stage: int = 4  # 1-based
    feed_mol_s: float = 1.
    feed_temperature_K: float = 430.
    top_pressure_Pa: float = 150000.
    stage_pressure_drop_Pa: float = 1000.
    distillate_mol_s: float = .5
    reflux_ratio: float = 3.


def solve_column(config=ColumnConfig()):
    c=config
    if not 2<=c.stages<=12 or not 1<=c.feed_stage<=c.stages:
        raise ValueError('Unsupported stage configuration')
    if not 0<c.distillate_mol_s<c.feed_mol_s or c.reflux_ratio<=0:
        raise ValueError('Invalid operating flows')
    eos=PengRobinson(); n=c.stages
    pressure=c.top_pressure_Pa+c.stage_pressure_drop_Pa*np.arange(n+1)
    zfeed=np.array([.25,.45,.30])
    feed=eos.flash(c.feed_temperature_K,float(pressure[c.feed_stage-1]),zfeed)
    reflux=c.reflux_ratio*c.distillate_mol_s
    overhead=reflux+c.distillate_mol_s
    bottoms=c.feed_mol_s-c.distillate_mol_s
    states=[CP.AbstractState('PR','&'.join(eos.names)) for _ in range(n+1)]
    def unpack(w):
        logits=np.column_stack([w[:2*(n+1)].reshape(n+1,2),np.zeros(n+1)])
        logits-=logits.max(axis=1)[:,None]
        x=np.exp(logits); x/=x.sum(axis=1)[:,None]
        vap=np.r_[overhead,np.exp(w[2*(n+1):])]
        y=[]; temps=[]; hl=[]; hv=[]
        for j,state in enumerate(states):
            state.set_mole_fractions(x[j]); state.update(CP.PQ_INPUTS,float(pressure[j]),0.)
            temp=state.T(); vv=np.array(state.mole_fractions_vapor())
            eos.check_tp(temp,float(pressure[j]))
            temps.append(temp); y.append(vv)
            hl.append(eos.properties(temp,pressure[j],x[j],'liquid')[2])
            hv.append(eos.properties(temp,pressure[j],vv,'vapor')[2])
        # Total balances eliminate liquid flows; no hidden mass clipping.
        liquid=np.array([reflux+vap[j+1]-overhead+(c.feed_mol_s if j>=c.feed_stage-1 else 0.) for j in range(n)])
        return x,np.array(y),np.array(temps),np.array(hl),np.array(hv),vap,liquid
    def residual(w):
        x,y,t,hl,hv,vap,liquid=unpack(w)
        # Total condenser returns the overhead composition at a cooled liquid h.
        condenser=eos.flash(300.,float(pressure[0]),y[0],verify_stability=False)
        hr=condenser.molar_enthalpy
        mass=[]; energy=[]
        for j in range(n):
            incoming=reflux*y[0] if j==0 else liquid[j-1]*x[j-1]
            power=reflux*hr if j==0 else liquid[j-1]*hl[j-1]
            incoming=incoming+vap[j+1]*y[j+1]; power+=vap[j+1]*hv[j+1]
            if j==c.feed_stage-1:
                incoming+=c.feed_mol_s*zfeed; power+=c.feed_mol_s*feed.molar_enthalpy
            rr=incoming-liquid[j]*x[j]-vap[j]*y[j]
            mass.extend(rr[:2]/c.feed_mol_s)
            energy.append((power-liquid[j]*hl[j]-vap[j]*hv[j])/50000.)
        mass.extend((liquid[-1]*x[-2]-bottoms*x[-1]-vap[-1]*y[-1])[:2]/c.feed_mol_s)
        return np.r_[mass,energy]
    frac=np.linspace(0,1,n+1)
    init_x=np.column_stack([.48*(1-frac)+.02*frac,.46*np.ones(n+1),.06*(1-frac)+.52*frac])
    w0=np.r_[np.log(init_x[:,:2]/init_x[:,2,None]).ravel(),np.log(np.full(n,overhead))]
    solution=least_squares(residual,w0,bounds=(np.r_[np.full(2*(n+1),-12),np.full(n,np.log(.05))],np.r_[np.full(2*(n+1),12),np.full(n,np.log(10.))]),max_nfev=160,xtol=1e-10,ftol=1e-10,gtol=1e-10)
    x,y,t,hl,hv,vap,liquid=unpack(solution.x)
    if not solution.success or np.max(abs(solution.fun))>1e-6 or (liquid<=0).any():
        raise ThermoError(f'Steady column did not converge: residual={np.max(abs(solution.fun)):.3g}')
    top_liquid=eos.flash(300.,float(pressure[0]),y[0])
    qr=bottoms*hl[-1]+vap[-1]*hv[-1]-liquid[-1]*hl[-2]
    qc=overhead*(hv[0]-top_liquid.molar_enthalpy)
    mass_balance=c.feed_mol_s*zfeed-c.distillate_mol_s*y[0]-bottoms*x[-1]
    energy_balance=c.feed_mol_s*feed.molar_enthalpy+qr-qc-c.distillate_mol_s*top_liquid.molar_enthalpy-bottoms*hl[-1]
    equilibrium=[]
    for j in range(n+1):
        equilibrium.append(float(np.max(abs(np.log(x[j])+eos.lnphi(t[j],pressure[j],x[j],'liquid')-np.log(y[j])-eos.lnphi(t[j],pressure[j],y[j],'vapor')))))
    if qr<=0 or qc<=0 or max(equilibrium)>1e-5:
        raise ThermoError('Invalid heat duty or independent equilibrium check')
    return {'scope':'steady six-stage MESH operating point; not dynamic validation','config':c.__dict__,'feed_composition':zfeed.tolist(),'temperature_K':t.tolist(),'pressure_Pa':pressure.tolist(),'liquid_composition':x.tolist(),'vapor_composition':y.tolist(),'vapor_mol_s':vap.tolist(),'liquid_mol_s':liquid.tolist(),'distillate_composition':y[0].tolist(),'bottoms_composition':x[-1].tolist(),'reboiler_duty_W':float(qr),'condenser_duty_W':float(qc),'component_balance_mol_s':mass_balance.tolist(),'energy_balance_W':float(energy_balance),'equilibrium_log_fugacity_residual':max(equilibrium),'solver_scaled_residual':float(np.max(abs(solution.fun))),'solver_evaluations':solution.nfev}


if __name__=='__main__':
    import json
    import hashlib
    import time
    import CoolProp
    from pathlib import Path
    started=time.perf_counter()
    result=solve_column()
    result['wall_seconds']=time.perf_counter()-started
    result['CoolProp_version']=CoolProp.__version__
    result['source_manifest']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('amd/thermo.py'),Path('amd/column.py')]}
    Path('reports/column-steady-pilot.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
