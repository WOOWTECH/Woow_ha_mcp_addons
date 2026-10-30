"""Run the ported HTTP-contract cases with the pinned app SDK, without root deps changes."""
import os
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_pinned_hermes_session_contract_cases():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    # Read-only reuse of the root test runner libraries; MCP comes from the app venv.
    env['PYTHONPATH'] = os.pathsep.join(map(str, [
        ROOT / 'apps/hermes/vendor', ROOT / 'apps/runtime', Path(pytest.__file__).parents[1],
    ]))
    with tempfile.TemporaryDirectory(prefix='ha-hermes-session-contract-') as temp:
        report = Path(temp) / 'junit.xml'
        result = subprocess.run([
            str(ROOT / 'apps/hermes/.venv/bin/python'), '-m', 'pytest', '-q',
            '--noconftest', '-c', '/dev/null', '-p', 'no:cacheprovider',
            '--rootdir', temp, '--basetemp', str(Path(temp) / 'pytest'),
            '--junitxml', str(report),
            str(ROOT / 'tests/helpers/hermes_session_contract_cases.py'),
        ], env=env, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
        cases = ET.parse(report).findall('.//testcase')
        assert len(cases) >= 28, result.stdout
        assert not any(case.find('skipped') is not None for case in cases), result.stdout
