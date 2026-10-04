"""Positive bounded projections for B1 partner counts/template discovery.

No ORM domains, contexts, arbitrary model names or backend text is disclosed.
The pinned source handler still runs; these functions only narrow its result.
"""

def count_rows(values):
    if not isinstance(values, list) or len(values) > 100:
        raise ValueError('BACKEND_RESPONSE_INVALID')
    result = []
    for row in values:
        if not isinstance(row, dict) or type(row.get('active')) is not bool:
            raise ValueError('BACKEND_RESPONSE_INVALID')
        count = row.get('id:count', row.get('id'))
        total = row.get('__count', count)
        if any(type(n) is not int or not 0 <= n <= 2147483647 for n in (count, total)):
            raise ValueError('BACKEND_RESPONSE_INVALID')
        result.append({'active': row['active'], 'id:count': count, '__count': total})
    return result


def odoo_counts(value):
    if not isinstance(value, dict) or value.get('success') is not True:
        return {'success': False, 'error': 'BACKEND_REQUEST_FAILED'}
    rows = count_rows(value.get('rows'))
    method, major = value.get('method'), value.get('major_version')
    if method not in ('read_group', 'formatted_read_group') or (major is not None and (type(major) is not int or not 1 <= major <= 100)):
        raise ValueError('BACKEND_RESPONSE_INVALID')
    return {'success': True, 'method': method, 'major_version': major,
            'model': 'res.partner', 'group_by': ['active'], 'measures': ['id:count'],
            'row_count': len(rows), 'rows': rows}


def manage_counts(value):
    return {'groups': count_rows(value.get('groups')), 'model': 'res.partner',
            'groupby': ['active'], 'aggregates': ['id:count']}


def resource_templates(value):
    templates = value.get('templates')
    if not isinstance(templates, list) or len(templates) > 4:
        raise ValueError('BACKEND_RESPONSE_INVALID')
    projected = []
    for row in templates:
        uri = row.get('uri_template')
        if uri not in ('odoo://{model}/record/{record_id}', 'odoo://{model}/search',
                       'odoo://{model}/count', 'odoo://{model}/fields'):
            raise ValueError('BACKEND_RESPONSE_INVALID')
        # All strings originate in the source-defined static template registry.
        # Validate bounds/types even though the pinned handler defines them.
        fields = {}
        for key in ('uri_template', 'description', 'example'):
            text = row.get(key)
            if type(text) is not str or len(text) > 256:
                raise ValueError('BACKEND_RESPONSE_INVALID')
            fields[key] = text
        fields['parameters'] = {key: text for key, text in row.get('parameters', {}).items()
                                if key in ('model', 'record_id') and type(text) is str and len(text) <= 256}
        projected.append(fields)
    models = value.get('enabled_models')
    if not isinstance(models, list):
        raise ValueError('BACKEND_RESPONSE_INVALID')
    enabled = ['res.partner'] if 'res.partner' in models else []
    return {'templates': projected, 'enabled_models': enabled, 'total_models': len(enabled),
            'note': 'Metadata only: resources/read remains denied. Use authorized bounded tools.'}
