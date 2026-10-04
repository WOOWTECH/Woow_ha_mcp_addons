"""Only invented bytes are copied/hashed; no real binary or network is used."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import builder_binary as binary


class BuilderBinaryTests(unittest.TestCase):
    def test_published_pin_is_fixed_not_an_environment_input(self):
        self.assertEqual(binary.SHA256,
            '696bc104bac3bb708eff1af3f8bbc09fda0fd88f5757c1f9b404a35117889224')

    def test_bad_bytes_never_become_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'mock-source'
            source.write_bytes(b'MOCK ONLY - not Buildx')
            target = root / 'docker'
            target.mkdir()
            with patch.object(binary, 'SOURCE', source), self.assertRaises(ValueError):
                binary.install(target)
            self.assertFalse((target / 'cli-plugins/docker-buildx').exists())

    def test_hash_then_private_copy_and_recheck_no_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'mock-source'
            data = b'MOCK ONLY - cannot execute'
            source.write_bytes(data)
            target = root / 'docker'
            target.mkdir()
            with patch.object(binary, 'SOURCE', source), patch.object(binary, 'SHA256', hashlib.sha256(data).hexdigest()):
                binary.install(target)
                plugin = target / 'cli-plugins/docker-buildx'
                self.assertEqual(plugin.read_bytes(), data)
                self.assertEqual(plugin.stat().st_mode & 0o777, 0o500)
                binary.verify(target)
                plugin.chmod(0o600)
                plugin.write_bytes(b'changed')
                with self.assertRaises(ValueError):
                    binary.verify(target)

    def test_symlink_source_is_not_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'mock-source'
            source.symlink_to(root / 'invented-missing-target')
            with patch.object(binary, 'SOURCE', source), self.assertRaises((OSError, ValueError)):
                binary.install(root)


if __name__ == '__main__':
    unittest.main()
