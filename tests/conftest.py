"""Per-test evidence when a qualification run opts into AMD_TRACE_DIR."""
import json
import os
from pathlib import Path
import uuid
import pytest
from amd.audit import Trace,evidence,utc


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item,nextitem):
    directory=os.environ.get('AMD_TRACE_DIR')
    if not directory:
        yield
        return
    log=Trace(directory)
    identifier=uuid.uuid4().hex;started=utc();source=Path(str(item.path))
    intent=log.directory/(identifier+'.intent.json')
    criterion={'test':item.nodeid,'criterion':'all assertions in versioned test source pass; setup and teardown succeed',
               'source':evidence(source)}
    intent.write_text(json.dumps(criterion),encoding='utf-8')
    item._trace_reports=[]
    yield
    reports=item._trace_reports
    passed=len(reports)==3 and all(r['outcome']=='passed' for r in reports)
    artifact=log.directory/(identifier+'.pytest.json');artifact.write_text(json.dumps(reports),encoding='utf-8')
    record={'operation_id':identifier,'started_at':started,'finished_at':utc(),'component':'pytest',
            'action':'test','target_ref':item.nodeid,'input':{},'source_ref':[str(source)],
            'state_before':{'applicable':False,'reason':'isolated fixture state specified by test'},
            'pass_criterion':criterion,'result':reports,'state_after':{'accepted':passed},
            'evidence':[evidence(intent),evidence(artifact)],'status':'PASS' if passed else 'FAIL'}
    if not passed:record.update(defect_id=item.nodeid,defect_state='OPEN',failure_reason='pytest setup/call/teardown did not all pass')
    log.append(record)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item,call):
    outcome=yield
    report=outcome.get_result()
    if hasattr(item,'_trace_reports'):
        item._trace_reports.append({'phase':report.when,'outcome':report.outcome,'duration_s':report.duration,
                                    'failure':str(report.longrepr) if report.failed else None})
