"""PaaS #160 (woow-mcp-server fb7571c): emqx_list_topics no longer says that a topic missing from its answer has no
subscriber.

The tool lists the broker's routes (GET /topics). A wildcard subscription is one route keyed by its filter ('a/#'), not
one route per concrete topic it covers, and shared or persisted-session subscriptions may not show up either. The old
text claimed the opposite ("A topic missing here means nobody is subscribed - which is the usual reason a published
message appears to vanish"), which sends a model to the wrong conclusion. PaaS replaced the two texts that carry it and
changed nothing else (text only: without docstrings the syntax trees of topics.py and registry.py are the ones before).

The add-on lists PaaS's text character for character in each place a client or a page gets it from:

- the vendored child's own tools/list (in its pinned venv, as CI installs it; the docstring is the tool's description);
- the vendored registry's one-line description of the tool (what PaaS's admin page shows; the add-on's own panel reads
  its tool catalog from the gateway's listing, not from this registry, so it is pinned at its source);
- the gateway's packaged listing (tool_snapshot.py, the answer when no child can give one; tests/test_tool_snapshot.py
  keeps it equal to the real child).

The three assertions of PaaS's test (test_subscription_match_topic.py, the case added by #160) run on the child's text
too. Notes: docs/provenance/emqx-topics-wording-20261125.md.
"""
import json
from pathlib import Path
import subprocess

import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core.tool_snapshot import LISTED

pytestmark = pytest.mark.usefixtures('log_scan')  # rule 3 of the slice rules: every new test runs under the log scan
ROOT = Path(__file__).resolve().parents[1]
TOOL = 'emqx_list_topics'
# The tool's description as PaaS fb7571c has it, character for character (the docstring as the child lists it: the
# common indentation is stripped and nothing follows the last line).
PAAS_DESCRIPTION = (
    "Routes currently present in the cluster (topics or topic filters).\n"
    "\n"
    "A wildcard subscription such as 'a/#' appears under the filter\n"
    "itself, not under the concrete topics it covers, and shared or\n"
    "persisted-session subscriptions may not appear either. So a\n"
    "concrete topic missing here does not mean that nobody is\n"
    "subscribed. To work out who receives messages published to a\n"
    "topic, use emqx_list_subscriptions.")
# The registry's one-line description as PaaS fb7571c has it.
PAAS_REGISTRY = ("Routes currently present in the cluster. A wildcard subscription shows as its filter, so a missing "
                 "concrete topic does not mean nobody is subscribed.")
# What the two texts said before (claude-delivery 092b1b5, the same as PaaS before #160), whitespace squashed and
# lower-cased.
OLD_CLAIMS = (
    'topics that currently have a route (i.e. at least one subscriber)',
    'a topic missing here means nobody is subscribed',
    'usual reason a published message appears to vanish',
    'routed topics currently present in the cluster',
)
# The vendored child's own tools/list and registry, in the venv CI installs (apps/emqx/.venv); the import path is the
# one products.child_spec gives the child. Importing the server makes no request.
CHILD = '''
import asyncio, json
from emqx_mcp_server.registry import TOOLS_BY_NAME
from emqx_mcp_server.server import mcp
listed = asyncio.run(mcp.list_tools(run_middleware=False))
print(json.dumps({'tools': {tool.name: tool.description for tool in listed},
                  'registry': {name: spec.description for name, spec in TOOLS_BY_NAME.items()}}))
'''


def squash(text):
    return ' '.join((text or '').split())


@pytest.fixture(scope='module')
def child(tmp_path_factory):
    work = tmp_path_factory.mktemp('emqx-topics')
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(work), 'PYTHONDONTWRITEBYTECODE': '1',
           'PYTHONPATH': str(ROOT / 'apps/emqx/vendor') + ':' + str(ROOT / 'apps/runtime'),
           'FASTMCP_CHECK_FOR_UPDATES': 'off', 'FASTMCP_SHOW_SERVER_BANNER': 'false'}
    done = subprocess.run([str(ROOT / 'apps/emqx/.venv/bin/python'), '-c', CHILD], env=env, cwd=work,
                          capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    assert done.returncode == 0, done.stderr[-3000:]
    return json.loads(done.stdout.splitlines()[-1])


def test_the_child_lists_the_paas_description(child):
    assert child['tools'][TOOL] == PAAS_DESCRIPTION


def test_a_missing_topic_is_not_said_to_mean_nobody_is_subscribed(child):
    """The case PaaS #160 added to test_subscription_match_topic.py, on the child's text."""
    whole = squash(child['tools'][TOOL]).lower()
    assert 'means nobody is subscribed' not in whole
    assert 'does not mean that nobody is subscribed' in whole
    assert 'wildcard subscription' in whole and 'emqx_list_subscriptions' in whole


def test_the_text_points_at_a_tool_the_child_lists(child):
    """The text sends the reader to emqx_list_subscriptions to find out who receives a topic: it has to be listed."""
    assert 'emqx_list_subscriptions' in child['tools']


def test_the_registry_carries_the_paas_text(child):
    assert child['registry'][TOOL] == PAAS_REGISTRY
    assert 'does not mean nobody is subscribed' in squash(child['registry'][TOOL]).lower()


def test_the_gateways_packaged_listing_carries_the_same_text():
    [tool] = [tool for tool in LISTED['emqx'] if tool['name'] == TOOL]
    assert tool['description'] == PAAS_DESCRIPTION


def test_no_text_keeps_the_old_claim(child):
    [packaged] = [tool for tool in LISTED['emqx'] if tool['name'] == TOOL]
    for where, text in (('child', child['tools'][TOOL]), ('registry', child['registry'][TOOL]),
                        ('packaged listing', packaged['description'])):
        for claim in OLD_CLAIMS:
            assert claim not in squash(text).lower(), (where, claim)
