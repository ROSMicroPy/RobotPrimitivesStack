from pathlib import Path
import sys

# Discover independent packages across all repository responsibility groups.
for source in Path(__file__).resolve().parents[3].glob("*/*/src"):
    sys.path.insert(0, str(source))
import unittest

COMPONENT_DIR = Path(__file__).resolve().parents[1]
SERVICES_DIR = COMPONENT_DIR.parent


from rpstack.distance_to_position import DistanceToPositionAdapter
from rpstack.interfaces import DistanceSample


class FakeDistanceObserver:
    # Prepare a distance sample with known quality for transform assertions.
    def __init__(self, value):
        self.sample = DistanceSample(value, "m", quality=0.8)

    # Return the fixed distance sample without hardware access.
    def distance(self):
        return self.sample


class DistanceToPositionTests(unittest.IsolatedAsyncioTestCase):
    # Verify signed offset conversion and preservation of the installed reference frame.
    async def test_applies_installation_transform(self):
        adapter = DistanceToPositionAdapter(FakeDistanceObserver(0.2), zero_offset_m=0.5, direction=-1, reference_frame="lift.base")
        sample = await adapter.position()
        self.assertAlmostEqual(sample.value, 0.3)
        self.assertEqual(sample.reference_frame, "lift.base")

    # Check that positions beyond configured travel bounds are marked invalid.
    async def test_marks_out_of_range_position_invalid(self):
        adapter = DistanceToPositionAdapter(FakeDistanceObserver(0.4), max_position_m=0.3)
        self.assertFalse((await adapter.position()).valid)


if __name__ == "__main__":
    unittest.main()
