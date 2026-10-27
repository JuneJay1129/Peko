"""气泡系统：普通气泡、打字机、主题应用、气泡窗口定位（从 pet.py 拆出）。"""
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

from .bubble_style import (
    _bubble_action_qss, _side_panel_style,
    _default_bubble_style, _bubble_style_from_config,
)


class BubbleMixin:
    """气泡系统：普通气泡、打字机、主题应用、气泡窗口定位（从 pet.py 拆出）。"""

    def apply_bubble_theme(self, name: str = "") -> None:
        """应用气泡主题：''/'pet' 用宠物自带样式，其余用预置主题（见 core.appearance）。"""
        try:
            from peko.core import appearance as appearance_mod
            style_cfg = appearance_mod.get_bubble_style(name) if name else None
        except Exception:
            style_cfg = None
        if style_cfg is None:
            style_cfg = self.bubble_style_config
        self.bubble_label.setStyleSheet(_bubble_style_from_config(style_cfg))

    def _position_bubble_window(self) -> None:
        if not self.bubble_window.isVisible():
            return
        pet_global = self.mapToGlobal(self.rect().topLeft())
        bw, bh = self.bubble_window.width(), self.bubble_window.height()
        bx = pet_global.x() + (self.width() - bw) // 2
        by = pet_global.y() - bh - 8
        screen = QApplication.desktop().screenGeometry()
        by = max(0, min(by, screen.height() - bh))
        bx = max(0, min(bx, screen.width() - bw))
        self.bubble_window.move(bx, by)

    # ---------- 安慰对话（头顶气泡 + 侧面操作面板） ----------

    def update_bubble(self, text: str, duration: int = 3000) -> None:
        self._set_bubble_dialog(False)
        self.bubble_label.setVisible(True)
        self.bubble_label.setText(text)
        self.bubble_label.setWordWrap(True)
        self.bubble_label.setFixedWidth(220)
        self.bubble_window.adjustSize()
        self.bubble_window.setVisible(True)
        self._position_bubble_window()
        self.bubble_timer.stop()
        self.bubble_timer.start(duration)
        self._notify_effect_bubble_shown()

    def show_bubble(self, text: str, duration: int = 3000, typing_speed: int = 50) -> None:
        # 打字机时长自适应：保证长文能完整读完（打字耗时 + 停留），上限 30 秒
        if typing_speed > 0 and text:
            needed = typing_speed * len(text) + 1500
            if duration < needed:
                duration = min(needed, 30000)
        self._set_bubble_dialog(False)
        self.bubble_label.setText("")
        self.bubble_label.setVisible(True)
        self.bubble_label.setWordWrap(True)
        self.bubble_label.setFixedWidth(220)
        self.bubble_window.adjustSize()
        self.bubble_window.setVisible(True)
        self._position_bubble_window()
        self.full_text = text
        self.current_text = ""
        self.typing_index = 0
        self.typing_timer.start(typing_speed)
        self.bubble_timer.start(duration)
        self._notify_effect_bubble_shown()

    def type_next_character(self):
        if self.typing_index < len(self.full_text):
            self.current_text += self.full_text[self.typing_index]
            self.bubble_label.setText(self.current_text)
            self.typing_index += 1
            self.bubble_window.adjustSize()
            self._position_bubble_window()
        else:
            self.typing_timer.stop()

    def hide_bubble(self):
        self._set_bubble_dialog(False)
        self._stop_side_follow()
        self._side_panel.hide()
        self.bubble_window.hide()
        self.bubble_timer.stop()
        self._notify_effect_bubble_hidden()

    def _notify_effect_bubble_shown(self):
        """气泡显示时，通知特效层：如果是思考特效则暂停（避让对话气泡）。"""
        if hasattr(self, "effect_overlay") and self._current_effect == "think":
            self.effect_overlay.set_paused(True)

    def _notify_effect_bubble_hidden(self):
        """气泡隐藏时，恢复思考特效。"""
        if hasattr(self, "effect_overlay") and self._current_effect == "think":
            self.effect_overlay.set_paused(False)

    def _stop_bubble_timers(self):
        """停止所有与气泡相关的定时器并隐藏气泡，用于关闭窗口前清理，避免关闭后定时器再次弹出气泡。"""
        self.bubble_timer.stop()
        self.typing_timer.stop()
        if hasattr(self, "_sayings_timer") and self._sayings_timer:
            self._sayings_timer.stop()
        self._stop_side_follow()
        if hasattr(self, "_side_panel"):
            self._side_panel.hide()
        self.bubble_window.hide()
        self._notify_effect_bubble_hidden()

    @pyqtSlot(str, int)
    def _on_bubble_text_ready(self, text: str, duration: int):
        self.update_bubble(text, duration=duration)

    @pyqtSlot(str, int)
    def _on_bubble_stream_ready(self, text: str, duration: int):
        """假流式播报：调用打字机逐字显示，跨线程安全地更新气泡。"""
        self.show_bubble(text, duration=duration, typing_speed=50)
