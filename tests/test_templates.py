import copy
import json
import tempfile
import unittest
from pathlib import Path

from id_platform.templates import TemplateError, load_catalog, prefill, validate_template


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.template = {
            'id': 'example.card', 'version': '0.1.0',
            'title': 'Test only', 'status': 'draft',
            'fields': [
                {'name': 'title', 'source': 'project.title', 'required': True},
                {'name': 'quantity', 'source': 'work.quantity', 'required': True},
            ],
        }

    def test_missing_keeps_recognized_values(self):
        result = prefill(self.template, {'project': {'title': 'Example'}})
        self.assertEqual(result['values']['title'], 'Example')
        self.assertEqual(result['missing'], ['quantity'])
        self.assertFalse(result['release_allowed'])

    def test_zero_is_not_missing_and_draft_cannot_release(self):
        result = prefill(self.template, {
            'project': {'title': 'Example'}, 'work': {'quantity': 0},
        })
        self.assertEqual(result['missing'], [])
        self.assertTrue(result['ready_for_review'])
        self.assertFalse(result['release_allowed'])
        self.assertEqual(result['provenance']['quantity'], 'work.quantity')

    def test_duplicate_fields_rejected(self):
        self.template['fields'].append(copy.deepcopy(self.template['fields'][0]))
        with self.assertRaises(TemplateError):
            validate_template(self.template)

    def test_approval_requires_source(self):
        self.template['status'] = 'approved'
        with self.assertRaises(TemplateError):
            validate_template(self.template)

    def test_catalog_hides_drafts(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'manifest.json').write_text(
                json.dumps(self.template), encoding='utf-8',
            )
            self.assertEqual(load_catalog(directory), [])
            self.assertEqual(len(load_catalog(directory, include_unapproved=True)), 1)

    def test_input_not_modified(self):
        context = {'project': {'title': 'Example'}, 'work': {'quantity': [1]}}
        snapshot = copy.deepcopy(context)
        result = prefill(self.template, context)
        result['values']['quantity'].append(2)
        self.assertEqual(context, snapshot)


if __name__ == '__main__':
    unittest.main()
