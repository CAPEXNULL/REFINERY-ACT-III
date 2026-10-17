import pytest
from amd.plant import CONFIGS,Scenario
from amd.planning import compare_actions


def test_configuration_c_changes_topology_and_b_changes_stage_count():
    assert CONFIGS['A'].stages==6 and CONFIGS['B'].stages==8
    assert CONFIGS['C'].condensers==2


@pytest.mark.parametrize('kwargs',[{'fault':'unsupported'},{'severity':0},{'fault_time':-1},{'severity':float('nan')}])
def test_scenario_rejects_invalid_input(kwargs):
    with pytest.raises(ValueError):Scenario(**kwargs)


def test_unknown_diagnosis_does_not_run_or_recommend_actions():
    result=compare_actions(None,None,{'label':'unknown'})
    assert result['available'] is False
