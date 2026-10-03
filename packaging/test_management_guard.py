"""Actual Linux bootstrap -> final exec -> same-UID hostile child; invented token only."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import management_launcher as management

ROOT = Path(__file__).resolve().parents[1]
CHILD = r'''
import ctypes, errno, os
assert 'SUPERVISOR_TOKEN' not in os.environ
pid = os.getppid()
assert os.getuid() == int(__import__('sys').argv[2])
for name in ('environ', 'mem'):
    try:
        fd = os.open('/proc/%d/%s' % (pid, name), os.O_RDONLY)
    except OSError as e:
        assert e.errno in (errno.EACCES, errno.EPERM)
    else:
        os.close(fd)
        raise AssertionError('parent procfs readable: ' + name)
class IOVec(ctypes.Structure):
    _fields_ = [('base', ctypes.c_void_p), ('length', ctypes.c_size_t)]
buf = ctypes.create_string_buffer(64)
local = IOVec(ctypes.addressof(buf), 64)
remote = IOVec(int(__import__('sys').argv[1]), 64)
libc = ctypes.CDLL(None, use_errno=True)
assert libc.process_vm_readv(pid, ctypes.byref(local), 1, ctypes.byref(remote), 1, 0) == -1
assert ctypes.get_errno() in (errno.EACCES, errno.EPERM)
'''


class GuardTests(unittest.TestCase):
    def test_guard_failure_never_enters_core(self):
        with patch.object(management.sys, 'argv', ['management_launcher.py', 'n8n']), \
             patch.object(management.os, 'geteuid', return_value=10001), \
             patch.object(management, 'guard', side_effect=RuntimeError('denied')), \
             patch.object(management.runpy, 'run_path') as core:
            with self.assertRaises(RuntimeError):
                management.main()
            core.assert_not_called()

    def test_actual_post_exec_guard(self):
        # CI may be nonroot; exercise actual drop when root, otherwise current UID.
        uid, gid = (10001, 10001) if os.getuid() == 0 else (os.getuid(), os.getgid())
        with tempfile.TemporaryDirectory(prefix='packaging-guard-') as d:
            root = Path(d)
            root.chmod(0o755)
            for name in ('.venv/bin', 'apps/n8n', 'data', 'packaging'):
                (root / name).mkdir(parents=True)
            (root / '.venv/bin/python').symlink_to('/usr/bin/python3')
            wrapper = ROOT / 'packaging/management_launcher.py'
            if wrapper.exists():
                shutil.copyfile(wrapper, root / 'packaging/management_launcher.py')
            (root / 'apps/n8n/run.py').write_text(
                'import ctypes,os,resource,subprocess\n'
                "assert os.environ['SUPERVISOR_TOKEN']=='INVENTED-GUARD-ONLY'\n"
                'assert ctypes.CDLL(None).prctl(3,0,0,0,0)==0, "post-exec management dumpable"\n'
                'assert resource.getrlimit(resource.RLIMIT_CORE)==(0,0)\n'
                'assert ctypes.CDLL(None).prctl(39,0,0,0,0)==1\n'
                'secret=ctypes.create_string_buffer(b"INVENTED-GUARD-ONLY")\n'
                f'subprocess.run(["/usr/bin/python3","-c",{CHILD!r},str(ctypes.addressof(secret)),str(os.getuid())],'
                'env={"PATH":"/usr/bin:/bin"},start_new_session=True,check=True)\n')
            launcher = (
                'import importlib.util,pathlib,sys; '
                f's=importlib.util.spec_from_file_location("entry",{str(ROOT / "packaging/entrypoint.py")!r}); '
                'e=importlib.util.module_from_spec(s); s.loader.exec_module(e); '
                f'e.ROOT=pathlib.Path({d!r}); e.UID={uid}; e.GID={gid}; '
                'original=e.prepare_data; e.prepare_data=lambda:original(e.ROOT/"data"); '
                'sys.argv=["entrypoint.py","n8n"]; e.main()')
            result = subprocess.run(['/usr/bin/python3', '-c', launcher],
                env={'PATH': '/usr/bin:/bin', 'SUPERVISOR_TOKEN': 'INVENTED-GUARD-ONLY',
                     'PYTHONDONTWRITEBYTECODE': '1'}, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_linux_control_unguarded_same_uid_environ_is_readable(self):
        code = ('import os,subprocess; '
                'subprocess.run(["/usr/bin/python3","-c",'
                '"import os,pathlib; assert \'SUPERVISOR_TOKEN\' not in os.environ; '
                'assert b\'SUPERVISOR_TOKEN=INVENTED-GUARD-ONLY\' in pathlib.Path(\'/proc/\'+str(os.getppid())+\'/environ\').read_bytes()"],'
                'env={"PATH":"/usr/bin:/bin"},check=True)')
        def drop():
            if os.getuid() == 0:
                os.setgroups([])
                os.setgid(10001)
                os.setuid(10001)
        result = subprocess.run(['/usr/bin/python3', '-c', code], preexec_fn=drop,
            env={'PATH': '/usr/bin:/bin', 'SUPERVISOR_TOKEN': 'INVENTED-GUARD-ONLY'},
            capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode())


if __name__ == '__main__':
    unittest.main()
