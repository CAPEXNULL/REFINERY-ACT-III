"""Parameterized surrogate refinery. Observation adapter never exports fault truth."""
from dataclasses import dataclass
import copy
import numpy as np
import CoolProp.CoolProp as CP
from amd.column import ColumnConfig,solve_column
from amd.thermo import PengRobinson,ThermoError


@dataclass(frozen=True)
class PlantConfig:
    name: str
    stages: int
    feed_stage: int
    condensers: int


CONFIGS={'A':PlantConfig('A',6,4,1),'B':PlantConfig('B',8,5,1),'C':PlantConfig('C',6,4,2)}
FAULTS=('normal','cooling_loss','heater_loss','sensor_bias')
ACTIONS=('hold','restore_cooling','reduce_heat','reduce_feed')


@dataclass(frozen=True)
class Scenario:
    fault: str='normal'
    fault_time: float=2.
    severity: float=.5
    sensor_bias_K: float=4.

    def __post_init__(self):
        if self.fault not in FAULTS or not np.isfinite([self.fault_time,self.severity,self.sensor_bias_K]).all() or self.fault_time<0 or not .2<=self.severity<=1:
            raise ValueError('Invalid scenario')


class Plant:
    def __init__(self,configuration='A',steady=None):
        if configuration not in CONFIGS:raise ValueError('Unsupported plant configuration')
        self.config=CONFIGS[configuration];c=self.config;self.eos=PengRobinson()
        self.steady=steady or solve_column(ColumnConfig(stages=c.stages,feed_stage=c.feed_stage))
        s=self.steady;self.n=c.stages;self.reboiler=self.n+1
        self.condensers=list(range(self.n+2,self.n+2+c.condensers))
        self.cells=['H-101']+[f'C-101:{j+1}' for j in range(self.n)]+['R-101']+[f'E-{101+j}' for j in range(c.condensers)]
        self.roles=['heater']+['column']*self.n+['reboiler']+['condenser']*c.condensers
        self.topology=[]
        self.guesses=[];amounts=[];energies=[];volumes=[]
        def add(t,p,q,v):
            f=self.eos.flash(float(t),float(p),q);total=v/f.molar_volume
            self.guesses.append(f);amounts.append(total*np.array(q));energies.append(total*f.molar_energy);volumes.append(v)
        feed_pressure=s['pressure_Pa'][c.feed_stage-1]
        add(430.,feed_pressure,s['feed_composition'],.2)
        for j in range(self.n+1):
            x=np.array(s['liquid_composition'][j]);y=np.array(s['vapor_composition'][j])
            add(s['temperature_K'][j],s['pressure_Pa'][j],.9*x+.1*y,1.)
        state=CP.AbstractState('PR','&'.join(self.eos.names));xd=np.array(s['distillate_composition'])
        state.set_mole_fractions(xd);state.update(CP.PQ_INPUTS,140000.,0.)
        for _ in self.condensers:add(state.T(),140000.,.8*xd+.2*np.array(state.mole_fractions_vapor()),3./c.condensers)
        self.amounts=np.array(amounts);self.energies=np.array(energies);self.volumes=np.array(volumes)
        self.initial_amounts=self.amounts.sum(axis=0).copy();self.initial_energy=float(self.energies.sum())
        self.nominal_liquid=(1-np.array([f.beta for f in self.guesses]))*self.amounts.sum(axis=1)
        self.supply=self.eos.flash(350.,feed_pressure,s['feed_composition'])
        self.heater_duty=self.guesses[0].molar_enthalpy-self.supply.molar_enthalpy
        f=self.guesses[self.condensers[0]]
        vapor_h=self.eos.properties(self.guesses[1].temperature,self.guesses[1].pressure,self.guesses[1].vapor,'vapor')[2]
        liquid_h=self.eos.properties(f.temperature,f.pressure,f.liquid,'liquid')[2]
        self.overhead=s['vapor_mol_s'][0]
        self.ua=(self.overhead*vapor_h-self.overhead*liquid_h)/(f.temperature-300)/c.condensers
        if self.ua<=0:raise ThermoError('Invalid conductance')
        self.reflux_fraction=s['config']['reflux_ratio']/(1+s['config']['reflux_ratio'])
        self.now=0.;self.ledger_n=np.zeros(3);self.ledger_u=0.;self.product_mol=0.
        self.integral=0.;self.cooling_command=1.;self.trip=False;self.trip_time=None;self.events=[]
        self.last_flows=[];self.last_heat=np.zeros(len(self.cells))
        self.topology.append({'source':'H-101','target':f'C-101:{c.feed_stage}','type':'material'})
        for j in range(1,self.n+1):
            self.topology.append({'source':self.cells[j+1],'target':self.cells[j],'type':'vapor'})
            self.topology.append({'source':self.cells[j],'target':self.cells[j+1],'type':'liquid'})
        for index in self.condensers:
            self.topology.extend([{'source':'C-101:1','target':self.cells[index],'type':'vapor'},
                                  {'source':self.cells[index],'target':'C-101:1','type':'reflux'}])

    def clone(self):
        result=Plant.__new__(Plant)
        result.__dict__={k:(self.eos if k=='eos' else copy.deepcopy(v)) for k,v in self.__dict__.items()}
        return result  # Forks are calculated serially; EOS is not shared across worker threads.

    def observe(self,scenario=None,rng=None,noise_K=0.,noise_kPa=0.):
        temperatures=np.array([f.temperature for f in self.guesses]);pressures=np.array([f.pressure for f in self.guesses])/1000
        measured=temperatures.copy();reference=float(temperatures[0])
        if scenario and scenario.fault=='sensor_bias' and self.now>=scenario.fault_time:measured[0]+=scenario.sensor_bias_K
        if rng is not None:
            measured+=rng.normal(0,noise_K,len(measured));pressures+=rng.normal(0,noise_kPa,len(pressures));reference+=float(rng.normal(0,noise_K))
        return {'time_s':float(self.now),'equipment':list(self.cells),'roles':list(self.roles),
                'temperature_K':measured.tolist(),'pressure_kPa':pressures.tolist(),
                'heater_reference_K':reference,'protection':{'latched':self.trip,'trip_time_s':self.trip_time}}

    def step(self,dt,scenario=Scenario(),action='hold',action_time=0.,controller=False,protection=True):
        if not np.isfinite(dt) or not 0<dt<=.5 or action not in ACTIONS:raise ValueError('Invalid integration/action')
        active=self.now>=scenario.fault_time;applied=action if self.now>=action_time else 'hold'
        peak=max(self.guesses[j].pressure for j in self.condensers)
        if protection and not self.trip and (peak>160000 or self.guesses[0].temperature>470):
            self.trip=True;self.trip_time=float(self.now);self.events.append({'time_s':self.now,'level':'TRIP','cause':'independent pressure/temperature limit'})
        if controller:
            error=(peak-140000)/1000;candidate=self.integral+.01*error*dt
            raw=1+.05*error+candidate
            if .4<raw<1.4 or raw>=1.4 and error<0 or raw<=.4 and error>0:self.integral=candidate
            self.cooling_command=float(np.clip(1+.05*error+self.integral,.4,1.4))
        else:self.cooling_command=1.
        feed=0. if self.trip else .8 if applied=='reduce_feed' else 1.
        heat_factor=0. if self.trip else .8 if applied=='reduce_heat' else 1.
        dn=np.zeros_like(self.amounts);du=np.zeros_like(self.energies);flows=[]
        def stream(source,target,rate,phase='liquid',cool=False):
            f=self.guesses[source]
            q=self.amounts[source]/self.amounts[source].sum() if phase=='mixed' else f.liquid if phase=='liquid' else f.vapor
            h=f.molar_enthalpy if phase=='mixed' else self.eos.properties(f.temperature,f.pressure,q,phase)[2]
            flows.append([source,target,max(float(rate),0.),phase,q,h,cool])
        stream(0,self.config.feed_stage,feed,'mixed')
        for source in range(1,self.n+2):
            targets=self.condensers if source==1 else [source-1]
            for target in targets:
                delta=max(self.guesses[source].pressure-self.guesses[target].pressure,0.)
                flow=self.steady['vapor_mol_s'][source-1]*np.sqrt(delta/(10000. if source==1 else 1000.))/len(targets)
                stream(source,target,flow,'vapor')
        for source in range(1,self.n+1):
            rate=self.steady['liquid_mol_s'][source-1]*(1-self.guesses[source].beta)*self.amounts[source].sum()/self.nominal_liquid[source]
            stream(source,source+1,rate)
        stream(self.reboiler,None,.5*(1-self.guesses[self.reboiler].beta)*self.amounts[self.reboiler].sum()/self.nominal_liquid[self.reboiler])
        for index in self.condensers:
            draw=self.overhead/len(self.condensers)*(1-self.guesses[index].beta)*self.amounts[index].sum()/self.nominal_liquid[index]
            stream(index,1,self.reflux_fraction*draw,cool=True);stream(index,None,(1-self.reflux_fraction)*draw,cool=True)
        for source in range(len(self.cells)):
            for phase in ('liquid','vapor','mixed'):
                ff=[e for e in flows if e[0]==source and e[3]==phase];requested=sum(e[2] for e in ff)*dt
                available=self.amounts[source].sum()*(1-self.guesses[source].beta if phase=='liquid' else self.guesses[source].beta if phase=='vapor' else 1)
                if requested>available and requested>0:
                    for e in ff:e[2]*=.95*available/requested
        external_n=feed*np.array(self.steady['feed_composition']);external_u=feed*self.supply.molar_enthalpy
        dn[0]+=external_n;du[0]+=external_u;heat=np.zeros(len(self.cells))
        heater_availability=scenario.severity if active and scenario.fault=='heater_loss' else 1.
        heat[0]=feed*self.heater_duty*heater_availability
        heat[self.reboiler]=heat_factor*self.steady['reboiler_duty_W']
        for position,index in enumerate(self.condensers):
            availability=scenario.severity if active and scenario.fault=='cooling_loss' and position==0 else 1.
            if applied=='restore_cooling':availability=1.
            heat[index]=-self.ua*availability*self.cooling_command*(self.guesses[index].temperature-300)
        du+=heat;external_u+=heat.sum()
        for source,target,flow,phase,q,h,cool in flows:
            dn[source]-=flow*q;du[source]-=flow*h;output_h=h
            if cool:
                output_h=self.eos.properties(300.,self.guesses[1].pressure,q,'liquid')[2];external_u+=flow*(output_h-h)
            if target is None:
                external_n-=flow*q;external_u-=flow*output_h;self.product_mol+=dt*flow
            else:dn[target]+=flow*q;du[target]+=flow*output_h
        self.amounts+=dt*dn;self.energies+=dt*du
        if (self.amounts<0).any():raise ThermoError('Negative inventory')
        self.ledger_n+=dt*external_n;self.ledger_u+=dt*external_u
        updated=[]
        for j,f in enumerate(self.guesses):
            try:updated.append(self.eos.flash_uv(self.amounts[j],self.energies[j],self.volumes[j],(f.temperature,f.pressure)))
            except ThermoError as error:
                raise ThermoError(f'{self.config.name} cell {self.cells[j]} at t={self.now+dt}: {error}') from error
        self.guesses=updated
        self.now+=dt;self.last_flows=flows;self.last_heat=heat

    def run(self,duration=6.,dt=.5,scenario=Scenario(),action='hold',action_time=0.,controller=False,protection=True,seed=0,noise_K=0.,noise_kPa=0.):
        if not np.isfinite([duration,dt,action_time,noise_K,noise_kPa]).all() or not self.now<duration<=120 or not 0<dt<=.5 or action_time<0 or noise_K<0 or noise_kPa<0:
            raise ValueError('Invalid run configuration')
        rng=np.random.default_rng(seed);records=[]
        while True:
            records.append({'observation':self.observe(scenario,rng,noise_K,noise_kPa),
                            'time_s':float(self.now),'temperature_K':[float(f.temperature) for f in self.guesses],
                            'pressure_Pa':[float(f.pressure) for f in self.guesses],'cooling_command':self.cooling_command})
            if self.now>=duration-1e-9:break
            step=min(dt,duration-self.now)
            for boundary in (scenario.fault_time,action_time):
                if self.now<boundary<self.now+step:step=boundary-self.now
            self.step(step,scenario,action,action_time,controller,protection)
        return {'scope':'surrogate refinery model; algebraic drum; not validated plant','configuration':self.config.name,
                'cells':self.cells,'roles':self.roles,'topology':self.topology,'series':records,'events':self.events,
                'component_balance_residual_mol':(self.amounts.sum(axis=0)-self.initial_amounts-self.ledger_n).tolist(),
                'energy_balance_residual_J':float(self.energies.sum()-self.initial_energy-self.ledger_u),
                'product_mol':float(self.product_mol),'trip':self.trip,'trip_time_s':self.trip_time,
                'private_truth':{'fault':scenario.fault,'severity':scenario.severity,'fault_time_s':scenario.fault_time,'action':action}}
