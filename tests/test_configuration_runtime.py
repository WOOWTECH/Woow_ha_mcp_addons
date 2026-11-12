"""Saved launch identity must match the actual child generation, not backend health."""
from types import SimpleNamespace

from mcp_admin_core.configuration import ConfigurationState
from mcp_admin_core.products import ProductStore


def setup_runtime(tmp_path, product='hermes'):
    store=ProductStore(tmp_path/'state',product)
    if product=='hermes':store.update(connection={'gateway_url':'https://fixture.invalid','gateway_api_key':'SYNTHETIC_ONLY'})
    elif product=='litellm':store.update(connection={'url':'https://fixture.invalid','master_key':'SYNTHETIC_ONLY'})
    manager=SimpleNamespace(starts=0,status='stopped')
    health=SimpleNamespace(settled=None)
    tracker=ConfigurationState(store,manager,health)
    return store,manager,health,tracker


def ready(manager,health,generation):
    manager.starts=generation;manager.status='running'
    # A failed backend read does not undo successful child protocol readiness.
    health.settled=(generation,True,'unreachable','BACKEND_UNAVAILABLE')


def test_spawn_is_pending_until_matching_protocol_readiness(tmp_path):
    s,m,h,t=setup_runtime(tmp_path)
    try:
        state=s.load();t.begin(state);m.starts=1;m.status='running'
        assert t.snapshot(state)['apply_state']=='pending'
        ready(m,h,1);out=t.snapshot(state)
        assert out['apply_state']=='applied' and out['applied_revision']==out['saved_revision']
        assert out['last_error_code'] is None
    finally:s.close()


def test_old_generation_and_old_configuration_cannot_apply_new_save(tmp_path):
    s,m,h,t=setup_runtime(tmp_path)
    try:
        first=s.load();t.begin(first);ready(m,h,1);old=t.snapshot(first)['applied_revision']
        second=s.update(connection={'gateway_url':'https://other.invalid','gateway_api_key':'SECOND_SYNTHETIC'})
        t.begin(second)
        # Old completed health check remains during restart; it cannot settle the new attempt.
        assert t.snapshot(second)['apply_state']=='pending'
        m.starts=2
        assert t.snapshot(second)['apply_state']=='pending'
        ready(m,h,2);new=t.snapshot(second)
        assert new['apply_state']=='applied' and new['applied_revision']!=old
        third=s.update(connection={'gateway_url':'https://third.invalid','gateway_api_key':'THIRD_SYNTHETIC'})
        # Even a successful check cannot claim an externally changed snapshot was launched.
        assert t.snapshot(third)['apply_state']=='pending'
        assert t.snapshot(third)['applied_revision']==new['applied_revision']
    finally:s.close()


def test_failure_survives_repeated_status_reads_and_retry_clears_it(tmp_path):
    s,m,h,t=setup_runtime(tmp_path)
    try:
        state=s.load();t.begin(state);t.failed('child_start_failed');m.status='failed'
        for _ in range(2):
            out=t.snapshot(s.load());assert out['apply_state']=='failed' and out['last_error_code']=='child_start_failed'
        t.begin(state);m.status='starting';h.settled=None
        assert t.snapshot(state)['apply_state']=='pending'
        ready(m,h,1);assert t.snapshot(state)['apply_state']=='applied'
        m.status='failed';assert t.snapshot(state)['apply_state']=='failed'
        assert t.snapshot(state)['applied_revision'] is None
    finally:s.close()


def test_protocol_failure_is_failed_and_later_matching_success_recovers(tmp_path):
    s,m,h,t=setup_runtime(tmp_path)
    try:
        state=s.load();t.begin(state);m.starts=1;m.status='running';h.settled=(1,False,'unknown','raw-secret-not-exported')
        out=t.snapshot(state);assert out['apply_state']=='failed' and out['last_error_code']=='child_not_ready'
        assert 'raw-secret' not in str(out)
        ready(m,h,1);assert t.snapshot(state)['apply_state']=='applied'
    finally:s.close()


def test_edit_revision_separate_from_launch_revision_and_secret_free(tmp_path):
    s,m,h,t=setup_runtime(tmp_path)
    try:
        state=s.load();t.begin(state);ready(m,h,1);a=t.snapshot(state)
        state=s.update(endpoint='https://endpoint.invalid/mcp',token=None,writes_enabled=False,enabled_write_tools=[])
        b=t.snapshot(state)
        assert a['revision']!=b['revision'] and a['saved_revision']==b['saved_revision']
        assert b['apply_state']=='applied'
        assert t.etag(state)=='"'+b['revision']+'"'
        assert not any(secret in str(b) for secret in ['SYNTHETIC_ONLY','fixture.invalid',state.child_token])
        other=ConfigurationState(s,m,h)
        assert other.revision(state)!=t.revision(state)  # old forms conflict after process restart
    finally:s.close()


def test_native_policy_is_part_of_launch_but_hermes_gateway_policy_is_not(tmp_path):
    s,m,h,t=setup_runtime(tmp_path,'litellm')
    try:
        state=s.load();t.begin(state);ready(m,h,1);a=t.snapshot(state)
        state=s.update(writes_enabled=False,enabled_write_tools=[])
        assert t.snapshot(state)['saved_revision']!=a['saved_revision']
        assert t.snapshot(state)['apply_state']=='pending'
    finally:s.close()


def test_unconfigured_and_runtime_without_observer_are_not_claimed_applied(tmp_path):
    s=ProductStore(tmp_path/'state','hermes')
    try:
        t=ConfigurationState(s)
        assert t.snapshot(s.load())['apply_state']=='unconfigured'
        state=s.update(connection={'gateway_url':'https://fixture.invalid','gateway_api_key':'SYNTHETIC_ONLY'})
        assert t.snapshot(state)['apply_state']=='unknown'
    finally:s.close()
