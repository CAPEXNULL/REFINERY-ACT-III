import json
import threading
import time
import pytest
from amd.audit import Trace
from amd.industry_service import IndustryService
from amd.workspace import Workspace,WorkspaceBusy,atomic_json


EVENT='industry-'+'a'*32


class Service:
    validate=staticmethod(IndustryService.validate)
    def __init__(self,root):
        self.audit=Trace(root/'runtime')
        self.started=threading.Event();self.release=threading.Event();self.calls=0
    def status(self):return {'model_ready':True}
    def run(self,args,progress=None):
        self.calls+=1;self.started.set()
        assert self.release.wait(5)
        if progress:progress('physical',40)
        result={'event_id':EVENT,'physical':{'cells':['E-101'],
            'series':[{'time_s':1.,'observation':{'pressure_kPa':[150.],
              'temperature_K':[380.],'heater_reference_K':380.,'protection':{'latched':False}}}]}}
        (self.audit.directory/(EVENT+'.accepted.json')).write_text(json.dumps(result))
        return result


def submit_request(token='a'*32,args=None):
    return {'request_token':token,'arguments':args or {'configuration':'A'}}


def finish(service,workspace,job):
    service.release.set()
    for t in workspace.threads:t.join(5)
    assert workspace.job(job['job_id'])['status']=='completed'


def test_background_job_idempotence_and_changed_payload_rejection(tmp_path):
    s=Service(tmp_path);w=Workspace(s,threading.Lock())
    job=w.submit(submit_request())
    assert s.started.wait(2)
    again=w.submit(submit_request())
    assert job['job_id']==again['job_id'] and s.calls==1
    with pytest.raises(ValueError,match='different arguments'):
        w.submit(submit_request(args={'configuration':'B'}))
    with pytest.raises(WorkspaceBusy):w.submit(submit_request('b'*32))
    finish(s,w,job)
    assert w.submit(submit_request())['status']=='completed' and s.calls==1
    assert s.audit.verify()['evidence_valid']


def test_startup_marks_abandoned_job_interrupted(tmp_path):
    s=Service(tmp_path);folder=s.audit.directory/'workspace';folder.mkdir()
    job={'job_id':'a'*32,'status':'running','stage':'physical','percent':40}
    atomic_json(folder/('job-'+job['job_id']+'.json'),job)
    w=Workspace(s,threading.Lock())
    assert w.job(job['job_id'])['status']=='running'
    with w.server_owner():w.recover_interrupted()
    assert w.job(job['job_id'])['status']=='interrupted'
    assert w.job(job['job_id'])['percent']==40


@pytest.mark.parametrize('payload',[{}, {'request_token':'short','arguments':{}},
    {'request_token':'a'*32,'arguments':{'duration_s':True}},
    {'request_token':'a'*32,'arguments':{'truth':'cooling_loss'}}])
def test_invalid_job_does_not_compute(tmp_path,payload):
    s=Service(tmp_path);w=Workspace(s,threading.Lock())
    with pytest.raises(ValueError):w.submit(payload)
    assert s.calls==0


@pytest.mark.parametrize('event',['../../private','industry-x',None])
def test_archive_path_cannot_escape(tmp_path,event):
    w=Workspace(Service(tmp_path),threading.Lock())
    with pytest.raises(ValueError):w.result(event)


def saved_event(s):
    s.release.set();s.run({})


def alarm():
    return {'id':'pressure|E-101|1','equipment':'E-101','signal':'pressure_kPa',
            'time_s':1.,'value':150.,'limit':145.}


def test_acknowledgement_is_durable_and_does_not_clear_condition(tmp_path):
    s=Service(tmp_path);saved_event(s);w=Workspace(s,threading.Lock())
    before=w.result(EVENT)
    record=w.annotate({'event_id':EVENT,'kind':'acknowledge','comment':'Reviewed cooling pressure','alarm':alarm()})
    assert record['actor_authenticated'] is False
    assert w.result(EVENT)==before
    assert Workspace(s,threading.Lock()).annotations(EVENT)==[record]
    with pytest.raises(ValueError,match='already been acknowledged'):
        w.annotate({'event_id':EVENT,'kind':'acknowledge','comment':'Duplicate review','alarm':alarm()})
    assert s.audit.verify()['evidence_valid']


@pytest.mark.parametrize('change',[{'value':160.},{'time_s':2.},{'limit':155.},{'equipment':'H-999'}])
def test_acknowledgement_rejects_fabricated_observation(tmp_path,change):
    s=Service(tmp_path);saved_event(s);w=Workspace(s,threading.Lock())
    with pytest.raises(ValueError):w.annotate({'event_id':EVENT,'kind':'acknowledge','comment':'Review','alarm':dict(alarm(),**change)})
    assert w.annotations(EVENT)==[]


def test_note_cannot_change_physics_or_impersonate_authenticated_user(tmp_path):
    s=Service(tmp_path);saved_event(s);w=Workspace(s,threading.Lock())
    record=w.annotate({'event_id':EVENT,'kind':'note','comment':'<script>inspection</script>'})
    assert record['comment']=='<script>inspection</script>' and record['actor']=='local-workstation'
    with pytest.raises(ValueError):w.annotate({'event_id':EVENT,'kind':'note','comment':'x','actor':'admin'})


def test_second_process_cannot_own_running_workspace(tmp_path):
    import subprocess
    import sys
    s=Service(tmp_path);w=Workspace(s,threading.Lock())
    script="""import sys,threading
from types import SimpleNamespace
from pathlib import Path
from amd.audit import Trace
from amd.workspace import Workspace,WorkspaceBusy
w=Workspace(SimpleNamespace(audit=Trace(Path(sys.argv[1]))),threading.Lock())
try:
 with w.server_owner():sys.exit(0)
except WorkspaceBusy:sys.exit(42)
"""
    with w.server_owner():
        result=subprocess.run([sys.executable,'-c',script,str(s.audit.directory)],timeout=20,check=False)
        assert result.returncode==42
