from pathlib import Path
import sys

# Discover independent packages across all repository responsibility groups.
for source in Path(__file__).resolve().parents[3].glob("*/*/src"):
    sys.path.insert(0, str(source))
import unittest
from somatic_mesh.micropyserver.rest import _json_value


class Sample:
    # Expose a minimal measurement dictionary for nested result serialization tests.
    def as_dict(self):
        return {'kind': 'linear', 'value': 0.125, 'unit': 'm'}


class SerializationTest(unittest.TestCase):
    # Verify nested sample objects become JSON-compatible dictionaries in task results.
    def test_serializes_completed_job_with_nested_measurements(self):
        result = _json_value({'state': 'succeeded', 'result': [Sample()]})
        self.assertEqual(result['result'][0], {'kind': 'linear', 'value': 0.125, 'unit': 'm'})
