"""
动作模块：自动模式（随机切换）、操控模式（键盘控制）、跟随鼠标模式
"""
from .constants import STANDARD_MOVEMENT_STATES, RESERVED_STATES
from .auto import AutoActions
from .control import ControlActions, CONTROL_KEY_TO_STATE
from .follow_mouse import FollowMouseActions

__all__ = [
    "AutoActions",
    "ControlActions",
    "FollowMouseActions",
    "CONTROL_KEY_TO_STATE",
    "STANDARD_MOVEMENT_STATES",
    "RESERVED_STATES",
]
