"""environment_gate.py with owned fake GitHub API answers: no network, token or real run."""
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

import environment_gate as g

OWNER = {'login': 'WOOWTECH', 'id': g.OWNER_ID, 'type': 'User'}
BASE = '/repos/WOOWTECH/Woow_ha_mcp_addons/environments/public-release'
ENVIRONMENT = {
    'id': 1, 'node_id': 'EN_x', 'name': 'public-release', 'url': 'https://api.github.com' + BASE,
    'created_at': '2026-11-18T00:00:00Z', 'updated_at': '2026-11-18T00:05:00Z', 'can_admins_bypass': False,
    'protection_rules': [{'id': 2, 'node_id': 'GA_y', 'type': 'required_reviewers', 'prevent_self_review': False,
                          'reviewers': [{'type': 'User', 'reviewer': OWNER}]},
                         {'id': 3, 'node_id': 'GA_z', 'type': 'branch_policy'}],
    'deployment_branch_policy': {'protected_branches': False, 'custom_branch_policies': True}}
POLICIES = {'total_count': 1, 'branch_policies': [{'id': 4, 'node_id': 'MD_w', 'name': 'release/*', 'type': 'branch'}]}
APPROVAL = {'environments': [{'id': 1, 'name': 'public-release'}], 'state': 'approved', 'user': OWNER, 'comment': 'odoo ok'}
RUN_ENV = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'WOOWTECH/Woow_ha_mcp_addons', 'GH_TOKEN': 'invented-token-not-real',
           'GITHUB_RUN_ID': '123456789', 'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_SHA': 'b' * 40,
           'GITHUB_REF': 'refs/heads/release/six-products-0.4.14-20261117', 'GITHUB_ACTOR': 'WOOWTECH',
           'GITHUB_TRIGGERING_ACTOR': 'WOOWTECH'}


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def error(code, retry_after=None):
    headers = {'Retry-After': str(retry_after)} if retry_after is not None else {}
    return urllib.error.HTTPError('https://api.github.com/x', code, 'invented', headers, io.BytesIO(b'{}'))


class FakeAPI:
    """Answers by path; a value that is an exception (or a list of answers, consumed in order) is raised/returned."""

    def __init__(self, environment=ENVIRONMENT, policies=POLICIES, approvals=(APPROVAL,), **extra):
        self.answers = {BASE: environment, BASE + '/deployment-branch-policies': policies,
                        '/repos/WOOWTECH/Woow_ha_mcp_addons/actions/runs/123456789/approvals': list(approvals), **extra}
        self.calls = []

    def __call__(self, url, headers):
        self.calls.append((url, dict(headers)))
        path = url[len(g.API):]
        answer = self.answers[path]
        if isinstance(answer, tuple):  # a sequence of answers for retries
            answer, rest = answer[0], answer[1:]
            self.answers[path] = rest if len(rest) > 1 else rest[0]
        if isinstance(answer, BaseException):
            raise answer
        return Response(answer if isinstance(answer, bytes) else json.dumps(answer).encode())


class EnvironmentGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.record = Path(self.temporary.name) / 'publish-evidence' / 'approval.json'

    def tearDown(self):
        self.temporary.cleanup()

    def gate(self, api, mode='gate', env=None):
        sleeps = []
        argv = ['gate'] if mode == 'gate' else ['publish', str(self.record)]
        with patch.object(g, 'request', side_effect=api):
            result = g.main(argv, env=RUN_ENV if env is None else env, sleep=sleeps.append)
        return result, sleeps

    def test_the_protected_environment_passes_and_the_token_is_only_a_header(self):
        api = FakeAPI()
        facts, sleeps = self.gate(api)
        self.assertEqual((facts['name'], facts['can_admins_bypass'], facts['prevent_self_review'], facts['updated_at']),
                         ('public-release', False, False, '2026-11-18T00:05:00Z'))
        self.assertEqual(facts['reviewers'], [{'type': 'User', 'id': g.OWNER_ID, 'login': 'WOOWTECH'}])
        self.assertEqual(sleeps, [])
        self.assertEqual([url for url, _ in api.calls], ['https://api.github.com' + BASE,
                                                         'https://api.github.com' + BASE + '/deployment-branch-policies'])
        for _, headers in api.calls:
            self.assertEqual(headers['Authorization'], 'Bearer invented-token-not-real')
            self.assertEqual(headers['X-GitHub-Api-Version'], '2022-11-28')

    def test_every_missing_or_loose_setting_fails(self):
        def env_with(**changes):
            value = copy.deepcopy(ENVIRONMENT)
            value.update(changes)
            return value

        def reviewers(*entries, prevent=False):
            return [{'id': 2, 'type': 'required_reviewers', 'prevent_self_review': prevent, 'reviewers': list(entries)},
                    {'id': 3, 'type': 'branch_policy'}]
        cases = {
            'missing environment (404)': FakeAPI(environment=error(404)),
            'another name': FakeAPI(environment=env_with(name='release')),
            'no reviewer rule': FakeAPI(environment=env_with(protection_rules=[{'id': 3, 'type': 'branch_policy'}])),
            'no reviewers': FakeAPI(environment=env_with(protection_rules=reviewers())),
            'another reviewer': FakeAPI(environment=env_with(protection_rules=reviewers(
                {'type': 'User', 'reviewer': {'login': 'someone', 'id': 1}}))),
            'the owner by name only': FakeAPI(environment=env_with(protection_rules=reviewers(
                {'type': 'User', 'reviewer': {'login': 'WOOWTECH', 'id': 2}}))),
            'the owner id as text': FakeAPI(environment=env_with(protection_rules=reviewers(
                {'type': 'User', 'reviewer': {'login': 'WOOWTECH', 'id': str(g.OWNER_ID)}}))),
            'a team with the owner id': FakeAPI(environment=env_with(protection_rules=reviewers(
                {'type': 'Team', 'reviewer': {'name': 'x', 'id': g.OWNER_ID}}))),
            'a second reviewer': FakeAPI(environment=env_with(protection_rules=reviewers(
                {'type': 'User', 'reviewer': OWNER}, {'type': 'User', 'reviewer': {'login': 'other', 'id': 5}}))),
            'two reviewer rules': FakeAPI(environment=env_with(protection_rules=reviewers(
                {'type': 'User', 'reviewer': OWNER}) + [{'id': 9, 'type': 'required_reviewers',
                                                          'reviewers': [{'type': 'User', 'reviewer': OWNER}]}])),
            'an unknown rule type': FakeAPI(environment=env_with(protection_rules=reviewers(
                {'type': 'User', 'reviewer': OWNER}) + [{'id': 9, 'type': 'custom_protection_rule'}])),
            'administrators can bypass': FakeAPI(environment=env_with(can_admins_bypass=True)),
            'bypass field missing': FakeAPI(environment={k: v for k, v in ENVIRONMENT.items() if k != 'can_admins_bypass'}),
            'bypass as 0': FakeAPI(environment=env_with(can_admins_bypass=0)),
            'branch policy null': FakeAPI(environment=env_with(deployment_branch_policy=None)),
            'protected branches': FakeAPI(environment=env_with(deployment_branch_policy={
                'protected_branches': True, 'custom_branch_policies': False})),
            'policy flags as numbers': FakeAPI(environment=env_with(deployment_branch_policy={
                'protected_branches': 0, 'custom_branch_policies': 1})),
            'a second branch policy': FakeAPI(policies={'total_count': 2, 'branch_policies': [
                POLICIES['branch_policies'][0], {'id': 5, 'name': 'main', 'type': 'branch'}]}),
            'a tag policy': FakeAPI(policies={'total_count': 1, 'branch_policies': [{'id': 4, 'name': 'release/*', 'type': 'tag'}]}),
            'another pattern': FakeAPI(policies={'total_count': 1, 'branch_policies': [{'id': 4, 'name': 'release/**', 'type': 'branch'}]}),
            'no branch policies': FakeAPI(policies={'total_count': 0, 'branch_policies': []}),
            'policies not found': FakeAPI(policies=error(404)),
            'a redirect': FakeAPI(environment=error(301)),
            'an unauthorized token': FakeAPI(environment=error(401)),
        }
        for name, api in cases.items():
            with self.subTest(name), self.assertRaises(g.Closed):
                self.gate(api)
        with self.assertRaisesRegex(g.Closed, 'GitHub creates an unprotected one'):
            self.gate(FakeAPI(environment=error(404)))

    def test_prevent_self_review_and_a_wait_timer_are_recorded_not_required(self):
        value = copy.deepcopy(ENVIRONMENT)
        value['protection_rules'][0]['prevent_self_review'] = True
        value['protection_rules'].append({'id': 7, 'type': 'wait_timer', 'wait_timer': 5})
        facts, _ = self.gate(FakeAPI(environment=value))
        self.assertEqual((facts['prevent_self_review'], facts['wait_timer']), (True, 5))

    def test_rate_limits_and_network_errors_are_retried_once_then_fail(self):
        api = FakeAPI(environment=(error(429, retry_after=7), ENVIRONMENT))
        _, sleeps = self.gate(api)
        self.assertEqual(sleeps, [7])
        api = FakeAPI(environment=(error(403, retry_after=600), ENVIRONMENT))
        _, sleeps = self.gate(api)
        self.assertEqual(sleeps, [60])  # Retry-After is capped at 60 seconds
        api = FakeAPI(environment=(urllib.error.URLError('invented outage'), ENVIRONMENT))
        _, sleeps = self.gate(api)
        self.assertEqual(sleeps, [5])
        for first, second in ((error(429), error(429)), (error(403), error(500)),
                              (urllib.error.URLError('x'), OSError('y')), (error(502), error(503))):
            api = FakeAPI(environment=(first, second))
            with self.subTest(first=first, second=second), self.assertRaisesRegex(g.Closed, 'twice'):
                self.gate(api)
            self.assertEqual(len(api.calls), 2)
        api = FakeAPI(environment=b'not json')
        with self.assertRaisesRegex(g.Closed, 'not JSON'):
            self.gate(api)
        self.assertEqual(len(api.calls), 1)  # a bad answer is not retried
        with self.assertRaisesRegex(g.Closed, 'too large'):
            self.gate(FakeAPI(environment=b'"' + b'x' * g.MAX_BODY + b'"'))

    def test_publish_needs_the_owners_approval_of_this_first_attempt(self):
        record, _ = self.gate(FakeAPI(), mode='publish')
        saved = json.loads(self.record.read_text())
        self.assertEqual(saved, record)
        self.assertEqual(saved['run'], {'id': 123456789, 'attempt': 1, 'sha': 'b' * 40,
                                        'ref': 'refs/heads/release/six-products-0.4.14-20261117', 'actor': 'WOOWTECH',
                                        'triggering_actor': 'WOOWTECH'})
        self.assertEqual(saved['reviews'], [{'state': 'approved', 'environments': ['public-release'],
                                             'user': {'login': 'WOOWTECH', 'id': g.OWNER_ID}, 'comment': 'odoo ok'}])
        self.assertEqual(self.record.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.record.parent.stat().st_mode & 0o777, 0o700)
        self.assertNotIn('invented-token-not-real', self.record.read_text())
        other = {**APPROVAL, 'user': {'login': 'someone', 'id': 1}}
        cases = {'no review': FakeAPI(approvals=()),
                 'rejected': FakeAPI(approvals=({**APPROVAL, 'state': 'rejected'},)),
                 'approved and then rejected': FakeAPI(approvals=(APPROVAL, {**APPROVAL, 'state': 'rejected'})),
                 'approved by someone else': FakeAPI(approvals=(other,)),
                 'pending only': FakeAPI(approvals=({**APPROVAL, 'state': 'pending'},)),
                 'another environment': FakeAPI(approvals=({**APPROVAL, 'environments': [{'id': 9, 'name': 'pages'}]},)),
                 'the owner id as text': FakeAPI(approvals=({**APPROVAL, 'user': {'login': 'WOOWTECH', 'id': str(g.OWNER_ID)}},)),
                 'review history missing': FakeAPI(**{'/repos/WOOWTECH/Woow_ha_mcp_addons/actions/runs/123456789/approvals': error(404)}),
                 'review history not a list': FakeAPI(**{'/repos/WOOWTECH/Woow_ha_mcp_addons/actions/runs/123456789/approvals': {'x': 1}}),
                 'an unprotected environment': FakeAPI(environment={**ENVIRONMENT, 'can_admins_bypass': True})}
        for name, api in cases.items():
            self.record.unlink(missing_ok=True)
            with self.subTest(name), self.assertRaises(g.Closed):
                self.gate(api, mode='publish')
            self.assertFalse(self.record.exists())
        for changes, message in (({'GITHUB_RUN_ATTEMPT': '2'}, 're-run'), ({'GITHUB_RUN_ATTEMPT': ''}, 're-run'),
                                 ({'GITHUB_RUN_ID': 'x'}, 'GITHUB_RUN_ID'), ({'GITHUB_ACTIONS': 'false'}, 'only in the workflow'),
                                 ({'GITHUB_REPOSITORY': 'someone/fork'}, 'not a run of')):
            api = FakeAPI()
            with self.subTest(changes=changes), self.assertRaisesRegex(g.Closed, message):
                self.gate(api, mode='publish', env={**RUN_ENV, **changes})
            self.assertEqual(api.calls, [])  # refused before any request
        self.record.unlink(missing_ok=True)
        self.gate(FakeAPI(), mode='publish')
        with self.assertRaises(FileExistsError):  # the record is written once
            self.gate(FakeAPI(), mode='publish')

    def test_token_and_anonymous_mode(self):
        for token in ('', ' ', 'two words'):
            api = FakeAPI()
            with self.subTest(token=token), self.assertRaisesRegex(g.Closed, 'GH_TOKEN'):
                self.gate(api, env={**RUN_ENV, 'GH_TOKEN': token})
            self.assertEqual(api.calls, [])
        with self.assertRaisesRegex(g.Closed, 'local checks only'):
            with patch.object(g, 'request', side_effect=FakeAPI()):
                g.main(['gate', '--anonymous'], env=RUN_ENV, sleep=list().append)
        api = FakeAPI()
        with patch.object(g, 'request', side_effect=api):
            g.main(['gate', '--anonymous'], env={}, sleep=list().append)
        self.assertTrue(all('Authorization' not in headers for _, headers in api.calls))
        for argv in ([], ['publish'], ['publish', 'x', '--anonymous'], ['gate', 'x'], ['other']):
            with self.subTest(argv=argv), self.assertRaisesRegex(g.Closed, 'usage'):
                g.main(argv, env=RUN_ENV, sleep=list().append)
        with self.assertRaisesRegex(g.Closed, 'unexpected API path'):
            g.fetch('/repos/someone/else/environments/x', 'token', sleep=list().append)

    def test_request_refuses_redirects_and_proxies(self):
        handlers = []
        real = g.urllib.request.build_opener

        def build(*args):
            handlers.extend(args)
            return real(*args)
        with patch.object(g.urllib.request, 'build_opener', side_effect=build), \
             patch.object(g.urllib.request.OpenerDirector, 'open', return_value=Response(b'{}')):
            g.request('https://api.github.com/repos/WOOWTECH/Woow_ha_mcp_addons/environments/public-release', {})
        proxy = next(h for h in handlers if isinstance(h, g.urllib.request.ProxyHandler))
        self.assertEqual(proxy.proxies, {})
        redirect = next(h for h in handlers if isinstance(h, g.urllib.request.HTTPRedirectHandler))
        self.assertIsNone(redirect.redirect_request(None, None, 302, 'Found', {}, 'https://elsewhere.invalid/'))

    def test_the_gate_is_standard_library_only_and_never_prints_the_token(self):
        source = Path(g.__file__).read_text()
        for absent in ('import yaml', 'import validate', 'import supply_chain', 'print(token', 'GITHUB_ENV', 'GITHUB_PATH'):
            self.assertNotIn(absent, source)
        script = str(Path(g.__file__).resolve())
        environment = {k: v for k, v in os.environ.items() if not k.startswith('GITHUB_') and k != 'GH_TOKEN'}
        result = subprocess.run([sys.executable, '-I', '-B', script, 'gate'], env=environment, capture_output=True,
                                text=True, timeout=60)
        self.assertEqual((result.returncode, result.stdout),
                         (1, ''))
        self.assertEqual(result.stderr, "environment gate CLOSED: GH_TOKEN (the run's GITHUB_TOKEN) is missing\n")


if __name__ == '__main__':
    unittest.main()
