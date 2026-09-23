"""
DistNet messaging package.

Nodes broadcast self-contained composition claims and transient runtime events.
Trackers build local composition views, while listeners may react to or ignore
broadcast events.
"""

from .schema import Schema
from .codec import MAX_SHORT_PACKET_BYTES, MessageCodec, MessageValidationError
from .capabilities import (
    CapabilityMatcher,
    ComponentNode,
    CompositeUnit,
    RobotRequirements,
    build_mount_claim,
    component_to_location,
    component_to_part,
    component_to_state,
    example_partial_arm,
    example_requirements,
)
from .protocol import MessagingEndpoint
from .registry import CompositionRegistry

__all__ = [
    "MAX_SHORT_PACKET_BYTES",
    "CapabilityMatcher",
    "ComponentNode",
    "CompositeUnit",
    "CompositionRegistry",
    "MessageCodec",
    "MessageValidationError",
    "MessagingEndpoint",
    "RobotRequirements",
    "Schema",
    "build_mount_claim",
    "component_to_location",
    "component_to_part",
    "component_to_state",
    "example_partial_arm",
    "example_requirements",
]
