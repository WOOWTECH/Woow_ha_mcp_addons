"""HM-11: the management answers the panel relies on once a product is switched on, recorded from the real 8099 app
(multi-profile plan 6, 12.3 HM-11; contract 3, 4.1).

packages/mcp-admin-ui/tests/profile-api-cases.json lists every management call the panel makes with profiles, and
every refusal it handles, as cases (a request and the answer's expected shape). This test runs every case against the
production runtime (tests/multi_profile_runtime.py: in process, the switch monkeypatched on, the children behind one
MockTransport) and requires exactly the case's expect. tests/browser/profile-api-parity.spec.mjs runs the same cases
against the panel's LOCAL MOCK (packages/mcp-admin-ui/fixtures/server.mjs) and requires the same: so the mock the
browser tests use answers as the add-on does (status, field names and types, the echo, the ETag), and a change of
either side fails one of the two.

The shape (the cases file's about and rules): the status, the class of the ETag header, the body's fields with their
types; the values of the rules' literal keys; ids by their role; Idempotency-Keys by the case that sent them; ETags and
revisions by class. Every case runs under the HM-01 log scan (tokens, child tokens and labels watched).
"""
from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import time

import httpx
import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from multi_profile_runtime import Children, create_profile, multi_profile_runtime
from mcp_admin_core import profile_runtime, profiles, restore_detect
from mcp_admin_core.products import ProductStore
from test_single_profile_golden import ADMIN, GENUINE_CLIENT, INGRESS, configure, settle

pytestmark = pytest.mark.usefixtures('log_scan')
CASES_FILE = Path(__file__).resolve().parents[1] / 'packages' / 'mcp-admin-ui' / 'tests' / 'profile-api-cases.json'
CASES = json.loads(CASES_FILE.read_text())
RULES = CASES['rules']
HEX24 = re.compile(r'[0-9a-f]{24}')
QUARANTINED = re.compile(r'profiles\.json\.quarantine-[0-9]{8}T[0-9]{6}Z(?:-[0-9]{1,3})?')
CLASSES = ((re.compile(r'"p1-[0-9a-f]{64}"'), '<etag:p1>'), (re.compile(r'"c1-[0-9a-f]{64}"'), '<etag:c1>'),
           (re.compile(r'p1-[0-9a-f]{64}'), '<revision:p1>'), (re.compile(r'c1-[0-9a-f]{64}'), '<revision:c1>'))


# ---- the shape (the same rules as profile-api-parity.spec.mjs) ----

def etag_class(value):
    if value is None:
        return None
    for pattern, name in CLASSES[:2]:
        if pattern.fullmatch(value):
            return name[len('<etag:'):-1]
    return 'other'


def shape(value, context, key=None):
    """The value as the cases compare it (see the module docstring)."""
    if isinstance(value, dict):
        return {name: shape(item, context, name) for name, item in value.items()}
    if isinstance(value, list):
        return [shape(item, context, key) for item in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return '<int>'
    if isinstance(value, float):
        return '<number>'
    if value == profiles.DEFAULT_PROFILE:
        return value
    if HEX24.fullmatch(value):
        return '<' + context['roles'].get(value, 'hex24') + '>'
    if value in context['keys']:
        return '<key:' + context['keys'][value] + '>'
    for pattern, name in CLASSES:
        if pattern.fullmatch(value):
            return name
    if QUARANTINED.fullmatch(value):
        return '<quarantine-name>'
    return value if key in RULES['literal'] else '<str>'


def projected(case, body):
    keys = case['keys']
    if keys == '*' or not isinstance(body, dict):
        return body
    names = {'bootstrap': RULES['bootstrap_keys'], 'bootstrap-profile': RULES['bootstrap_profile_keys']}[keys] if isinstance(
        keys, str) else keys
    return {name: body[name] for name in names if name in body}


def observed(case, response, context):
    """What a case compares of an answer."""
    seen = {'status': response.status_code, 'etag': etag_class(response.headers.get('etag'))}
    if response.headers.get('content-type', '').startswith('application/json'):
        seen['body'] = shape(projected(case, response.json()), context)
    else:
        seen['body'] = '<empty>' if not response.content else '<text>'
    return seen


# ---- the requests ----

def operation_key():
    """An Idempotency-Key as the panel makes one (a second ago, 16 random bytes; never committed)."""
    return f'{int(time.time() * 1000) - 1000}.{secrets.token_hex(16)}'


def resolved(text, context):
    for role, value in context['ids'].items():
        text = text.replace('{' + role + '}', value)
    for value, name in context['keys'].items():
        text = text.replace('{key:' + name + '}', value)
    return text.replace('{endpoint}', RULES['endpoint'])


def profile_value(spec, context):
    return context['ids'].get(spec, spec) if spec in context['ids'] or spec == 'default' else resolved(spec, context)


class Rig:
    """One scenario's runtime and the panel's requests to its 8099 app."""

    def __init__(self, runtime, switched_on):
        self.runtime, self.switched_on = runtime, switched_on

    def client(self):
        return GENUINE_CLIENT(transport=httpx.ASGITransport(app=self.runtime.admin_app, client=INGRESS),
                              base_url='http://admin')

    async def bootstrap(self, profile_id='default'):
        headers = {**ADMIN, **({'X-MCP-Profile': profile_id} if self.switched_on else {})}
        async with self.client() as client:
            response = await client.get('/api/bootstrap', headers=headers)
        assert response.status_code == 200, response.content
        return response.json()

    async def index_etag(self):
        async with self.client() as client:
            response = await client.get('/api/profiles', headers=ADMIN)
        assert response.status_code == 200, response.content
        return response.headers['etag']

    async def send(self, case, context):
        spec = case['request']
        headers = dict(ADMIN)
        if 'profile' in spec:
            headers['X-MCP-Profile'] = profile_value(spec['profile'], context)
        match = spec.get('if_match')
        if match == 'index':
            headers['If-Match'] = await self.index_etag()
        elif match == 'raw':
            headers['If-Match'] = (await self.bootstrap())['profile_index_etag']
        elif match is not None and match.startswith('config:'):
            role = match[len('config:'):]
            revision = (await self.bootstrap(context['ids'].get(role, role)))['configuration']['revision']
            headers['If-Match'] = f'"{revision}"'
        elif match is not None:
            headers['If-Match'] = RULES[match.replace('-', '_')]
        if spec.get('csrf'):  # last, from the newest bootstrap (as the mock spec takes it)
            headers['X-CSRF-Token'] = (await self.bootstrap())['csrf']
        key = spec.get('key')
        if key == 'new':
            headers['Idempotency-Key'] = operation_key()
            context['keys'][headers['Idempotency-Key']] = case['name']
        elif key is not None:
            headers['Idempotency-Key'] = next(value for value, name in context['keys'].items()
                                              if name == key[len('same:'):])
        body = spec.get('body')
        if body is not None:
            body = json.loads(resolved(json.dumps(body), context))
        async with self.client() as client:
            return await client.request(spec['method'], resolved(spec['path'], context), headers=headers,
                                        **({} if body is None else {'json': body}))


# ---- the scenarios' state, as the cases file's setup says ----

def children_for(data, product, extras):
    """Every profile's child behind its index port (the default profile's on 3000)."""
    children = Children()
    children.profile_child(3000, 'default', product, data)
    for number, profile_id in enumerate(extras):
        children.profile_child(18000 + number, f'p{number}', product, profiles.Layout(data).profile(profile_id))
    return children


def replace_index(data):
    """The index replaced behind the add-on's back (its bytes in a new file): unusable until a restart (DQ-12)."""
    path = profiles.Layout(Path(data)).index
    raw = path.read_bytes()
    path.unlink()
    path.write_bytes(raw)
    path.chmod(0o600)


def watch(log_scan, data, setup):
    for path in [Path(data) / 'state.json', *sorted((Path(data) / 'profiles').glob('*/state.json'))]:
        value = json.loads(path.read_text())
        log_scan.watch(*(item for item in (value['token'], value['child_token']) if item))
    labels = [extra['label'] for extra in setup.get('extras', []) + setup.get('unavailable', [])]
    log_scan.watch(*labels, 'Kappa Desk', 'Lambda Desk', kind='name')


async def run_scenario(scenario, tmp_path, log_scan):
    setup, product = scenario['setup'], scenario['setup']['product']
    ids = RULES['ids']
    data = tmp_path / scenario['name'] / 'data'
    data.mkdir(parents=True)
    configure(data, product)
    if setup.get('policy'):  # HM-13c: the default profile's policy, before any profile copies it (DQ-02)
        store = ProductStore(data, product)
        try:
            store.update(**setup['policy'])
        finally:
            store.close()
    extras = [ids[extra['role']] for extra in setup['extras']]
    for number, extra in enumerate(setup['extras']):
        create_profile(data, product, ids[extra['role']], label=extra['label'], port=18000 + number)
    for orphan in setup.get('orphans', []):
        create_profile(data, product, ids[orphan], label='Orphan Ops', port=18090, indexed=False)
    for number, role in enumerate(setup.get('quarantine', [])):  # HM-13c: the boot guard quarantines these
        create_profile(data, product, ids[role], label='Orphan Ops', port=18080 + number, indexed=False)
        (profiles.Layout(data).profile(ids[role]) / '.writer.lock').unlink()
    for number, extra in enumerate(setup.get('unavailable', [])):
        create_profile(data, product, ids[extra['role']], label=extra['label'], port=18050 + number)
    watch(log_scan, data, setup)
    for extra in setup.get('unavailable', []):
        shutil.rmtree(profiles.Layout(data).profile(ids[extra['role']]))
    if setup.get('restore'):  # HM-13c: the entrypoint's marker of a restore (signal 1), before the start
        os.close(os.open(data / profiles.RESTORE_MARKER_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600))
    if setup.get('no_index_file'):
        # The add-on's first switched-on start made the sentinel and its record before any profile data (HM-13a; as
        # create_profile does): an unlistable profiles entry, not a restore. HM-13c renews the journal beside the index
        # at a restore, so the cases' keys (made a second ago) would be from before it (410 operation_restored).
        restore_detect.detect(data, enabled=True)
        profiles.Layout(data).profiles.write_text('not a directory')
    # Without additional profiles the default profile's child is the golden MockChild (multi_profile_runtime's own).
    options = {'switch': not setup.get('switched_off'),
               **({'children': children_for(data, product, extras)} if extras else {})}
    if setup.get('file_budget') == 'short':
        from test_router_passthrough import FakeResource
        needed, _ = profile_runtime.open_file_budget(product)
        options['resources'] = FakeResource(256, needed - 1)
    context = {'ids': dict(ids), 'roles': {value: role for role, value in ids.items()}, 'keys': {}}
    seen = {}
    async with AsyncExitStack() as stack:
        patch = stack.enter_context(pytest.MonkeyPatch.context())
        # tests/owned_network.py refuses every bind of 18000-18099: a new profile's port is allocated without the
        # spawn check's test bind; the memory readings are the scenario's.
        patch.setattr(profiles, 'port_occupied', lambda port: None)
        patch.setattr(profiles, 'memory_limit_mib', lambda: setup.get('memory_limit_mib'))
        patch.setattr(profiles, 'available_memory_mib', lambda: setup.get('available_memory_mib', 4096))
        runtime = await stack.enter_async_context(multi_profile_runtime(product, data, **options))
        await settle(runtime, 'configured')
        if setup.get('restore'):
            # HM-13c: the boot guard renewed every journal at the restore, refusing every operation id up to then (410
            # operation_restored); the cases' keys are made a second before they are sent (as the panel takes the
            # server's time after the start), so they wait until that second is after the restore.
            await asyncio.sleep(1.1)
        if setup.get('no_port'):
            patch.setattr(runtime.manager, 'free_port', lambda: None)
        if setup.get('corrupt'):
            replace_index(data)
        rig = Rig(runtime, not setup.get('switched_off'))
        for case in scenario['cases']:
            response = await rig.send(case, context)
            if case.get('learn') and response.status_code in (200, 201):
                learnt = response.json()['id']
                context['ids'][case['learn']], context['roles'][learnt] = learnt, case['learn']
            if case.get('learn_quarantine') and response.status_code == 200:  # HM-13c: a quarantine directory's name
                context['ids'][case['learn_quarantine']] = response.json()['quarantined'][0]['name']
            seen[case['name']] = observed(case, response, context)
    return seen


@pytest.mark.parametrize('scenario', CASES['scenarios'], ids=[item['name'] for item in CASES['scenarios']])
async def test_the_real_management_app_answers_every_panel_case_as_recorded(scenario, tmp_path, log_scan):
    """Every case of the scenario, against the production runtime: exactly its expect (status, ETag class, shape)."""
    seen = await run_scenario(scenario, tmp_path, log_scan)
    expected = {case['name']: case.get('expect') for case in scenario['cases']}
    if seen != expected:
        different = {name: seen[name] for name in seen if seen[name] != expected[name]}
        pytest.fail('the add-on answers differently from profile-api-cases.json:\n'
                    + json.dumps(different, ensure_ascii=False, indent=1))
