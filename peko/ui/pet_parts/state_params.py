"""状态配置：帧率 / 动作参数 / 显示缩放（从 pet.py 拆出，行为不变）。"""
import random
import sys
from typing import Any, Dict, Optional, Tuple

from PyQt5.QtCore import (
    Qt, QTimer, pyqtSlot, pyqtSignal, QDateTime, QRect, QPoint,
    QPropertyAnimation, QParallelAnimationGroup, QEasingCurve,
)
from PyQt5.QtGui import QPixmap, QFont
from PyQt5.QtWidgets import (
    QLabel, QWidget, QApplication, QGraphicsOpacityEffect, QFrame,
    QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QPushButton,
)


class StateParamsMixin:
    """状态配置：帧率 / 动作参数 / 显示缩放（从 pet.py 拆出，行为不变）。"""

    def _get_current_frame_rate(self) -> int:
        if self.follow_mouse_mode and getattr(self, "_follow_mouse_frame_rate", None) is not None:
            return max(1, min(60, self._follow_mouse_frame_rate))
        cfg = self._get_effective_state_config(self.current_state)
        return cfg.get("frameRate") or self.frame_rate

    def _get_effective_state_config(self, state_name: str) -> Dict[str, Any]:
        """在分身模式下，为特定动作应用 cloneModeActions 中的 frameRate/stateSwitchInterval 覆盖，并叠加每个分身的随机抖动。"""
        cfg = self._state_config.get(state_name, {}) or {}
        if not getattr(self, "clone_mode", False):
            return cfg
        ov = self._clone_mode_action_overrides.get(state_name)
        if not isinstance(ov, dict) or not ov:
            effective = dict(cfg)
        else:
            effective = dict(cfg)
            effective.update(ov)

        # 叠加分身抖动：让同一个动作在不同宠物实例上表现不同
        jit = getattr(self, "_clone_mode_action_jitter", None) or {}
        fr_mul = float(jit.get("frameRateMul", 1.0))
        si_mul = float(jit.get("stateSwitchIntervalMul", 1.0))
        ms_mul = float(jit.get("moveSpeedMul", 1.0))

        if "frameRate" in effective and isinstance(effective.get("frameRate"), (int, float)):
            effective["frameRate"] = int(max(1, min(60, round(float(effective["frameRate"]) * fr_mul))))
        if "stateSwitchInterval" in effective and isinstance(effective.get("stateSwitchInterval"), (int, float)):
            effective["stateSwitchInterval"] = int(max(500, min(120000, round(float(effective["stateSwitchInterval"]) * si_mul))))
        if "moveSpeed" in effective and isinstance(effective.get("moveSpeed"), (int, float)):
            effective["moveSpeed"] = int(max(1, min(50, round(float(effective["moveSpeed"]) * ms_mul))))

        return effective

    def _apply_state_frame_rate(self) -> None:
        fps = max(1, self._get_current_frame_rate())
        self.timer.setInterval(max(50, 1000 // fps))

    def get_action_params(self) -> Dict[str, Any]:
        """供参数面板读取：当前动作相关参数。"""
        return {
            "frameRate": self.frame_rate,
            "stateSwitchInterval": self.state_switch_interval,
            "moveSpeed": self.move_speed,
        }

    def get_action_params_for_state(self, state_name: Optional[str]) -> Dict[str, Any]:
        """获取指定动作的参数；state_name 为 None 或空时返回全局默认。"""
        if not state_name or state_name == "__all__":
            return self.get_action_params()
        cfg = self._state_config.get(state_name, {})
        return {
            "frameRate": cfg.get("frameRate") or self.frame_rate,
            "stateSwitchInterval": cfg.get("stateSwitchInterval") or self.state_switch_interval,
            "moveSpeed": cfg.get("moveSpeed") or self.move_speed,
        }

    def set_action_params_for_state(
        self,
        state_name: Optional[str],
        frame_rate: Optional[int] = None,
        state_switch_interval: Optional[int] = None,
        move_speed: Optional[int] = None,
    ) -> None:
        """仅更新指定动作的参数；state_name 为 None 或 '__all__' 时更新全局并应用到所有动作。"""
        if not state_name or state_name == "__all__":
            self.set_action_params(
                frame_rate=frame_rate,
                state_switch_interval=state_switch_interval,
                move_speed=move_speed,
                apply_to_all_states=True,
            )
            return
        if state_name not in self._state_config:
            return
        cfg = self._state_config[state_name]
        if frame_rate is not None:
            cfg["frameRate"] = max(1, min(60, frame_rate))
        if state_switch_interval is not None:
            cfg["stateSwitchInterval"] = max(500, min(120000, state_switch_interval))
        if move_speed is not None:
            cfg["moveSpeed"] = max(1, min(50, move_speed))
        self._apply_state_frame_rate()
        if not self.control_mode and not self.follow_mouse_mode and hasattr(self, "_auto_actions"):
            self._auto_actions.schedule_next()

    def get_display_scale(self) -> float:
        """当前宠物显示缩放比例，1.0 为配置的原始大小。"""
        return getattr(self, "_display_scale", 1.0)

    def set_display_scale(self, scale: float) -> None:
        """设置宠物显示缩放比例（如 0.5～2.0），立即生效。"""
        scale = max(0.5, min(2.0, float(scale)))
        self._display_scale = scale
        if not hasattr(self, "_base_display_width"):
            return
        w = max(1, int(self._base_display_width * scale))
        h = max(1, int(self._base_display_height * scale))
        self.setFixedSize(w, h)
        if hasattr(self, "label"):
            self.label.setFixedSize(self.size())
        self.update_frame()
        self._position_bubble_window()

    def set_action_params(
        self,
        frame_rate: Optional[int] = None,
        state_switch_interval: Optional[int] = None,
        move_speed: Optional[int] = None,
        apply_to_all_states: bool = True,
    ) -> None:
        """
        实时更新动作参数并生效。
        apply_to_all_states 为 True 时同时更新各状态覆盖值；会立即刷新帧率与状态切换定时器。
        """
        if frame_rate is not None:
            self.frame_rate = max(1, min(60, frame_rate))
            if apply_to_all_states:
                for cfg in self._state_config.values():
                    cfg["frameRate"] = self.frame_rate
        if state_switch_interval is not None:
            self.state_switch_interval = max(500, min(120000, state_switch_interval))
            if apply_to_all_states:
                for cfg in self._state_config.values():
                    cfg["stateSwitchInterval"] = self.state_switch_interval
        if move_speed is not None:
            self.move_speed = max(1, min(50, move_speed))
            if apply_to_all_states:
                for cfg in self._state_config.values():
                    cfg["moveSpeed"] = self.move_speed
        self._apply_state_frame_rate()
        if not self.control_mode and not self.follow_mouse_mode and hasattr(self, "_auto_actions"):
            self._auto_actions.schedule_next()
