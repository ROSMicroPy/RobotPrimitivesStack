from pathlib import Path
import sys
import unittest
for runtime_src in Path(__file__).resolve().parents[2].glob('*/src'):
    sys.path.insert(0, str(runtime_src))
from rpstack.micropyserver.rest import _json_value


class Sample:
    def as_dict(self):
        return {'kind': 'linear', 'value': 0.125, 'unit': 'm'}


class SerializationTest(unittest.TestCase):
    def test_serializes_completed_job_with_nested_measurements(self):
        result = _json_value({'state': 'succeeded', 'result': [Sample()]})
        self.assertEqual(result['result'][0], {'kind': 'linear', 'value': 0.125, 'unit': 'm'})
