"""Optional CPython ROS facade; importing it does not import ROS libraries."""
from .gateway import SlideRosBehavior

__all__ = ['SlideRosBehavior']
