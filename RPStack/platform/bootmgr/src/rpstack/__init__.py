"""Shared namespace for independently installed RPStack components."""

try:
    from pkgutil import extend_path
except ImportError:
    extend_path = None

if extend_path is not None:
    __path__ = extend_path(__path__, __name__)
