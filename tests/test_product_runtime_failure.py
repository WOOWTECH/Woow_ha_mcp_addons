"""Runtime replacement failures cannot leave old backend credentials active."""
import asyncio
from types import SimpleNamespace

import pytest

from mcp_admin_core import run_product


async def test_invalid_replacement_spec_stops_previous_child_first(tmp_path, monkeypatch):
    events = []
    callback = None

    class Manager:
        def __init__(self, spec):
            self.spec = spec
        async def start(self): events.append('start')
        async def stop(self): events.append('stop')

    def child_spec(state, directory):
        if not events:
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
        async def run(self): await asyncio.Event().wait()

    class Listener:
        def __init__(self, config): self.should_exit = False
        async def serve(self):
            # First listener triggers an invalid configured replacement.
            if events == ['start']:
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
        await run_product.run(args)
    assert events[:3] == ['start', 'stop', 'invalid-replacement']
    assert events.count('start') == 1
