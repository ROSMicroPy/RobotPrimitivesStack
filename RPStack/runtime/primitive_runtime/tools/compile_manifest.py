#!/usr/bin/env python3
"""Validate an authoring YAML manifest and emit compact device JSON."""

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PrimitiveRuntime import ServiceManifest  # noqa: E402


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
