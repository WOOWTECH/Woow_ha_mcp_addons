"""Odoo chatter_post: the preview's approval object, sent back unchanged with confirm=true, is accepted.

The pinned child's preview answers approval = {model, method, record_ids, kwargs, instance, token} and its text says
"Re-call chatter_post with the returned approval and confirm=true". Up to 0.1.14 the gateway's Approval model accepted
only {token} (additionalProperties false), so doing exactly that was always -32602 Invalid params.

0.2.0 serves the full child surface: the arguments reach the child unchanged and the child checks the token against
the payload it rebuilds from the call (a foreign or stale approval fails there, never posts). The real child round
trip (preview, then the whole approval back) is in tests/test_expansion_runtime.py. The bounded 0.1.x model (still
in BOUNDED_TOOLS) accepts the preview object as well.
"""
import copy
import json

import pytest

from mcp_admin_core.expansion import Approval, Chatter
from mcp_admin_core.policy import ToolCallRefused, authorize, declared_schema
from mcp_admin_core.products import BOUNDED_TOOLS, ProductState, TOOLS
from test_expansion_policy import call

TOKEN = 'odoo-write:' + '0123456789abcdef' * 2
CALL = {'model': 'res.partner', 'record_id': 7, 'body': '  Owned test comment  '}
# Exactly what tools_write.chatter_post previews for CALL (body stripped, instance resolved to 'default').
PREVIEW_APPROVAL = {'model': 'res.partner', 'method': 'message_post', 'record_ids': [7],
                    'kwargs': {'body': 'Owned test comment', 'message_type': 'comment'},
                    'instance': 'default', 'token': TOKEN}


def state(grants=('chatter_post',)):
    return ProductState(product='odoo', token='a' * 43, child_token='b' * 43, enabled_write_tools=list(grants))


def confirm(approval, **changes):
    return call('chatter_post', {**CALL, **changes, 'approval': approval, 'confirm': True})


@pytest.mark.parametrize('approval', [PREVIEW_APPROVAL, {'token': TOKEN}], ids=['preview-unchanged', 'token-only'])
def test_full_surface_forwards_the_returned_approval_unchanged(approval):
    message = confirm(copy.deepcopy(approval))
    forwarded = copy.deepcopy(message['params']['arguments'])
    assert authorize(message, TOOLS['odoo'], state()) == 'tools/call'
    assert message['params']['arguments'] == forwarded


def test_full_surface_still_needs_the_write_grant():
    with pytest.raises(ToolCallRefused) as refused:
        authorize(confirm(copy.deepcopy(PREVIEW_APPROVAL)), TOOLS['odoo'], state(grants=()))
    assert refused.value.kind == 'unknown_tool'


# The bounded 0.1.x model (BOUNDED_TOOLS) keeps the fix: members accepted, checked against the call, not forwarded.
@pytest.mark.parametrize('approval', [PREVIEW_APPROVAL, {'token': TOKEN}], ids=['preview-unchanged', 'token-only'])
def test_bounded_model_confirms_and_forwards_only_the_token(approval):
    message = confirm(copy.deepcopy(approval))
    assert authorize(message, BOUNDED_TOOLS['odoo'], state()) == 'tools/call'
    forwarded = message['params']['arguments']
    assert forwarded['approval'] == {'token': TOKEN}
    assert forwarded['confirm'] is True and forwarded['body'] == CALL['body']
    assert authorize(message, BOUNDED_TOOLS['odoo'], state()) == 'tools/call'  # idempotent
    assert message['params']['arguments'] == forwarded


@pytest.mark.parametrize('member,value', [
    ('record_ids', [8]), ('record_ids', [7, 8]), ('model', 'res.users'), ('method', 'write'),
    ('kwargs', {'body': 'Another comment', 'message_type': 'comment'}),
    ('kwargs', {'body': 'Owned test comment', 'message_type': 'notification'}),
    ('kwargs', {'body': 'Owned test comment', 'message_type': 'comment', 'partner_ids': [1]}),
    ('instance', 'other'), ('unknown', 1)])
def test_bounded_model_refuses_a_preview_for_another_call(member, value):
    approval = {**copy.deepcopy(PREVIEW_APPROVAL), member: value}
    with pytest.raises(ToolCallRefused) as refused:
        authorize(confirm(approval), BOUNDED_TOOLS['odoo'], state())
    error = refused.value.error()
    assert error['code'] == -32602 and error['message'] == 'Invalid params'
    assert 'Another comment' not in json.dumps(error) and 'res.users' not in json.dumps(error)


def test_bounded_declared_schema_describes_the_preview_members():
    schema = declared_schema(Chatter)
    approval = schema['$defs']['Approval']
    assert set(approval['properties']) == {'token', 'model', 'method', 'record_ids', 'kwargs', 'instance'}
    assert approval['required'] == ['token'] and approval['additionalProperties'] is False
    assert Approval.model_validate(PREVIEW_APPROVAL).model_dump(mode='json') == {'token': TOKEN}
