"""Require real nonempty unit results, including no skipped external prerequisites."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

root = ET.fromstring(Path(sys.argv[1]).read_bytes())
cases = root.findall('.//testcase')
if not cases or any(case.find(tag) is not None for case in cases for tag in ('skipped', 'failure', 'error')):
    raise SystemExit('unit gate failed: empty, skipped, failed or errored tests')
print(f'PASS: {len(cases)} executed unit/integration cases, no skips')
