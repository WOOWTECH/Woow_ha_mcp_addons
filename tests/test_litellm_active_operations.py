"""Run native callbacks in the existing pinned child SDK, not the core venv."""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_native_active_operation_contract():
    # Override is test-only, for an existing equivalent SDK environment during
    # source review. CI uses the app environment installed by packaging/unit.sh.
    python = os.environ.get("LITELLM_TEST_PYTHON", str(ROOT / "apps/litellm/.venv/bin/python"))
    result = subprocess.run(
        [python, "-B", str(ROOT / "tests/litellm_active_contract.py")],
        cwd=ROOT, env={"PATH": "/usr/bin:/bin", "FASTMCP_CHECK_FOR_UPDATES": "off"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["passed_cases"] == 27
