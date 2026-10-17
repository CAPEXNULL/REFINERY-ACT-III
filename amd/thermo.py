"""Independent PR equations with CoolProp ideal-gas caloric data.

CoolProp is not used to solve our cubic, fugacity, stability or TP flash.
Mixture validity is limited to the configured hydrocarbon surrogate.
"""
from dataclasses import dataclass
from functools import lru_cache
import numpy as np
from scipy.optimize import brentq, minimize, least_squares
import CoolProp.CoolProp as CP

R = 8.31446261815324
NAMES = ('n-Hexane', 'n-Decane', 'n-Dodecane')


class ThermoError(ValueError):
    pass


@dataclass(frozen=True)
class Flash:
    temperature: float
    pressure: float
    beta: float
    liquid: np.ndarray
    vapor: np.ndarray
    molar_volume: float
    molar_energy: float
    molar_enthalpy: float
    phase: str
    equilibrium_residual: float


class PengRobinson:
    def __init__(self, names=NAMES, kij=None):
        self.names = tuple(names)
        self.c = len(names)
        # Use the cubic databank's reducing constants, not rounded documentation.
        self.states = [CP.AbstractState('PR', name) for name in names]
        self.tc = np.array([s.T_critical() for s in self.states])
        self.pc = np.array([s.p_critical() for s in self.states])
        self.omega = np.array([s.acentric_factor() for s in self.states])
        self.mw = np.array([s.molar_mass() for s in self.states])
        self.kij = np.zeros((self.c, self.c)) if kij is None else np.array(kij, float)
        if self.kij.shape != (self.c, self.c) or not np.allclose(self.kij, self.kij.T):
            raise ThermoError('kij must be a finite symmetric component matrix')
        if not np.isfinite(self.kij).all() or not np.allclose(np.diag(self.kij), 0):
            raise ThermoError('Invalid kij')
        self.m = .37464 + 1.54226*self.omega - .26992*self.omega**2
        self.b = .07779607390388846*R*self.tc/self.pc

    def composition(self, value):
        q = np.array(value, float)
        if q.shape != (self.c,) or not np.isfinite(q).all() or (q < 0).any():
            raise ThermoError('Invalid mole fractions')
        if abs(q.sum()-1) > 1e-8:
            raise ThermoError('Mole fractions must sum to one')
        return q / q.sum()

    @staticmethod
    def check_tp(t, p):
        if not np.isfinite([t, p]).all() or not 280 <= t <= 600 or not 1e4 <= p <= 2e6:
            raise ThermoError('Outside pilot domain: 280–600 K, 10–2000 kPa absolute')

    def coefficients(self, t, q):
        base = .4572355289213822*R**2*self.tc**2/self.pc
        f = 1+self.m*(1-np.sqrt(t/self.tc))
        ai = base*f**2
        dai = -base*f*self.m/np.sqrt(t*self.tc)
        aij = np.sqrt(np.outer(ai, ai))*(1-self.kij)
        daij = .5*aij*(dai[:, None]/ai[:, None]+dai[None, :]/ai[None, :])
        return q@aij@q, q@self.b, aij, q@daij@q

    def roots(self, t, p, q):
        a, b, _, _ = self.coefficients(t, q)
        A, B = a*p/(R*t)**2, b*p/(R*t)
        rr = np.roots([1, B-1, A-3*B*B-2*B, -(A*B-B*B-B**3)])
        valid = sorted(r.real for r in rr if abs(r.imag)<1e-8 and r.real>B)
        if not valid:
            raise ThermoError('No physically admissible PR root')
        return np.array(valid)

    def lnphi(self, t, p, q, phase):
        a, b, aij, _ = self.coefficients(t, q)
        zz = self.roots(t, p, q)
        z = zz[0] if phase=='liquid' else zz[-1]
        A, B = a*p/(R*t)**2, b*p/(R*t)
        log_ratio = np.log((z+(1+np.sqrt(2))*B)/(z+(1-np.sqrt(2))*B))
        return self.b/b*(z-1)-np.log(z-B)-A/(2*np.sqrt(2)*B)*(2*(aij@q)/a-self.b/b)*log_ratio

    @lru_cache(maxsize=8192)
    def ideal_enthalpies(self, t):
        values=[]
        for s in self.states:
            s.specify_phase(CP.iphase_gas)
            s.update(CP.PT_INPUTS, 1000., t)
            values.append(s.hmolar_idealgas())
        return np.array(values)

    def properties(self, t, p, q, phase):
        a, b, _, dadt = self.coefficients(t, q)
        rr = self.roots(t, p, q)
        z = rr[0] if phase=='liquid' else rr[-1]
        B = b*p/(R*t)
        ratio = np.log((z+(1+np.sqrt(2))*B)/(z+(1-np.sqrt(2))*B))
        h = q@self.ideal_enthalpies(float(t))+R*t*(z-1)+(t*dadt-a)/(2*np.sqrt(2)*b)*ratio
        v = z*R*t/p
        return v, h-p*v, h

    def stable_phase(self, t, p, q):
        roots = self.roots(t,p,q)
        if len(roots)==1:
            return 'vapor' if roots[0]>.5 else 'liquid'
        gl = q@self.lnphi(t, p, q, 'liquid')
        gv = q@self.lnphi(t, p, q, 'vapor')
        return 'liquid' if gl <= gv else 'vapor'

    def stability(self, t, p, q):
        """Multistart tangent-plane distance; a numerical stability test.

        Restricted to the configured positive ternary mixtures. Not a global
        proof for arbitrary mixtures or liquid-liquid phase splitting.
        """
        active = q > 0
        if active.sum()==1:
            return 0., None
        phase = self.stable_phase(t, p, q)
        d = np.log(q[active])+self.lnphi(t,p,q,phase)[active]
        def composition(z):
            z = np.append(z, 0.)
            z -= np.max(z)
            qq=np.zeros(self.c); qq[active]=np.exp(z)/np.exp(z).sum()
            return qq
        def objective(z):
            w=composition(z)
            ph=self.stable_phase(t,p,w)
            return w[active]@(np.log(w[active])+self.lnphi(t,p,w,ph)[active]-d)
        seeds=[q[active]]
        # Incipient phases of a nearly saturated mixture may lie between
        # component-rich seeds. Wilson liquid/vapor estimates add those
        # physically distinct basins without relaxing the stability test.
        wilson=np.exp(np.clip(np.log(self.pc/p)+5.373*(1+self.omega)*(1-self.tc/t),-40,40))
        for candidate in (q*wilson,q/wilson):
            candidate=candidate[active]
            seeds.append(candidate/candidate.sum())
        count=active.sum()
        for i in range(count):
            v=np.full(count,.02/(count-1)); v[i]=.98; seeds.append(v)
        best=(0.,None)
        for seed in seeds:
            res=minimize(objective,np.log(seed[:-1]/seed[-1]), method='L-BFGS-B',bounds=[(-25,25)]*(count-1))
            if not res.success:
                raise ThermoError('Stability minimization did not converge')
            if res.fun<best[0]: best=(float(res.fun),composition(res.x))
        return best

    def flash(self, t, p, z, verify_stability=True):
        self.check_tp(t,p); z=self.composition(z)
        phase=self.stable_phase(t,p,z)
        if verify_stability:
            tpd,_=self.stability(t,p,z)
            if tpd >= -1e-7:
                v,u,h=self.properties(t,p,z,phase)
                return Flash(t,p,float(phase=='vapor'),z.copy(),z.copy(),v,u,h,phase,0.)
        # Wilson initial K; fugacity iteration and safeguarded Rachford–Rice.
        logk=np.log(self.pc/p)+5.373*(1+self.omega)*(1-self.tc/t)
        for iteration in range(250):
            k=np.exp(np.clip(logk,-40,40))
            def rr(beta): return np.sum(z*(k-1)/(1+beta*(k-1)))
            if rr(0)<=0: beta=0.
            elif rr(1)>=0: beta=1.
            else: beta=brentq(rr,0.,1.,xtol=1e-13)
            x=z/(1+beta*(k-1)); y=k*x
            x/=x.sum(); y/=y.sum()
            new=self.lnphi(t,p,x,'liquid')-self.lnphi(t,p,y,'vapor')
            error=np.max(abs(new-logk))
            if error<1e-9:
                if beta<=1e-8 or beta>=1-1e-8 or np.max(abs(x-y))<1e-7:
                    if verify_stability and tpd < -1e-7:
                        raise ThermoError('Unstable feed converged to a trivial flash')
                    v,u,h=self.properties(t,p,z,phase)
                    return Flash(t,p,float(phase=='vapor'),z.copy(),z.copy(),v,u,h,phase,float(error))
                vl,ul,hl=self.properties(t,p,x,'liquid'); vv,uv,hv=self.properties(t,p,y,'vapor')
                if np.max(abs((1-beta)*x+beta*y-z))>1e-8:
                    raise ThermoError('Flash component balance failed')
                return Flash(t,p,float(beta),x,y,(1-beta)*vl+beta*vv,(1-beta)*ul+beta*uv,(1-beta)*hl+beta*hv,'two-phase',float(error))
            logk=.5*logk+.5*new
        raise ThermoError('TP flash iteration budget exceeded')

    def flash_uv(self, amounts, energy, volume, guess=(420.,150000.)):
        amounts=np.asarray(amounts,float)
        if amounts.shape!=(self.c,) or not np.isfinite(amounts).all() or (amounts<0).any() or amounts.sum()<=0:
            raise ThermoError('Invalid conserved component inventories')
        if not np.isfinite([energy,volume]).all() or volume<=0:
            raise ThermoError('Invalid internal energy or vessel volume')
        total=amounts.sum(); q=amounts/total
        target_u=energy/total; target_v=volume/total
        scale_u=max(abs(target_u),1e4)
        def residual(value, stable=False):
            f=self.flash(value[0],np.exp(value[1]),q,verify_stability=stable)
            return [np.log(f.molar_volume/target_v),(f.molar_energy-target_u)/scale_u]
        starts=[guess,(400.,100000.),(460.,300000.)]
        for initial in starts:
            sol=least_squares(residual,[initial[0],np.log(initial[1])],bounds=([280,np.log(10001)],[600,np.log(1999999)]),xtol=1e-11,ftol=1e-11,gtol=1e-11,max_nfev=100)
            if sol.success and np.max(abs(sol.fun))<1e-8:
                final=self.flash(sol.x[0],np.exp(sol.x[1]),q)
                if abs(final.molar_volume/target_v-1)>1e-7 or abs(final.molar_energy-target_u)/scale_u>1e-7:
                    continue
                return final
        # The inexpensive TP iteration can select a different phase branch
        # close to saturation. Refine with the same stability decision used
        # for acceptance, instead of accepting its nonconserving final state.
        initial=sol.x
        sol=least_squares(lambda value:residual(value,stable=True),initial,
            bounds=([280,np.log(10001)],[600,np.log(1999999)]),
            xtol=1e-11,ftol=1e-11,gtol=1e-11,max_nfev=100)
        if sol.success and np.max(abs(sol.fun))<1e-8:
            final=self.flash(sol.x[0],np.exp(sol.x[1]),q)
            if abs(final.molar_volume/target_v-1)<=1e-7 and abs(final.molar_energy-target_u)/scale_u<=1e-7:
                return final
        raise ThermoError('UV flash failed conservation or stability checks')
