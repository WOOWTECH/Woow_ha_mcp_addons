"""Offline source-bundle tests on owned throwaway repositories. No network."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import source_bundle as s


def make_repo(root):
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(root), 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
           'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.invalid',
           'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@example.invalid'}
    repo = root / 'repo'
    run = lambda *a: subprocess.run(['git', *a], cwd=repo, env=env, check=True, capture_output=True, text=True).stdout
    repo.mkdir()
    run('init', '--quiet', '-b', 'main')
    shas = []
    for i in range(3):
        (repo / 'f.txt').write_text(str(i))
        run('add', 'f.txt')
        run('commit', '--quiet', '-m', str(i))
        shas.append(run('rev-parse', 'HEAD').strip())
    return repo, shas, run


class SourceBundleTests(unittest.TestCase):
    def test_roundtrip_binds_exact_commit_and_full_history(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo, shas, run = make_repo(root)
            receipt = s.create(repo, shas[1], root / 'out')
            self.assertEqual(receipt['commits'], 2)
            bundle = root / 'out' / receipt['bundle']
            self.assertEqual(bundle.stat().st_mode & 0o777, 0o600)
            self.assertEqual((root / 'out').stat().st_mode & 0o777, 0o700)
            s.verify(bundle, shas[1], root / 'out' / 'source-receipt.json', root / 'co')
            self.assertEqual((root / 'co' / 'f.txt').read_text(), '1')
            # The shared repository gained no refs.
            self.assertNotIn('candidate', run('for-each-ref', '--format=%(refname)'))

    def test_denials(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo, shas, _ = make_repo(root)
            for bad in ('', shas[0][:12], shas[0].upper(), 'g' * 40):
                with self.subTest(sha=bad), self.assertRaises(ValueError):
                    s.create(repo, bad, root / ('x' + str(len(bad))))
            receipt = s.create(repo, shas[2], root / 'out')
            with self.assertRaises(FileExistsError):
                s.create(repo, shas[2], root / 'out')
            bundle = root / 'out' / receipt['bundle']
            rpath = root / 'out' / 'source-receipt.json'
            with self.assertRaises(ValueError):
                s.verify(bundle, shas[1], rpath, root / 'co1')  # different commit than receipt
            tampered = root / 'out2'
            tampered.mkdir()
            data = bytearray(bundle.read_bytes())
            data[-1] ^= 1
            (tampered / receipt['bundle']).write_bytes(bytes(data))
            with self.assertRaisesRegex(ValueError, 'hash'):
                s.verify(tampered / receipt['bundle'], shas[2], rpath, root / 'co2')
            forged = dict(receipt, sha256=s.digest(tampered / receipt['bundle']))
            (tampered / 'r.json').write_text(json.dumps(forged))
            with self.assertRaises((ValueError, RuntimeError)):
                s.verify(tampered / receipt['bundle'], shas[2], tampered / 'r.json', root / 'co3')
            self.assertFalse((root / 'co1').exists())

    def test_extra_ref_bundle_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo, shas, run = make_repo(root)
            out = root / 'out'
            out.mkdir()
            bundle = out / ('woow-mcp-' + shas[2][:12] + '.bundle')
            run('update-ref', s.REF, shas[2])
            run('bundle', 'create', '--quiet', str(bundle), s.REF, 'main')
            receipt = {'commit': shas[2], 'ref': s.REF, 'bundle': bundle.name, 'sha256': s.digest(bundle)}
            (out / 'r.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, 'exactly'):
                s.verify(bundle, shas[2], out / 'r.json', root / 'co')


if __name__ == '__main__':
    unittest.main()
