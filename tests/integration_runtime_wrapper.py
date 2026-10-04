"""PRIVATE local harness copied to a disposable packaging root; never shipped.

Entrypoint still does its real uid drop/final exec. Real management main applies
its guard before this runpy interception sets test-only ports, WS transport and
Ingress socket simulation. No production module has a test flag.
"""
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).parent.parent
CONFIG = json.loads((ROOT / 'local-test.json').read_text())
sys.path.insert(0, CONFIG['source'] + '/tests')
from owned_network import install, install_subprocess_guard
install()
install_subprocess_guard()
spec = importlib.util.spec_from_file_location('real_management', CONFIG['source'] + '/packaging/management_launcher.py')
management = importlib.util.module_from_spec(spec)
spec.loader.exec_module(management)
original_run = management.runpy.run_path


def actual_app(path, **kwargs):
    import ctypes
    import os
    assert ctypes.CDLL(None).prctl(3, 0, 0, 0, 0) == 0
    assert os.getuid() == 10001
    assert path == CONFIG['source'] + '/apps/n8n/run.py'
    sys.argv = [path, '--data', CONFIG['data'], '--host', '127.0.0.1',
                '--admin-port', str(CONFIG['admin_port']), '--mcp-port', str(CONFIG['mcp_port'])]
    from mcp_admin_core import ha_role, gateway
    connect = ha_role._NoRedirectConnect
    def owned_transport(uri, **options):
        assert uri == 'ws://supervisor/core/websocket'
        assert options['proxy'] is None and options['logger'].disabled
        return connect(uri, host='127.0.0.1', port=CONFIG['ws_port'], **options)
    ha_role._NoRedirectConnect = owned_transport
    factory = ha_role.make_ha_admin_verifier
    def observed_factory():
        (Path(CONFIG['data'])/'factory-called').write_text('real factory')
        return factory()
    ha_role.make_ha_admin_verifier = observed_factory
    real_apps = gateway.make_apps
    class LocalIngress:
        def __init__(self, app): self.app = app
        async def __call__(self, scope, receive, send):
            if scope['type'] == 'http':
                scope = dict(scope)
                scope['client'] = ('172.30.32.2', 12345)
                headers = list(scope['headers'])
                # Fixed local subject; tests can also submit an explicit subject
                # to exercise nonadmin/duplicates through actual core validation.
                if not any(k == b'x-remote-user-id' for k,v in headers):
                    headers.append((b'x-remote-user-id', b'owner'))
                if scope['path'].startswith('/api/hassio_ingress/DUMMY/'):
                    headers.append((b'x-ingress-path', b'/api/hassio_ingress/DUMMY'))
                scope['headers'] = headers
            tail = b''
            async def checked_send(message):
                nonlocal tail
                if message['type'] == 'http.response.body':
                    data = tail + message.get('body', b'')
                    assert b'INVENTED-LOCAL-MACHINE-ONLY' not in data, 'machine token on admin wire'
                    tail = data[-64:]
                await send(message)
            await self.app(scope, receive, checked_send)
    def observed_apps(*args, **kwargs):
        admin, mcp = real_apps(*args, **kwargs)
        return LocalIngress(admin), mcp
    gateway.make_apps = observed_apps
    # Instrument the actual pinned Node child, not a replacement child. Its
    # preload asserts parent environ/mem denial before loading n8n itself.
    import n8n_adapter
    from mcp_admin_core.lifecycle import ChildSpec
    child_spec = n8n_adapter.child_spec
    def checked_child(state, directory):
        value = child_spec(state, directory)
        assert 'SUPERVISOR_TOKEN' not in value.env
        return ChildSpec((value.argv[0], '--require', str(ROOT/'child-check.cjs'), *value.argv[1:]), value.env, value.cwd)
    n8n_adapter.child_spec = checked_child
    # Import the real executable after the real post-exec guard, then bind its
    # module aliases before main. No runpy __main__ alias is patched too late.
    from mcp_admin_core import ui
    ui.UI_ROOT = Path(CONFIG['ui_dist'])
    app_spec = importlib.util.spec_from_file_location('owned_real_n8n', path)
    app = importlib.util.module_from_spec(app_spec)
    app_spec.loader.exec_module(app)
    from owned_executable import install_runner
    install_runner(app, CONFIG['owned_runtime'])
    return app.main()

management.runpy.run_path = actual_app
management.main()
