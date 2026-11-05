"""动作相关常量，供 auto / control 及 pet 使用。"""
from ...core.weather_anim import WEATHER_STATE

STANDARD_MOVEMENT_STATES = ["walk_left", "walk_right", "walk_up", "walk_down"]
# 天气动作是播报时的临时状态，播完就摘掉：留在池子里会被自动模式随机抽到，
# 变成一只没查天气也在淋雨的仓鼠。
RESERVED_STATES = ["stand", "dragged", WEATHER_STATE]

# 操控模式：上下左右对应的四个动作（BB 等宠物均使用这组）
CONTROL_DIRECTION_STATES = ["walk_up", "walk_down", "walk_left", "walk_right"]
