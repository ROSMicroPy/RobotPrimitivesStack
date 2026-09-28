"""Transport-independent validation rejects unsafe coercion before dispatch."""
from pathlib import Path
import sys

# Discover independent packages across all repository responsibility groups.
for source in Path(__file__).resolve().parents[3].glob("*/*/src"):
    sys.path.insert(0, str(source))
import unittest
from somatic_mesh.fabric_node.validation import validate_values


class ValidationTest(unittest.TestCase):
    # Ensure integer arguments respect bounds and reject booleans, fractions, and numeric
    # strings.
    def test_numeric_limits_and_booleans_are_not_coerced(self):
        schema = {'steps': {'type': 'integer', 'minimum': 1, 'required': True}}
        for value in (True, 0, 1.5, '3'):
            with self.assertRaises(ValueError):
                validate_values(schema, {'steps': value}, 'jog')
        self.assertEqual(validate_values(schema, {'steps': 3}, 'jog'), {'steps': 3})

    # Reject NaN and infinite motion targets during argument validation.
    def test_nonfinite_motion_target_rejected(self):
        for value in (float('nan'), float('inf'), -float('inf')):
            with self.assertRaises(ValueError):
                validate_values({'target': {'type': 'number'}}, {'target': value}, 'move')
