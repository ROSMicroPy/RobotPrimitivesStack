"""Generic node boot: all application assembly is declared in the manifest."""
from rpstack.node_runtime import run_manifest

if __name__ == "__main__":
    run_manifest("/lib/linear_slide_manifest.json")
