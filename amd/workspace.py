"""Local engineering workspace persistence. No authentication or plant actuation."""
from pathlib import Path
import hashlib
import json
import math
import os
import re
import threading
import uuid
from contextlib import contextmanager
from amd.audit import evidence, utc


class WorkspaceBusy(Exception):
    pass


def atomic_json(path, value):
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.pending')
    with temporary.open('x',encoding='utf8') as stream:
        written=stream.write(json.dumps(value,allow_nan=False))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary,path)
    return written


class Workspace:
    def __init__(self, service, computation_lock):
        self.service=service
        self.audit=service.audit
        self.directory=self.audit.directory/'workspace'
        self.directory.mkdir(exist_ok=True)
        self.lock=threading.RLock()
        self.computation_lock=computation_lock
        self.threads=[]
    @contextmanager
    def server_owner(self):
        """Exclusive lifetime ownership, independent of TRACE writer locks."""
        path=self.directory/'server.owner.lock'
        with path.open('a+b') as handle:
            if handle.tell()==0:handle.write(b'0');handle.flush()
            handle.seek(0)
            try:
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError as error:
                raise WorkspaceBusy('Another server already owns this workspace') from error
            try:yield
            finally:
                handle.seek(0)
                if os.name=='nt':
                    msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
                else:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)

    def recover_interrupted(self):
        # Invoke only after exclusive server ownership, never on module import.
        for path in self.directory.glob('job-*.json'):
            job=json.loads(path.read_text(encoding='utf8'))
            if job['status'] in ('queued','running'):
                self._transition(job,status='interrupted',stage='interrupted',
                    error='Server restarted before this calculation completed')

    def _transition(self, job, **changes):
        with self.lock:
            next_job=dict(job,**changes,updated_at=utc())
            snapshot=self.directory/('transition-'+uuid.uuid4().hex+'.json')
            def save():
                snapshot.write_text(json.dumps(next_job,allow_nan=False),encoding='utf8')
                atomic_json(self.directory/('job-'+next_job['job_id']+'.json'),next_job)
                job.clear();job.update(next_job)
                return True
            self.audit.execute('workspace','job transition',next_job['job_id'],
                {'stage':next_job['stage'],'status':next_job['status']},
                'Durably persist actual job phase and immutable transition evidence',save,
                lambda v:({'persisted':v},[snapshot]))

    def submit(self, payload):
        if not isinstance(payload,dict) or set(payload)!={'request_token','arguments'}:
            raise ValueError('Expected request_token and arguments')
        token=payload['request_token']
        if not isinstance(token,str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,100}',token):
            raise ValueError('Invalid request token')
        arguments=self.service.validate(payload['arguments'])
        key=hashlib.sha256(token.encode()).hexdigest()[:32]
        path=self.directory/('job-'+key+'.json')
        with self.lock:
            if path.exists():
                existing=json.loads(path.read_text(encoding='utf8'))
                if existing['arguments']!=arguments:raise ValueError('Request token was used for different arguments')
                return existing
            if not self.service.status()['model_ready']:raise ValueError('Diagnostic training qualification is pending')
            if not self.computation_lock.acquire(blocking=False):
                raise WorkspaceBusy('A calculation is already running')
            job={'job_id':key,'request_token':token,'arguments':arguments,
                 'created_at':utc(),'status':'queued','stage':'queued','percent':0,
                 'result_event_id':None,'error':None}
            try:
                self._transition(job)
                worker=threading.Thread(target=self._run,args=(job,),daemon=True,
                    name='refinery-calculation-'+key)
                self.threads=[t for t in self.threads if t.is_alive()]+[worker]
                worker.start()
            except Exception:
                self.computation_lock.release()
                raise
            return dict(job)

    def _run(self, job):
        try:
            self._transition(job,status='running',stage='initialization',percent=0)
            def progress(stage,percent):
                # Discrete completed phases, not an estimate of elapsed runtime.
                self._transition(job,stage=stage,percent=percent)
            value=self.service.run(job['arguments'],progress=progress)
            self._transition(job,status='completed',stage='completed',percent=100,
                             result_event_id=value['event_id'])
        except Exception as error:
            reason=str(error) if isinstance(error,ValueError) else 'Calculation failed; no new result accepted'
            self._transition(job,status='failed',stage='failed',error=reason)
        finally:
            self.computation_lock.release()

    def job(self, key):
        if not re.fullmatch(r'[a-f0-9]{32}',key):raise ValueError('Invalid job identifier')
        path=self.directory/('job-'+key+'.json')
        with self.lock:
            if not path.is_file():raise FileNotFoundError('Job not found')
            return json.loads(path.read_text(encoding='utf8'))

    def result(self, event):
        if not isinstance(event,str) or not re.fullmatch(r'industry-[a-f0-9]{32}',event):
            raise ValueError('Invalid event identifier')
        path=self.audit.directory/(event+'.accepted.json')
        if not path.is_file():raise FileNotFoundError('Accepted result not found')
        value=json.loads(path.read_text(encoding='utf8'))
        value['_archive_sha256']=evidence(path)['sha256']
        return value

    def history(self):
        rows=[]
        for path in sorted(self.audit.directory.glob('industry-*.accepted.json'),
                           key=lambda p:p.stat().st_mtime,reverse=True)[:100]:
            value=json.loads(path.read_text(encoding='utf8'))
            rows.append({'event_id':value['event_id'],'created_at':value.get('created_at'),
                'configuration':value['physical']['configuration'],
                'duration_s':value['physical']['series'][-1]['time_s'],
                'diagnosis':value['diagnosis']['label'],
                'model_version':value['diagnosis']['model_version'],
                'sha256':evidence(path)['sha256'],'source':'synthetic-physics'})
        return rows

    def annotations(self, event):
        self.result(event)
        path=self.directory/(event+'.annotations.json')
        with self.lock:
            return json.loads(path.read_text(encoding='utf8')) if path.exists() else []

    def annotate(self, payload):
        if not isinstance(payload,dict) or set(payload)-{'event_id','kind','comment','alarm'}:
            raise ValueError('Invalid annotation')
        value=self.result(payload.get('event_id'))
        kind=payload.get('kind')
        comment=payload.get('comment')
        if kind not in ('note','acknowledge') or not isinstance(comment,str) or not 3<=len(comment.strip())<=2000:
            raise ValueError('A comment of 3 to 2000 characters is required')
        if any(ord(c)<32 and c not in '\n\t' for c in comment):
            raise ValueError('Invalid characters in comment')
        alarm=payload.get('alarm')
        if kind=='acknowledge':
            self._validate_alarm(value,alarm)
        elif alarm is not None:raise ValueError('A note cannot acknowledge an alarm')
        event=value['event_id']
        with self.lock:
            rows=self.annotations(event)
            if kind=='acknowledge' and any(x['kind']=='acknowledge' and x['alarm']['id']==alarm['id'] for x in rows):
                raise ValueError('This alarm occurrence has already been acknowledged')
            record={'annotation_id':uuid.uuid4().hex,'event_id':event,'kind':kind,
                'comment':comment.strip(),'created_at':utc(),
                'actor':'local-workstation','actor_authenticated':False,'alarm':alarm}
            snapshot=self.directory/('annotation-'+record['annotation_id']+'.json')
            def save():
                snapshot.write_text(json.dumps(record,allow_nan=False),encoding='utf8')
                atomic_json(self.directory/(event+'.annotations.json'),rows+[record])
                return record
            return self.audit.execute('workspace',kind,event,{'actor':'local-workstation'},
                'Persist a review record for an accepted event; acknowledgement never alters physics',
                save,lambda v:({'saved':v['annotation_id']==record['annotation_id']},[snapshot]))

    @staticmethod
    def _validate_alarm(value, alarm):
        if not isinstance(alarm,dict) or set(alarm)!={'id','equipment','signal','time_s','value','limit'}:
            raise ValueError('Invalid alarm evidence')
        if not isinstance(alarm['id'],str) or not 1<=len(alarm['id'])<=180:raise ValueError('Invalid alarm identifier')
        cells=value['physical']['cells']
        if alarm['equipment'] not in cells:raise ValueError('Alarm equipment not found')
        index=cells.index(alarm['equipment'])
        row=next((x for x in value['physical']['series'] if x['time_s']==alarm['time_s']),None)
        if row is None:raise ValueError('Alarm time not observed')
        obs=row['observation'];signal=alarm['signal']
        if signal=='pressure_kPa':actual=obs['pressure_kPa'][index]
        elif signal=='temperature_K':actual=obs['temperature_K'][index]
        elif signal=='sensor_difference_K' and index==0:
            actual=abs(obs['temperature_K'][0]-obs['heater_reference_K'])
        elif signal=='protection':actual=1 if obs['protection']['latched'] else 0
        else:raise ValueError('Unsupported alarm signal')
        for number in (alarm['value'],alarm['limit']):
            if isinstance(number,bool) or not isinstance(number,(int,float)) or not math.isfinite(number):
                raise ValueError('Alarm values must be finite')
        if not math.isfinite(actual) or abs(actual-alarm['value'])>1e-7 or actual<=alarm['limit']:
            raise ValueError('Alarm must match an observed threshold exceedance')
