"""Generic node boot: all application assembly is declared in the manifest."""
from somatic_mesh.fabric_node import run_manifest

if __name__ == "__main__":
    run_manifest("/lib/linear_slide_manifest.json")
