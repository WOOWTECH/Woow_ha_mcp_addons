"""Odoo chatter_post: the preview's approval object, sent back unchanged with confirm=true, is accepted.

The pinned child's preview answers approval = {model, method, record_ids, kwargs, instance, token} and its text says
"Re-call chatter_post with the returned approval and confirm=true". Up to 0.1.14 the gateway's Approval model accepted
only {token} (additionalProperties false), so doing exactly that was always -32602 Invalid params. The real child
round trip (preview, then the whole approval back) is in tests/test_expansion_runtime.py.
"""
import copy
import json

import pytest

from mcp_admin_core.expansion import Approval, Chatter
from mcp_admin_core.policy import ToolCallRefused, authorize, declared_schema
from mcp_admin_core.products import ProductState, TOOLS
from test_expansion_policy import call

TOKEN = 'odoo-write:' + '0123456789abcdef' * 2
CALL = {'model': 'res.partner', 'record_id': 7, 'body': '  Owned test comment  '}
# Exactly what tools_write.chatter_post previews for CALL (body stripped, instance resolved to 'default').
PREVIEW_APPROVAL = {'model': 'res.partner', 'method': 'message_post', 'record_ids': [7],
                    'kwargs': {'body': 'Owned test comment', 'message_type': 'comment'},
                    'instance': 'default', 'token': TOKEN}


def state():
    return ProductState(product='odoo', token='a' * 43, child_token='b' * 43, enabled_write_tools=['chatter_post'])


def confirm(approval, **changes):
    return call('chatter_post', {**CALL, **changes, 'approval': approval, 'confirm': True})


@pytest.mark.parametrize('approval', [PREVIEW_APPROVAL, {'token': TOKEN}], ids=['preview-unchanged', 'token-only'])
def test_the_returned_approval_confirms_and_only_the_token_is_forwarded(approval):
    message = confirm(copy.deepcopy(approval))
    assert authorize(message, TOOLS['odoo'], state()) == 'tools/call'
    forwarded = message['params']['arguments']
    assert forwarded['approval'] == {'token': TOKEN}  # the child reads approval['token'] only
    assert forwarded['confirm'] is True and forwarded['body'] == CALL['body']
    # Authorization stays idempotent (the gateway authorizes again on fresh state inside the slot).
    assert authorize(message, TOOLS['odoo'], state()) == 'tools/call'
    assert message['params']['arguments'] == forwarded


def test_preview_with_instance_given_explicitly():
    message = confirm(copy.deepcopy(PREVIEW_APPROVAL), instance='default')
    assert authorize(message, TOOLS['odoo'], state()) == 'tools/call'


@pytest.mark.parametrize('member,value', [
    ('record_ids', [8]), ('record_ids', [7, 8]), ('model', 'res.users'), ('method', 'write'),
    ('kwargs', {'body': 'Another comment', 'message_type': 'comment'}),
    ('kwargs', {'body': 'Owned test comment', 'message_type': 'notification'}),
    ('kwargs', {'body': 'Owned test comment', 'message_type': 'comment', 'partner_ids': [1]}),
    ('instance', 'other'), ('unknown', 1)])
def test_a_preview_for_another_call_or_an_unknown_member_is_refused(member, value):
    approval = {**copy.deepcopy(PREVIEW_APPROVAL), member: value}
    with pytest.raises(ToolCallRefused) as refused:
        authorize(confirm(approval), TOOLS['odoo'], state())
    error = refused.value.error()
    assert error['code'] == -32602 and error['message'] == 'Invalid params'
    assert 'Another comment' not in json.dumps(error) and 'res.users' not in json.dumps(error)


def test_without_the_write_grant_the_confirmation_is_still_refused():
    message = confirm(copy.deepcopy(PREVIEW_APPROVAL))
    denied = ProductState(product='odoo', token='a' * 43, child_token='b' * 43)
    with pytest.raises(ToolCallRefused) as refused:
        authorize(message, TOOLS['odoo'], denied)
    assert refused.value.kind == 'unknown_tool'


def test_declared_schema_describes_the_preview_members():
    schema = declared_schema(Chatter)
    approval = schema['$defs']['Approval']
    assert set(approval['properties']) == {'token', 'model', 'method', 'record_ids', 'kwargs', 'instance'}
    assert approval['required'] == ['token'] and approval['additionalProperties'] is False
    assert Approval.model_validate(PREVIEW_APPROVAL).model_dump(mode='json') == {'token': TOKEN}
