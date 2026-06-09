"""Mood interaction panel."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, QPoint, QRect, pyqtSignal, QEvent
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)
from .theme import (
    BG_CREAM, BG_CONTENT, BG_INPUT, BG_OVERLAY,
    TEXT_PRIMARY, TEXT_BODY, TEXT_SECONDARY, TEXT_MUTED,
    BORDER_WARM, ACCENT, ACCENT_HOVER,
    RADIUS_SM, RADIUS_LG,
    FONT_SIZE_SM, FONT_SIZE_BASE, FONT_SIZE_TITLE,
    MOOD_GRADIENT, SATIETY_GRADIENT, ENERGY_GRADIENT,
)


PANEL_STYLE = f"""
    QFrame#panel {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {BG_CREAM}, stop:1 {BG_CONTENT});
        border: 2px solid {BORDER_WARM};
        border-radius: {RADIUS_LG}px;
    }}
    QLabel#titleLabel {{
        color: {TEXT_PRIMARY};
        font-size: {FONT_SIZE_TITLE}px;
        font-weight: 700;
    }}
    QLabel#badgeLabel {{
        color: {TEXT_PRIMARY};
        font-size: 13px;
        font-weight: 700;
        background: rgba(255, 255, 255, 0.7);
        border-radius: 10px;
        padding: 5px 10px;
    }}
    QLabel#descLabel {{
        color: {TEXT_BODY};
        font-size: 13px;
    }}
    QLabel#metaLabel {{
        color: {TEXT_SECONDARY};
        font-size: {FONT_SIZE_SM}px;
    }}
    QLabel#sectionLabel {{
        color: {TEXT_PRIMARY};
        font-size: {FONT_SIZE_SM}px;
        font-weight: 700;
        letter-spacing: 0.5px;
    }}
    QLabel#statLabel {{
        color: {TEXT_PRIMARY};
        font-size: {FONT_SIZE_SM}px;
        font-weight: 700;
    }}
    QLabel#statHint {{
        color: {TEXT_SECONDARY};
        font-size: 11px;
    }}
    QPushButton#closeBtn {{
        background: {BG_INPUT};
        border: 2px solid {BORDER_WARM};
        border-radius: 14px;
        color: {TEXT_SECONDARY};
        font-size: 15px;
        font-weight: 700;
        min-width: 28px; max-width: 28px;
        min-height: 28px; max-height: 28px;
        padding: 0;
    }}
    QPushButton#closeBtn:hover {{
        background: {BG_CREAM};
        border-color: {ACCENT};
        color: {TEXT_PRIMARY};
    }}
    QProgressBar {{
        border: none;
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.7);
        text-align: center;
        height: 16px;
        font-size: 11px;
        font-weight: 700;
        color: {TEXT_PRIMARY};
    }}
    QProgressBar#moodBar::chunk {{
        border-radius: 8px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, {MOOD_GRADIENT});
    }}
    QProgressBar#satietyBar::chunk {{
        border-radius: 8px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, {SATIETY_GRADIENT});
    }}
    QProgressBar#energyBar::chunk {{
        border-radius: 8px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, {ENERGY_GRADIENT});
    }}
    QPushButton#actionBtn {{
        background: {BG_OVERLAY};
        border: 2px solid {BORDER_WARM};
        border-radius: {RADIUS_SM}px;
        padding: 10px 12px;
        color: {TEXT_PRIMARY};
        font-size: 13px;
        font-weight: 700;
        min-height: 38px;
    }}
    QPushButton#actionBtn:hover {{
        background: {BG_CREAM};
        border-color: {ACCENT};
        color: {ACCENT_HOVER};
    }}
"""


class MoodDialog(QDialog):
    interactionRequested = pyqtSignal(str)
    particleToggleRequested = pyqtSignal(bool)  # True=开启, False=关闭

    def __init__(self, parent=None, interaction_options: Optional[List[Dict[str, str]]] = None):
        super().__init__(parent)
        import sys
        self._is_mac = sys.platform == "darwin"
        # macOS 上 Qt.Popup + WA_TranslucentBackground 会崩溃，改用 Tool 窗口
        # 并手动处理点击外部关闭的行为
        if self._is_mac:
            # 与桌宠主窗一致：避免 Qt.Tool（NSPanel）在失焦时被系统隐藏
            self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            # 不抢前台，避免部分 macOS/Qt 版本在 activateWindow + 透明无边框时崩溃
            self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        else:
            self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._interaction_options = interaction_options or []
        self._drag_offset: Optional[QPoint] = None
        self._event_filter_installed = False  # 跟踪事件过滤器状态
        self._build_ui()

    def _build_ui(self) -> None:
        container = QFrame(self)
        container.setObjectName("panel")
        container.setStyleSheet(PANEL_STYLE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(10)

        self.title_label = QLabel("宠物状态")
        self.title_label.setObjectName("titleLabel")
        header_row.addWidget(self.title_label)
        header_row.addStretch()

        self.mood_label = QLabel("平静")
        self.mood_label.setObjectName("badgeLabel")
        header_row.addWidget(self.mood_label)

        self.close_button = QPushButton("×", self)
        self.close_button.setObjectName("closeBtn")
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.clicked.connect(self.hide)
        header_row.addWidget(self.close_button)
        layout.addLayout(header_row)

        self.desc_label = QLabel("状态安稳，想和你轻轻互动一下。")
        self.desc_label.setWordWrap(True)
        self.desc_label.setObjectName("descLabel")
        layout.addWidget(self.desc_label)

        self.mood_bar = self._add_stat_block(layout, "心情值", "开心", "moodBar")
        self.satiety_bar = self._add_stat_block(layout, "饱食度", "刚刚好", "satietyBar")
        self.energy_bar = self._add_stat_block(layout, "精力值", "状态稳定", "energyBar")

        self.recent_label = QLabel("最近互动：还没有记录")
        self.recent_label.setObjectName("metaLabel")
        layout.addWidget(self.recent_label)

        self.daily_label = QLabel("今天还没互动，右边的按钮点一点吧。")
        self.daily_label.setWordWrap(True)
        self.daily_label.setObjectName("metaLabel")
        layout.addWidget(self.daily_label)

        section = QLabel("快速互动")
        section.setObjectName("sectionLabel")
        layout.addWidget(section)

        self.button_grid = QGridLayout()
        self.button_grid.setHorizontalSpacing(10)
        self.button_grid.setVerticalSpacing(10)
        layout.addLayout(self.button_grid)

        self._buttons: Dict[str, QPushButton] = {}
        for index, item in enumerate(self._interaction_options):
            button = QPushButton(item["label"], self)
            button.setObjectName("actionBtn")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda checked=False, action_id=item["id"]: self.interactionRequested.emit(action_id))
            row = index // 2
            col = index % 2
            self.button_grid.addWidget(button, row, col)
            self._buttons[item["id"]] = button

        # 粒子特效开关
        self._particle_toggle_row = QHBoxLayout()
        self._particle_toggle_row.setContentsMargins(0, 4, 0, 0)
        self._particle_toggle_row.setSpacing(8)
        particle_hint = QLabel("✨ 心情粒子")
        particle_hint.setObjectName("sectionLabel")
        self._particle_toggle_row.addWidget(particle_hint)
        self._particle_toggle_row.addStretch()
        self._particle_btn = QPushButton("开", self)
        self._particle_btn.setObjectName("closeBtn")
        self._particle_btn.setCursor(Qt.PointingHandCursor)
        self._particle_btn.setFixedSize(36, 24)
        self._particle_btn.clicked.connect(self._on_particle_toggle)
        self._particle_toggle_row.addWidget(self._particle_btn)
        layout.addLayout(self._particle_toggle_row)

        self.setFixedWidth(360)

    def _add_stat_block(self, layout: QVBoxLayout, title: str, hint: str, object_name: str) -> QProgressBar:
        row = QVBoxLayout()
        row.setSpacing(5)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title_label = QLabel(title)
        title_label.setObjectName("statLabel")
        header.addWidget(title_label)
        header.addStretch()

        hint_label = QLabel(hint)
        hint_label.setObjectName("statHint")
        header.addWidget(hint_label)
        row.addLayout(header)

        bar = QProgressBar(self)
        bar.setObjectName(object_name)
        bar.setRange(0, 100)
        bar.setFormat("%v / 100")
        row.addWidget(bar)

        layout.addLayout(row)
        setattr(self, f"{object_name}_hint", hint_label)
        return bar

    def update_view(self, view_data: Dict[str, Any]) -> None:
        self.title_label.setText(f"{view_data.get('pet_name', '宠物')} 的状态")
        self.mood_label.setText(view_data.get("label", "平静"))
        self.desc_label.setText(view_data.get("description", ""))

        self.mood_bar.setValue(int(view_data.get("score", 0)))
        self.satiety_bar.setValue(int(view_data.get("satiety", 0)))
        self.energy_bar.setValue(int(view_data.get("energy", 0)))

        self.moodBar_hint.setText(view_data.get("label", "平静"))
        self.satietyBar_hint.setText(view_data.get("satiety_label", "刚刚好"))
        self.energyBar_hint.setText(view_data.get("energy_label", "状态稳定"))

        self.recent_label.setText(f"最近互动：{view_data.get('recent_interaction', '还没有记录')}")
        self.daily_label.setText(view_data.get("daily_hint", ""))

    def set_particle_enabled(self, enabled: bool) -> None:
        """由外部同步粒子开关状态到面板显示。"""
        self._particle_enabled = enabled
        self._particle_btn.setText("开" if enabled else "关")

    def _on_particle_toggle(self) -> None:
        new_state = not getattr(self, "_particle_enabled", True)
        self._particle_enabled = new_state
        self._particle_btn.setText("开" if new_state else "关")
        self.particleToggleRequested.emit(new_state)

    def show_at(self, global_pos: QPoint, pet_rect: Optional[QRect] = None) -> None:
        self.adjustSize()
        screen = QApplication.desktop().availableGeometry()

        if pet_rect is not None:
            prefer_right_x = pet_rect.right() + 14
            prefer_left_x = pet_rect.left() - self.width() - 14
            if prefer_right_x + self.width() <= screen.right():
                target_x = prefer_right_x
            elif prefer_left_x >= screen.left():
                target_x = prefer_left_x
            else:
                target_x = pet_rect.center().x() - self.width() // 2
            target_y = pet_rect.center().y() - self.height() // 2
        else:
            target_x = global_pos.x() + 12
            target_y = global_pos.y() + 12

        target_x = max(screen.x(), min(target_x, screen.right() - self.width()))
        target_y = max(screen.y(), min(target_y, screen.bottom() - self.height()))
        self.move(target_x, target_y)
        # macOS 上显示时安装事件过滤器
        if self._is_mac and not self._event_filter_installed:
            QApplication.instance().installEventFilter(self)
            self._event_filter_installed = True
        self.show()
        self.raise_()
        if not self._is_mac:
            self.activateWindow()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._drag_offset is not None:
            self.move(event.globalPos() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def eventFilter(self, obj, event):
        """macOS 上监听全局鼠标点击，点击对话框外部则关闭。"""
        if self._is_mac and self.isVisible():
            if event.type() == QEvent.MouseButtonPress:
                pet = self.parent()
                if pet is not None and isinstance(obj, QWidget):
                    if obj is pet or pet.isAncestorOf(obj):
                        # 点击仍落在桌宠窗口上（含用右键再次呼出面板）：勿当成「点外部」关闭，
                        # 否则会与 show 打架并可能触发闪退。
                        return False
                click_pos = event.globalPos()
                dialog_rect = self.rect()
                dialog_top_left = self.mapToGlobal(dialog_rect.topLeft())
                global_rect = QRect(dialog_top_left, dialog_rect.size())
                if not global_rect.contains(click_pos):
                    self.hide()
                    return True  # 过滤该事件
        return super().eventFilter(obj, event)

    def hideEvent(self, event):
        """隐藏时移除事件过滤器。"""
        if self._is_mac and self._event_filter_installed:
            QApplication.instance().removeEventFilter(self)
            self._event_filter_installed = False
        super().hideEvent(event)
