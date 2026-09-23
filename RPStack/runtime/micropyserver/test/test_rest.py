"""Transport-independent validation rejects unsafe coercion before dispatch."""
from pathlib import Path
import sys
import unittest
for runtime_src in Path(__file__).resolve().parents[2].glob('*/src'):
    sys.path.insert(0, str(runtime_src))
from rpstack.primitive_runtime.validation import validate_values


class ValidationTest(unittest.TestCase):
    def test_numeric_limits_and_booleans_are_not_coerced(self):
        schema = {'steps': {'type': 'integer', 'minimum': 1, 'required': True}}
        for value in (True, 0, 1.5, '3'):
            with self.assertRaises(ValueError):
                validate_values(schema, {'steps': value}, 'jog')
        self.assertEqual(validate_values(schema, {'steps': 3}, 'jog'), {'steps': 3})

    def test_nonfinite_motion_target_rejected(self):
        for value in (float('nan'), float('inf'), -float('inf')):
            with self.assertRaises(ValueError):
                validate_values({'target': {'type': 'number'}}, {'target': value}, 'move')
