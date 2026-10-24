"""Runtime replacement failures cannot leave old backend credentials active."""
import asyncio
from types import SimpleNamespace

import pytest

from mcp_admin_core import run_product


async def test_invalid_replacement_spec_stops_previous_child_first(tmp_path, monkeypatch):
    events = []
    callback = None
    spec_calls = 0
    triggered = False

    class Manager:
        def __init__(self, spec):
            self.spec = spec
        async def start(self): events.append('start')
        async def stop(self): events.append('stop')

    def child_spec(state, directory):
        nonlocal spec_calls
        spec_calls += 1
        if spec_calls == 1:
            return None
        events.append('invalid-replacement')
        raise RuntimeError('invalid launch')

    def apps(store, tools, child, **kwargs):
        nonlocal callback
        callback = lambda: kwargs['backend_changed'](store.load())
        return object(), object()

    class Monitor:
        def __init__(self, *args): pass
        def snapshot(self): return {}
        def availability(self): return {'child': 'running', 'ready': False, 'backend': 'unknown', 'reason': None}  # 0.2.2: forward
        async def run(self): await asyncio.Event().wait()

    class Listener:
        def __init__(self, config): self.should_exit = False
        async def serve(self):
            nonlocal triggered
            # First listener triggers an invalid configured replacement.
            if 'start' in events and not triggered:
                triggered = True
                try:
                    await callback()
                except RuntimeError:
                    pass
                return
            while not self.should_exit:
                await asyncio.sleep(.01)

    monkeypatch.setattr(run_product, 'Supervisor', Manager)
    monkeypatch.setattr(run_product, 'child_spec', child_spec)
    monkeypatch.setattr(run_product, 'make_apps', apps)
    monkeypatch.setattr(run_product, 'HealthMonitor', Monitor)
    monkeypatch.setattr(run_product, 'Listener', Listener)
    args = SimpleNamespace(data=tmp_path / 'state', product='emqx', host='127.0.0.1', admin_port=8099, mcp_port=8081)
    with pytest.raises(RuntimeError, match='runtime component stopped'):
        await asyncio.wait_for(run_product.run(args), 3)
    assert events[:4] == ['stop', 'start', 'stop', 'invalid-replacement']
    assert events.count('start') == 1


@pytest.mark.parametrize('product', ['hermes', 'n8n'])
async def test_initial_launch_failure_keeps_management_alive_and_retry_observable(tmp_path, monkeypatch, product):
    import run as n8n_run
    from mcp_admin_core.products import ProductStore
    module = n8n_run if product == 'n8n' else run_product
    directory = tmp_path/'configured'
    store = ProductStore(directory, product)
    if product == 'n8n':
        store.update(backend_url='https://fixture.invalid', backend_key='SYNTHETIC_ONLY')
    else:
        store.update(connection={'gateway_url':'https://fixture.invalid','gateway_api_key':'SYNTHETIC_ONLY'})
    store.close()
    captured = {}; calls = 0; triggered = False

    class Manager:
        def __init__(self, spec):
            self.spec=spec; self.starts=0; self.status='stopped'
        async def stop(self): self.status='stopped'
        async def start(self): self.starts+=1; self.status='running'

    def spec(state, directory):
        nonlocal calls
        calls += 1
        if calls == 1: raise RuntimeError('SYNTHETIC_PRIVATE_FAILURE')
        return object()

    class Monitor:
        def __init__(self, *args): self.settled=None; captured['health']=self
        def snapshot(self): return {}
        def availability(self): return {}
        async def run(self): await asyncio.Event().wait()

    def apps(store, tools, child, **kwargs):
        captured.update(store=store, configuration=kwargs['configuration'], apply=kwargs['backend_changed'])
        return object(), object()

    class Listener:
        def __init__(self, config): self.should_exit=False
        async def serve(self):
            nonlocal triggered
            if not triggered:
                triggered=True
                tracker=captured['configuration']; state=captured['store'].load()
                status=tracker.snapshot(state)
                assert status['apply_state']=='failed'
                assert status['last_error_code']=='child_start_failed'
                assert 'SYNTHETIC_PRIVATE_FAILURE' not in str(status)
                await captured['apply'](state)
                assert tracker.snapshot(state)['apply_state']=='pending'
                captured['health'].settled=(1, True, 'unreachable', None)
                assert tracker.snapshot(state)['apply_state']=='applied'
                return
            while not self.should_exit: await asyncio.sleep(.01)

    for name,value in [('Supervisor',Manager),('child_spec',spec),('HealthMonitor',Monitor),('make_apps',apps),('Listener',Listener)]:
        monkeypatch.setattr(module,name,value)
    args=SimpleNamespace(data=directory,product=product,host='127.0.0.1',admin_port=8099,mcp_port=8081)
    with pytest.raises(RuntimeError, match='runtime component stopped'):
        await asyncio.wait_for(module.run(args), 3)
    assert calls==2
