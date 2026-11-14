"""HM-02: log redaction aligned with the PaaS rules (woow-mcp-server #149), checked on the PaaS corpora.

Every log record (redact.scrub: the record factory of redact.install(), and RedactSecretPaths) and every line of child
output (diagnostics.scrub_line) goes through the PaaS log redaction first, mcp_admin_core/log_redaction.py vendored
byte for byte from woow-mcp-server 7d111b1, then through the HA rules, so a secret path still reads
/private_[REDACTED] (multi-profile plan section 8.6, DQ-38 (a)). Checked here, with values made while the test runs:

- the 97 request targets of the PaaS review (mp-verify-n8n-20261113 harness/cases.py, the list PaaS
  tests/test_log_redaction_private_separators.py copies) as sent, decoded, and quoted the way uvicorn's access log
  writes a path, in five places: a log message, a log argument, an exception, uvicorn's access record, a child line;
- #149's query credentials: every name of log_redaction.CREDENTIAL_PARAM_NAMES (and token, access_token) in each
  spelling after ? & ;, and the 97 forms as query values;
- no worse than the pinned PaaS module: the threshold is what log_redaction itself shows for the same input in the
  same place, computed while the test runs, so a later sync of the module moves it without an edit here;
- the order, PaaS first and HA after: a secret path keeps the HA form, and the reversed order, computed on the same
  corpus, does not meet the threshold;
- no regression against bb48449's own redaction (redact.py and diagnostics.py, frozen byte for byte in
  tests/fixtures/): whatever it hid stays hidden, on the corpora, on the counterexamples that need redact.shows_hidden
  and in a differential fuzz;
- key= in child output (FM-75: bb48449 left ?key= and key=), without masking keys=, key_id=, monkey= or keyword=.

A value shows when any MIN_FRAGMENT characters of it in a row are in the output (as the PaaS tests count it).
"""
from __future__ import annotations

import ast
from collections import Counter
import hashlib
import importlib.util
import json
import logging
from pathlib import Path
import random
import sys
import time
import types
from urllib.parse import quote, unquote

import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core import diagnostics, log_redaction, redact

pytestmark = pytest.mark.usefixtures('log_scan')  # every new test runs under the HM-01 log scan

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures'
VENDORED = ROOT / 'packages/mcp-admin-core/mcp_admin_core/log_redaction.py'
VENDORED_TESTS = ROOT / 'tests/vendor_paas'
PAAS_COMMIT = '7d111b175fbbcdf692ff579cc5793bf8c7de3a7b'  # woow-mcp-server main, #149 merged
PAAS_PATH = 'packages/mcp-admin-core/mcp_admin_core/log_redaction.py'
PAAS_SHA256 = '1fec42aab78201e5c2bd892586e19ee640f0214905189ff9dbfea29d729b1f91'
PAAS_TESTS_SHA256 = {  # packages/mcp-admin-core/tests/<name> at PAAS_COMMIT: the module's four pure tests
    'test_log_redaction_encoded_boundaries.py': '22d713099d246accc9bb5eb301029e63bff0910ab04ac1d1beb4f2f18924e0f7',
    'test_log_redaction_linear.py': 'c57226789450143b9921c33a2f93895182c6c7ad22fed939b9329c5c0ed6b6b0',
    'test_log_redaction_segments.py': 'afcb8914f0867fb5dce2c9283a9c9e9655f78b66dc6195f5355eb2603d9bb6fb',
    'test_log_redaction_single_pass.py': '4d5b724c00868054f9c90c6a9be0c0b1c92142270755ce03bd9822677a5e7168',
}
BB48449_REDACT_SHA256 = 'ab208293548bc35e3eb986e564ec35ecb8f414a8879b591892425904e6b0013b'
BB48449_DIAGNOSTICS_SHA256 = '5e42057e59cf5abbc1eae9bd709d09f663e5b6832c34b621ab4644aa8ef4f6b7'
MIN_FRAGMENT = 8
LETTERS = 'GHJKLMNPQRSTUVWXYZ'  # no hexadecimal digit: a value never completes a percent escape


def _digest(label: str) -> bytes:
    return hashlib.sha256(b'woow-ha HM-02 synthetic ' + label.encode()).digest()


def _letters(label: str, length: int = 16) -> str:
    return ''.join(LETTERS[byte % len(LETTERS)] for byte in (_digest(label) + _digest(label + ' more'))[:length])


# Synthetic values, made here (none is a credential of any service): the two path token shapes of the PaaS tests,
# 64 hex and URL-safe (the add-on's own token is 43 URL-safe characters), and a letters-only query credential value.
TOKENS = {'hex': _digest('path token').hex(),
          'urlsafe': ''.join('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'[byte % 64]
                             for byte in _digest('urlsafe path token') + _digest('urlsafe path token 2'))[:43]}
VALUE = _letters('query credential value')
PLAIN_PRIVATE = '/private_' + 'T' * 43 + '/mcp'  # a /private_ URL whose own token is not under test


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frozen_bb48449():
    """bb48449's redact.py and diagnostics.py as they were (byte-for-byte copies); diagnostics' ``from . import redact``
    gets the frozen redact through a package of its own, registered only while the copy loads."""
    package = types.ModuleType('hm02_bb48449')
    package.__path__ = []
    old_redact = _load('hm02_bb48449.redact', FIXTURES / 'redact_bb48449.py')
    package.redact = old_redact
    saved = {name: sys.modules.get(name) for name in ('hm02_bb48449', 'hm02_bb48449.redact')}
    sys.modules.update({'hm02_bb48449': package, 'hm02_bb48449.redact': old_redact})
    try:
        old_diagnostics = _load('hm02_bb48449.diagnostics', FIXTURES / 'diagnostics_bb48449.py')
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
    return old_redact, old_diagnostics


OLD_REDACT, OLD_DIAGNOSTICS = _frozen_bb48449()


def _fragment(text: str, value: str) -> str | None:
    for start in range(len(value) - MIN_FRAGMENT + 1):
        if value[start:start + MIN_FRAGMENT] in text:
            return value[start:start + MIN_FRAGMENT]
    return None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# the 97 request targets (mp-verify-n8n-20261113 harness/cases.py; PaaS test_log_redaction_private_separators.py)
# ---------------------------------------------------------------------------

def _enc(text: str) -> str:
    return quote(text, safe='')


ENCODED_FIRST = [
    ('space', ' '), ('tab', '\t'), ('lf', '\n'), ('cr', '\r'), ('vt', '\x0b'), ('ff', '\x0c'), ('fs_1c', '\x1c'),
    ('us_1f', '\x1f'), ('nel_85', '\x85'), ('nbsp_a0', '\xa0'), ('ogham_1680', '\u1680'), ('enquad_2000', '\u2000'),
    ('thinsp_2009', '\u2009'), ('zwsp_200b', '\u200b'), ('linesep_2028', '\u2028'), ('nnbsp_202f', '\u202f'),
    ('mmsp_205f', '\u205f'), ('ideographic_space_3000', '\u3000'), ('bom_feff', '\ufeff'),
    ('dquote', '"'), ('squote', "'"), ('question', '?'), ('hash', '#'), ('slash', '/'), ('backslash', '\\'),
    ('percent', '%'), ('amp', '&'), ('semicolon', ';'), ('equals', '='), ('plus', '+'), ('comma', ','), ('colon', ':'),
    ('at', '@'), ('star', '*'), ('lt', '<'), ('gt', '>'), ('backtick', '`'), ('lbrace', '{'), ('rbrace', '}'),
    ('pipe', '|'), ('caret', '^'), ('lbracket', '['), ('rbracket', ']'), ('bang', '!'), ('dollar', '$'), ('lparen', '('),
    ('rparen', ')'), ('tilde', '~'), ('dot', '.'), ('dash', '-'), ('underscore', '_'),
    ('fullwidth_quote_ff02', '\uff02'), ('left_dquote_201c', '\u201c'), ('right_squote_2019', '\u2019'),
]

LITERAL_FIRST = [
    ('squote', "'"), ('dquote', '"'), ('lt', '<'), ('gt', '>'), ('lbrace', '{'), ('rbrace', '}'), ('pipe', '|'),
    ('caret', '^'), ('backtick', '`'), ('lbracket', '['), ('rbracket', ']'), ('bang', '!'), ('dollar', '$'),
    ('lparen', '('), ('rparen', ')'), ('star', '*'), ('comma', ','), ('semicolon', ';'), ('equals', '='), ('at', '@'),
    ('colon', ':'), ('plus', '+'), ('backslash', '\\'), ('space', ' '),
]


def build_targets(token: str) -> dict[str, str]:
    """case name -> the request target as sent on the wire (the harness's order)."""
    half = len(token) // 2
    out = {'canonical': f'/private_{token}/mcp', 'canonical_no_suffix': f'/private_{token}'}
    for name, char in ENCODED_FIRST:
        out['enc_first_' + name] = f'/private_{_enc(char)}{token}/mcp'
    for name, char in LITERAL_FIRST:
        out['lit_first_' + name] = f'/private_{char}{token}/mcp'
    out.update({
        'wrap_dquote_encoded': f'/private_%22{token}%22/mcp',
        'wrap_squote_literal': f"/private_'{token}'/mcp",
        'wrap_squote_encoded': f'/private_%27{token}%27/mcp',
        'wrap_space_encoded': f'/private_%20{token}%20/mcp',
        'wrap_angle_encoded': f'/private_%3C{token}%3E/mcp',
        'wrap_smart_dquotes': f'/private_{_enc(chr(0x201c))}{token}{_enc(chr(0x201d))}/mcp',
        'mid_space': f'/private_{token[:half]}%20{token[half:]}/mcp',
        'mid_dquote': f'/private_{token[:half]}%22{token[half:]}/mcp',
        'mid_ideographic_space': f'/private_{token[:half]}%E3%80%80{token[half:]}/mcp',
        'mid_question_encoded': f'/private_{token[:half]}%3F{token[half:]}/mcp',
        'end_space': f'/private_{token}%20/mcp',
        'end_dquote': f'/private_{token}%22/mcp',
        'query_literal_q_before_token': f'/private_?{token}/mcp',
        'query_token_param': f'/private_x/mcp?token={token}',
        'query_bare_token': f'/private_x/mcp?{token}',
        'double_slash_after_prefix': f'/private_//{token}/mcp',
        'double_leading_slash': f'//private_{token}/mcp',
    })
    return out


FORMS = ('raw', 'decoded', 'access')


def forms(target: str) -> dict[str, str]:
    """raw: as sent; decoded: every escape decoded once (what an exception message with the ASGI path shows);
    access: the decoded path quoted again plus the query as sent (uvicorn's access line)."""
    path, mark, query = target.partition('?')
    return {'raw': target, 'decoded': unquote(target), 'access': quote(unquote(path)) + mark + query}


def query_value_forms(value: str) -> dict[str, str]:
    """#149: the 97 forms as a query value, ``<form>`` of ``/private_<form>/mcp``; the four forms that concern the
    query or only the prefix are the value itself (as PaaS test_log_redaction_query_credentials.py builds them)."""
    out = {}
    for case, target in build_targets(value).items():
        if case in ('query_token_param', 'query_bare_token', 'double_leading_slash', 'canonical_no_suffix'):
            out[case] = value
            continue
        body = target[len('/private_'):]
        out[case] = body[:-len('/mcp')] if body.endswith('/mcp') else body
    return out


# ---------------------------------------------------------------------------
# the five places a text is shown, each with the HA composition, the pinned PaaS module and bb48449
# ---------------------------------------------------------------------------

TEMPLATE = 'request failed for %s (synthetic)'
ACCESS_TEMPLATE = '%s - "%s %s HTTP/%s" %d'  # uvicorn's access record


def _message_record(text: str) -> logging.LogRecord:
    return logging.LogRecord('hm02.matrix', logging.WARNING, __file__, 1, TEMPLATE % text, (), None)


def _argument_record(text: str) -> logging.LogRecord:
    return logging.LogRecord('hm02.matrix', logging.WARNING, __file__, 1, TEMPLATE, (text,), None)


def _exception_record(text: str) -> logging.LogRecord:
    try:
        raise RuntimeError('upstream failed for ' + text)
    except RuntimeError:
        return logging.LogRecord('hm02.matrix', logging.ERROR, __file__, 1, 'request failed', (), sys.exc_info())


def _access_record(text: str) -> logging.LogRecord:
    return logging.LogRecord('uvicorn.access', logging.INFO, __file__, 1, ACCESS_TEMPLATE,
                             ('127.0.0.1:5555', 'GET', text, '1.1', 404), None)


RECORDS = {'message': _message_record, 'argument': _argument_record, 'exception': _exception_record,
           'access': _access_record}
FORMATTER = logging.Formatter('%(message)s')


def _shown(scrub, make):
    def show(text):
        record = make(text)
        scrub(record)
        return FORMATTER.format(record)
    return show


def _paas_child(text: str) -> str:
    """The pinned PaaS module in the child line pipeline in place of the HA rules (the same ANSI, printable and length
    handling as diagnostics.scrub_line, which bb48449 has too)."""
    text = log_redaction.redact(diagnostics.ANSI.sub('', text))
    return ''.join(c for c in text if c == '\t' or c.isprintable())[:diagnostics.MAX_LINE]


PLACES = {  # place -> (HA as it is now, the pinned PaaS module, bb48449)
    **{place: (_shown(redact.scrub, make), _shown(log_redaction.scrub_record, make), _shown(OLD_REDACT.scrub, make))
       for place, make in RECORDS.items()},
    'child': (diagnostics.scrub_line, _paas_child, OLD_DIAGNOSTICS.scrub_line),
}


def _plain_composition(record):
    """The composition without redact.shows_hidden: the PaaS module, then bb48449's scrub."""
    log_redaction.scrub_record(record)
    OLD_REDACT.scrub(record)


def _reversed_composition(record):
    """The reversed order: bb48449's scrub (the HA rule alone), then the PaaS module."""
    OLD_REDACT.scrub(record)
    log_redaction.scrub_record(record)


def _leaks(show, texts: dict, value: str) -> set:
    return {key for key, text in texts.items() if _fragment(show(text), value) is not None}


def _target_texts(token: str) -> dict:
    return {(case, form): text for case, target in build_targets(token).items() for form, text in forms(target).items()}


QUERY_KEYS = ('token', 'access_token', 'api_key', 'key')
QUERY_BASES = ('/api/x', PLAIN_PRIVATE)
QUERY_TAILS = ('', '&tail=1')


def _query_texts(value: str) -> dict:
    out = {}
    for case, form_value in query_value_forms(value).items():
        for key in QUERY_KEYS:
            for base in QUERY_BASES:
                for tail in QUERY_TAILS:
                    for form, text in forms(f'{base}?{key}={form_value}{tail}').items():
                        out[(case, key, base, tail, form)] = text
    return out


def credential_names() -> list[str]:
    """Each spelling the PaaS tests use: words joined by _, - or nothing; lower, upper and alternating case."""
    names = set()
    for words in (*log_redaction.CREDENTIAL_PARAM_NAMES, ('token',), ('access', 'token')):
        for joint in ('_', '-', ''):
            name = joint.join(words)
            names |= {name, name.upper(), ''.join(c.upper() if i % 2 else c for i, c in enumerate(name))}
    return sorted(names)


CREDENTIAL_TEMPLATES = (
    '/x?{name}={value}', '/x?a=1&{name}={value}&b=2', '/x?a=1;{name}={value}', 'GET /x?{name}={value} HTTP/1.1',
    '/x?{name}=%20{value}%20&b=2', '/x?{name}=%22{value}%22', PLAIN_PRIVATE + '?{name}={value}',
    'HTTP Request: GET http://backend.invalid:4000/v1/x?{name}={value} "HTTP/1.1 200 OK"',
)


# ---------------------------------------------------------------------------
# the inputs themselves
# ---------------------------------------------------------------------------

def test_vendored_module_is_paas_7d111b1_verbatim():
    """The module is woow-mcp-server 7d111b1's file byte for byte, and the ledger entry names that source."""
    assert _sha256(VENDORED) == PAAS_SHA256
    ledger = json.loads((ROOT / 'docs/provenance/runtime-patches.json').read_text())
    [entry] = [patch for patch in ledger['patches'] if patch['path'] == str(VENDORED.relative_to(ROOT))]
    assert entry['sha256'] == PAAS_SHA256 and entry['guarded_sources'] == {}
    assert all(part in entry['change'] for part in ('WOOWTECH/woow-mcp-server', PAAS_COMMIT, PAAS_PATH, PAAS_SHA256))


def test_vendored_paas_tests_are_7d111b1_verbatim():
    """tests/vendor_paas/ holds the module's four pure PaaS tests byte for byte (they import it under the same name, so
    not even an import changed) and only the HA conftest.py and __init__.py besides."""
    assert {path.name for path in VENDORED_TESTS.iterdir() if path.name != '__pycache__'} == {
        *PAAS_TESTS_SHA256, 'conftest.py', '__init__.py'}
    for name, digest in PAAS_TESTS_SHA256.items():
        path = VENDORED_TESTS / name
        assert _sha256(path) == digest, name
        imported = {alias.name if isinstance(node, ast.Import) else node.module
                    for node in ast.walk(ast.parse(path.read_text())) if isinstance(node, (ast.Import, ast.ImportFrom))
                    for alias in node.names}
        assert {module for module in imported if module and module.startswith('mcp_admin_core')} == {'mcp_admin_core'}
        assert 'from mcp_admin_core import log_redaction' in path.read_text(), name


def test_frozen_bb48449_redaction_is_verbatim():
    assert _sha256(FIXTURES / 'redact_bb48449.py') == BB48449_REDACT_SHA256
    assert _sha256(FIXTURES / 'diagnostics_bb48449.py') == BB48449_DIAGNOSTICS_SHA256
    assert OLD_REDACT.redact('/private_x/mcp') == '/private_[REDACTED]/mcp' and OLD_DIAGNOSTICS.redact is OLD_REDACT


def test_matrix_is_the_reviewed_97_cases():
    for token in TOKENS.values():
        targets = build_targets(token)
        assert len(targets) == 97 and all(target.isascii() for target in targets.values())
        groups = Counter(case.split('_')[0] for case in targets)
        assert groups == {'canonical': 2, 'enc': 54, 'lit': 24, 'wrap': 6, 'mid': 4, 'end': 2, 'query': 3,
                          'double': 2}, groups
    assert len(query_value_forms(VALUE)) == 97 and query_value_forms(VALUE)['enc_first_space'] == '%20' + VALUE
    assert len(TOKENS['hex']) == 64 and len(TOKENS['urlsafe']) == 43 and not set(VALUE) & set('0123456789abcdefABCDEF')


def test_the_pinned_module_lists_the_reported_credential_names():
    """#149 (FM-75): the names the PaaS pre-release retest reported, key included (FM-65: bb48449 left ?key=)."""
    reported = {'api_key', 'apikey', 'key', 'secret', 'client_secret', 'password', 'passwd', 'pwd', 'auth',
                'authorization', 'jwt', 'access_key', 'signature', 'sig'}
    assert reported <= set(credential_names())


# ---------------------------------------------------------------------------
# no worse than the pinned PaaS module (threshold computed now), no regression against bb48449
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('place', list(PLACES))
@pytest.mark.parametrize('kind', list(TOKENS))
def test_97_targets_are_never_worse_than_the_pinned_paas_module(kind, place):
    token = TOKENS[kind]
    texts = _target_texts(token)
    ha, paas, _ = PLACES[place]
    worse = sorted(_leaks(ha, texts, token) - _leaks(paas, texts, token))
    assert not worse, f'{len(worse)} target form(s) the pinned PaaS module masks show the token here: {worse}'
    for form in FORMS:  # the plain shapes: always masked
        for case in ('canonical', 'canonical_no_suffix'):
            assert _fragment(ha(texts[(case, form)]), token) is None, (case, form)


@pytest.mark.parametrize('place', list(PLACES))
@pytest.mark.parametrize('kind', list(TOKENS))
def test_97_targets_never_show_what_bb48449_masked(kind, place):
    token = TOKENS[kind]
    texts = _target_texts(token)
    ha, _, old = PLACES[place]
    regressed = sorted(_leaks(ha, texts, token) - _leaks(old, texts, token))
    assert not regressed, regressed


@pytest.mark.parametrize('place', list(PLACES))
def test_97_forms_as_query_values_are_never_worse_than_the_pinned_paas_module(place):
    texts = _query_texts(VALUE)
    ha, paas, _ = PLACES[place]
    worse = sorted(_leaks(ha, texts, VALUE) - _leaks(paas, texts, VALUE))
    assert not worse, f'{len(worse)} query value form(s) the pinned PaaS module masks show here: {worse[:20]}'


@pytest.mark.parametrize('place', list(PLACES))
def test_97_forms_as_query_values_never_show_what_bb48449_masked(place):
    texts = _query_texts(VALUE)
    ha, _, old = PLACES[place]
    regressed = sorted(_leaks(ha, texts, VALUE) - _leaks(old, texts, VALUE))
    assert not regressed, regressed[:20]


@pytest.mark.parametrize('place', list(PLACES))
def test_query_credentials_of_149_are_masked(place):
    """Every credential name in every spelling, after ? & ;, plain, padded with encoded spaces or quoted: masked in
    each place (the pinned PaaS module masks every one of them too)."""
    ha, paas, _ = PLACES[place]
    shown = []
    for name in credential_names():
        for template in CREDENTIAL_TEMPLATES:
            text = template.format(name=name, value=VALUE)
            assert _fragment(paas(text), VALUE) is None, (name, template)
            if _fragment(ha(text), VALUE) is not None:
                shown.append((name, template))
    assert not shown, f'{len(shown)} credential value(s) shown: {shown[:20]}'


@pytest.mark.parametrize('text', [
    '/x?limit=5&page=2&x=1',
    '/api/logs/search?q=token&limit=100&regex=false',
    '/x?mytoken=abc&token_type=bearer&session_id=0b5e1d9c',
    '/x?keys=1&key_id=2&monkey=3&keyword=4&keyring=5',
    '/x?signature_version=4&auth_mode=basic&authority=x&passwords_changed=1',
    '/x?q=password&q2=api_key',
    '/x?api_key',
    'api_key=abc without a lead',
    '/mcp and /health/ready',
    '/x?q=a%20b&page=2',
])
def test_ordinary_text_stays_readable_in_log_records(text):
    for place in ('message', 'argument'):
        ha, paas, _ = PLACES[place]
        assert ha(text) == paas(text) == TEMPLATE % text, (place, text)


# ---------------------------------------------------------------------------
# the order: the PaaS rules first, the HA rules after them
# ---------------------------------------------------------------------------

def test_the_paas_rules_run_first_then_the_ha_rule():
    token = TOKENS['urlsafe']
    text = f'GET /private_{token}/mcp?token={token} 200'
    paas_only = 'GET /private_***/mcp?token=*** 200'
    composed = 'GET /private_[REDACTED]/mcp?token=*** 200'
    assert log_redaction.redact(text) == paas_only
    assert redact.redact(text) == f'GET /private_[REDACTED]/mcp?token={token} 200'  # the HA rule alone: unchanged
    assert log_redaction.redact(redact.redact(text)) == paas_only  # the other order shows the PaaS mask
    assert redact.scrub_text(text) == composed
    for place in ('message', 'argument'):
        assert PLACES[place][0](text) == TEMPLATE % composed, place
    assert diagnostics.scrub_line(text) == 'GET /private_[REDACTED]/mcp?token=[REDACTED] 200'  # + the child rules


def test_the_reversed_order_would_not_meet_the_threshold():
    """The corpus tells the two orders apart: the HA rule first, then the PaaS module, shows targets the PaaS module
    alone masks, so the threshold above fails when someone swaps the order."""
    reversed_worse = Counter()
    for token in TOKENS.values():
        texts = _target_texts(token)
        paas = _leaks(PLACES['argument'][1], texts, token)
        reversed_worse.update(form for _, form in
                              _leaks(_shown(_reversed_composition, _argument_record), texts, token) - paas)
    assert sum(reversed_worse.values()) > 0, 'the corpus no longer distinguishes the two orders'


def test_install_scrubs_every_record_with_the_composition(log_scan, monkeypatch):
    """What every handler gets (log_scan renders each record as dispatched, before any handler filter): the factory
    redact.install() sets runs the PaaS rules, then the HA rule. It compiles the PaaS module's lazy patterns, as the PaaS
    install() does; the PaaS module's own logger filters are not put on uvicorn's or httpx's loggers: they would mask
    again after the HA rule and show /private_*** on a handler without RedactSecretPaths (logging.lastResort)."""
    monkeypatch.setattr(logging, '_logRecordFactory', logging.LogRecord)
    monkeypatch.setattr(redact, '_installed', False)
    monkeypatch.setattr(log_redaction, '_clean_value_res', {})
    before = {name: list(logging.getLogger(name).filters) for name in log_redaction.PATH_LOGGERS}
    redact.install()
    assert set(log_redaction._clean_value_res) == {('wide', 'all'), ('lenient', 'all'), ('lenient', 'q'),
                                                   ('lenient', 'amp'), ('strict', 'qs'), ('strict', 'q')}
    assert {name: list(logging.getLogger(name).filters) for name in log_redaction.PATH_LOGGERS} == before
    lines = []

    class Lines(logging.Handler):
        def emit(self, record):
            lines.append(self.format(record))

    sent = 0
    for name in ('hm02.matrix.install', 'uvicorn.error', 'httpx'):
        logger = logging.getLogger(name)
        handler = Lines()
        saved = (logger.handlers, logger.level, logger.propagate)
        logger.handlers, logger.propagate = [handler], False
        logger.setLevel(logging.INFO)
        try:
            for token in TOKENS.values():
                log_scan.watch(token)
                for text in _target_texts(token).values():
                    if _fragment(PLACES['argument'][1](text), token) is None:  # what the PaaS module masks
                        logger.warning(TEMPLATE, text)
                        sent += 1
                logger.warning('library echo %s', f'/private_{token}/mcp?token={token}')
                assert lines[-1] == 'library echo /private_[REDACTED]/mcp?token=***', (name, lines[-1])
        finally:
            logger.handlers, logger.propagate = saved[0], saved[2]
            logger.setLevel(saved[1])
    assert sent > 3 * 2 * 250 and len(lines) == sent + 3 * 2
    assert all(_fragment(line, token) is None for line in lines for token in TOKENS.values())


# ---------------------------------------------------------------------------
# the HA forms, child output and key=
# ---------------------------------------------------------------------------

def test_the_ha_forms_are_unchanged():
    token = TOKENS['urlsafe']
    assert redact.REDACTED == '/private_[REDACTED]' and redact.SECRET_MASK == '[REDACTED]'
    assert redact.PRIVATE_SEGMENT.pattern == OLD_REDACT.PRIVATE_SEGMENT.pattern
    for name in ('AUTH', 'ASSIGNMENT', 'USERINFO'):  # bb48449's child rules, unchanged; key= is a rule of its own
        assert getattr(diagnostics, name).pattern == getattr(OLD_DIAGNOSTICS, name).pattern, name
    for raw, expected in ((f'GET /private_{token}/mcp 200', 'GET /private_[REDACTED]/mcp 200'),
                          (f"'/private_{token}/mcp'", "'/private_[REDACTED]/mcp'"),
                          (f'/private_{token}/mcp?x=1', '/private_[REDACTED]/mcp?x=1'),
                          (f'/private_{token}/messages/?session_id=abc', '/private_[REDACTED]/messages/?session_id=abc')):
        assert redact.scrub_text(raw) == expected and diagnostics.scrub_line(raw) == expected
        for place in ('message', 'argument'):
            assert PLACES[place][0](raw) == TEMPLATE % expected, (place, raw)
    for line, secrets in ((f'login {VALUE}', (VALUE,)), (f'Authorization: Bearer {VALUE}', ()),
                          (f'password={VALUE} next', ()), (f'url http://user:{VALUE}@h.invalid/x', ()),
                          (f'token: "{VALUE}"', ())):  # the child rules of bb48449: the same line as before
        assert diagnostics.scrub_line(line, secrets) == OLD_DIAGNOSTICS.scrub_line(line, secrets), line
        assert '[REDACTED]' in diagnostics.scrub_line(line, secrets) and VALUE not in diagnostics.scrub_line(line, secrets)


KEY_LINES = (
    'HTTP Request: GET http://backend.invalid:4000/key/info?key={value} "HTTP/1.1 200 OK"',  # LiteLLM, FM-65
    'GET /v1/x?a=1&key={value}', 'GET /v1/x?a=1;KEY={value}',
    'key={value}', 'KEY={value}', 'key = {value}', 'key: {value}', '{{"key": "{value}"}}', "{{'key': '{value}'}}",
    'virtual_key={value}', 'litellm-master-key={value}', 'x-api-key: {value}', 'Key={value} done',
)


@pytest.mark.parametrize('line', KEY_LINES)
def test_child_output_masks_key_values(line):
    text = line.format(value=VALUE)
    shown = diagnostics.scrub_line(text)
    assert _fragment(shown, VALUE) is None, shown
    assert '[REDACTED]' in shown, shown


@pytest.mark.parametrize('line', [
    'keys=12 cached', 'key_id=7', 'monkey=3', 'keyword=x', 'keyboard=us', 'hotkey=F1', 'keyring=on',
    'GET /x?keys=1&key_id=2&monkey=3&keyword=4&keyring=5', 'primary keys: 3', 'the key is set',
])
def test_child_output_keeps_other_key_words(line):
    assert diagnostics.scrub_line(line) == line


def test_the_key_rule_runs_after_the_bb48449_child_rules():
    """key= is the last child rule: in ASSIGNMENT it would hide key=...@ first and leave the userinfo in front of it,
    which bb48449 hid (found by the differential fuzz below)."""
    text = f'url http://user:{VALUE}&key=@h.invalid/x'
    assert _fragment(OLD_DIAGNOSTICS.scrub_line(text), VALUE) is None
    assert [pattern for pattern, _ in diagnostics.RULES] == [redact.PRIVATE_SEGMENT, diagnostics.AUTH,
                                                            diagnostics.ASSIGNMENT, diagnostics.USERINFO, diagnostics.KEY]
    assert diagnostics.KEY.sub(r'\1[REDACTED]', diagnostics.USERINFO.sub(r'\1[REDACTED]@', text)) == \
        'url http://[REDACTED]@h.invalid/x'
    assert _fragment(diagnostics.scrub_line(text), VALUE) is None


# ---------------------------------------------------------------------------
# what the HA rules alone hide stays hidden (redact.shows_hidden)
# ---------------------------------------------------------------------------

def _counterexamples(token: str) -> dict:
    """Inputs where the composition without redact.shows_hidden would show what bb48449 hid (found by the differential
    fuzz): the PaaS module answers with the decoded text once a decoded-text rule masked something, and the HA rule
    then stops at the space an escape became; its value rule ends at a # inside what the HA rule takes as one secret
    path (no escape needed); it masks key=...@ before the userinfo rule of the child lines sees the @."""
    half = len(token) // 2
    return {
        'query after the secret path': f'/private_abc?a=1%20{token}&token=%2Fv',
        'secret path inside a token value, then #': f'/x?token=abc/private_{token}#{_letters("after hash")}/x',
        'token value split by an encoded space': f';access_token=/{token[:half]}%20{token[half:]}>',
        'userinfo before a key value': f'http://user:{token}&key=@h.invalid/x',
    }


PLAIN = {'message': _shown(_plain_composition, _message_record),
         'argument': _shown(_plain_composition, _argument_record),
         'exception': _shown(_plain_composition, _exception_record),
         'access': _shown(_plain_composition, _access_record),
         'child': lambda text: OLD_DIAGNOSTICS.scrub_line(_paas_child(text))}  # the PaaS rules, then bb48449's line rules


@pytest.mark.parametrize('kind', list(TOKENS))
def test_counterexamples_fail_closed_where_bb48449_hid_the_value(kind):
    token = TOKENS[kind]
    for name, text in _counterexamples(token).items():
        values = [value for value in (token, _letters('after hash')) if value[:MIN_FRAGMENT] in text]
        guarded = []
        for place, (ha, paas, old) in PLACES.items():
            shown, hidden_before = ha(text), [value for value in values if _fragment(old(text), value) is None]
            assert all(_fragment(shown, value) is None for value in hidden_before), (name, place)  # stays hidden
            assert all(_fragment(shown, value) is None or _fragment(paas(text), value) is not None
                       for value in values), (name, place)  # never worse than the PaaS module alone
            if any(_fragment(PLAIN[place](text), value) is not None for value in hidden_before):
                assert log_redaction.AMBIGUOUS in shown, (name, place)  # the guard put the placeholder in
                guarded.append(place)
        assert guarded, name  # each input needs the guard somewhere
    hashed = _counterexamples(token)['secret path inside a token value, then #']
    assert '%' not in hashed and log_redaction.AMBIGUOUS in PLACES['message'][0](hashed)


def test_failing_closed_keeps_uvicorns_five_arguments_and_the_exception_shape():
    text = _counterexamples(TOKENS['hex'])['query after the secret path']
    record = _access_record(text)
    redact.scrub(record)
    assert record.args == ('127.0.0.1:5555', 'GET', log_redaction.AMBIGUOUS, '1.1', 404)
    failing = _exception_record(text)
    redact.scrub(failing)
    assert failing.exc_text == log_redaction.AMBIGUOUS and failing.getMessage() == 'request failed'
    argument = _argument_record(text)
    redact.scrub(argument)
    assert argument.getMessage() == log_redaction.AMBIGUOUS and argument.args == ()


def test_shows_hidden_compares_with_the_ha_rules_alone():
    token = TOKENS['urlsafe']
    text = f'/private_abc?a=1%20{token}&token=%2Fv'
    assert redact.shows_hidden(text, f'/private_[REDACTED] {token}&token=***')  # a decoded answer showing the token
    assert not redact.shows_hidden(text, redact.redact(text))  # the HA rule alone
    assert not redact.shows_hidden(text, log_redaction.AMBIGUOUS)
    assert not redact.shows_hidden(text, '/private_*** \u2026[truncated 9 chars]')
    plain = f'/x?a=1%20{token}&token=%2Fv'  # no secret path: the HA rule alone hides nothing, the PaaS answer may stay
    assert not redact.shows_hidden(plain, log_redaction.redact(plain))
    twice = f'/private_{token} and {token}'  # what the HA rule alone shows elsewhere too may stay
    assert not redact.shows_hidden(twice, f'/private_*** and {token}')
    hashed = f'/private_{token}#{VALUE}'  # no escape needed: the PaaS segment ends at #, the HA one does not
    assert redact.shows_hidden(hashed, f'/private_[REDACTED]#{VALUE}')
    child = f'http://user:{VALUE}&key=@h.invalid/x'
    assert redact.shows_hidden(child, f'http://user:{VALUE}&key=[REDACTED]', diagnostics.RULES)
    assert redact.apply_rules(child, diagnostics.RULES) == ('http://[REDACTED]@h.invalid/x', [f'http://user:{VALUE}&key=@'])


def test_the_guard_is_bounded_on_pathological_lines():
    """shows_hidden keeps only the pieces of what is shown and reads the original up to the PaaS module's own limit;
    every shape here stays far below the bound (each takes milliseconds; an unbounded check took seconds)."""
    rng = random.Random(20261115)
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    noise = ''.join(rng.choice(alphabet) for _ in range(512 * 1024))
    shapes = {
        'long text with an escape': noise + '%20',
        'many secret paths': ''.join(f'/private_{noise[i:i + 40]}%20x&token=%2Fv ' for i in range(0, 96000, 40)),
        'one long secret path': '/private_' + noise[:131000] + '?a=1%20b&token=%2Fv',
        'longer than the PaaS limit': '/private_' + noise + '?a=1%20b&token=%2Fv',
    }
    for name, text in shapes.items():
        started = time.perf_counter()
        redact.scrub(_message_record(text))
        diagnostics.scrub_line(text[:diagnostics.MAX_LINE])
        assert time.perf_counter() - started < 1.5, name


def test_composition_is_stable_on_the_corpora():
    """Scrubbing again (RedactSecretPaths after the record factory) never shows more, and the result is stable from the
    second pass on. The first pass can keep a backslash the PaaS module read as noise after the prefix:
    /private_\\<token> -> /private_\\*** (PaaS) -> /private_[REDACTED]\\*** (the HA rule stops at a backslash); the second
    pass reads [REDACTED]\\*** as the segment and gives /private_[REDACTED]."""
    texts = [*((token, text) for token in TOKENS.values() for text in _target_texts(token).values()),
             *((VALUE, text) for text in _query_texts(VALUE).values()),
             *((VALUE, template.format(name=name, value=VALUE)) for name in credential_names()
               for template in CREDENTIAL_TEMPLATES)]
    changed = Counter()
    for value, text in texts:
        passes = [redact.scrub_text(text)]
        record = _argument_record(text)
        records = []
        for _ in range(3):
            redact.scrub(record)
            records.append(record.getMessage())
        lines = [diagnostics.scrub_line(text)] if text.isprintable() else []
        # child output drops what is not printable after the scrub, as bb48449 does, which can join a token to the
        # mask in front of it (a decoded control character or Unicode space before it: the PaaS module and bb48449
        # show that token too); a second scrub then reads another text, so only printable lines are scrubbed again
        for scrub, results in ((redact.scrub_text, passes), (diagnostics.scrub_line, lines)):
            while results and len(results) < 3:
                results.append(scrub(results[-1]))
        for results in (passes, records, lines):
            if not results:
                continue
            assert results[2] == results[1], (text, results)
            first = _fragment(results[0], value) is not None
            assert all(first or _fragment(result, value) is None for result in results[1:]), (text, results)
            changed[results[1] != results[0]] += 1
    assert changed[False] > 10 * changed[True], changed  # almost every text is final after the first pass


# ---------------------------------------------------------------------------
# differential fuzz against bb48449 and the pinned PaaS module (seeded): what either hides stays hidden
# ---------------------------------------------------------------------------

_PREFIXES = ('/private_', '/private_', 'GET /private_', '"/private_', "'/private_", '//private_', '/x/private_',
             'http://h.invalid:8099/private_', '/p%72ivate_', '%2Fprivate_', '/private%5F', '\\private_', '/PRIVATE_',
             '/Private_', '/private_x/mcp?', '?token=', '&token=', ';access_token=', '?api_key=', '?key=', '&secret=',
             '?password=', 'token=', 'key=', 'Bearer ', 'password: ', 'http://user:', '?a=1&', '/x?q=', ' ')
_JOINS = ('', '', '', '', '%20', '%22', '%3F', '?', '/', '//', "'", '"', ' ', '%2F', '%25', '%', '\\', '<', '>',
          '&', ';', '=', '#', '%E3%80%80', '\ufffd', '*', '%5C', '+', '@', '%26', '%3D', '%23', '/private_', '&key=',
          '?token=', '%3Ftoken%3D', '&tail=', ':')
_TAILS = ('/mcp', '', '', '/mcp?x=1', '/sse?session_id=1', ' HTTP/1.1', '"', "'", '>', '%20/mcp', '/mcp ', '?',
          '&token=', '%zz', '/mcp#f', '&tail=1', ';x', '/messages/?session_id=abc', '@h.invalid/x', '#', '&')
_FILLERS = ('', '', 'proxy POST ', 'library echo ', 'url ', '[mcp-server] ', 'x=1 ', 'HTTP Request: GET ')
FUZZ_VALUES = (*(_letters(f'fuzz value {i}', 24) for i in range(8)), *(_digest(f'fuzz hex {i}').hex() for i in range(3)))


def _fuzz_text(rng: random.Random, values) -> str:
    parts = []
    for _ in range(rng.randint(1, 3)):
        value = rng.choice(values)
        cut = rng.randint(0, len(value))
        parts.append(rng.choice(_FILLERS) + rng.choice(_PREFIXES) + rng.choice(_JOINS) + value[:cut]
                     + rng.choice(_JOINS if rng.random() < .35 else ('',)) + value[cut:]
                     + rng.choice(_JOINS if rng.random() < .3 else ('',))
                     + (rng.choice(values) if rng.random() < .15 else '') + rng.choice(_TAILS))
    return rng.choice((' ', '', ' and ', '&', '#')).join(parts)


@pytest.mark.parametrize('seed', [20261114, 20261115])
def test_differential_fuzz_never_shows_what_bb48449_or_the_pinned_paas_module_hides(seed):
    """Every synthetic value in a generated line that bb48449 hides, or the pinned PaaS module hides, in a place stays
    hidden there (the guard of redact.shows_hidden keeps the first; the order keeps the second)."""
    rng = random.Random(seed)
    hidden_before, hidden_by_paas, regressed, worse = Counter(), Counter(), [], []
    for _ in range(1200):
        values = rng.sample(FUZZ_VALUES, 3)
        text = _fuzz_text(rng, values)
        for place, (ha, paas, old) in PLACES.items():
            shown, by_paas, before = ha(text), paas(text), old(text)
            for value in set(values):
                if _fragment(text, value) is None:
                    continue
                shows = _fragment(shown, value) is not None
                if _fragment(before, value) is None:
                    hidden_before[place] += 1
                    if shows:
                        regressed.append((place, FUZZ_VALUES.index(value), text.replace(value, '<value>')))
                if _fragment(by_paas, value) is None:
                    hidden_by_paas[place] += 1
                    if shows:
                        worse.append((place, FUZZ_VALUES.index(value), text.replace(value, '<value>')))
    assert not regressed, regressed[:5]
    assert not worse, worse[:5]
    for counts in (hidden_before, hidden_by_paas):  # the fuzz has bite: many values were hidden by the reference
        assert min(counts[place] for place in PLACES) >= 200, counts
