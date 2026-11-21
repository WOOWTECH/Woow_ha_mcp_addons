"""n8n executable with the approved fixed-query HA administrator-role provider.

Run with PYTHONPATH=packages/mcp-admin-core:apps/n8n .venv/bin/python apps/n8n/run.py
Deployment options are listener addresses/ports and the dedicated state directory,
never backend credentials, tool policy, tokens or arbitrary child commands.

HM-25 (multi-profile plan 9 n8n row, 12.3 HM-25; unreleased): n8n's runtime is run_product's (run_product.run with
the n8n adapter: n8n_adapter's tools and child spec, the default profile's catalog copy before the profile's runtime is
made, an additional profile's own copy before its child starts, the copy removed with the profile). Switched off it
serves the default profile's lone ProfileRuntime, as every other product, answer for answer what this file built
itself before (HM-01's golden regression); switched on (only n8n's upgrade PR switches it on) the ProfileManager.
"""
import argparse
import asyncio
from pathlib import Path
from types import SimpleNamespace

from mcp_admin_core import run_product
from mcp_admin_core.config import ConfigError
from mcp_admin_core.lifecycle import CHILD_PORT
from n8n_adapter import TOOLS, child_spec, prepare_child, remove_profile_catalog


async def run(args, *, child_port=CHILD_PORT):
    # HM-04: one port for the child's spec (PORT), the health monitor, the gateway and its capability probe. main()
    # runs the default profile's child on CHILD_PORT; an extra profile's runtime (multi-profile plan 5.4) passes its own.
    # The adapter's names are looked up here, at each start (tests replace them in this module).
    async def prepare(profile_id, state):
        await prepare_child(profile_id, state, root=args.data)
    adapter = run_product.ProductAdapter(TOOLS, child_spec, prepare_child=prepare,
                                         profile_removed=remove_profile_catalog)
    await run_product.run(SimpleNamespace(**{**vars(args), 'product': 'n8n'}), child_port=child_port, adapter=adapter)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("/data/mcp"))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--admin-port", type=int, default=8099)
    parser.add_argument("--mcp-port", type=int, default=8081)
    args = parser.parse_args()
    if args.admin_port == args.mcp_port or CHILD_PORT in (args.admin_port, args.mcp_port):
        parser.error(f"listeners must be distinct and cannot use child port {CHILD_PORT}")
    try:
        asyncio.run(run(args))
    except (ConfigError, RuntimeError):
        # Never stringify third-party/config exceptions: they may contain secrets.
        raise SystemExit("runtime unavailable; local recovery required") from None


if __name__ == "__main__":
    main()
