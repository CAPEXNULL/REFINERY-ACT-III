"""Conserving condenser-cell pilot. Not yet a whole refinery simulation."""
import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
import time
import numpy as np
import CoolProp
from amd.thermo import PengRobinson


def condenser_pilot(duration=60., dt=2., degradation=.5):
    if duration<=0 or dt<=0 or dt>duration or not 0<degradation<=1:
        raise ValueError('Invalid pilot configuration')
    eos=PengRobinson()
    initial=eos.flash(420.,150000.,[.25,.45,.3])
    volume=.1
    amounts=np.array([.25,.45,.3])*volume/initial.molar_volume
    energy=amounts.sum()*initial.molar_energy
    initial_energy=energy
    ua=4.; coolant=300.; duty=ua*(initial.temperature-coolant)
    records=[]; heat_integral=0.; now=0.; f=initial
    while True:
        records.append({'time_s':now,'temperature_K':float(f.temperature),'pressure_Pa':float(f.pressure),'vapor_fraction':float(f.beta),'internal_energy_J':float(energy),'component_inventory_mol':amounts.tolist(),'phase':f.phase})
        if now>=duration-1e-10: break
        step=min(dt,duration-now)
        # Explicit energy step: same heat flux integrates both state and ledger.
        net_heat=duty-ua*degradation*(f.temperature-coolant)
        energy+=step*net_heat; heat_integral+=step*net_heat; now+=step
        f=eos.flash_uv(amounts,energy,volume,(f.temperature,f.pressure))
    balance=energy-initial_energy-heat_integral
    return {'scope':'closed condenser equilibrium cell; no flow/column yet','device':'CPU','property_set':'surrogate-v1','CoolProp_version':CoolProp.__version__,'config':{'duration_s':duration,'step_s':dt,'degradation':degradation,'volume_m3':volume,'UA_W_K':ua,'coolant_K':coolant,'heat_input_W':duty},'energy_balance_residual_J':float(balance),'series':records}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--duration',type=float,default=60); parser.add_argument('--step',type=float,default=2); parser.add_argument('--output',default='reports/condenser-pilot.json')
    args=parser.parse_args(); start=time.perf_counter()
    result=condenser_pilot(args.duration,args.step)
    result['wall_seconds']=time.perf_counter()-start
    result['created_at']=datetime.now(timezone.utc).isoformat()
    result['source_manifest']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('amd/thermo.py'),Path('amd/pilot.py')]}
    path=Path(args.output); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    first,last=result['series'][0],result['series'][-1]
    print(json.dumps({'output':str(path),'initial':first,'final':last,'balance_J':result['energy_balance_residual_J'],'wall_seconds':result['wall_seconds']},indent=2))


if __name__=='__main__': main()
