"""Bounded BT1 validation job; signals only its own launched process group."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('name')
    parser.add_argument('deadline', type=int)
    parser.add_argument('selection', nargs='+')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    reports = Path('/data/pi-agent/home/work/mcp-haos-team-runtime/reports')
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/tmp',
           'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1',
           'OWNED_UI_DIST': '/data/pi-agent/home/work/Woow_ha_mcp_addons/packages/mcp-admin-ui/dist'}
    command = [str(root/'.venv/bin/python'), '-m', 'pytest', '-vv', '-s', '-p',
               'no:cacheprovider', *args.selection, f'--junitxml={reports/args.name}.xml']
    record = {'cwd': str(root), 'argv': command, 'deadline_seconds': args.deadline,
              'start': datetime.now(timezone.utc).isoformat(), 'signals': []}
    path = reports/(args.name+'-job.json')
    def save():
        path.write_text(json.dumps(record, indent=2)+'\n')
    with (reports/(args.name+'.log')).open('wb') as log:
        process = subprocess.Popen(command, cwd=root, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        record.update(pid=process.pid, owned_pgid=process.pid)
        save()
        try:
            process.wait(timeout=args.deadline)
        except subprocess.TimeoutExpired:
            record['signals'].append('SIGINT')
            os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=25)
            except subprocess.TimeoutExpired:
                record['signals'].append('SIGKILL')
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        record.update(exit_code=process.returncode, reaped=True,
                      end=datetime.now(timezone.utc).isoformat())
        save()
    print(json.dumps(record, indent=2), flush=True)
    return process.returncode


if __name__ == '__main__':
    sys.exit(main())
