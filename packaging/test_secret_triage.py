"""Offline checks for the triaged secret-pin allowlist fed to gitleaks. No scanner run here."""
import json
import re
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
        self.assertEqual(values, s.triaged_pins())
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


if __name__ == '__main__':
    unittest.main()
