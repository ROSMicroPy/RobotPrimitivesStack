from pathlib import Path
import sys

# Discover independent packages across all repository responsibility groups.
for source in Path(__file__).resolve().parents[3].glob("*/*/src"):
    sys.path.insert(0, str(source))
import unittest

COMPONENT_DIR = Path(__file__).resolve().parents[1]

from rpstack.interfaces import DistanceSample, PositionSample


class InterfaceTests(unittest.TestCase):
    # Verify measurement metadata survives serialization and invalid quality is rejected.
    def test_measurement_metadata_and_quality_validation(self):
        sample = DistanceSample(0.25, "m", quality=0.75, reference_frame="sensor.front")
        self.assertEqual(sample.as_dict()["reference_frame"], "sensor.front")
        with self.assertRaises(ValueError):
            DistanceSample(1, "m", quality=1.1)

    # Ensure linear positions cannot be constructed using noncanonical millimetre units.
    def test_position_enforces_canonical_units(self):
        with self.assertRaises(ValueError):
            PositionSample("linear", 10, "mm", "axis")


if __name__ == "__main__":
    unittest.main()
