"""
API 设置对话框：编辑 config/secrets.json 中的 apiKey、config/api.json 中的 modelId（可选，也可直接编辑配置文件）
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QFormLayout, QMessageBox,
)

from ..ai.config_loader import (
    get_models,
    load_user_api_config,
    save_user_api_config,
    get_ai_config,
)


class ApiSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑 API 配置（config/secrets.json + api.json）")
        self.setMinimumWidth(400)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.api_key_edit = QLineEdit(self)
        self.api_key_edit.setPlaceholderText("请输入 API Key（必填）")
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        user = load_user_api_config()
        self.api_key_edit.setText(user.get("apiKey", ""))
        form.addRow("API Key:", self.api_key_edit)

        self.model_combo = QComboBox(self)
        models = get_models()
        current_id = user.get("modelId") or (get_ai_config().get("modelId"))
        current_index = 0
        for i, m in enumerate(models):
            self.model_combo.addItem(m.get("name", m.get("id", "")), m.get("id"))
            if m.get("id") == current_id:
                current_index = i
        self.model_combo.setCurrentIndex(max(0, current_index))
        form.addRow("模型:", self.model_combo)

        layout.addLayout(form)

        hint = QLabel("支持 SiliconFlow、OpenAI、豆包等兼容接口；讯飞星火需在下方或环境变量配置。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(hint)

        save_btn = QPushButton("保存并应用", self)
        save_btn.clicked.connect(self.save_and_close)
        cancel_btn = QPushButton("取消", self)
        cancel_btn.clicked.connect(self.reject)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def save_and_close(self):
        api_key = self.api_key_edit.text().strip()
        model_id = self.model_combo.currentData() or self.model_combo.currentText()
        if not api_key and not load_user_api_config().get("apiKey"):
            QMessageBox.warning(
                self,
                "提示",
                "请填写 API Key 后再与宠物对话。也可直接编辑 config/secrets.json。",
            )
        save_user_api_config(api_key=api_key, model_id=model_id)
        self.accept()
