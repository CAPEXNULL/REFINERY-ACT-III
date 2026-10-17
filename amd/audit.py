"""Append-only scoped evidence log. Never repairs missing historical records."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import threading
import uuid
import os
import time
from contextlib import contextmanager

_LOCK = threading.RLock()

REQUIRED = {'run_id','sequence','operation_id','started_at','finished_at','component',
            'action','target_ref','input','source_ref','state_before','pass_criterion',
            'result','state_after','evidence','status'}


@contextmanager
def writer_lock(directory):
    with _LOCK:
        with (Path(directory)/'.writer.lock').open('a+b') as lock:
            if os.name=='nt':
                import msvcrt
                if lock.tell()==0: lock.write(b'0'); lock.flush()
                lock.seek(0)
                deadline=time.monotonic()+30.
                while True:
                    try:
                        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
                        break
                    except OSError as error:
                        if error.errno not in (13,36):raise
                        if time.monotonic()>=deadline:
                            raise TimeoutError('Audit writer remained locked for30seconds') from error
                        time.sleep(.05)
            else:
                import fcntl
                fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
            try: yield
            finally:
                if os.name=='nt':
                    lock.seek(0); msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
                else: fcntl.flock(lock.fileno(),fcntl.LOCK_UN)


def utc():
    return datetime.now(timezone.utc).isoformat()


def evidence(path):
    p = Path(path)
    return {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}


class Trace:
    def __init__(self, directory, run_id=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'TRACE.jsonl'
        self.state_path=self.directory/'RUN_STATE.json'
        with writer_lock(self.directory):
            if self.state_path.exists():
                state=json.loads(self.state_path.read_text(encoding='utf-8-sig'))
                self.run_id=state['run_id']
                if run_id is not None and self.run_id!=run_id:
                    raise ValueError('Cannot change run_id in an existing run')
            else:
                old_rows=[json.loads(line) for line in self.path.read_text(encoding='utf-8').splitlines()] if self.path.exists() else []
                identities={r['run_id'] for r in old_rows}
                if len(identities)>1:raise ValueError('Existing journal contains mixed run identities')
                inherited=next(iter(identities)) if identities else None
                if inherited and run_id and inherited!=run_id:raise ValueError('Existing journal identity conflict')
                self.run_id=inherited or run_id or uuid.uuid4().hex
                self.state_path.write_text(json.dumps({'run_id':self.run_id,'state':'ACTIVE',
                    'historical_trace_complete':False}),encoding='utf-8')

    def records(self):
        if not self.path.exists():
            return []
        rows = [json.loads(line) for line in self.path.read_text(encoding='utf-8').splitlines()]
        if [r['sequence'] for r in rows] != list(range(1, len(rows)+1)):
            raise ValueError('Trace sequence is not contiguous')
        for row in rows:
            if not REQUIRED.issubset(row) or row['run_id']!=self.run_id:
                raise ValueError('Trace schema or run identity invalid')
        return rows

    def append(self, record):
        with writer_lock(self.directory):
            rows = self.records()
            record = dict(record, run_id=self.run_id, sequence=len(rows)+1)
            raw = json.dumps(record, ensure_ascii=False, allow_nan=False)
            if not REQUIRED.issubset(record): raise ValueError('Required trace fields missing')
            with self.path.open('a', encoding='utf-8') as stream:
                stream.write(raw+'\n')
                stream.flush()
                os.fsync(stream.fileno())
            return record

    def defect_attempts(self, defect_id):
        return sum(r.get('defect_id')==defect_id and r['status']=='FAIL' for r in self.records())

    def verify(self):
        rows=self.records()
        for row in rows:
            for item in row['evidence']:
                if evidence(item['path'])['sha256']!=item['sha256']:
                    raise ValueError('Evidence changed: '+item['path'])
        return {'records':len(rows),'evidence_valid':True}

    def execute(self, component, action, target, inputs, criterion, operation, validate,
                sources=(), before=None, defect_id=None):
        if defect_id and self.defect_attempts(defect_id)>=3:
            self.state_path.write_text(json.dumps({'run_id':self.run_id,'state':'BLOCKED',
                'defect_id':defect_id,'reason':'three failed attempts'}),encoding='utf-8')
            raise RuntimeError('Three failed attempts for defect '+defect_id)
        operation_id = uuid.uuid4().hex
        started = utc()
        base = dict(operation_id=operation_id, component=component, action=action,
                    target_ref=target, input=inputs, source_ref=list(sources),
                    state_before=before or {'applicable': False, 'reason': 'no prior state supplied'},
                    pass_criterion=criterion)
        if defect_id: base['defect_id']=defect_id
        source_evidence=[evidence(p) for p in sources if Path(p).is_file()]
        # Durable intent proves the criterion existed before the operation.
        intent = self.directory / (operation_id+'.intent.json')
        with intent.open('x', encoding='utf-8') as stream:
            json.dump(dict(base, run_id=self.run_id, started_at=started), stream, allow_nan=False)
        try:
            result = operation()
            checks, artifacts = validate(result)
            passed = bool(checks) and all(v is True for v in checks.values())
            record = dict(base, started_at=started, finished_at=utc(),
                          result={'checks': checks}, state_after={'accepted': passed},
                          evidence=[evidence(intent)]+[evidence(p) for p in artifacts],
                          source_manifest=source_evidence,
                          status='PASS' if passed else 'FAIL')
            if not passed:
                record.update(defect_id=defect_id or operation_id, defect_state='OPEN',
                              failure_reason='Acceptance checks failed')
            elif defect_id: record['defect_state']='CLOSED'
            self.append(record)
            if not passed:
                raise RuntimeError('Trace acceptance failed: '+operation_id)
            return result
        except Exception as error:
            # Do not duplicate an already recorded validation failure.
            if not any(r['operation_id']==operation_id for r in self.records()):
                self.append(dict(base, started_at=started, finished_at=utc(),
                                 result={'exception_type': type(error).__name__},
                                 state_after={'accepted': False}, evidence=[evidence(intent)],
                                 status='FAIL', defect_id=defect_id or operation_id, defect_state='OPEN',
                                 failure_reason='Operation raised an exception'))
            raise
