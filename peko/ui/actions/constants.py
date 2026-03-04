"""动作相关常量，供 auto / control 及 pet 使用。"""
STANDARD_MOVEMENT_STATES = ["walk_left", "walk_right", "walk_up", "walk_down"]
RESERVED_STATES = ["stand", "dragged"]

# 操控模式：上下左右对应的四个动作（BB 等宠物均使用这组）
CONTROL_DIRECTION_STATES = ["walk_up", "walk_down", "walk_left", "walk_right"]
