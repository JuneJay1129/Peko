"""
API 设置对话框：编辑 config/secrets.json 中的 apiKey、config/api.json 中的 modelId。
Animal Island UI 风格。
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QFormLayout, QMessageBox, QFrame,
)

from ..ai.config_loader import (
    get_models,
    load_user_api_config,
    save_user_api_config,
    get_ai_config,
)
from .theme import (
    BG_CREAM, BG_CONTENT, BG_INPUT, TEXT_PRIMARY, TEXT_BODY, TEXT_SECONDARY,
    TEXT_MUTED, BORDER_LIGHT, BORDER_WARM, BORDER_FOCUS, ACCENT, ACCENT_HOVER,
    BTN_GREEN, BTN_GREEN_HOVER, BTN_GREEN_PRESS, BTN_DISABLED,
    RADIUS_SM, RADIUS_LG, RADIUS_PILL, FONT_FAMILY,
    FONT_SIZE_BASE, FONT_SIZE_TITLE, FONT_SIZE_SM,
    DIALOG_CONTAINER_QSS, INPUT_QSS, COMBOBOX_QSS,
    PRIMARY_BUTTON_QSS, SECONDARY_BUTTON_QSS, CLOSE_BUTTON_QSS,
)

_DIALOG_STYLE = f"""
    QDialog {{
        background: transparent;
    }}
    QFrame#dialogContainer {{
        {DIALOG_CONTAINER_QSS}
        padding: 32px;
    }}
    QLabel#titleLabel {{
        color: {TEXT_PRIMARY};
        font-size: {FONT_SIZE_TITLE}px;
        font-weight: 700;
    }}
    QLabel#hintLabel {{
        color: {TEXT_SECONDARY};
        font-size: {FONT_SIZE_SM}px;
    }}
    QLabel#formLabel {{
        color: {TEXT_BODY};
        font-size: {FONT_SIZE_BASE}px;
        font-weight: 600;
    }}
    QLineEdit#apiKeyInput {{
        {INPUT_QSS}
    }}
    QComboBox#modelCombo {{
        {COMBOBOX_QSS}
    }}
    QPushButton#saveBtn {{
        background: {BTN_GREEN};
        color: #ffffff;
        font-size: {FONT_SIZE_BASE}px;
        font-weight: 700;
        border: 2px solid {BTN_GREEN};
        border-radius: {RADIUS_PILL}px;
        padding: 10px 28px;
        letter-spacing: 0.02em;
    }}
    QPushButton#saveBtn:hover {{
        background: {BTN_GREEN_HOVER};
        border-color: {BTN_GREEN_HOVER};
    }}
    QPushButton#saveBtn:pressed {{
        background: {BTN_GREEN_PRESS};
        border-color: {BTN_GREEN_PRESS};
    }}
    QPushButton#cancelBtn {{
        background: {BG_INPUT};
        color: {TEXT_BODY};
        font-size: {FONT_SIZE_BASE}px;
        font-weight: 500;
        border: 2px solid {BORDER_LIGHT};
        border-radius: {RADIUS_PILL}px;
        padding: 10px 28px;
    }}
    QPushButton#cancelBtn:hover {{
        color: {ACCENT};
        border-color: {ACCENT};
    }}
"""


class ApiSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ AI 设置")
        self.setMinimumWidth(420)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._setup_ui()

    def _setup_ui(self):
        # 外层透明布局
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # 圆角容器
        container = QFrame(self)
        container.setObjectName("dialogContainer")

        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        # ── 标题行 ──
        header_row = QHBoxLayout()
        header_row.setSpacing(10)
        title = QLabel("⚙️ AI 设置")
        title.setObjectName("titleLabel")
        header_row.addWidget(title)
        header_row.addStretch()

        close_btn = QPushButton("×", self)
        close_btn.setObjectName("closeBtn")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        header_row.addWidget(close_btn)
        layout.addLayout(header_row)

        # ── 分隔线 ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background: {BORDER_LIGHT}; max-height: 1px; border: none;")
        layout.addWidget(sep)

        # ── 表单 ──
        form = QFormLayout()
        form.setSpacing(12)
        form.setContentsMargins(0, 8, 0, 8)

        api_key_label = QLabel("🔑 API Key")
        api_key_label.setObjectName("formLabel")
        self.api_key_edit = QLineEdit(self)
        self.api_key_edit.setObjectName("apiKeyInput")
        self.api_key_edit.setPlaceholderText("请输入 API Key")
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        user = load_user_api_config()
        self.api_key_edit.setText(user.get("apiKey", ""))
        form.addRow(api_key_label, self.api_key_edit)

        model_label = QLabel("🤖 模型")
        model_label.setObjectName("formLabel")
        self.model_combo = QComboBox(self)
        self.model_combo.setObjectName("modelCombo")
        models = get_models()
        current_id = user.get("modelId") or (get_ai_config().get("modelId"))
        current_index = 0
        for i, m in enumerate(models):
            self.model_combo.addItem(m.get("name", m.get("id", "")), m.get("id"))
            if m.get("id") == current_id:
                current_index = i
        self.model_combo.setCurrentIndex(max(0, current_index))
        form.addRow(model_label, self.model_combo)

        layout.addLayout(form)

        # ── 提示 ──
        hint = QLabel("支持 SiliconFlow、OpenAI、豆包、小米 MiMo 等兼容接口。")
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ── 按钮行 ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch()

        cancel_btn = QPushButton("取消", self)
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("保存并应用", self)
        save_btn.setObjectName("saveBtn")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self.save_and_close)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

        outer.addWidget(container)
        self.setStyleSheet(_DIALOG_STYLE)

        # 关闭按钮样式（复用 theme）
        close_btn.setStyleSheet(f"""
            QPushButton {{
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
            QPushButton:hover {{
                background: {BG_CREAM};
                border-color: {ACCENT};
                color: {TEXT_PRIMARY};
            }}
        """)

    def save_and_close(self):
        api_key = self.api_key_edit.text().strip()
        existing_api_key = load_user_api_config().get("apiKey", "")
        model_id = self.model_combo.currentData() or self.model_combo.currentText()
        if not api_key and not existing_api_key:
            QMessageBox.warning(self, "提示", "请先填写 API Key，再保存设置。")
            return
        save_user_api_config(api_key=api_key or existing_api_key, model_id=model_id)
        QMessageBox.information(self, "已保存", "AI 设置已保存，并会在下次对话时立即生效。")
        self.accept()
