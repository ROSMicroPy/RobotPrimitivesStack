#!/usr/bin/env python3
"""Validate an authoring YAML manifest and emit compact device JSON."""

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
# Discover independently packaged dependencies when invoked directly from the checkout.
for source in ROOT.glob("*/*/src"):
    sys.path.insert(0, str(source))

from rpstack.node_runtime import ServiceManifest  # noqa: E402


# Validate a source service manifest and write compact JSON for device deployment.
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    manifest = ServiceManifest.load(str(arguments.source))
    arguments.destination.write_text(
        json.dumps(manifest.document, separators=(",", ":")) + "\n"
    )


if __name__ == "__main__":
    main()
