"""check_release.py, the GitHub-hosted route's dispatch gate: fake Git only (no checkout, network or token)."""
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import check_release as r
import validate as v

BRANCH = 'refs/heads/release/six-products-0.4.14-20261117'
SHA = 'b' * 40


class ReleaseTests(unittest.TestCase):
    def invoke(self, app='n8n', *, event='workflow_dispatch', ref=BRANCH, sha=SHA, source=SHA, head=None,
               manifest=None, attempt='1'):
        """check_release.check(app) in a dispatched run; None leaves a variable unset. Returns (stdout, git calls,
        loaded paths)."""
        env = {key: value for key, value in (('GITHUB_EVENT_NAME', event), ('GITHUB_REF', ref), ('GITHUB_SHA', sha),
                                             ('SOURCE_SHA', source), ('GITHUB_RUN_ATTEMPT', attempt)) if value is not None}
        calls, loaded = [], []

        def output(command, **kwargs):
            calls.append(command)
            return (sha if head is None else head) + '\n'

        def load(path):
            loaded.append(Path(path))
            value = v.load(path)
            return value if manifest is None else {**value, 'version': manifest}
        with patch.dict(r.os.environ, env, clear=True), patch.object(r.subprocess, 'check_output', side_effect=output), \
             patch.object(r, 'load', side_effect=load), redirect_stdout(io.StringIO()) as printed:
            r.check(app)
        return printed.getvalue(), calls, loaded

    def test_every_imaged_product_passes_from_a_release_branch_at_the_owner_approved_commit(self):
        for app in v.PRODUCTS:
            if app in r.IMAGELESS:
                continue
            with self.subTest(app=app):
                printed, calls, loaded = self.invoke(app)
                self.assertIn(f'PASS: {app} {v.version_for(app)} from {BRANCH}', printed)
                self.assertEqual(calls, [['git', 'rev-parse', 'HEAD']])
                self.assertEqual(loaded, [v.ROOT / 'addons' / app / 'config.yaml'])

    def test_only_a_manual_dispatch_of_a_release_branch(self):
        for event in ('push', 'pull_request', 'pull_request_target', 'workflow_run', 'schedule', 'release', '', None):
            with self.subTest(event=event), self.assertRaisesRegex(v.Invalid, 'manual event required'):
                self.invoke(event=event)
        for ref in ('refs/heads/main', 'refs/heads/claude-delivery', 'refs/heads/release', 'refs/heads/release/',
                    'refs/heads/releases/0.4.14', 'refs/heads/feature/release/0.4.14', 'refs/heads/xrelease/0.4.14',
                    'refs/heads/release/a/b', 'refs/heads/release/-x', 'refs/heads/release/x y',
                    'refs/heads/release/x\n', 'refs/tags/release/0.4.14', 'refs/tags/v0.4.14', 'refs/pull/119/merge',
                    'refs/pull/119/head', 'release/0.4.14', 'REFS/HEADS/RELEASE/X', '', None):
            with self.subTest(ref=ref), self.assertRaisesRegex(v.Invalid, 'release/\\* branch'):
                self.invoke(ref=ref)
        # The deployment-branch rule release/* of the public-release environment matches one path segment.
        self.assertEqual([bool(r.RELEASE_BRANCH.fullmatch(ref)) for ref in (
            'refs/heads/release/six-products-0.4.14-20261117', 'refs/heads/release/0.4.14', 'refs/heads/release/a_b.c')],
            [True, True, True])

    def test_source_sha_binds_the_exact_dispatched_commit(self):
        cases = [({'source': None}, 'source_sha must be'), ({'source': ''}, 'source_sha must be'),
                 ({'source': SHA[:7]}, 'source_sha must be'), ({'source': SHA.upper()}, 'source_sha must be'),
                 ({'source': SHA + '\n'}, 'source_sha must be'), ({'source': ' ' + SHA}, 'source_sha must be'),
                 ({'source': 'g' * 40}, 'source_sha must be'),
                 ({'source': 'c' * 40}, 'not the commit this run was dispatched at'),
                 ({'sha': None}, 'dispatched SHA'), ({'sha': 'b' * 39}, 'dispatched SHA'),
                 ({'head': 'c' * 40}, 'checkout differs'), ({'head': ''}, 'checkout differs')]
        for kwargs, message in cases:
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(v.Invalid, message):
                self.invoke(**kwargs)

    def test_a_re_run_is_refused_in_every_job(self):
        # A re-run reuses the original commit and inputs, and an approval binds one attempt: dispatch anew instead.
        for attempt in ('2', '3', '', None, '01', ' 1', '1 '):
            with self.subTest(attempt=attempt), self.assertRaisesRegex(v.Invalid, 're-run'):
                self.invoke(attempt=attempt)

    def test_imageless_retired_and_unknown_products_are_refused_before_anything_else(self):
        self.assertEqual(r.IMAGELESS, ('opendesign',))
        for app, message in (('opendesign', 'no image'), ('odoo-manage', 'not allowed'), ('unknown', 'not allowed'),
                             ('../../other', 'not allowed'), ('', 'not allowed')):
            with self.subTest(app=app), self.assertRaisesRegex(v.Invalid, message):
                self.invoke(app, event=None, ref=None, sha=None, source=None)

    def test_the_manifest_version_is_the_release_version(self):
        for app in ('odoo', 'headscale'):
            others = {v.VERSION, *v.VERSION_OVERRIDES.values(), '99.0.0'} - {v.version_for(app)}
            for other in sorted(others):
                with self.subTest(app=app, other=other), self.assertRaisesRegex(v.Invalid, 'manifest version'):
                    self.invoke(app, manifest=other)

    def test_release_gates_file_is_not_a_release_input_any_more(self):
        _, _, loaded = self.invoke('emqx')
        self.assertNotIn(v.ROOT / 'RELEASE-GATES.json', loaded)
        self.assertNotIn('RELEASE-GATES', Path(r.__file__).read_text().split('"""', 2)[2])

    def test_cli_fails_closed_with_one_line(self):
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith('GITHUB_') and key not in ('SOURCE_SHA', 'PYTHONPATH', 'PYTHONSAFEPATH')}
        script = str(Path(r.__file__).resolve())
        for argv, message in (([], 'product required'), (['n8n'], 'manual event required'),
                              (['opendesign'], 'product has no image to publish')):
            with self.subTest(argv=argv):
                result = subprocess.run([sys.executable, '-B', script, *argv], env=environment, capture_output=True,
                                        text=True, timeout=60)
                self.assertEqual((result.returncode, result.stdout, result.stderr), (1, '', message + '\n'))


if __name__ == '__main__':
    unittest.main()
