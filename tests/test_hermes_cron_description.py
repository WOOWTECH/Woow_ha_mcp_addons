"""HM-33 (multi-profile plan 12.3; PaaS #156, woow-mcp-server 34769c2): hermes_cron's description says what Hermes does
with a paused job.

PaaS added two sentences to the tool's description and changed nothing else (text only; the docstring-free syntax tree
of server.py is the one before):

- create: enabled=false creates the job paused, so it does not run until resumed. The child sends paused=not enabled
  together with enabled in its one POST (PaaS #138; in the add-on since PR #85, merged 2026-11-12, which the released
  Hermes 0.4.13 does not have yet: it ships with the next release. tests/test_hermes_cron_paused_contract.py checks
  the request).
- trigger: Hermes v0.22.x also resumes a paused job when it is triggered, so a caller that wants it to stay paused
  calls pause afterwards. PaaS measured it on 2026-11-16 against the real Hermes Agent v0.22.5 (the image PaaS
  production runs); calling the Agent API directly does the same, so it is upstream behaviour. The child's trigger is
  one POST .../trigger, as before; it does not pause or resume the job by itself (the last test here; HM-33 review
  S-1).

The add-on lists PaaS's text character for character, in both places a client gets it from: the vendored child's own
tools/list (in its pinned venv, as CI installs it) and the gateway's packaged listing (tool_snapshot.py, the answer when
no child can give one; tests/test_tool_snapshot.py keeps it equal to the real child). The rest of the description stays
as it was. Notes: docs/provenance/ha-multiprofile-HM-33-20261117.md.
"""
import json
from pathlib import Path
import subprocess

import pytest

from log_scan import log_scan  # noqa: F401  (fixture)
from mcp_admin_core.tool_snapshot import LISTED
from test_hermes_safe_public_errors import _direct_call
from test_six_hardening import Quiet, runtime, serve
from switch_modes import switched_off  # noqa: F401  (fixture: the switch these tests pin)

pytestmark = pytest.mark.usefixtures('log_scan', 'switched_off')  # rule 3 of the slice rules: every new test runs under the log scan
ROOT = Path(__file__).resolve().parents[1]
# The two sentences, unwrapped.
SENTENCES = (
    'enabled=false creates it paused, so it does not run until resumed',
    'Hermes v0.22.x also resumes a paused job when it is triggered; call pause afterwards if it should stay paused',
)
# What the two sentences add to the description, wrapped as the PaaS docstring wraps them (34769c2,
# apps/hermes/hermes_mcp_server/server.py hermes_cron), and where.
ADDED = (
    ('- create: new job (requires name, schedule, prompt)',
     '; enabled=false creates\n  it paused, so it does not run until resumed'),
    ('- trigger: run job now (requires job_id)',
     '. Hermes v0.22.x also resumes a\n  paused job when it is triggered; call pause afterwards if it should\n'
     '  stay paused'),
)
# The description as PaaS 34769c2 has it, character for character (the docstring as the child lists it: Python 3.13
# strips the common indentation, the line after the last one leaves the final newline).
PAAS = ("Manage Hermes cron/scheduled jobs.\n"
        "\n"
        "Actions: list, create, update, delete, trigger, pause, resume\n"
        "- list: show all cron jobs\n"
        "- create: new job (requires name, schedule, prompt); enabled=false creates\n"
        "  it paused, so it does not run until resumed\n"
        "- update: modify job (requires job_id, plus fields to change)\n"
        "- delete: remove job (requires job_id)\n"
        "- trigger: run job now (requires job_id). Hermes v0.22.x also resumes a\n"
        "  paused job when it is triggered; call pause afterwards if it should\n"
        "  stay paused\n"
        "- pause / resume: toggle job state (requires job_id)\n"
        "\n"
        "schedule uses cron syntax: '0 9 * * 1-5' = weekdays at 9am\n")
# The description before HM-33 (claude-delivery 7646f0f), the same as PaaS before #156.
BEFORE = ("Manage Hermes cron/scheduled jobs.\n"
          "\n"
          "Actions: list, create, update, delete, trigger, pause, resume\n"
          "- list: show all cron jobs\n"
          "- create: new job (requires name, schedule, prompt)\n"
          "- update: modify job (requires job_id, plus fields to change)\n"
          "- delete: remove job (requires job_id)\n"
          "- trigger: run job now (requires job_id)\n"
          "- pause / resume: toggle job state (requires job_id)\n"
          "\n"
          "schedule uses cron syntax: '0 9 * * 1-5' = weekdays at 9am\n")
# hermes_cron's own tools/list in the vendored child, in the venv CI installs (apps/hermes/.venv); the import path is
# the one products.child_spec gives the child. Importing the server makes no request.
CHILD = '''
import asyncio, json
from hermes_mcp_server.server import mcp
[tool] = [tool for tool in asyncio.run(mcp.list_tools()) if tool.name == 'hermes_cron']
print(json.dumps({'description': tool.description, 'inputSchema': tool.input_schema}))
'''


def assert_paas_text(description):
    assert description == PAAS
    flat = ' '.join(description.split())
    for sentence in SENTENCES:
        assert flat.count(sentence) == 1, sentence
    removed = description
    for line, addition in ADDED:
        assert removed.count(line + addition + '\n') == 1, line
        removed = removed.replace(line + addition + '\n', line + '\n')
    assert removed == BEFORE  # only the two sentences changed


def test_the_child_lists_the_paas_text():
    env = {'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1',
           'PYTHONPATH': str(ROOT / 'apps/hermes/vendor') + ':' + str(ROOT / 'apps/runtime')}
    done = subprocess.run([str(ROOT / 'apps/hermes/.venv/bin/python'), '-c', CHILD], env=env, capture_output=True,
                          text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-3000:]
    listed = json.loads(done.stdout.splitlines()[-1])
    assert_paas_text(listed['description'])
    # The parameter the first sentence names: enabled, a boolean that defaults to true (a job runs unless asked not to).
    assert listed['inputSchema']['properties']['enabled'] == {'default': True, 'title': 'Enabled', 'type': 'boolean'}


def test_the_gateways_packaged_listing_carries_the_same_text():
    [tool] = [tool for tool in LISTED['hermes'] if tool['name'] == 'hermes_cron']
    assert_paas_text(tool['description'])
    assert tool['inputSchema']['properties']['enabled'] == {'default': True, 'title': 'Enabled', 'type': 'boolean'}


async def test_trigger_is_one_post_and_never_pauses_or_resumes_by_itself(tmp_path):
    """The second sentence's advice (call pause afterwards to keep the job paused) holds only while the child's trigger
    is exactly one POST /api/cron/jobs/<id>/trigger: no pause, resume or second trigger of its own, before or after
    (HM-33 review S-1). Real Hermes child, fake dashboard that records every request it gets."""
    events = []

    class Dashboard(Quiet):
        def record(self):
            events.append((self.command, self.path))

        def do_POST(self):
            self.record()
            if self.path == '/auth/password-login':
                self.send_response(200)
                self.send_header('Set-Cookie', 'hermes_session_at=synthetic-cookie')
                self.send_header('Content-Length', '2')
                self.end_headers()
                self.wfile.write(b'{}')
                return
            self.reply({'ok': True})

        def do_GET(self):
            self.record()
            self.reply({})

        do_PUT = do_DELETE = do_PATCH = do_GET

    with serve(Dashboard) as base:
        async with runtime(tmp_path, 'hermes', base, write_grants=('hermes_cron:trigger',)) as (
            _client, _headers, _store, manager, child
        ):
            reply = await _direct_call(child, manager.endpoint, 'hermes_cron',
                                       {'action': 'trigger', 'job_id': 'synthetic-job'}, 103)

    assert reply['isError'] is False
    assert json.loads(reply['content'][0]['text']) == {'ok': True, 'triggered': 'synthetic-job'}
    assert events == [('POST', '/auth/password-login'), ('POST', '/api/cron/jobs/synthetic-job/trigger')]
