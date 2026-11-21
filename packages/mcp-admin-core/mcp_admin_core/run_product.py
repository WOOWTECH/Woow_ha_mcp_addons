"""Executable product boundary (Odoo, Odoo Manage, Hermes, OpenDesign, EMQX, LiteLLM, Nextcloud) with approved, fail-closed HA admin verification.

PYTHONPATH=packages/mcp-admin-core .venv/bin/python -m mcp_admin_core.run_product emqx
GUI owns typed connection/token/policy. CLI owns deployment fields only.

HM-25 (multi-profile plan 9 n8n row, 12.3 HM-25): n8n's runtime is this one too. apps/n8n/run.py calls run() with the
n8n adapter (ProductAdapter: its tool registry and child spec from apps/n8n/n8n_adapter.py, which this package never
imports, the default profile's catalog copy before the profile's runtime is made, an additional profile's catalog
copy before its child starts, the copy removed with the profile), so a switched-on n8n has the ProfileManager of every
other product, and a switched-off one the default profile's lone ProfileRuntime: what apps/n8n/run.py built itself
before, answer for answer (HM-01's golden regression).
"""
import argparse
import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import signal
from typing import Callable, Mapping

import uvicorn

from . import features, redact, restore_lock, version_for_product
from .config import ConfigError
from .capabilities import ManagementOptions
from .ha_role import make_ha_admin_verifier
from .lifecycle import CHILD_PORT, child_port_text
from .products import INSTRUCTIONS, PRODUCTS, ProductStore, TOOLS, child_spec
from .profile_runtime import ProfileManager, ProfileRuntime
from .reply_worker import ReplyWorker
from .surface import FULL_PRODUCTS, listing


class Listener(uvicorn.Server):
    @contextmanager
    def capture_signals(self):
        yield


@dataclass(frozen=True)
class ProductAdapter:
    """HM-25: what a product outside this package gives run(): its tool registry (tools) and its child spec builder
    (child_spec(state, directory, port=...)), and optionally
    - before_start(): called once the boot guard has run, before any profile's runtime is made (n8n: the default
      profile's catalog copy, as apps/n8n/run.py made it before);
    - prepare_child(profile_id, state): awaited before an additional profile's child spec is built (n8n: that profile's
      own catalog copy, in a worker thread);
    - profile_removed(profile_id): called once a deleted profile's directory is gone (n8n: its catalog copy removed).
    Left out of run() (every product of this package): TOOLS[product] and products.child_spec, nothing else."""
    tools: Mapping
    child_spec: Callable
    before_start: Callable[[], None] | None = None
    prepare_child: Callable | None = None
    profile_removed: Callable[[str], None] | None = None


async def run(args, *, child_port=CHILD_PORT, adapter=None):
    # HM-04: one port for the child's spec, the health monitor, the gateway and its capability probe. main() runs the
    # default profile's child on CHILD_PORT; an extra profile's runtime (multi-profile plan 5.4) passes its own.
    child_port_text(child_port)  # an invalid port is refused before anything starts
    # HM-25: the product's tools and child spec (apps/n8n/run.py gives n8n's adapter; left out: this package's own)
    adapter = ProductAdapter(TOOLS[args.product], child_spec) if adapter is None else adapter
    # Owner decision 2026-10-27: a legacy state is switched to the all-on defaults once, before anything starts
    # (no upgrade review stage); a failure changes nothing and stops the runtime (ConfigError).
    from .owner_defaults import apply_legacy_upgrade
    apply_legacy_upgrade(args.data, args.product)
    store = ProductStore(args.data, args.product)
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    try:
        # The switch is read once per start: the boot guard and the runtime below see the same answer (plan 3.3).
        enabled = features.enabled(args.product)
        # HM-13b (plan 8.4; contract 1.2, 7; not gated): the boot guard, after the legacy migration and before any child
        # or listener: a restore, an unfinished "revoke all", dormant profiles. A product not switched on without
        # profile data is left alone (a restore's marker only gets its notice). ConfigError: nothing is served, the
        # next start runs it again.
        guarded = restore_lock.guard(store, args.product, enabled=enabled)
        # HM-13c (DQ-03 (b); not gated): the restore notice the guard left when a restore kept the default profile's
        # token, for the panel until the token changes. None (no notice: every installation never restored): nothing
        # below changes.
        found = restore_lock.read_notice(store.directory)
        notice = None if found is None else restore_lock.Notice(store.directory, found)
        if adapter.before_start is not None:
            adapter.before_start()  # HM-25: n8n's catalog copy, where apps/n8n/run.py made it before
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        options = dict(
            verify_admin=make_ha_admin_verifier(),
            management=ManagementOptions(kind="ha-addon", authority="ha-admin",
                                         product_version=version_for_product(args.product)),
            server_name='woow-mcp-' + args.product, instructions=INSTRUCTIONS.get(args.product),
            # 0.2.2: clients connect without a backend or a running child (Odoo Manage: unchanged)
            listing=listing(args.product) if args.product in FULL_PRODUCTS else None,
            # Headscale's secret URL is used by Claude.ai; other browser origins must not
            # acquire the Headscale API key's authority through a leaked link.
            secret_path_allowed_origins=(frozenset({"https://claude.ai"})
                                         if args.product == "headscale" else None))
        worker = None
        if enabled:
            # HM-08 (multi-profile plan 3.1, 5.1, 5.2; read at every start): every profile of the add-on. 8081 is the
            # token dispatcher (each profile's admission, byte budget, stream cap; 64 + 32 x the product's limit as
            # the outer bound when the open-file limit allows it), 8099 the default profile's management app with the
            # add-on's shared administration (HM-10 routes the others). HM-09 (plan 5.4): launch() below starts the
            # default profile's child as before; monitor() also starts the others (staggered) and runs every profile's
            # monitor, and only the default profile's ending stops the add-on (DQ-21); closing it stops every child at
            # once (HA's 30 s). HM-30 (plan 5.5): one reply worker processes every profile's replies, the profiles
            # taking turns; it starts before the listeners serve and stops after they stopped (the replies still queued
            # are answered at once, the one in process is waited for at most reply_worker.STOP_SECONDS), and should its
            # thread end while the add-on serves, the add-on stops, as for any other component (the Supervisor restarts
            # it).
            worker = ReplyWorker()
            profile = ProfileManager(store, args.product, adapter.tools, adapter.child_spec, port=child_port,
                                     app_options=options, reply_worker=worker, restore_notice=notice,
                                     prepare_child=adapter.prepare_child, profile_removed=adapter.profile_removed)
        else:
            # HM-05 (multi-profile plan 3.2): the default profile's runtime. It makes the child's Supervisor, client,
            # HealthMonitor and ConfigurationState and the two apps (make_apps with these product options) as this
            # function made them, and closes them in the same order (the client, then the child). No shared
            # administration: the apps make their own AdminAuthority and management slots, as before. HM-13b: dormant
            # profiles (profile data on disk) add their number to the bootstrap; without profile data, nothing changes.
            profile = ProfileRuntime(store, adapter.tools, adapter.child_spec, port=child_port, app_options=options,
                                     dormant_profiles=guarded.dormant, restore_notice=notice,
                                     prepare_child=(None if adapter.prepare_child is None else
                                                    lambda state: adapter.prepare_child('default', state)))
        async with profile:
            servers = [Listener(uvicorn.Config(app, host=args.host, port=port,
                proxy_headers=False, access_log=False, log_level='warning', server_header=False,
                lifespan='off', limit_concurrency=limit, timeout_keep_alive=5))
                for app, port, limit in ((profile.admin_app, args.admin_port, 64),
                                         (profile.mcp_app, args.mcp_port, profile.mcp_listener_limit))]
            # 0.1.12: /private_<token>/mcp puts the token in the request path. access_log stays False; every record
            # (uvicorn's error log, tracebacks, any library) is scrubbed to /private_[REDACTED]/ when created and
            # again by uvicorn's handlers.
            redact.install()
            redact.guard_handlers(*redact.UVICORN_LOGGERS)
            if worker is not None:
                worker.start()
            try:
                # launch() keeps authenticated management available to report/retry a
                # fixed launch failure; it never echoes third-party exception text.
                await profile.launch()
                tasks = [asyncio.create_task(server.serve()) for server in servers]
                monitor = asyncio.create_task(profile.monitor())
                stopping = asyncio.create_task(stop.wait())
                ended = None if worker is None else asyncio.create_task(worker.ended.wait())
                try:
                    done, _ = await asyncio.wait([*tasks, monitor, stopping, *([ended] if ended else [])],
                                                 return_when=asyncio.FIRST_COMPLETED)
                    if monitor in done or any(t in done for t in tasks) or ended in done:
                        raise RuntimeError('runtime component stopped') from None
                finally:
                    for server in servers:
                        server.should_exit = True
                    monitor.cancel()
                    stopping.cancel()
                    await asyncio.gather(monitor, stopping, return_exceptions=True)
                    try:
                        async with asyncio.timeout(5):
                            await asyncio.gather(*tasks)
                    except TimeoutError:
                        for task in tasks:
                            task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
                    if ended is not None:
                        ended.cancel()
                        await asyncio.gather(ended, return_exceptions=True)
            finally:
                if worker is not None:
                    await worker.stop()
    finally:
        store.close()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('product', choices=PRODUCTS)
    parser.add_argument('--data', type=Path, default=Path('/data/mcp'))
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--admin-port', type=int, default=8099)
    parser.add_argument('--mcp-port', type=int, default=8081)
    args = parser.parse_args()
    if args.admin_port == args.mcp_port or CHILD_PORT in (args.admin_port, args.mcp_port):
        parser.error(f'listeners must be distinct and cannot use child port {CHILD_PORT}')
    try:
        asyncio.run(run(args))
    except (ConfigError, RuntimeError):
        raise SystemExit('runtime unavailable; local recovery required') from None


if __name__ == '__main__':
    main()
