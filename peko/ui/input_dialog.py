from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel,
    QFrame,
)
from PyQt5.QtGui import QFont
import sys


def _dialog_font():
    """跨平台字体：Mac 无 Microsoft YaHei，用 PingFang SC。"""
    return QFont("PingFang SC" if sys.platform == "darwin" else "Microsoft YaHei", 14, QFont.Bold)


def _dialog_styles() -> str:
    """对话框样式：按当前外观主题的 UI 色板生成（容器 + 控件）。"""
    try:
        from ..core import appearance as ap
        ui = ap.get_ui_style(ap.get_theme())
    except Exception:
        ui = {"bg": "#faf3e0", "card": "#ffffff", "accent": "#4CAF50", "accent_hover": "#45A049",
              "ink": "#333333", "ink_soft": "#888888", "border": "#CCCCCC"}
    return f"""
    QFrame#dialogContainer {{
        background-color: {ui['card']};
        border: 2px solid {ui['accent']};
        border-radius: 15px;
        padding: 10px;
    }}
    QLineEdit {{
        font-size: 14px;
        border: 1px solid {ui['border']};
        border-radius: 8px;
        padding: 5px;
        background: {ui['card']};
        color: {ui['ink']};
        selection-background-color: {ui['accent']};
    }}
    QLineEdit:focus {{
        border-color: {ui['accent']};
    }}
    QPushButton#sendBtn {{
        font-size: 14px;
        background-color: {ui['accent']};
        color: #ffffff;
        border-radius: 10px;
        padding: 5px 15px;
    }}
    QPushButton#sendBtn:hover {{
        background-color: {ui['accent_hover']};
    }}
    QPushButton#quickBtn {{
        font-size: 12px;
        background-color: {ui['bg']};
        color: {ui['accent']};
        border: 1px solid {ui['accent']};
        border-radius: 8px;
        padding: 3px 10px;
    }}
    QPushButton#quickBtn:hover {{
        background-color: {ui['border']};
    }}
    QLabel#hintLabel {{
        font-size: 11px;
        color: {ui['ink_soft']};
    }}
    QPushButton#closeBtn {{
        font-size: 16px;
        font-weight: 300;
        background: transparent;
        color: {ui['ink_soft']};
        border: none;
        border-radius: 10px;
        padding: 2px 8px;
        min-width: 28px;
        min-height: 28px;
    }}
    QPushButton#closeBtn:hover {{
        background-color: {ui['border']};
        color: {ui['ink']};
    }}
"""


# 快捷指令模板：(按钮名, 模板文本, 选中起点, 选中长度)。模板与 nl_intent 的识别句式一一对应，
# 选中区即用户要改的「关键字段」——选中后直接 typing 即替换。
# 记账拆成「记支出 / 记收入」两个按钮，模板带「支出/收入」字样，类型一目了然；
# nl_intent 会按该词自动判定 kind，且不会把「支出/收入」写进标题。
QUICK_COMMANDS = [
    ("记支出", "记一笔 支出 午饭 38", 7, 5),      # 选中「午饭 38」
    ("记收入", "记一笔 收入 兼职 500", 7, 6),     # 选中「兼职 500」
    ("待办", "提醒我 17:00 交周报", 4, 9),         # 选中「17:00 交周报」
    ("专注", "开始专注 25 分钟", 5, 2),           # 选中「25」
]


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
        container.setStyleSheet(_dialog_styles())

        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # 标题行：左侧标题 + 右侧 × 关闭
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 4)
        title_label = QLabel("与宠物对话")
        title_label.setFont(_dialog_font())
        try:
            from ..core import appearance as ap
            title_label.setStyleSheet(f"color: {ap.get_ui_style(ap.get_theme())['ink']};")
        except Exception:
            title_label.setStyleSheet("color: black;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        close_btn = QPushButton("×", self)
        close_btn.setObjectName("closeBtn")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        header_layout.addWidget(close_btn)
        main_layout.addLayout(header_layout)

        # 快捷指令按钮：点击自动填入模板并选中关键字段，用户改几个字即可（全程非 AI）
        quick_layout = QHBoxLayout()
        quick_layout.setSpacing(6)
        for label, template, sel_start, sel_len in QUICK_COMMANDS:
            btn = QPushButton(label, self)
            btn.setObjectName("quickBtn")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(
                lambda checked=False, t=template, s=sel_start, n=sel_len: self.fill_template(t, s, n)
            )
            quick_layout.addWidget(btn)
        quick_layout.addStretch()
        main_layout.addLayout(quick_layout)

        # 输入框
        self.input_field = QLineEdit(self)
        self.input_field.setPlaceholderText("想说的话，或点上方按钮快速记录...")
        self.input_field.setFocusPolicy(Qt.ClickFocus)
        main_layout.addWidget(self.input_field)

        # 用法提示（非 AI 引导）
        hint_label = QLabel("点快捷按钮填模板，改选中部分即可；手动输入也行：记一笔 支出 午饭 38 / 记一笔 收入 兼职 500")
        hint_label.setObjectName("hintLabel")
        hint_label.setWordWrap(True)
        main_layout.addWidget(hint_label)

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
        self.setFixedSize(320, 230)

    def fill_template(self, template: str, sel_start: int, sel_len: int) -> None:
        """快捷按钮：填入模板并选中关键字段，用户直接 typing 即替换。"""
        self.input_field.setText(template)
        self.input_field.setFocus()
        self.input_field.setSelection(sel_start, sel_len)

    def submit_text(self, on_submit):
        """
        处理用户输入并调用回调函数。
        """
        text = self.input_field.text().strip()
        if text:
            on_submit(self, text)  # 调用回调函数
        self.close()
