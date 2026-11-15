"""HM-09 probe for tests/test_extra_child_resources.py: an additional profile's child resources as the add-on user.

Root (the CI) can write any oom_score_adj and lower any nice value, so a proof run as root proves nothing (plan
§10.1, C4-SF-6). Run as root, this probe first writes its own oom_score_adj baseline (a privileged write, which also
sets the floor an unprivileged process cannot go below: what Docker does for an HA add-on, 200 by default), then
drops to uid and gid 10001 with no group and no capability, and only then starts the Supervisor. Run as any other
user, it runs as that user on the environment's baseline (and writes none).

Every module is imported here, at module level, before the drop: the checkout may not be readable by uid 10001 then
(a CI runner's home directory need not be open to other users). The interpreter running it must be readable by uid
10001 (the test copies one).

argv[1]: JSON {"baseline": int or null, "resources": {"oom_score_adj": int, "nice": int}, "work": a directory the
probe's user can write, "raise_nice": int (optional)}. raise_nice: the probe raises its own nice value by this much
before it starts the Supervisor (as its user: raising needs no privilege), so that "+5" and "set to 5" differ (HM-09
review S-5). Prints one JSON line: what the child saw itself (its oom_score_adj, nice value and uid), the
Supervisor's resource_state and status, the probe's own values (its nice value before and after raise_nice), and
every lifecycle WARNING written (no token here).
"""
import asyncio
import json
import logging
import os
from pathlib import Path
import sys

from mcp_admin_core.lifecycle import ChildLog, ChildResources, ChildSpec, LifecycleLog, Supervisor

CHILD = ("import json, os, sys, time\n"
         "values = {'oom_score_adj': int(open('/proc/self/oom_score_adj').read()),\n"
         "          'nice': os.getpriority(os.PRIO_PROCESS, 0), 'uid': os.getuid(), 'argv': sys.argv[1:]}\n"
         "open(sys.argv[1] + '.tmp', 'w').write(json.dumps(values))\n"
         "os.replace(sys.argv[1] + '.tmp', sys.argv[1])\n"
         "while True:\n    time.sleep(1)\n")


class Records(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


def own_oom():
    with open('/proc/self/oom_score_adj') as handle:
        return int(handle.read())


async def run(config, records):
    work = Path(config['work'])
    out = work / 'child.json'
    supervisor = Supervisor(ChildSpec((sys.executable, '-c', CHILD, str(out)), {'PATH': '/usr/bin:/bin'}, work),
                            grace=0.5, delays=(30,), resources=ChildResources(**config['resources']),
                            log=ChildLog(LifecycleLog(), 'a' * 24, 'aaaaaaaa', 18000))
    await supervisor.start()
    try:
        async with asyncio.timeout(20):
            while not out.exists() or supervisor.resource_state is None:
                await asyncio.sleep(0.02)
        return {'child': json.loads(out.read_text()), 'resource_state': supervisor.resource_state,
                'status': supervisor.status, 'probe': {'uid': os.getuid(), 'oom_score_adj': own_oom(),
                                                       'nice': os.getpriority(os.PRIO_PROCESS, 0),
                                                       'nice_before': config['nice_before']},
                'warnings': list(records.lines)}
    finally:
        await supervisor.stop()


def main():
    config = json.loads(sys.argv[1])
    if os.geteuid() == 0:
        if config['baseline'] is not None:
            fd = os.open('/proc/self/oom_score_adj', os.O_WRONLY)
            try:
                os.write(fd, str(config['baseline']).encode())
            finally:
                os.close(fd)
        os.setgroups([])
        os.setgid(10001)
        os.setuid(10001)
        assert os.getuid() == os.geteuid() == 10001 and os.getgid() == 10001
    config['nice_before'] = os.getpriority(os.PRIO_PROCESS, 0)
    if config.get('raise_nice'):
        os.nice(config['raise_nice'])
    records = Records()
    events = logging.getLogger('mcp_admin_core.lifecycle')
    events.addHandler(records)
    events.setLevel(logging.WARNING)
    print(json.dumps(asyncio.run(run(config, records))), flush=True)


if __name__ == '__main__':
    main()
