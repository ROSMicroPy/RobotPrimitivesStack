from pathlib import Path
import sys
import unittest

COMPONENT_DIR = Path(__file__).resolve().parents[1]
SERVICES_DIR = COMPONENT_DIR.parent
sys.path.insert(0, str(SERVICES_DIR / "interfaces" / "src"))
sys.path.insert(0, str(COMPONENT_DIR / "src"))

from DistanceToPosition import DistanceToPositionAdapter
from RPInterfaces import DistanceSample


class FakeDistanceObserver:
    def __init__(self, value):
        self.sample = DistanceSample(value, "m", quality=0.8)

    def distance(self):
        return self.sample


class DistanceToPositionTests(unittest.TestCase):
    def test_applies_installation_transform(self):
        adapter = DistanceToPositionAdapter(FakeDistanceObserver(0.2), zero_offset_m=0.5, direction=-1, reference_frame="lift.base")
        sample = adapter.position()
        self.assertAlmostEqual(sample.value, 0.3)
        self.assertEqual(sample.reference_frame, "lift.base")

    def test_marks_out_of_range_position_invalid(self):
        adapter = DistanceToPositionAdapter(FakeDistanceObserver(0.4), max_position_m=0.3)
        self.assertFalse(adapter.position().valid)


if __name__ == "__main__":
    unittest.main()
