"""Source-guarded B2 facade: constrain RPCs BEFORE genuine Odoo handlers run.

No global client monkeypatch; old handlers keep their reviewed behavior. Only
projected metadata is cached (two keys), attached to the actual lifespan/client.
Counts use Odoo's credential/record-rule/default active context, not sudo.
"""
import functools
import hashlib
from pathlib import Path
from types import SimpleNamespace

MODEL = 'res.partner'
FIELD_TYPES = {'id': 'integer', 'name': 'char', 'display_name': 'char', 'active': 'boolean',
               'parent_id': 'many2one', 'child_ids': 'one2many'}
ATTRIBUTES = ['type', 'required', 'readonly', 'store', 'relation']
SOURCES = {
    'tools_read': '4c8bf33b35c54757b93f0cc367b4f5027488ca8fbf63f68c1241f1a4be784de0',
    'tools_diagnostics': '957f3affa479cb079350de8874064d89594ab0661cfbfd7675b7f26930d32772',
    'diagnostics': '1fb1632cc711a7dfa4d5f6700472abeaffb897a094a4c399c21ce045aebb0dc7',
    'tools_data_quality': '5a0b35eb4d5196321dbba042d89afe2d62d1e8e4d51337b6a54999e108ecaa34',
    'data_quality': 'c939be7370cd797abdb079513c1949339445c1e6aa3b9bb3d06a075924b1c3fe',
    'server_core': 'b6872eb7dd7e4b937ebb8dd0ae2b80e29a79a3e34f2beaeaf092f0d9b2b79c03',
    'odoo_client': '8bd06a523cb8049f14f54d06d9b73c3d7787108e7e78cf58bfb725ec9a97f74d',
    'field_policy': 'f6763bd2d5eca68445cdc4302b68fcd38cf145f608de16a12b00e2ac1a7dd978',
    'tool_helpers': '51276e68897d45f812048400d79100ba1a6a589de05fc7c50dff96d4c9596e64',
}
DEFAULTS = {
    'schema_catalog': dict(query=None, models=[MODEL], include_fields=False, refresh=False, limit=1, instance=None),
    'inspect_model_relationships': dict(fields_metadata=None, include_readonly=True, include_computed=True,
                                        use_live_metadata=True, instance=None),
    'data_quality_report': dict(checks=['missing_required'], key_fields=['name'], sample_limit=100, instance=None),
}


def require(condition):
    if not condition:
        raise ValueError('BACKEND_RESPONSE_INVALID')


def arguments(name, values):
    """Defense in depth on the private child; parent owns the public schema."""
    defaults = DEFAULTS[name]
    require(set(values) <= set(defaults) | ({'model'} if name != 'schema_catalog' else set()))
    args = {**defaults, **values}
    require(args['instance'] in (None, 'default'))
    if name == 'schema_catalog':
        require(args['query'] is None and args['models'] == [MODEL])
        require(type(args['models']) is list and type(args['limit']) is int and args['limit'] == 1)
        require(type(args['include_fields']) is bool and type(args['refresh']) is bool)
    else:
        require(args.get('model') == MODEL)
        if name == 'inspect_model_relationships':
            require(args['fields_metadata'] is None and args['use_live_metadata'] is True)
            require(args['include_computed'] is True and type(args['include_readonly']) is bool)
        else:
            require(type(args['checks']) is list and args['checks'] == ['missing_required'])
            require(type(args['key_fields']) is list and args['key_fields'] == ['name'])
            require(type(args['sample_limit']) is int and 1 <= args['sample_limit'] <= 100)
    # Avoid a second upstream named-client cache for the same default credential.
    args['instance'] = None
    return args


def metadata(raw, names):
    require(type(raw) is dict and 'error' not in raw)
    result = {}
    for name in names:
        if name not in raw:
            continue  # genuine Odoo fields_get may omit unavailable fields
        value = raw[name]
        require(type(value) is dict and value.get('type') == FIELD_TYPES[name])
        entry = {'type': value['type']}
        for flag in ('required', 'readonly', 'store'):
            if flag in value:
                require(type(value[flag]) is bool)
                entry[flag] = value[flag]
        if name in ('parent_id', 'child_ids'):
            require(value.get('relation') == MODEL)
            entry['relation'] = MODEL
        result[name] = entry
    require(bool(result))
    return result


class ScopedClient:
    """Only three operations, no delegate fallback or arbitrary methods."""
    def __init__(self, client, quality=False):
        self.client = client
        self.names = ['name', 'active'] if quality else list(FIELD_TYPES)
        self.quality = quality
        self.required = set()

    def get_models(self):
        require(not self.quality)
        rows = self.client.execute_method('ir.model', 'search_read', [['model', '=', MODEL]],
                                          fields=['model'], limit=1)
        require(type(rows) is list and len(rows) <= 1)
        require(all(type(row) is dict and row.get('model') == MODEL for row in rows))
        return {'model_names': [MODEL] if rows else [], 'models_details': {}}

    def get_model_fields(self, model):
        require(model == MODEL)
        attributes = ['type', 'required', 'store'] if self.quality else ATTRIBUTES
        fields = metadata(self.client.execute_method(MODEL, 'fields_get', self.names,
                                                     attributes=attributes), self.names)
        self.required = {name for name, meta in fields.items() if meta.get('required') and meta.get('store', True)}
        return fields

    def execute_method(self, model, method, *args, **kwargs):
        require(self.quality and model == MODEL and method == 'search_count' and not kwargs)
        require(len(args) == 1 and type(args[0]) is list and len(args[0]) == 1)
        clause = args[0][0]
        require(type(clause) is list and len(clause) == 3 and clause[0] in self.required
                and clause[1] == '=' and clause[2] is False)
        self.required.remove(clause[0])  # at most one count per required field
        count = self.client.execute_method(MODEL, 'search_count', args[0])
        require(type(count) is int and 0 <= count <= 2147483647)
        return count


def project(name, report):
    require(type(report) is dict and report.get('success') is True and not report.get('error'))
    base = {'success': True, 'tool': name}
    if name == 'schema_catalog':
        rows = report['result']
        require(type(rows) is list and len(rows) <= 1)
        result = []
        for row in rows:
            require(row['model'] == MODEL and not row.get('field_error'))
            entry = {'model': MODEL}
            if 'fields' in row:
                entry['fields'] = metadata(row['fields'], list(FIELD_TYPES))
            result.append(entry)
        used = report['metadata_used']
        require(all(type(used[key]) is bool for key in ('live_odoo', 'fields_get', 'cache_hit')))
        return {**base, 'count': len(result), 'result': result,
                'metadata_used': {key: used[key] for key in ('live_odoo', 'fields_get', 'cache_hit')}}
    if name == 'inspect_model_relationships':
        # All identifiers/flags came from the positive metadata projection, not
        # arbitrary labels/help/compute text. Source guard covers report builder.
        require(not report['metadata_used'].get('error'))
        relationships = {kind: [{k: item[k] for k in ('name', 'relation', 'required', 'readonly')}
                                for item in report['relationships'][kind]]
                         for kind in ('many2one', 'one2many', 'many2many')}
        return {**base, 'model': MODEL, 'summary': report['summary'], 'relationships': relationships,
                'required_fields': report['required_fields'], 'metadata_used': {'fields_get': True, 'source': 'server'}}
    results = report['results']
    require(len(results) == 1 and results[0]['check'] == 'missing_required' and not results[0].get('error'))
    result = {key: results[0][key] for key in ('check', 'ok', 'issue_count', 'fields_checked', 'evidence')}
    return {**base, 'model': MODEL, 'sample_limit': report['sample_limit'], 'checks_run': report['checks_run'],
            'results': [result], 'summary': report['summary']}


def guard_sources():
    import odoo_mcp
    root = Path(odoo_mcp.__file__).parent
    for module, digest in SOURCES.items():
        if hashlib.sha256((root / (module + '.py')).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Odoo B2 source review required')


def wrap(name, original):
    @functools.wraps(original)
    def bounded(**kwargs):
        try:
            ctx = kwargs.pop('ctx')
            app = ctx.request_context.lifespan_context
            # Retain only the existing cache for failure invalidation. Do not
            # resolve/create a client or execute a handler before source checks.
            cached = getattr(app, '_b2_catalog', None)
            if cached is not None:
                cache = cached[1]
            guard_sources()  # even a cache hit cannot bypass the source guard
            args = arguments(name, kwargs)
            from odoo_mcp.server_core import _resolve_odoo
            instance, client = _resolve_odoo(ctx, None)
            require(instance == 'default')
            # ChildSpec uses immutable credential env; config changes replace the
            # process. Client identity additionally prevents reuse across clients.
            if cached is None or cached[0] is not client:
                cached = (client, {})
                app._b2_catalog = cached
            cache = cached[1]
            require(len(cache) <= 2)
            scoped = SimpleNamespace(odoo=ScopedClient(client, name == 'data_quality_report'),
                                     _default_instance_name='default', schema_cache=cache)
            context = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=scoped))
            report = original(ctx=context, **args)
            result = project(name, report)
            # Catalog stores only already-projected metadata; remove the native
            # empty label/field_error keys from the cached report too.
            if name == 'schema_catalog':
                import json
                key = json.dumps({k: args[k] for k in ('query', 'models', 'include_fields', 'limit')}
                                 | {'instance': 'default'}, sort_keys=True)
                cache[key] = result
                require(len(cache) <= 2)
            return result
        except Exception:
            # Native handlers catch exceptions into strings, including per-check
            # quality errors. Never publish those reports, even as partial success.
            if 'cache' in locals() and name == 'schema_catalog':
                cache.clear()
            return {'success': False, 'tool': name, 'error': 'BACKEND_RESPONSE_INVALID'}
    return bounded


def install(mcp):
    guard_sources()
    descriptions = {
        'schema_catalog': 'Bounded res.partner schema only; two projected metadata cache keys, refresh explicitly for fresh metadata.',
        'inspect_model_relationships': 'Live res.partner field metadata and parent_id/child_ids self-relations only, depth 1; no record values or write authority.',
        'data_quality_report': 'Count missing required stored name/active values on res.partner; no record samples. Totals sum missing-field counts, not distinct records.',
    }
    for name in DEFAULTS:
        tool = mcp._tool_manager.get_tool(name)
        tool.fn = wrap(name, tool.fn)
        tool.description = descriptions[name]
