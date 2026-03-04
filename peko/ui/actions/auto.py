"""
自动动作模块：按 stateSwitchInterval 随机切换站立/行走/自定义动作等。
"""
import random
from typing import TYPE_CHECKING

from .constants import STANDARD_MOVEMENT_STATES, RESERVED_STATES

if TYPE_CHECKING:
    from ..pet import DesktopPet


class AutoActions:
    """自动模式：定时随机切换宠物动作，由 state_timer 驱动。"""

    def __init__(self, pet: "DesktopPet", state_timer):
        self.pet = pet
        self.state_timer = state_timer
        self.state_timer.setSingleShot(True)
        self.state_timer.timeout.connect(self.on_state_tick)

    def schedule_next(self) -> None:
        """安排下一次状态切换（仅在非操控模式下调用）。"""
        if self.pet.control_mode:
            return
        self.state_timer.stop()
        if self.pet.current_state == "dragged":
            self.pet.current_state = "stand"
            self.pet.current_frame_index = 0
        cfg = self.pet._state_config.get(self.pet.current_state, {})
        interval = cfg.get("stateSwitchInterval") or self.pet.state_switch_interval
        interval = max(500, int(interval) if isinstance(interval, (int, float)) else self.pet.state_switch_interval)
        self.state_timer.setInterval(interval)
        self.state_timer.start()

    def on_state_tick(self) -> None:
        """state_timer 超时：随机选下一个动作。"""
        if self.pet.control_mode or self.pet.current_state == "dragged" or not self.pet.allow_movement:
            return
        walk_states = [s for s in STANDARD_MOVEMENT_STATES if s in self.pet.animations]
        custom_states = [
            k for k in self.pet.animations.keys()
            if k not in RESERVED_STATES and k not in STANDARD_MOVEMENT_STATES
        ]
        pool = []
        if "stand" in self.pet.animations:
            pool.append("stand")
        pool.extend(walk_states)
        pool.extend(custom_states)
        if not pool:
            return
        self.pet.current_state = random.choice(pool)
        self.pet.current_frame_index = 0
        self.pet._apply_state_frame_rate()
        self.pet.update_frame()
        self.schedule_next()

    def stop(self) -> None:
        """停止定时（切换至操控模式时调用）。"""
        self.state_timer.stop()

    def resume(self) -> None:
        """恢复自动模式并调度下一次切换。"""
        self.schedule_next()
