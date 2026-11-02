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


# ---------- 打字机节奏（想整体调快/调慢只改这几个常量） ----------
# 普通气泡（天气、提示、欢迎语等）：每个字的间隔毫秒
BUBBLE_TYPING_MS = 50
# AI 流式对话：每个节拍间隔毫秒 + 每拍吐几个字。
# 80ms/字（含标点停顿后约 8~9 字/秒）——比整段瞬显慢得多，读得过来又不至于拖沓。
CHAT_STREAM_TYPING_MS = 80
CHAT_STREAM_CHARS_PER_TICK = 1
# 标点后额外停顿的倍数：让语气有「换气」感，而不是匀速机器人念稿
TYPING_PUNCTUATION = "，。！？；：、…—～,.!?;:~"
TYPING_PUNCTUATION_PAUSE = 2.4


class BubbleMixin:
    """气泡系统：普通气泡、打字机、主题应用、气泡窗口定位（从 pet.py 拆出）。"""

    # 打字机状态默认值（实例使用时会覆盖；放类属性避免未初始化就被读到）
    _typing_interval = BUBBLE_TYPING_MS
    _typing_chunk = 1
    _chat_stream_active = False
    _chat_stream_target = ""
    full_text = ""
    current_text = ""
    typing_index = 0

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
        # 整段瞬显（错误提示、即时消息）：打断打字机队列，避免旧流式文本串进新消息
        self.typing_timer.stop()
        self._chat_stream_active = False
        self._chat_stream_target = ""
        self.full_text = ""
        self.current_text = ""
        self.typing_index = 0
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

    def _reset_typing_shell(self, interval: int, chunk: int = 1) -> None:
        """清空气泡并准备逐字吐出：显示气泡窗、重置打字机指针与节奏。"""
        self._typing_interval = max(1, int(interval))
        self._typing_chunk = max(1, int(chunk))
        self._chat_stream_active = False
        self._chat_stream_target = ""
        self.full_text = ""
        self.current_text = ""
        self.typing_index = 0
        self.typing_timer.stop()
        self._set_bubble_dialog(False)
        self.bubble_label.setText("")
        self.bubble_label.setVisible(True)
        self.bubble_label.setWordWrap(True)
        self.bubble_label.setFixedWidth(220)
        self.bubble_window.adjustSize()
        self.bubble_window.setVisible(True)
        self._position_bubble_window()

    def show_bubble(self, text: str, duration: int = 3000, typing_speed: int = 50) -> None:
        # 打字机时长自适应：保证长文能完整读完（打字耗时 + 停留），上限 30 秒
        if typing_speed > 0 and text:
            needed = typing_speed * len(text) + 1500
            if duration < needed:
                duration = min(needed, 30000)
        self._reset_typing_shell(typing_speed)
        self.full_text = text
        self.typing_timer.start(self._typing_interval)
        self.bubble_timer.start(duration)
        self._notify_effect_bubble_shown()

    def type_next_character(self):
        total = len(self.full_text)
        if self.typing_index >= total:
            self.typing_timer.stop()
            return
        end = min(total, self.typing_index + self._typing_chunk)
        self.current_text += self.full_text[self.typing_index:end]
        self.typing_index = end
        self.bubble_label.setText(self.current_text)
        self.bubble_window.adjustSize()
        self._position_bubble_window()
        if self.typing_index >= total:
            self.typing_timer.stop()
            return
        # 标点后放慢一拍，读起来更像「在说话」
        interval = self._typing_interval
        if self.full_text[end - 1] in TYPING_PUNCTUATION:
            interval = int(interval * TYPING_PUNCTUATION_PAUSE)
        self.typing_timer.start(interval)

    def hide_bubble(self):
        # 话还没「说完」（打字机仍有待吐字符）就先别收气泡，按剩余字数续期
        if self.typing_timer.isActive() and self.typing_index < len(self.full_text):
            remain = (len(self.full_text) - self.typing_index) * self._typing_interval
            self.bubble_timer.start(max(1000, int(remain)))
            return
        self._chat_stream_active = False
        self._chat_stream_target = ""
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
        self._chat_stream_active = False
        self._chat_stream_target = ""
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
        self.show_bubble(text, duration=duration, typing_speed=BUBBLE_TYPING_MS)

    @pyqtSlot(str, bool, int)
    def _on_bubble_chat_stream(self, delta: str, reset: bool, duration: int):
        """AI 流式回复：把增量塞进打字机队列，由固定节奏逐字吐出。

        模型吐字快慢不影响观感 —— 多出来的内容排在队列里慢慢显示，
        用户看到的始终是约 CHAT_STREAM_TYPING_MS 一拍的说话节奏。
        """
        if reset or not self._chat_stream_active:
            self._reset_typing_shell(CHAT_STREAM_TYPING_MS, CHAT_STREAM_CHARS_PER_TICK)
            self._chat_stream_active = True
            self._notify_effect_bubble_shown()
        self._chat_stream_target += delta or ""
        self.full_text = self._chat_stream_target
        if not self.typing_timer.isActive():
            self.typing_timer.start(self._typing_interval)
        # 队列没吐完之前不能收气泡：续期沿用 duration，由 hide_bubble 兜底再加时
        self.bubble_timer.start(duration)
