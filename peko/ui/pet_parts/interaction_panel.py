"""交互面板与浮动特效：心情面板开关、互动锁定、飘字动画（从 pet.py 拆出）。"""
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


class InteractionPanelMixin:
    """交互面板与浮动特效：心情面板开关、互动锁定、飘字动画（从 pet.py 拆出）。"""

    @pyqtSlot()
    def show_custom_input_dialog(self):
        """委托给聊天模块。"""
        self._close_interaction_panel()
        if self._chat:
            self._chat.show_dialog()

    def _pet_display_name(self) -> str:
        return str(self.pet_package.get("name") or self.pet_package.get("id") or "Peko")

    def can_show_interaction_panel(self) -> bool:
        return not self.control_mode and not self.follow_mouse_mode and not getattr(self, "clone_mode", False)

    def _close_interaction_panel(self) -> None:
        if self._interaction_panel is not None:
            self._interaction_panel.hide()

    def _get_interaction_panel(self):
        if self._interaction_panel is None:
            from ..mood_dialog import MoodDialog

            self._interaction_panel = MoodDialog(self, self._mood_engine.get_interaction_options())
            self._interaction_panel.interactionRequested.connect(self.apply_mood_interaction)
        self._refresh_interaction_panel()
        return self._interaction_panel

    def _refresh_interaction_panel(self) -> None:
        if self._interaction_panel is None:
            return
        self._interaction_panel.update_view(self._mood_engine.get_view(self._pet_display_name()))

    def show_mood_panel(self, global_pos=None) -> None:
        if not self.can_show_interaction_panel():
            self.update_bubble("切回自动模式后再来互动吧。", duration=2200)
            return
        panel = self._get_interaction_panel()
        if global_pos is None:
            global_pos = self.mapToGlobal(self.rect().center())
        pet_origin = self.mapToGlobal(self.rect().topLeft())
        pet_rect = QRect(pet_origin.x(), pet_origin.y(), self.width(), self.height())
        panel.show_at(global_pos, pet_rect=pet_rect)

    def is_interaction_locked(self) -> bool:
        return QDateTime.currentMSecsSinceEpoch() < getattr(self, "_interaction_lock_until_ms", 0)

    def get_interaction_lock_remaining_ms(self) -> int:
        return max(0, int(getattr(self, "_interaction_lock_until_ms", 0) - QDateTime.currentMSecsSinceEpoch()))

    def _pause_auto_for_interaction(self, hold_ms: int) -> None:
        self.state_timer.stop()
        self._interaction_resume_timer.stop()
        self._interaction_lock_until_ms = QDateTime.currentMSecsSinceEpoch() + max(500, hold_ms)
        self._interaction_resume_timer.start(max(500, hold_ms))

    def _show_floating_effects(self, effect_items) -> None:
        if not effect_items:
            return
        pet_origin = self.mapToGlobal(self.rect().topLeft())
        center_x = pet_origin.x() + self.width() // 2
        base_y = pet_origin.y() - 12

        for index, item in enumerate(effect_items[:3]):
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            color = str(item.get("color") or "#d28e51")
            effect_label = QLabel(text)
            effect_label.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            effect_label.setAttribute(Qt.WA_TranslucentBackground, True)
            effect_label.setStyleSheet(
                "background: rgba(255, 252, 245, 0.96);"
                f"border: 1px solid {color};"
                "border-radius: 12px;"
                f"color: {color};"
                "padding: 5px 10px;"
                "font-size: 12px;"
                "font-weight: 700;"
            )
            effect_label.adjustSize()

            start_x = center_x - effect_label.width() // 2 + (index - 1) * 18
            start_y = base_y - index * 10
            start_pos = QPoint(start_x, start_y)
            end_pos = QPoint(start_x + (index - 1) * 10, start_y - 52 - index * 10)

            opacity = QGraphicsOpacityEffect(effect_label)
            effect_label.setGraphicsEffect(opacity)
            opacity.setOpacity(1.0)

            move_anim = QPropertyAnimation(effect_label, b"pos", self)
            move_anim.setDuration(850)
            move_anim.setStartValue(start_pos)
            move_anim.setEndValue(end_pos)
            move_anim.setEasingCurve(QEasingCurve.OutCubic)

            fade_anim = QPropertyAnimation(opacity, b"opacity", self)
            fade_anim.setDuration(850)
            fade_anim.setStartValue(1.0)
            fade_anim.setEndValue(0.0)
            fade_anim.setEasingCurve(QEasingCurve.InCubic)

            group = QParallelAnimationGroup(self)
            group.addAnimation(move_anim)
            group.addAnimation(fade_anim)

            effect_label.move(start_pos)
            effect_label.show()
            effect_label.raise_()

            animation_ref = {"label": effect_label, "group": group}
            self._ui_effect_animations.append(animation_ref)

            def _cleanup(ref=animation_ref):
                try:
                    ref["label"].close()
                    ref["label"].deleteLater()
                except Exception:
                    pass
                if ref in self._ui_effect_animations:
                    self._ui_effect_animations.remove(ref)

            group.finished.connect(_cleanup)
            group.start()

    def _clear_ui_effects(self) -> None:
        while self._ui_effect_animations:
            ref = self._ui_effect_animations.pop()
            try:
                ref["group"].stop()
            except Exception:
                pass
            try:
                ref["label"].close()
                ref["label"].deleteLater()
            except Exception:
                pass

    def _resume_after_manual_interaction(self) -> None:
        self._interaction_lock_until_ms = 0
        if self.current_state not in {"listen", "dragged"}:
            self.current_state = "stand"
            self.current_frame_index = 0
            self._apply_state_frame_rate()
            self.update_frame()
        if not self.control_mode and not self.follow_mouse_mode:
            self._auto_actions.resume()

    def _available_states(self):
        return [state for state, frames in self.animations.items() if frames]

    def expand_auto_action_pool(self, pool):
        return self._mood_engine.expand_auto_action_pool(pool)

    def get_chat_context(self) -> str:
        return self._mood_engine.get_chat_context(self._pet_display_name())

    def apply_mood_interaction(self, interaction_id: str) -> None:
        outcome = self._mood_engine.apply_interaction(interaction_id, self._available_states())
        self._refresh_interaction_panel()
        self._show_floating_effects(outcome.effect_items)
        self.update_bubble(outcome.bubble, duration=max(2400, outcome.hold_ms + 800))

        if interaction_id == "chat":
            self._close_interaction_panel()
            QTimer.singleShot(100, self.show_custom_input_dialog)
            return

        if outcome.suggested_state:
            self.current_state = outcome.suggested_state
            self.current_frame_index = 0
            self._apply_state_frame_rate()
            self.update_frame()
        self._pause_auto_for_interaction(outcome.hold_ms)
