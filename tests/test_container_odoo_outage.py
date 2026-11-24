"""Real management/child with the candidate's exact HTTP fixture; no Docker/HAOS claim."""
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
import importlib
import socket
import sys
import threading

from mcp_admin_core.health import HEALTH_INTERVAL
import test_real_products as real


async def test_candidate_odoo_two_failed_checks_keep_child_alive(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(real.ROOT / 'packaging'))
    monkeypatch.setattr(sys, 'argv', ['container_probe.py', 'odoo'])
    probe = importlib.import_module('container_probe')
    monkeypatch.setattr(probe, 'APP', 'odoo')
    probe.CALLS.clear()
    probe.OFFLINE.clear()
    probe.container_profiles.ODOO_OUTAGE_CHECKS.clear()

    @contextmanager
    def candidate_backend(product):
        assert product == 'odoo'
        host = socket.gethostbyname(socket.gethostname())
        server = ThreadingHTTPServer((host, 0), probe.Backend)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f'http://{host}:{server.server_port}', probe.CALLS, probe.OFFLINE
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
            probe.OFFLINE.clear()

    async def outage(client, ready_url):
        await probe.container_profiles.odoo_outage(probe, client, ready_url)
        checks = probe.container_profiles.ODOO_OUTAGE_CHECKS
        assert len(checks) == 2, 'must observe two actual failed backend checks'
        assert checks[1] - checks[0] >= HEALTH_INTERVAL, 'runtime health cadence changed'

    monkeypatch.setattr(real, 'backend', candidate_backend)
    # Includes real child initialization/read/auth, PID stability, ping and clean shutdown.
    await real.test_real_child_fake_backend_and_boundary(tmp_path, 'odoo', outage_check=outage)
