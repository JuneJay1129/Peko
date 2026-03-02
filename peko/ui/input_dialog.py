from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel,
    QFrame,
)
from PyQt5.QtGui import QFont

# 与宠物气泡一致：半透明白底、绿色边框、圆角 15px、padding 10px
CONTAINER_STYLE = """
    QFrame#dialogContainer {
        background-color: rgba(255, 255, 255, 0.9);
        border: 2px solid #4CAF50;
        border-radius: 15px;
        padding: 10px;
    }
"""

CONTENT_STYLE = """
    QLineEdit {
        font-size: 14px;
        border: 1px solid #CCCCCC;
        border-radius: 8px;
        padding: 5px;
        background: white;
        selection-background-color: #4CAF50;
    }
    QLineEdit:focus {
        border-color: #4CAF50;
    }
    QPushButton#sendBtn {
        font-size: 14px;
        background-color: #4CAF50;
        color: white;
        border-radius: 10px;
        padding: 5px 15px;
    }
    QPushButton#sendBtn:hover {
        background-color: #45A049;
    }
    QPushButton#closeBtn {
        font-size: 16px;
        font-weight: 300;
        background: transparent;
        color: #666;
        border: none;
        border-radius: 10px;
        padding: 2px 8px;
        min-width: 28px;
        min-height: 28px;
    }
    QPushButton#closeBtn:hover {
        background-color: rgba(0,0,0,0.08);
        color: #333;
    }
"""


class InputDialog(QDialog):
    def __init__(self, parent, on_submit):
        """
        与宠物对话对话框：四周圆角、右上角 × 关闭。
        """
        super().__init__(parent)
        self.setWindowTitle("与宠物对话")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 圆角容器
        container = QFrame(self)
        container.setObjectName("dialogContainer")
        container.setStyleSheet(CONTAINER_STYLE + CONTENT_STYLE)

        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # 标题行：左侧标题 + 右侧 × 关闭
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 4)
        title_label = QLabel("与宠物对话")
        title_label.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        title_label.setStyleSheet("color: black;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
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
        send_btn = QPushButton("发送", self)
        send_btn.setObjectName("sendBtn")
        send_btn.setCursor(Qt.PointingHandCursor)
        send_btn.clicked.connect(lambda: self.submit_text(on_submit))
        btn_layout.addWidget(send_btn)
        main_layout.addLayout(btn_layout)

        # 将容器铺满对话框
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)

        # 与气泡一致：气泡 max_width 200，对话框略大以容纳输入框和按钮
        self.setFixedSize(260, 160)

    def submit_text(self, on_submit):
        """
        处理用户输入并调用回调函数。
        """
        text = self.input_field.text().strip()
        if text:
            on_submit(self, text)  # 调用回调函数
        self.close()
