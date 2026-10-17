import pytest
from amd.audit import Trace


def test_restart_keeps_run_and_rejects_new_identity(tmp_path):
    first=Trace(tmp_path)
    assert Trace(tmp_path).run_id==first.run_id
    with pytest.raises(ValueError):Trace(tmp_path,'other')


def test_tampered_evidence_is_detected(tmp_path):
    artifact=tmp_path/'answer.txt';artifact.write_text('42')
    log=Trace(tmp_path)
    log.execute('test','read',str(artifact),{},'answer 42',lambda:42,lambda r:({'answer':r==42},[artifact]))
    assert log.verify()['evidence_valid']
    artifact.write_text('43')
    with pytest.raises(ValueError):log.verify()


def test_recheck_preserves_original_failure_and_closes_defect(tmp_path):
    log=Trace(tmp_path)
    with pytest.raises(RuntimeError):log.execute('test','check','a',{},'answer 1',lambda:2,lambda r:({'ok':r==1},[]),defect_id='D1')
    old=log.path.read_bytes()
    log.execute('test','RECHECK','a',{},'answer 1',lambda:1,lambda r:({'ok':r==1},[]),defect_id='D1')
    assert log.path.read_bytes().startswith(old)
    assert log.records()[-1]['defect_state']=='CLOSED'


def test_third_failed_defect_blocks_next_attempt(tmp_path):
    log=Trace(tmp_path)
    for _ in range(3):
        with pytest.raises(RuntimeError):log.execute('test','check','a',{},'answer 1',lambda:2,lambda r:({'ok':r==1},[]),defect_id='D1')
    with pytest.raises(RuntimeError,match='Three failed'):log.execute('test','check','a',{},'answer 1',lambda:1,lambda r:({'ok':True},[]),defect_id='D1')
