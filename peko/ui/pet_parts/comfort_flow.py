"""安慰对话流程：头顶气泡多轮对话 + 侧面操作面板（从 pet.py 拆出）。"""
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


class ComfortFlowMixin:
    """安慰对话流程：头顶气泡多轮对话 + 侧面操作面板（从 pet.py 拆出）。"""

    def _set_bubble_dialog(self, on: bool) -> None:
        """切换气泡为「安慰对话模式」：气泡放宽以容纳多行文本。"""
        self.bubble_label.setFixedWidth(380 if on else 220)

    def refresh_theme(self, theme: str = "") -> None:
        """外观主题切换后刷新气泡与侧面操作面板配色。"""
        try:
            if theme:
                self.apply_bubble_theme(theme)
            else:
                from peko.core import appearance as appearance_mod
                self.apply_bubble_theme(appearance_mod.get_theme())
            self._side_panel.setStyleSheet(_side_panel_style())
        except Exception:
            pass

    def close_comfort_dialog(self) -> None:
        """结束安慰对话：收起侧面操作面板与气泡。"""
        self._comfort_session = None
        self._comfort_busy = False
        self._stop_side_follow()
        self._side_panel.hide()
        self._set_bubble_dialog(False)
        self.bubble_window.hide()
        self.bubble_timer.stop()
        self.typing_timer.stop()
        self._notify_effect_bubble_hidden()

    def start_comfort_dialog(self, initial_hint: str = "") -> None:
        """用桌宠气泡开启引导式安慰对话（无 AI 也能用）。"""
        try:
            from peko.ai.service import validate_ai_config
            self._comfort_ai_mode = bool(validate_ai_config())
        except Exception:
            self._comfort_ai_mode = False
        self.refresh_theme()
        from peko.core.comfort import ComfortSession
        self._comfort_session = ComfortSession()
        self._comfort_busy = False
        turn = self._comfort_session.start()
        hint = (initial_hint or "").strip()
        if hint:
            turn = self._comfort_session.respond(hint)
        self._bubble_show_turn(turn)

    def _bubble_show_turn(self, turn: dict) -> None:
        """渲染安慰对话的一轮：气泡显示文本，侧面面板显示选项与输入。"""
        if not self._comfort_session:
            return
        self._set_bubble_dialog(True)
        self.bubble_label.setVisible(True)
        self.bubble_label.setText(turn.get("text") or "")
        self._side_render_options(turn.get("options") or [])
        self.bubble_timer.stop()
        if turn.get("finished"):
            self._side_inp_edit.setEnabled(False)
            self._side_panel.show()
            self._position_side_panel()
            self._stop_side_follow()
            self.bubble_window.adjustSize()
            self.bubble_window.setVisible(True)
            self._position_bubble_window()
            self._notify_effect_bubble_shown()
            QTimer.singleShot(2800, self.hide_bubble)
            return
        self._side_inp_edit.setEnabled(True)
        self._side_panel.show()
        self._position_side_panel()
        self._start_side_follow()
        self.bubble_window.adjustSize()
        self.bubble_window.setVisible(True)
        self._position_bubble_window()
        self._notify_effect_bubble_shown()
        # 兜底：对话进行中气泡常驻（20s 无操作才隐藏，防异常卡死）
        self.bubble_timer.start(20000)

    def _side_render_options(self, options) -> None:
        while self._side_opt_grid.count():
            item = self._side_opt_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        for idx, opt in enumerate(options):
            btn = QPushButton(opt.get("label", ""), self._side_panel)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, oid=opt.get("id"): self._bubble_option(oid))
            self._side_opt_grid.addWidget(btn, idx // 2, idx % 2)

    def _position_side_panel(self) -> None:
        """将侧面操作面板定位到宠物右侧（超屏放左侧），垂直居中。"""
        if not self._side_panel.isVisible():
            return
        try:
            pet_global = self.mapToGlobal(self.rect().topLeft())
            screen = QApplication.desktop().screenGeometry()
            pw, ph = self.width(), self.height()
            self._side_panel.adjustSize()
            sw, sh = self._side_panel.width(), self._side_panel.height()
            right_x = pet_global.x() + pw + 14
            left_x = pet_global.x() - sw - 14
            if right_x + sw <= screen.right():
                x = right_x
            elif left_x >= screen.left():
                x = left_x
            else:
                x = max(screen.left(), min(right_x, screen.right() - sw))
            y = pet_global.y() + (ph - sh) // 2
            y = max(screen.top(), min(y, screen.bottom() - sh))
            self._side_panel.move(x, y)
        except Exception:
            pass

    def _start_side_follow(self) -> None:
        try:
            self._side_follow_timer.start()
        except Exception:
            pass

    def _stop_side_follow(self) -> None:
        try:
            self._side_follow_timer.stop()
        except Exception:
            pass

    def _bubble_option(self, option_id: str) -> None:
        if self._comfort_busy or not self._comfort_session:
            return
        self._comfort_busy = True
        turn = self._comfort_session.choose(option_id)
        self._bubble_maybe_ai(turn, user_hint=option_id)

    def _bubble_send(self) -> None:
        if self._comfort_busy or not self._comfort_session:
            return
        text = self._side_inp_edit.text().strip()
        if not text:
            return
        self._side_inp_edit.clear()
        self._comfort_busy = True
        turn = self._comfort_session.respond(text)
        self._bubble_maybe_ai(turn, user_hint=text)

    def _bubble_maybe_ai(self, turn: dict, user_hint: str = "") -> None:
        """有 AI 且非开场/收尾完成时，后台生成文本覆盖；否则直接渲染。"""
        if self._comfort_ai_mode and turn.get("stage") != "intro" and not turn.get("finished"):
            self.bubble_label.setText("…")
            self.bubble_window.adjustSize()
            self._bubble_ai_fetch(turn, user_hint)
            return
        self._comfort_busy = False
        self._bubble_show_turn(turn)

    def _bubble_ai_fetch(self, turn: dict, user_hint: str) -> None:
        """后台线程生成安慰文本，经信号回主线程渲染。"""
        def _work():
            try:
                from peko.ai.service import stream_chat, validate_ai_config
                if not validate_ai_config():
                    return
                try:
                    pet_name = self._pet_display_name()
                except Exception:
                    pet_name = "BB鼠"
                ctx = self._comfort_session.context() if self._comfort_session else ""
                sys_prompt = (
                    f"你现在是{pet_name}，一只天真温暖的小仓鼠，最会安慰人。"
                    f"{ctx}"
                    "请用 2~4 句简短、温暖、不说教的话回应，像朋友一样站TA这边，给到实实在在的安抚。"
                )
                msgs = [{"role": "system", "content": sys_prompt},
                        {"role": "user", "content": user_hint or "陪我聊聊"}]
                text = stream_chat(msgs).strip()
                if text:
                    turn["text"] = text
            except Exception:
                pass
            self.comfort_turn_ready.emit(turn)
        import threading
        threading.Thread(target=_work, daemon=True).start()

    def _on_comfort_turn_ready(self, turn: dict) -> None:
        self._comfort_busy = False
        self._bubble_show_turn(turn)
