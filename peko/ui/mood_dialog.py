"""Mood interaction panel."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, QPoint, QRect, pyqtSignal
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
)


PANEL_STYLE = """
    QFrame#panel {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #fff8ef, stop:1 #f9ecd8);
        border: 1px solid #e7d3b3;
        border-radius: 20px;
    }
    QLabel#titleLabel {
        color: #4f3f33;
        font-size: 17px;
        font-weight: 700;
    }
    QLabel#badgeLabel {
        color: #8d5d2f;
        font-size: 13px;
        font-weight: 700;
        background: rgba(255, 255, 255, 0.7);
        border-radius: 10px;
        padding: 5px 10px;
    }
    QLabel#descLabel {
        color: #5b4a3d;
        font-size: 13px;
    }
    QLabel#metaLabel {
        color: #846b57;
        font-size: 12px;
    }
    QLabel#sectionLabel {
        color: #6d5644;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.5px;
    }
    QLabel#statLabel {
        color: #5d4a3a;
        font-size: 12px;
        font-weight: 700;
    }
    QLabel#statHint {
        color: #8b6f58;
        font-size: 11px;
    }
    QPushButton#closeBtn {
        background: rgba(255, 255, 255, 0.8);
        border: 1px solid #e2c7a5;
        border-radius: 12px;
        color: #7a6250;
        font-size: 14px;
        font-weight: 700;
        min-width: 24px;
        max-width: 24px;
        min-height: 24px;
        max-height: 24px;
        padding: 0;
    }
    QPushButton#closeBtn:hover {
        background: #fffef9;
        border-color: #d2a56c;
        color: #5a4738;
    }
    QProgressBar {
        border: none;
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.7);
        color: #6d5644;
        text-align: center;
        height: 16px;
        font-size: 11px;
        font-weight: 700;
    }
    QProgressBar#moodBar::chunk {
        border-radius: 8px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #f0bf77, stop:1 #d28e51);
    }
    QProgressBar#satietyBar::chunk {
        border-radius: 8px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #76c17a, stop:1 #4ea861);
    }
    QProgressBar#energyBar::chunk {
        border-radius: 8px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #74b6ff, stop:1 #4c86e6);
    }
    QPushButton#actionBtn {
        background: rgba(255, 255, 255, 0.88);
        border: 1px solid #e2c7a5;
        border-radius: 14px;
        padding: 10px 12px;
        color: #5a4738;
        font-size: 13px;
        font-weight: 700;
        min-height: 38px;
    }
    QPushButton#actionBtn:hover {
        background: #fffef9;
        border-color: #d2a56c;
    }
"""


class MoodDialog(QDialog):
    interactionRequested = pyqtSignal(str)

    def __init__(self, parent=None, interaction_options: Optional[List[Dict[str, str]]] = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._interaction_options = interaction_options or []
        self._drag_offset: Optional[QPoint] = None
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
        self.show()
        self.raise_()
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
