"""Optional CPython ROS facade; importing it does not import ROS libraries."""
from .gateway import SlideRosGateway

__all__ = ['SlideRosGateway']
