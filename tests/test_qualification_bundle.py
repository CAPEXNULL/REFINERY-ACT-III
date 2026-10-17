"""Clean-checkout qualification and rejected stale/tampered proof tests."""
import json
import shutil
from pathlib import Path
import pytest
from amd.industry_service import IndustryService

ROOT=Path(__file__).resolve().parents[1]


def checkout(tmp_path):
    bundle=tmp_path/'assets/refinery';bundle.mkdir(parents=True)
    for p in (ROOT/'assets/refinery').iterdir():shutil.copyfile(p,bundle/p.name)
    report=json.loads((bundle/'TRANSFER_REPORT.json').read_text(encoding='utf-8-sig'))
    for item in report['protocol']['source_manifest']:
        relative=Path(item['path'].replace('\\','/'));source=ROOT/relative;target=tmp_path/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    return bundle,report


def test_clean_checkout_uses_portable_qualified_model_without_runtime_archive(tmp_path):
    bundle,_=checkout(tmp_path);service=IndustryService(tmp_path)
    assert service.status()['model_ready']
    assert service.model_source==bundle/'FROZEN_MODEL.json'
    assert not list((tmp_path/'reports/trace').glob('*/transfer-*/TRANSFER_REPORT.json'))


@pytest.mark.parametrize('artifact',['FROZEN_MODEL.json','TRANSFER_REPORT.json'])
def test_modified_qualification_artifact_is_rejected(tmp_path,artifact):
    bundle,_=checkout(tmp_path)
    with (bundle/artifact).open('a',encoding='utf-8') as out:out.write(' ')
    assert not IndustryService(tmp_path).status()['model_ready']


def test_changed_physical_source_invalidates_qualification(tmp_path):
    _,report=checkout(tmp_path)
    target=tmp_path/Path(report['protocol']['source_manifest'][0]['path'].replace('\\','/'))
    with target.open('a',encoding='utf-8') as out:out.write('\n# changed\n')
    assert not IndustryService(tmp_path).status()['model_ready']


def test_clean_checkout_end_to_end_observation_diagnosis_forecast_feedback(tmp_path):
    checkout(tmp_path);service=IndustryService(tmp_path)
    result=service.run({'configuration':'A','fault':'cooling_loss','severity':.5,'duration_s':4.,'plan_actions':True})
    assert result['diagnosis']['label']=='cooling_loss'
    assert result['action_forecast'] is not None
    assert result['physical']['energy_balance_residual_J']<1e-3
    assert result['event_id'] in service.agent.state.processed_events


@pytest.mark.parametrize('ending',[b'\n',b'\r\n'])
def test_git_checkout_line_endings_preserve_equivalent_source_qualification(tmp_path,ending):
    _,report=checkout(tmp_path)
    for item in report['protocol']['source_manifest']:
        target=tmp_path/Path(item['path'].replace('\\','/'))
        target.write_bytes(target.read_bytes().replace(b'\r\n',b'\n').replace(b'\n',ending))
    assert IndustryService(tmp_path).status()['model_ready']


@pytest.mark.parametrize('malformed',['[]','null'])
def test_malformed_qualification_descriptor_rejects_readiness_without_crash(tmp_path,malformed):
    bundle,_=checkout(tmp_path)
    (bundle/'QUALIFICATION.json').write_text(malformed,encoding='utf-8')
    assert not IndustryService(tmp_path).status()['model_ready']
