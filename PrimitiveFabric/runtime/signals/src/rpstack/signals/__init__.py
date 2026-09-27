"""Transport-independent signals scoped to one robot/entity."""
from .bus import SignalBus
from .model import encode, decode, identity
__all__ = ("SignalBus", "encode", "decode", "identity")
