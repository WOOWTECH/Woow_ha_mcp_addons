"""Publication gate negatives/positive use only fake Git and owned evidence files."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import check_release as r
import validate as v


class ReleaseTests(unittest.TestCase):
    def gates(self):
        gates = v.load(v.ROOT / 'RELEASE-GATES.json')
        gates['approved_commit'] = 'a' * 40
        for gate in [gates[k] for k in ('source', 'license', 'secret', 'publisher')]:
            gate.update(cleared=True, evidence='docs/operations/evidence/review.md')
        for product in gates['products'].values():
            for gate in product.values():
                gate.update(cleared=True, evidence='docs/operations/evidence/review.md')
        return gates

    def invoke(self, gates, *, app='n8n', event='workflow_dispatch', ref='refs/heads/main', changes='RELEASE-GATES.json\n', head=None, ancestor=0):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / 'docs/operations/evidence/review.md'
            evidence.parent.mkdir(parents=True)
            evidence.write_text('invented evidence only for isolated gate tests\n' * 4)
            def output(command, **kwargs):
                return (head or 'b' * 40) + '\n' if command[1] == 'rev-parse' else changes
            def result(command, **kwargs):
                return type('Result', (), {'returncode': ancestor if command[1] == 'merge-base' else 0})()
            with patch.object(r, 'ROOT', root), patch.object(r, 'load', return_value=gates), \
                 patch.dict(r.os.environ, {'GITHUB_EVENT_NAME': event, 'GITHUB_REF': ref, 'GITHUB_SHA': 'b' * 40}, clear=True), \
                 patch.object(r.subprocess, 'check_output', side_effect=output), \
                 patch.object(r.subprocess, 'run', side_effect=result):
                with redirect_stdout(io.StringIO()):
                    r.check(app)

    def test_fully_cleared_reviewed_source_fixture(self):
        self.invoke(self.gates())

    def test_all_six_independent_gates_required(self):
        for key in ('source', 'license', 'secret', 'publisher', 'image', 'ha'):
            gates = self.gates()
            gate = gates[key] if key in gates else gates['products']['n8n'][key]
            gate['cleared'] = False
            with self.subTest(key=key), self.assertRaises(v.Invalid):
                self.invoke(gates)

    def test_source_event_ref_and_allowlist(self):
        for kwargs in ({'event': 'pull_request'}, {'ref': 'refs/heads/feature'},
                       {'app': '../../other'}, {'changes': 'apps/n8n/run.py\n'},
                       {'head': 'c' * 40}, {'ancestor': 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(v.Invalid):
                self.invoke(self.gates(), **kwargs)

    def test_unapproved_source(self):
        gates = self.gates()
        gates['approved_commit'] = None
        with self.assertRaises(v.Invalid):
            self.invoke(gates)


if __name__ == '__main__':
    unittest.main()
