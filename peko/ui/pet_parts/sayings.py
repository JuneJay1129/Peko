"""随机文案：闲时随机说话与动作气泡（从 pet.py 拆出）。"""
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


class SayingsMixin:
    """随机文案：闲时随机说话与动作气泡（从 pet.py 拆出）。"""

    def _schedule_next_saying(self, initial_delay: bool = False) -> None:
        """安排下一次随机文案弹出（单次定时器，随机间隔）。"""
        if not self._sayings_enabled or not self._sayings_phrases:
            return
        low, high = self._sayings_interval_min, self._sayings_interval_max
        delay = random.randint(10000, 30000) if initial_delay else (random.randint(low, high) if low <= high else low)
        self._sayings_timer.stop()
        self._sayings_timer.setInterval(delay)
        self._sayings_timer.start()

    def _on_sayings_tick(self) -> None:
        """定时到：若当前无气泡则随机选一句用气泡显示，然后安排下一次。

        主动关心：以低概率且间隔足够时，从安慰语库取一句暖心话，温和低频、不打扰。
        """
        if not self._sayings_enabled or not self._sayings_phrases:
            return
        if self.bubble_window.isVisible():
            self._schedule_next_saying()
            return
        # 温和低频的主动关心：距上次 ≥ 8 分钟且概率 12%
        try:
            now_ms = QDateTime.currentMSecsSinceEpoch()
            if (now_ms - self._last_care_ts) >= 8 * 60 * 1000 and random.random() < 0.12:
                from peko.core import comfort as comfort_lib
                self._last_care_ts = now_ms
                care_text = comfort_lib.active_care_text()
                if care_text:
                    self.update_bubble(care_text, duration=self._sayings_duration)
                    self._schedule_next_saying()
                    return
        except Exception:
            pass
        text = random.choice(self._sayings_phrases)
        if text and isinstance(text, str):
            self.update_bubble(text.strip(), duration=self._sayings_duration)
        self._schedule_next_saying()

    def try_show_action_bubble(self, state_name: str) -> None:
        """若当前无气泡且该动作配置了专属气泡，则显示。用于随机/分身模式切换动作时，不与 randomSayings 冲突。"""
        if self.bubble_window.isVisible():
            return
        animations = self.pet_package.get("animations") or {}
        bubble_cfg = animations.get(state_name) or {}
        raw = bubble_cfg.get("bubbles") if "bubbles" in bubble_cfg else bubble_cfg.get("bubble")
        if isinstance(raw, list):
            text = (random.choice(raw).strip() if raw else "")
        else:
            text = (raw or "").strip() if isinstance(raw, str) else ""
        if not text:
            text = self._mood_engine.get_idle_bubble(self._pet_display_name())
        if not text:
            return
        self.update_bubble(text, duration=self._sayings_duration)
