from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QPushButton


# 与宠物气泡一致：圆角、半透明白底、绿色边框
BUBBLE_STYLE = """
    QDialog {
        background-color: rgba(255, 255, 255, 0.9);
        border: 2px solid #4CAF50;
        border-radius: 15px;
        padding: 10px;
    }
    QLineEdit {
        font-size: 14px;
        border: 1px solid #CCCCCC;
        border-radius: 8px;
        padding: 5px;
        background: white;
    }
    QPushButton {
        font-size: 14px;
        background-color: #4CAF50;
        color: white;
        border-radius: 10px;
        padding: 5px 15px;
    }
    QPushButton:hover {
        background-color: #45A049;
    }
"""


class InputDialog(QDialog):
    def __init__(self, parent, on_submit):
        """
        自定义输入对话框，样式与宠物气泡一致（圆角气泡）。
        """
        super().__init__(parent)
        self.setWindowTitle("与宠物对话")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)  # 透明背景，只显示圆角气泡区域
        self.setStyleSheet(BUBBLE_STYLE)

        # 输入框
        self.layout = QVBoxLayout(self)
        self.input_field = QLineEdit(self)
        self.input_field.setPlaceholderText("请输入想说的话...")
        self.input_field.setFocusPolicy(Qt.ClickFocus)  # 仅在用户点击时显示光标
        self.layout.addWidget(self.input_field)

        # 确定按钮
        self.button = QPushButton("发送", self)
        self.button.clicked.connect(lambda: self.submit_text(on_submit))
        self.layout.addWidget(self.button)

        self.setLayout(self.layout)
        self.setFixedSize(300, 150)

    def submit_text(self, on_submit):
        """
        处理用户输入并调用回调函数。
        """
        text = self.input_field.text().strip()
        if text:
            on_submit(self, text)  # 调用回调函数
        self.close()
