"""Offline checks for the triaged secret-pin allowlist fed to gitleaks. No scanner run here."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import unittest
from unittest.mock import patch

import supply_chain as s


class SecretTriageTests(unittest.TestCase):
    def test_config_is_default_rules_plus_exact_anchored_pins(self):
        config = s.gitleaks_config()
        self.assertTrue(config.startswith('[extend]\nuseDefault = true\n'))
        pattern = re.search(r"regexes = \['''(.*)'''\]", config).group(1)
        self.assertTrue(pattern.startswith('^(?:') and pattern.endswith(')$'))
        values = pattern[4:-2].split('|')
        self.assertEqual(values, sorted(set(s.triaged_pins()) | set(s.recorded_digests())))
        self.assertTrue(set(s.recorded_digests()) <= set(values))
        self.assertTrue(all(re.fullmatch(r'[0-9a-f]{64}', v) for v in values))
        compiled = re.compile(pattern)
        self.assertTrue(compiled.fullmatch(values[0]))
        for other in (values[0][:-1] + ('0' if values[0][-1] != '0' else '1'), values[0] + 'a',
                      'x' + values[0], 'ghp_' + 'a' * 36, ''):
            self.assertIsNone(compiled.fullmatch(other))
        self.assertNotIn('targetRules', config)  # observed: gitleaks 8.28.0 then ignores the allowlist

    def test_malformed_triage_fails_closed(self):
        good = json.loads((s.ROOT / 'packaging/secret-triage.json').read_text())
        bad_docs = [
            dict(good, schema=2),
            dict(good, requires_security_review=False),
            dict(good, values=[]),
            dict(good, values=good['values'] + [good['values'][0]]),
            dict(good, values=[dict(good['values'][0], sha256_pin='A' * 64)]),
            dict(good, values=[dict(good['values'][0], sha256_pin='.*')]),
            dict(good, values=[dict(good['values'][0], seen_in=[])]),
        ]
        for doc in bad_docs:
            with self.subTest(doc=str(doc)[:60]), patch.object(s, 'read_json', return_value=doc):
                with self.assertRaises(s.Closed):
                    s.gitleaks_config()

    def _fake_gitleaks(self, tmp, findings, stderr=True):
        tool = Path(tmp) / 'gitleaks'
        body = ('#!/usr/bin/python3\nimport json,sys\na=sys.argv\n'
                'open(a[a.index("--report-path")+1],"w").write(json.dumps(%r))\n' % findings)
        if stderr:
            body += 'print("leaks found", file=sys.stderr)\n'
        tool.write_text(body)
        tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
        return tool

    def test_image_scan_hash_matching_and_scrub(self):
        doc = json.loads((s.ROOT / 'packaging/secret-triage.json').read_text())
        approved_value, pending_value = 'example-approved-value', 'example-pending-value'
        doc['image_findings'] = {'entries': [
            {'rule': 'r1', 'secret_sha256': hashlib.sha256(approved_value.encode()).hexdigest(), 'seen': ['x'], 'approved': True},
            {'rule': 'r1', 'secret_sha256': hashlib.sha256(pending_value.encode()).hexdigest(), 'seen': ['y'], 'approved': False}]}
        cases = {'approved only': ([{'RuleID': 'r1', 'Secret': approved_value}], True),
                 'none': ([], True),
                 'pending': ([{'RuleID': 'r1', 'Secret': pending_value}], False),
                 'unknown': ([{'RuleID': 'r1', 'Secret': approved_value}, {'RuleID': 'r1', 'Secret': 'new'}], False),
                 'same value other rule': ([{'RuleID': 'r2', 'Secret': approved_value}], False)}
        real_read = s.read_json
        for name, (findings, passes) in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                private = Path(tmp)
                tool = self._fake_gitleaks(tmp, findings)
                with patch.object(s, 'read_json', side_effect=lambda path: doc if path.name == 'secret-triage.json' else real_read(path)):
                    if passes:
                        s.secret_scan(tool, 'dir', private, private, 'image', {'PATH': '/usr/bin:/bin'})
                    else:
                        with self.assertRaises(s.Closed):
                            s.secret_scan(tool, 'dir', private, private, 'image', {'PATH': '/usr/bin:/bin'})
                self.assertEqual((private / 'image.json').read_text(), '[]\n')  # raw values scrubbed

    def test_source_scan_stays_redacted_and_zero_tolerance(self):
        with tempfile.TemporaryDirectory() as tmp:
            # No stderr, so the only reason to close is the non-empty redacted report.
            tool = self._fake_gitleaks(tmp, [{'RuleID': 'r1', 'Secret': 'REDACTED'}], stderr=False)
            with self.assertRaises(s.Closed):
                s.secret_scan(tool, 'dir', Path(tmp), Path(tmp), 'source', {'PATH': '/usr/bin:/bin'})
            clean = self._fake_gitleaks(tmp, [], stderr=False)
            s.secret_scan(clean, 'dir', Path(tmp), Path(tmp), 'source', {'PATH': '/usr/bin:/bin'})

    def test_pending_entries_are_not_approved_in_repository(self):
        entries = json.loads((s.ROOT / 'packaging/secret-triage.json').read_text())['image_findings']['entries']
        self.assertTrue(entries)
        self.assertEqual(s.approved_image_findings(), {(e['rule'], e['secret_sha256']) for e in entries if e['approved'] is True})


if __name__ == '__main__':
    unittest.main()
