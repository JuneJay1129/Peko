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
        """安排下一次状态切换（仅在非操控、非跟随鼠标模式下调用）。"""
        if self.pet.control_mode or getattr(self.pet, "follow_mouse_mode", False):
            return
        if self.pet.current_state == "listen":
            return
        self.state_timer.stop()
        if getattr(self.pet, "is_interaction_locked", lambda: False)():
            remaining = max(300, getattr(self.pet, "get_interaction_lock_remaining_ms", lambda: 300)())
            self.state_timer.setInterval(remaining)
            self.state_timer.start()
            return
        if self.pet.current_state == "dragged":
            self.pet.current_state = "stand"
            self.pet.current_frame_index = 0
        cfg = self.pet._get_effective_state_config(self.pet.current_state)
        interval = cfg.get("stateSwitchInterval") or self.pet.state_switch_interval
        interval = max(500, int(interval) if isinstance(interval, (int, float)) else self.pet.state_switch_interval)
        self.state_timer.setInterval(interval)
        self.state_timer.start()

    def on_state_tick(self) -> None:
        """state_timer 超时：随机选下一个动作。"""
        if self.pet.control_mode or getattr(self.pet, "follow_mouse_mode", False) or self.pet.current_state == "dragged" or not self.pet.allow_movement:
            return
        if getattr(self.pet, "is_interaction_locked", lambda: False)():
            self.schedule_next()
            return
        def _has_frames(state_key):
            frames = self.pet.animations.get(state_key) or []
            return len(frames) > 0

        # 分身模式：若配置了 cloneModeActions 则只用该列表，否则为 stand + walk_left/right + 所有原地动作（除 listen）
        if getattr(self.pet, "clone_mode", False):
            clone_actions = self.pet.pet_package.get("cloneModeActions")
            if isinstance(clone_actions, list) and len(clone_actions) > 0:
                pool = []
                for item in clone_actions:
                    state_key = None
                    if isinstance(item, str):
                        state_key = item
                    elif isinstance(item, dict):
                        state_key = item.get("state") or item.get("action") or item.get("key") or item.get("name")
                    if not isinstance(state_key, str) or not state_key or state_key == "listen":
                        continue
                    if state_key in self.pet.animations and _has_frames(state_key):
                        pool.append(state_key)
            else:
                pool = []
                if "stand" in self.pet.animations and _has_frames("stand"):
                    pool.append("stand")
                for s in ("walk_left", "walk_right"):
                    if s in self.pet.animations and _has_frames(s):
                        pool.append(s)
                custom_states = [
                    k for k in self.pet.animations.keys()
                    if k not in RESERVED_STATES and k not in STANDARD_MOVEMENT_STATES and k != "listen" and _has_frames(k)
                ]
                pool.extend(custom_states)
            if not pool:
                return
            pool = getattr(self.pet, "expand_auto_action_pool", lambda value: value)(pool)
            self.pet.current_state = random.choice(pool)
            self.pet.current_frame_index = 0
            self.pet._apply_state_frame_rate()
            self.pet.update_frame()
            self.pet.try_show_action_bubble(self.pet.current_state)
            self.schedule_next()
            return
        walk_states = [s for s in STANDARD_MOVEMENT_STATES if s in self.pet.animations and _has_frames(s)]
        custom_states = [
            k for k in self.pet.animations.keys()
            if k not in RESERVED_STATES and k not in STANDARD_MOVEMENT_STATES and k != "listen" and _has_frames(k)
        ]
        pool = []
        if "stand" in self.pet.animations and _has_frames("stand"):
            pool.append("stand")
        pool.extend(walk_states)
        pool.extend(custom_states)
        if not pool:
            return
        pool = getattr(self.pet, "expand_auto_action_pool", lambda value: value)(pool)
        self.pet.current_state = random.choice(pool)
        self.pet.current_frame_index = 0
        self.pet._apply_state_frame_rate()
        self.pet.update_frame()
        self.pet.try_show_action_bubble(self.pet.current_state)
        self.schedule_next()

    def stop(self) -> None:
        """停止定时（切换至操控模式时调用）。"""
        self.state_timer.stop()

    def resume(self) -> None:
        """恢复自动模式并调度下一次切换。"""
        self.schedule_next()
