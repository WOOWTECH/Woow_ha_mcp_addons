"""Bounded ownership-visibility probe, not a replacement joined runtime test."""
import asyncio
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys

from mcp_admin_core.lifecycle import ChildSpec
from mcp_admin_core.child_identity import inspect_listener
from owned_executable import serve_proofs
from owned_network import install, install_subprocess_guard
from owned_runtime import Endpoint

install()
install_subprocess_guard()
config = json.loads(sys.argv[1])
root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('actual_guard', root/'packaging/management_launcher.py')
management = importlib.util.module_from_spec(spec)
spec.loader.exec_module(management)


async def main():
    endpoint = Endpoint(port=config['child_port'])
    code = ('import ctypes,socket,time; assert ctypes.CDLL(None).prctl(3,0,0,0,0)==1; s=socket.socket(); '
            f's.bind(("127.0.0.1", {endpoint.port})); s.listen(); time.sleep(30)')
    manager = endpoint.supervisor(ChildSpec(('/usr/bin/python3', '-c', code), {'PATH':'/usr/bin:/bin'}, Path('/tmp')), prepared=True)
    with socket.socket() as public:
        public.bind(('127.0.0.1', config['public_ports'][0]))
        public.listen()
        ipc = serve_proofs(config, endpoint)
        try:
            await manager.start()
            assert ctypes.CDLL(None).prctl(3, 0, 0, 0, 0) == 0
            # Real uid 10001, non-dumpable manager, actual exec'd dumpable child.
            for _ in range(200):
                identity = await asyncio.to_thread(inspect_listener, manager.process.pid, endpoint.port)
                if identity == 'owned':
                    break
                await asyncio.sleep(.025)
            assert identity == 'owned', identity
            # Same-UID target that intentionally disables dumping must degrade, never claim mismatch.
            code = ('import ctypes,socket,sys; s=socket.socket(); '
                    's.bind(("127.0.0.1",0)); s.listen(); '
                    'assert ctypes.CDLL(None).prctl(4,0,0,0,0)==0; '
                    'print(s.getsockname()[1],flush=True); sys.stdin.readline()')
            hidden = await asyncio.create_subprocess_exec('/usr/bin/python3', '-c', code,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
            try:
                hidden_port = int(await asyncio.wait_for(hidden.stdout.readline(), 5))
                assert inspect_listener(hidden.pid, hidden_port) == 'unavailable'
            finally:
                hidden.stdin.write(b'\n')
                await hidden.stdin.drain()
                await asyncio.wait_for(hidden.wait(), 5)
            print('OWNED_UID_PROOF_READY', flush=True)
            await asyncio.to_thread(sys.stdin.readline)
        finally:
            await manager.stop()
            endpoint.close()
            ipc.close()


if __name__ == '__main__':
    os.setgroups([])
    os.setgid(10001)
    os.setuid(10001)
    management.guard()  # real nondumpable/no_new_privs/core-limit guard
    assert os.getuid() == 10001 and ctypes.CDLL(None).prctl(3, 0, 0, 0, 0) == 0
    asyncio.run(main())
