"""Robot Primitive manifest, binding, supervision, and test runtime."""

from .manifest import ManifestError, SCHEMA_ID, ServiceManifest, load_document
from .registry import CapabilityRegistry, ResolutionError, ServiceDefinition
from .supervisor import LifecycleError, ServiceSupervisor
from .testing import ManifestTestError, ManifestTestRunner
from .node import NodeRuntime, run_manifest

__all__ = (
    "CapabilityRegistry", "LifecycleError", "ManifestError",
    "ManifestTestError", "ManifestTestRunner", "ResolutionError", "SCHEMA_ID",
    "ServiceDefinition", "ServiceManifest", "ServiceSupervisor", "load_document",
    "NodeRuntime", "run_manifest",
)
