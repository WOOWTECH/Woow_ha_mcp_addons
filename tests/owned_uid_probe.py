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
    code = ('import socket,time; s=socket.socket(); '
            f's.bind(("127.0.0.1", {endpoint.port})); s.listen(); time.sleep(30)')
    manager = endpoint.supervisor(ChildSpec(('/usr/bin/python3', '-c', code), {'PATH':'/usr/bin:/bin'}, Path('/tmp')), prepared=True)
    with socket.socket() as public:
        public.bind(('127.0.0.1', config['public_ports'][0]))
        public.listen()
        ipc = serve_proofs(config, endpoint)
        try:
            await manager.start()
            assert ctypes.CDLL(None).prctl(3, 0, 0, 0, 0) == 0
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
