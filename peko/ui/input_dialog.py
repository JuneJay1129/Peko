from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel,
    QFrame,
)
from PyQt5.QtGui import QFont
import sys

from .theme import (
    BG_CREAM, BG_CONTENT, BG_INPUT, BG_HOVER,
    TEXT_PRIMARY, TEXT_BODY, TEXT_SECONDARY, TEXT_MUTED,
    BORDER_LIGHT, BORDER_WARM, ACCENT, ACCENT_HOVER,
    BTN_GREEN, BTN_GREEN_HOVER, BTN_GREEN_PRESS,
    RADIUS_SM, RADIUS_BASE, RADIUS_LG, RADIUS_PILL,
    FONT_FAMILY, FONT_SIZE_BASE, FONT_SIZE_TITLE,
)
from .round_button import RoundButton


def _dialog_font():
    """跨平台字体：Mac 无 Microsoft YaHei，用 PingFang SC。"""
    return QFont("PingFang SC" if sys.platform == "darwin" else "Microsoft YaHei", 14, QFont.Bold)


CONTAINER_STYLE = f"""
    QFrame#dialogContainer {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {BG_CREAM}, stop:1 {BG_CONTENT});
        border: 2px solid {BORDER_WARM};
        border-radius: {RADIUS_LG}px;
    }}
"""

CONTENT_STYLE = f"""
    QLineEdit {{
        font-size: {FONT_SIZE_BASE}px;
        border: 2.5px solid {BORDER_LIGHT};
        border-radius: {RADIUS_PILL}px;
        padding: 6px 14px;
        background: {BG_INPUT};
        color: {TEXT_BODY};
        font-family: {FONT_FAMILY};
    }}
    QLineEdit:focus {{
        border-color: {ACCENT};
        background: #ffffff;
    }}
    QLineEdit::placeholder {{
        color: {TEXT_MUTED};
    }}
    QPushButton#sendBtn {{
        font-size: {FONT_SIZE_BASE}px;
        font-weight: 700;
        background: {BTN_GREEN};
        color: {TEXT_PRIMARY};
        border: 2px solid {BTN_GREEN};
        border-radius: {RADIUS_PILL}px;
        padding: 5px 18px;
    }}
    QPushButton#sendBtn:hover {{
        background: {BTN_GREEN_HOVER};
        border-color: {BTN_GREEN_HOVER};
    }}
    QPushButton#sendBtn:pressed {{
        background: {BTN_GREEN_PRESS};
        border-color: {BTN_GREEN_PRESS};
    }}
    QPushButton#expandBtn {{
        font-size: 13px;
        font-weight: 300;
        background: transparent;
        color: {TEXT_SECONDARY};
        border: none;
        border-radius: 10px;
        padding: 2px 6px;
        min-width: 24px;
        min-height: 24px;
    }}
    QPushButton#expandBtn:hover {{
        background: {BG_HOVER};
        color: {ACCENT};
    }}
    QPushButton#closeBtn {{
        font-size: 14px;
        font-weight: 300;
        background: transparent;
        color: {TEXT_SECONDARY};
        border: none;
        border-radius: 10px;
        padding: 2px 6px;
        min-width: 24px;
        min-height: 24px;
    }}
    QPushButton#closeBtn:hover {{
        background: {BG_HOVER};
        color: {TEXT_PRIMARY};
    }}
"""


class InputDialog(QDialog):
    def __init__(self, parent, on_submit, on_expand=None):
        """
        与宠物对话对话框：四周圆角、右上角 ⤢ 展开 + × 关闭。
        on_expand: 可选回调，点击展开按钮时调用（打开完整聊天窗口）。
        """
        super().__init__(parent)
        self._on_expand = on_expand
        self.setWindowTitle("与宠物对话")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 圆角容器
        container = QFrame(self)
        container.setObjectName("dialogContainer")
        container.setStyleSheet(CONTAINER_STYLE + CONTENT_STYLE)

        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(16, 12, 16, 12)

        # 标题行：左侧标题 + 右侧 ⤢ 展开 + × 关闭
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 2)
        title_label = QLabel("🐹 与宠物对话")
        title_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: {FONT_SIZE_BASE}px; font-weight: 700; font-family: {FONT_FAMILY};")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        expand_btn = QPushButton("⤢", self)
        expand_btn.setObjectName("expandBtn")
        expand_btn.setCursor(Qt.PointingHandCursor)
        expand_btn.setToolTip("展开完整聊天窗口")
        expand_btn.clicked.connect(self._expand)
        header_layout.addWidget(expand_btn)
        close_btn = QPushButton("×", self)
        close_btn.setObjectName("closeBtn")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        header_layout.addWidget(close_btn)
        main_layout.addLayout(header_layout)

        # 输入框
        self.input_field = QLineEdit(self)
        self.input_field.setPlaceholderText("请输入想说的话...")
        self.input_field.setFocusPolicy(Qt.ClickFocus)
        main_layout.addWidget(self.input_field)

        # 发送按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        send_btn = RoundButton("发送", self, radius=12, padding_h=18, padding_v=5)
        send_btn.clicked.connect(lambda: self.submit_text(on_submit))
        btn_layout.addWidget(send_btn)
        main_layout.addLayout(btn_layout)

        # 将容器铺满对话框
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)

        # 与气泡一致：气泡 max_width 200，对话框略大以容纳输入框和按钮
        self.setFixedSize(300, 155)

    def submit_text(self, on_submit):
        """
        处理用户输入并调用回调函数。
        """
        text = self.input_field.text().strip()
        if text:
            on_submit(self, text)  # 调用回调函数
        self.close()

    def _expand(self):
        """关闭小输入框，打开完整聊天窗口。"""
        if self._on_expand:
            self._on_expand()
        self.close()
