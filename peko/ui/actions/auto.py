"""
自动动作模块：按 stateSwitchInterval 随机切换站立/行走/自定义动作等。
支持心情驱动的自主行为（疲惫→睡觉、饥饿→求食、伤心→求安慰）。
"""
import random
import time
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
        # 心情驱动行为冷却：避免频繁弹气泡
        self._last_mood_bubble_ts = 0.0
        self._mood_bubble_cooldown = 60.0  # 秒

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
        """state_timer 超时：先检查心情驱动行为，再随机选动作。"""
        if self.pet.control_mode or getattr(self.pet, "follow_mouse_mode", False) or self.pet.current_state == "dragged" or not self.pet.allow_movement:
            return
        if getattr(self.pet, "is_interaction_locked", lambda: False)():
            self.schedule_next()
            return

        # 心情驱动的自主行为（优先级：疲惫 > 饥饿 > 伤心）
        if self._try_mood_driven_behavior():
            return

        self._random_action()

    def _try_mood_driven_behavior(self) -> bool:
        """根据心情状态触发自主行为。返回 True 表示已接管，不需要随机动作。"""
        snap = self.pet._mood_engine.snapshot
        now = time.time()
        can_show_bubble = (now - self._last_mood_bubble_ts) >= self._mood_bubble_cooldown

        def _has_frames(state_key):
            return len(self.pet.animations.get(state_key) or []) > 0

        def _switch_to(state_key):
            self.pet.current_state = state_key
            self.pet.current_frame_index = 0
            self.pet._apply_state_frame_rate()
            self.pet.update_frame()
            self.schedule_next()

        # 优先级 1：精力极低 → 睡觉
        if snap.energy < 15:
            sleep_states = ["sleep", "lie_down", "sit"]
            for st in sleep_states:
                if _has_frames(st):
                    if can_show_bubble:
                        self.pet.update_bubble("好困……我要休息一下 zzZ", duration=5000)
                        self._last_mood_bubble_ts = now
                    _switch_to(st)
                    return True

        # 优先级 2：饱食度极低 → 饥饿行为
        if snap.satiety < 15:
            hungry_states = ["cook", "eat", "sulk"]
            for st in hungry_states:
                if _has_frames(st):
                    if can_show_bubble:
                        self.pet.update_bubble("肚子好饿……有吃的吗？", duration=5000)
                        self._last_mood_bubble_ts = now
                    _switch_to(st)
                    return True
            # 没有饥饿动画，只弹气泡
            if can_show_bubble:
                self.pet.update_bubble("咕噜噜……肚子在叫了", duration=5000)
                self._last_mood_bubble_ts = now
                return True

        # 优先级 3：心情很低 → 伤心行为
        if snap.mood_score < 20:
            sad_states = ["sulk", "cry", "sit"]
            for st in sad_states:
                if _has_frames(st):
                    if can_show_bubble:
                        self.pet.update_bubble("有点不开心……能陪陪我吗？", duration=6000)
                        self._last_mood_bubble_ts = now
                    _switch_to(st)
                    return True

        return False

    def _random_action(self) -> None:
        """随机选择下一个动作（原有逻辑）。"""
        def _has_frames(state_key):
            return len(self.pet.animations.get(state_key) or []) > 0

        # 分身模式：若配置了 cloneModeActions 则只用该列表
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

        # 正常模式
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
