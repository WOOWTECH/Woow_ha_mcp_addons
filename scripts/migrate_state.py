#!/usr/bin/env python3
"""Source-checkout entrypoint; the production CLI lives in mcp_admin_core."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'packages/mcp-admin-core'))

from mcp_admin_core.migration import main

if __name__ == '__main__':
    raise SystemExit(main())
