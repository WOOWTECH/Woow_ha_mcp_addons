"""Local bounded metadata subset; not a general config or key-material view.

The five existing handlers keep their source API routes/parameter names. Only
these calls use this projection. No fallback endpoints, retries or auto paging.
"""
import asyncio
import json
import math
import re

from backend_policy import public_backend_error
from output_policy import record
from .errors import LiteLLMApiError

MAX_BYTES = 256 * 1024
TIMEOUT = 5
ROLES = ('proxy_admin', 'proxy_admin_viewer', 'internal_user', 'internal_user_viewer')
MODES = ('chat', 'completion', 'embedding', 'image_generation', 'image_edit',
         'audio_transcription', 'audio_speech', 'moderation', 'rerank', 'video_generation', 'search')
SEGMENT = r'^[A-Za-z0-9_-]+$'
GROUP = r'^[A-Za-z0-9][A-Za-z0-9_./:-]*$'
PATHS = frozenset(('/model/info', '/model_group/info', '/team/info', '/user/list', '/user/info'))


def invalid():
    raise LiteLLMApiError('BACKEND_INVALID_RESPONSE')


def identifier(value, *, group=False):
    if (type(value) is not str or not 1 <= len(value) <= (256 if group else 128)
            or re.fullmatch(GROUP if group else SEGMENT, value) is None):
        raise ValueError('invalid metadata identifier')
    return value


def user_params(page, page_size, role, user_ids, user_email, team, sort_by, sort_order):
    if (type(page) is not int or not 1 <= page <= 10000
            or type(page_size) is not int or not 1 <= page_size <= 100
            or role is not None and role not in ROLES
            or any(v is not None for v in (user_email, sort_by, sort_order))):
        raise ValueError('invalid metadata pagination/filter')
    params = {'page': page, 'page_size': page_size}
    if role is not None:
        params['role'] = role
    if team is not None:
        params['team'] = identifier(team)
    if user_ids is not None:
        if type(user_ids) is not list or not 1 <= len(user_ids) <= 20:
            raise ValueError('invalid metadata user ids')
        params['user_ids'] = ','.join(identifier(v) for v in user_ids)
    return params


def bounded_shape(value, depth=0, budget=None):
    # Includes excluded fields: unknown data cannot hide unbounded nesting/lists.
    if budget is None:
        budget = [10000]
    budget[0] -= 1
    if depth > 8 or budget[0] < 0:
        invalid()
    if type(value) is dict:
        if len(value) > 128:
            invalid()
        for key, item in value.items():
            if len(key) > 256:
                invalid()
            bounded_shape(item, depth + 1, budget)
    elif type(value) is list:
        if len(value) > 100:
            invalid()
        for item in value:
            bounded_shape(item, depth + 1, budget)
    elif type(value) is str:
        if len(value) > 16384:
            invalid()
    elif type(value) in (int, float):
        if not math.isfinite(value) or abs(value) > 1e15:
            invalid()
    elif value is not None and type(value) is not bool:
        invalid()


def object_body(value):
    if type(value) is not dict or value.get('error') is not None:
        invalid()
    return value


def scalar_record(body, fields, required=()):
    """Validate selected fields before reusing the reviewed positive projector.

    Missing optional data remains omitted (never fabricated as a default/null).
    Unknown fields are excluded. Present wrong types fail, not silently vanish.
    """
    object_body(body)
    for key in required:
        if key not in body or body[key] is None:
            invalid()
    for key, kind in fields.items():
        if key not in body or body[key] is None:
            continue
        v = body[key]
        if kind == 'id':
            try:
                identifier(v)
            except ValueError:
                invalid()
        elif kind == 'group':
            try:
                identifier(v, group=True)
            except ValueError:
                invalid()
        elif kind == 'text':
            if type(v) is not str or not 1 <= len(v) <= 256 or any(ord(c) < 32 for c in v):
                invalid()
        elif kind == 'number':
            if type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1e15:
                invalid()
        elif kind == 'bool':
            if type(v) is not bool:
                invalid()
        elif kind == 'role':
            if type(v) is not str or v not in ROLES:
                invalid()
        elif kind == 'mode':
            if type(v) is not str or v not in MODES:
                invalid()
    return record(body, [key for key in fields if key in body])


LIMITS = {'max_budget': 'number', 'tpm_limit': 'number', 'rpm_limit': 'number'}
USER = {'user_id': 'id', 'user_alias': 'text', 'user_role': 'role', **LIMITS}
TEAM = {'team_id': 'id', 'team_alias': 'text', **LIMITS, 'blocked': 'bool'}
MODEL = {'id': 'id', 'mode': 'mode', 'max_input_tokens': 'number', 'max_output_tokens': 'number'}
MODEL_GROUP = {'model_group': 'group', 'mode': 'mode', 'max_input_tokens': 'number',
               'max_output_tokens': 'number', 'tpm': 'number', 'rpm': 'number'}


def project(path, body, params):
    bounded_shape(body)
    object_body(body)
    if path in ('/model/info', '/model_group/info'):
        data = body.get('data')
        # Explicit single selector only: empty, multiple or mismatched rows are
        # not silently converted to success. Unfiltered enumeration is withheld.
        if type(data) is not list or len(data) != 1:
            invalid()
        row = object_body(data[0])
        if path == '/model/info':
            result = scalar_record(row, {'model_name': 'text'}, ('model_name',))
            info = scalar_record(row.get('model_info'), MODEL, ('id',))
            if info['id'] != params['litellm_model_id']:
                invalid()
            result['model_info'] = info
        else:
            result = scalar_record(row, MODEL_GROUP, ('model_group',))
            if result['model_group'] != params['model_group']:
                invalid()
        return {'data': [result]}
    if path in ('/team/info', '/user/info'):
        key, fields = ('team', TEAM) if path == '/team/info' else ('user', USER)
        identity, envelope = key + '_id', key + '_info'
        info = scalar_record(body.get(envelope), fields, (identity,))
        if body.get(identity) != params[identity] or info[identity] != params[identity]:
            invalid()
        return {identity: params[identity], envelope: info}
    if path != '/user/list':
        invalid()
    data = body.get('users')
    if type(data) is not list or len(data) > params['page_size']:
        invalid()
    for key in ('total', 'page', 'page_size', 'total_pages'):
        if type(body.get(key)) is not int or not 0 <= body[key] <= 2147483647:
            invalid()
    if body['page'] != params['page'] or body['page_size'] != params['page_size']:
        invalid()
    if body['total_pages'] != (body['total'] + body['page_size'] - 1) // body['page_size']:
        invalid()
    if len(data) > body['total'] or (not data and body['total'] > (body['page']-1)*body['page_size']):
        invalid()
    result = {'users': [scalar_record(row, USER, ('user_id',)) for row in data]}
    result.update(record(body, ('total', 'page', 'page_size', 'total_pages')))
    return result


async def read_metadata(handle, path, params):
    """Borrow the existing scoped/DNS-pinned client; one bounded streaming GET.

    Identity transfer only, max 256 KiB, five seconds total. This is local to
    LiteLLM metadata; other transport/error behavior is deliberately unchanged.
    """
    if path not in PATHS:
        raise ValueError('unsupported metadata path')
    try:
        async with asyncio.timeout(TIMEOUT):
            async with handle.raw.stream('GET', path, params=params,
                                         headers={'Accept-Encoding': 'identity'}) as response:
                if not response.is_success:
                    raise LiteLLMApiError(f'BACKEND_HTTP_ERROR status={response.status_code}')
                if response.headers.get('content-encoding', 'identity').strip().lower() != 'identity':
                    invalid()
                data = bytearray()
                # aiter_bytes also handles pre-buffered MockTransport responses.
                # Identity-only above means no response decompression is allowed.
                async for chunk in response.aiter_bytes():
                    if len(data) + len(chunk) > MAX_BYTES:
                        invalid()
                    data.extend(chunk)
        body = json.loads(data)
        return project(path, body, params)
    except LiteLLMApiError:
        raise
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise LiteLLMApiError('BACKEND_INVALID_RESPONSE') from None
    except Exception as exc:
        raise LiteLLMApiError(public_backend_error(exc)) from None
