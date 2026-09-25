"""Robot Primitive manifest, binding, supervision, and test runtime."""

from .manifest import ManifestError, SCHEMA_ID, ServiceManifest, load_document
from .registry import ServiceRegistry, ResolutionError, ServiceDefinition
from .supervisor import LifecycleError, ServiceSupervisor
from .testing import ManifestTestError, ManifestTestRunner
from .node import NodeRuntime, run_manifest
from .host import NodeHost, run_manifests

__all__ = (
    "ServiceRegistry", "LifecycleError", "ManifestError",
    "ManifestTestError", "ManifestTestRunner", "ResolutionError", "SCHEMA_ID",
    "ServiceDefinition", "ServiceManifest", "ServiceSupervisor", "load_document",
    "NodeRuntime", "run_manifest", "NodeHost", "run_manifests",
)
