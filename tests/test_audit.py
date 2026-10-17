import json
import pytest
from amd.audit import Trace


def test_intent_exists_before_action_and_evidence_is_hashed(tmp_path):
    log=Trace(tmp_path,'test-run')
    def action():
        intent=list(tmp_path.glob('*.intent.json'))
        assert len(intent)==1
        assert json.loads(intent[0].read_text())['pass_criterion']=={'answer':42}
        return 42
    assert log.execute('test','calculate','answer',{}, {'answer':42}, action,
                       lambda value:({'answer':value==42},[]))==42
    row=log.records()[0]
    assert row['status']=='PASS' and len(row['evidence'][0]['sha256'])==64


def test_failure_is_logged_once_and_prior_bytes_are_preserved(tmp_path):
    log=Trace(tmp_path,'test-run')
    log.execute('test','ok','answer',{},'must equal 1',lambda:1,lambda r:({'ok':r==1},[]))
    original=log.path.read_bytes()
    with pytest.raises(RuntimeError):
        log.execute('test','bad','answer',{},'must equal 1',lambda:2,lambda r:({'ok':r==1},[]))
    assert log.path.read_bytes().startswith(original)
    assert len(log.records())==2
    assert log.records()[-1]['defect_state']=='OPEN'


def test_exception_is_logged_and_corrupt_sequence_is_rejected(tmp_path):
    log=Trace(tmp_path)
    def fail(): raise ValueError('failure')
    with pytest.raises(ValueError):
        log.execute('test','fail','answer',{},'must complete',fail,lambda r:({'ok':True},[]))
    assert log.records()[0]['status']=='FAIL'
    log.path.write_text('{"sequence":3}\n',encoding='utf-8')
    with pytest.raises(ValueError): log.records()
