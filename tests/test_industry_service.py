import pytest
from amd.industry_service import IndustryService


def test_unqualified_model_cannot_accept_diagnosis(tmp_path):
    service=IndustryService(tmp_path)
    assert service.status()['model_ready'] is False
    with pytest.raises(ValueError,match='qualification is pending'):
        service.run({'configuration':'A','fault':'cooling_loss'})
    assert service.agent.state.memory==[]


@pytest.mark.parametrize('args',[{'fault':'invented'},{'configuration':'D'},
    {'duration_s':True},{'severity':float('nan')},{'plan_actions':'yes'},{'truth':'heater_loss'}])
def test_invalid_requests_are_rejected_before_computation(tmp_path,args):
    service=IndustryService(tmp_path)
    with pytest.raises(ValueError):service.run(args)
    assert service.agent.state.memory==[]


def test_unobservable_confirmed_feedback_is_preserved_without_training_and_cannot_repeat(tmp_path):
    import copy
    from amd.perseus import Perseus
    service=IndustryService(tmp_path)
    roles=['heater']+['column']*6+['reboiler','condenser']
    observation={'time_s':4.,'equipment':[f'cell-{i}' for i in range(9)],'roles':roles,
        'temperature_K':[430.]*9,'pressure_kPa':[150.]*9,'heater_reference_K':430.,
        'protection':{'latched':False,'trip_time_s':None}}
    hypothesis=service.agent.diagnose_observation(observation,observation,'tiny-loss')
    before=copy.deepcopy(service.agent.state.task_models['industrial_diagnosis'])
    with pytest.raises(ValueError,match='Unverified'):
        service.confirm_feedback('tiny-loss','cooling_loss',hypothesis['prediction'],{'mass_balance_pass':False})
    result=service.confirm_feedback('tiny-loss','cooling_loss',hypothesis['prediction'],{'mass_balance_pass':True,'energy_balance_pass':True})
    assert result['training_applied'] is False
    assert service.agent.state.task_models['industrial_diagnosis']==before
    restored=Perseus(service.agent.state_path)
    record=next(x for x in restored.state.memory if x['event_id']=='tiny-loss')
    assert record['confirmed_label']=='cooling_loss' and record['outcome']=='CONFIRMED_NOT_IDENTIFIABLE'
    assert 'tiny-loss' in restored.state.processed_events and 'tiny-loss' not in restored.state.diagnosis_pending
    with pytest.raises(ValueError,match='duplicate'):
        service.confirm_feedback('tiny-loss','cooling_loss',hypothesis['prediction'],{'mass_balance_pass':True,'energy_balance_pass':True})
