"""Local template metadata and deterministic prefill; no normative claims."""
import copy
import json
from pathlib import Path


class TemplateError(ValueError):
    pass


def validate_template(template):
    if not isinstance(template, dict):
        raise TemplateError('Template must be an object')
    for key in ('id', 'version', 'title', 'status'):
        if not isinstance(template.get(key), str) or not template[key].strip():
            raise TemplateError('Missing string: ' + key)
    if template['status'] not in ('draft', 'review', 'approved'):
        raise TemplateError('Invalid status')
    fields = template.get('fields')
    if not isinstance(fields, list) or not fields:
        raise TemplateError('Nonempty fields list required')
    names = set()
    for field in fields:
        if not isinstance(field, dict):
            raise TemplateError('Field must be an object')
        name = field.get('name')
        if not isinstance(name, str) or not name.strip() or name in names:
            raise TemplateError('Invalid or duplicate field name')
        names.add(name)
        if not isinstance(field.get('source'), str) or not field['source'].strip():
            raise TemplateError('Field source required: ' + name)
        if not isinstance(field.get('required', False), bool):
            raise TemplateError('Required must be boolean')
    if template['status'] == 'approved':
        sources = template.get('sources')
        if not isinstance(sources, list) or not sources:
            raise TemplateError('Approved template requires source references')
        for source in sources:
            if not isinstance(source, dict) or not all(
                isinstance(source.get(k), str) and source[k].strip()
                for k in ('document', 'edition', 'location')
            ):
                raise TemplateError('Incomplete source reference')
    return template


def load_catalog(directory, include_unapproved=False):
    root = Path(directory)
    if not root.is_dir():
        raise TemplateError('Catalog directory does not exist')
    templates = []
    identities = set()
    for path in sorted(root.rglob('manifest.json')):
        try:
            template = validate_template(json.loads(path.read_text(encoding='utf-8')))
        except (OSError, ValueError) as error:
            raise TemplateError(str(path) + ': ' + str(error)) from error
        identity = (template['id'], template['version'])
        if identity in identities:
            raise TemplateError('Duplicate template version: ' + repr(identity))
        identities.add(identity)
        if include_unapproved or template['status'] == 'approved':
            templates.append(copy.deepcopy(template))
    return templates


def prefill(template, context):
    validate_template(template)
    if not isinstance(context, dict):
        raise TemplateError('Context must be an object')
    values, provenance, missing = {}, {}, []
    for field in template['fields']:
        value = context
        for part in field['source'].split('.'):
            value = value.get(part) if isinstance(value, dict) else None
        name = field['name']
        values[name] = copy.deepcopy(value)
        if value is not None:
            provenance[name] = field['source']
        empty = value is None or value == '' or value == [] or value == {}
        if field.get('required', False) and empty:
            missing.append(name)
    return {
        'template_id': template['id'],
        'template_version': template['version'],
        'template_status': template['status'],
        'values': values, 'provenance': provenance, 'missing': missing,
        'ready_for_review': not missing,
        'release_allowed': template['status'] == 'approved' and not missing,
    }
