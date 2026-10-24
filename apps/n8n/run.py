"""n8n executable with the approved fixed-query HA administrator-role provider.

Run with PYTHONPATH=packages/mcp-admin-core:apps/n8n .venv/bin/python apps/n8n/run.py
Deployment options are listener addresses/ports and the dedicated state directory,
never backend credentials, tool policy, tokens or arbitrary child commands.
"""
import argparse
import asyncio
from contextlib import contextmanager
from pathlib import Path
import signal

import httpx
import uvicorn

from mcp_admin_core import redact
from mcp_admin_core.config import ConfigError
from mcp_admin_core.capabilities import ManagementOptions
from mcp_admin_core.products import ProductStore
from mcp_admin_core.gateway import make_apps
from mcp_admin_core.ha_role import make_ha_admin_verifier
from mcp_admin_core.health import HealthMonitor
from mcp_admin_core.lifecycle import Supervisor
from mcp_admin_core.surface import listing
from n8n_adapter import TOOLS, child_spec


class Listener(uvicorn.Server):
    @contextmanager
    def capture_signals(self):
        # One top-level signal owner shuts down BOTH listeners and the child group.
        yield


async def run(args):
    from mcp_admin_core.upgrade import run_upgrade_review
    if not await run_upgrade_review(args, 'n8n'):
        return
    store = ProductStore(args.data, 'n8n')
    manager = Supervisor(child_spec(store.load(), store.directory))
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    tasks = []
    servers = []
    try:
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False,
            timeout=httpx.Timeout(10, connect=3), limits=httpx.Limits(max_connections=40)) as child:
            health = HealthMonitor(store, manager, child)
            async def backend_changed(state):
                health.backend = "unknown"
                await manager.restart(child_spec(state, store.directory))
            admin, mcp = make_apps(store, TOOLS, child, health=health.snapshot,
                                   backend_changed=backend_changed,
                                   management=ManagementOptions(kind="ha-addon", authority="ha-admin"),
                                   backend_check=getattr(health, "test_saved", None), restart_child=backend_changed, diagnostics=getattr(manager, "diagnostics", None),
                                   verify_admin=make_ha_admin_verifier(),
                                   server_name="woow-mcp-n8n",
                                   # 0.2.2: the full list and clean refusals without a backend or a running child
                                   listing=listing("n8n"), availability=health.availability)
            servers = [Listener(uvicorn.Config(app, host=args.host, port=port,
                proxy_headers=False, access_log=False, log_level="warning", server_header=False,
                lifespan="off",  # this function, not ASGI lifespan, owns runtime resources
                limit_concurrency=64, timeout_keep_alive=5)) for app, port in
                ((admin, args.admin_port), (mcp, args.mcp_port))]
            # 0.1.12: the token may be in a request path (/private_<token>/mcp): scrub every log record.
            redact.install()
            redact.guard_handlers(*redact.UVICORN_LOGGERS)
            await manager.start()
            monitor_task = asyncio.create_task(health.run())
            tasks = [asyncio.create_task(server.serve()) for server in servers]
            stop_task = asyncio.create_task(stop.wait())
            try:
                done, _ = await asyncio.wait([*tasks, monitor_task, stop_task], return_when=asyncio.FIRST_COMPLETED)
                if monitor_task in done or any(task in done for task in tasks):
                    # A monitor/listener ending is NOT an orderly signal shutdown.
                    # Never propagate its possibly credential-bearing exception text.
                    raise RuntimeError("runtime component stopped") from None
            finally:
                for server in servers:
                    server.should_exit = True
                monitor_task.cancel()
                stop_task.cancel()
                await asyncio.gather(monitor_task, stop_task, return_exceptions=True)
                try:
                    async with asyncio.timeout(5):
                        await asyncio.gather(*tasks)
                except TimeoutError:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                await manager.stop()
    finally:
        store.close()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("/data/mcp"))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--admin-port", type=int, default=8099)
    parser.add_argument("--mcp-port", type=int, default=8081)
    args = parser.parse_args()
    if args.admin_port == args.mcp_port or 3000 in (args.admin_port, args.mcp_port):
        parser.error("listeners must be distinct and cannot use child port 3000")
    try:
        asyncio.run(run(args))
    except (ConfigError, RuntimeError):
        # Never stringify third-party/config exceptions: they may contain secrets.
        raise SystemExit("runtime unavailable; local recovery required") from None


if __name__ == "__main__":
    main()
