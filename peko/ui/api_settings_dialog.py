"""
AI 设置（简单聊天版）

- AiSettingsPanel：可内嵌 QWidget，供「设置」页直接使用；含 三要素表单 + 测试连接 + 保存。
- ApiSettingsDialog：独立弹窗，包一层 AiSettingsPanel（托盘等旧入口向后兼容）。

温度 / 最大 Token 用内置基础默认值，用户无需关心。
"""
import sys

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFormLayout, QMessageBox,
)

from ..ai.config_loader import load_user_api_config, save_ai_settings, DEFAULT_TEMPERATURE, DEFAULT_MAX_TOKENS
from ..ai.service import test_connection


def _font_family() -> str:
    return "PingFang SC" if sys.platform == "darwin" else "Microsoft YaHei"


def _panel_style() -> str:
    """AI 面板样式：按当前外观主题的 UI 色板生成。"""
    try:
        from ..core import appearance as appearance_mod
        ui = appearance_mod.get_ui_style(appearance_mod.get_theme())
    except Exception:
        ui = {"bg": "#faf3e0", "card": "#fffef9", "accent": "#c4a574", "accent_hover": "#b59668",
              "ink": "#4a3f35", "ink_soft": "#9a8f7f", "border": "#e8dcc4"}
    return f"""
    QWidget {{ background-color: transparent; font-family: '{_font_family()}'; }}
    QLabel {{ color: {ui['ink']}; font-size: 14px; }}
    QLabel#hint {{ color: {ui['ink_soft']}; font-size: 12px; }}
    QLabel#status_ok {{ color: #3f7d4e; font-weight: 600; font-size: 13px; }}
    QLabel#status_err {{ color: #b0554c; font-weight: 600; font-size: 13px; }}
    QLineEdit {{
        background-color: {ui['card']};
        border: 1.5px solid {ui['border']};
        border-radius: 8px;
        padding: 9px 12px;
        color: {ui['ink']};
        font-size: 14px;
        selection-background-color: {ui['border']};
    }}
    QLineEdit:hover {{ border-color: {ui['ink_soft']}; }}
    QLineEdit:focus {{ border-color: {ui['accent']}; background-color: {ui['card']}; }}
    QPushButton {{
        background-color: {ui['card']};
        border: 1.5px solid {ui['border']};
        border-radius: 8px;
        padding: 9px 22px;
        color: {ui['ink']};
        font-size: 13px;
        font-family: '{_font_family()}';
    }}
    QPushButton:hover {{ background-color: {ui['bg']}; }}
    QPushButton:pressed {{ background-color: {ui['border']}; }}
    QPushButton#primary {{
        background-color: {ui['accent']};
        color: {ui['card']};
        font-weight: 600;
        border: none;
        padding: 9px 26px;
    }}
    QPushButton#primary:hover {{ background-color: {ui['accent_hover']}; }}
    QPushButton#test {{ background-color: #eef3e9; border: 1.5px solid #c9d6bd; color: #4c6b4c; }}
    QPushButton#test:hover {{ background-color: #e3ecdc; }}
    QPushButton:disabled {{ color: {ui['ink_soft']}; background-color: {ui['border']}; border-color: {ui['border']}; }}
"""


class _TestWorker(QThread):
    """后台线程执行连接测试，避免卡住界面。"""
    result = pyqtSignal(bool, str)

    def __init__(self, api_url: str, api_key: str, model: str, parent=None):
        super().__init__(parent)
        self.api_url = api_url
        self.api_key = api_key
        self.model = model

    def run(self):
        ok, msg = test_connection(self.api_url, self.api_key, self.model)
        self.result.emit(ok, msg)


class AiSettingsPanel(QWidget):
    """内嵌 AI 配置面板：URL / Key / 模型名 + 测试连接 + 保存。"""

    saved = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_panel_style())
        self._worker = None
        self.setup_ui()

    def apply_theme(self):
        """外观主题切换后刷新配色。"""
        self.setStyleSheet(_panel_style())

    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setHorizontalSpacing(16)

        user = load_user_api_config()

        self.api_url_edit = QLineEdit(self)
        self.api_url_edit.setPlaceholderText("https://api.xxx.com/v1/chat/completions")
        self.api_url_edit.setToolTip("可填完整地址（含 /chat/completions），也可只填基础地址，会自动补全。")
        self.api_url_edit.setText(user.get("apiUrl", ""))
        form.addRow("API URL", self.api_url_edit)

        self.api_key_edit = QLineEdit(self)
        self.api_key_edit.setPlaceholderText("sk-...")
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setText(user.get("apiKey", ""))
        form.addRow("API Key", self.api_key_edit)

        self.model_edit = QLineEdit(self)
        self.model_edit.setPlaceholderText("如 gpt-4o / deepseek-chat")
        self.model_edit.setText(user.get("model", ""))
        form.addRow("模型名", self.model_edit)

        root.addLayout(form)
        root.addSpacing(4)

        hint = QLabel("任意 OpenAI 兼容服务都能用：SiliconFlow、DeepSeek、Kimi、GLM、通义、Ollama 等。\nURL 可填基础地址，保存 / 测试时自动补全 /chat/completions。")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.status_label = QLabel("")
        self.status_label.setObjectName("status_ok")
        root.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        test_btn = QPushButton("测试连接", self)
        test_btn.setObjectName("test")
        test_btn.clicked.connect(self.run_test)
        self.test_btn = test_btn
        btn_row.addWidget(test_btn)
        btn_row.addStretch(1)
        save_btn = QPushButton("保存并应用", self)
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self.save_and_emit)
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)

    # ----- 测试连接 -----
    def run_test(self):
        api_url = self.api_url_edit.text().strip()
        api_key = self.api_key_edit.text().strip()
        model = self.model_edit.text().strip()
        if not api_url or not api_key or not model:
            self._show_status(False, "请先完整填写 API URL / Key / 模型名")
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText("测试中…")
        self.status_label.setObjectName("status_ok")
        self.status_label.setText("正在连接，请稍候…")
        self.status_label.repaint()
        self._worker = _TestWorker(api_url, api_key, model, self)
        self._worker.result.connect(self._on_test_result)
        self._worker.finished.connect(self._on_test_finished)
        self._worker.start()

    def _on_test_result(self, ok: bool, msg: str):
        self._show_status(ok, msg)

    def _on_test_finished(self):
        self.test_btn.setEnabled(True)
        self.test_btn.setText("测试连接")

    def _show_status(self, ok: bool, msg: str):
        self.status_label.setObjectName("status_ok" if ok else "status_err")
        self.status_label.setText(msg)

    # ----- 保存 -----
    def save_and_emit(self):
        if self.save():
            self._show_status(True, "已保存，下次对话立即生效 ✓")
            self.saved.emit()

    def save(self) -> bool:
        """保存当前表单；成功返回 True。"""
        api_url = self.api_url_edit.text().strip()
        api_key = self.api_key_edit.text().strip()
        model = self.model_edit.text().strip()
        if not api_url or not model:
            QMessageBox.warning(self, "提示", "请填写 API URL 和模型名，再保存。")
            return False
        try:
            save_ai_settings(
                api_url=api_url,
                api_key=api_key,
                model=model,
                temperature=DEFAULT_TEMPERATURE,
                max_tokens=DEFAULT_MAX_TOKENS,
            )
        except Exception as e:
            QMessageBox.warning(self, "提示", f"保存失败：{e}")
            return False
        return True


class ApiSettingsDialog(QDialog):
    """独立 AI 设置弹窗（旧入口兼容），内部即 AiSettingsPanel。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 设置")
        self.setMinimumWidth(520)
        self.setStyleSheet(_panel_style())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        title = QLabel("AI 设置")
        try:
            from ..core import appearance as appearance_mod
            ink = appearance_mod.get_ui_style(appearance_mod.get_theme())["ink"]
        except Exception:
            ink = "#3d3329"
        title.setStyleSheet(f"font-size: 20px; font-weight: 600; color: {ink};")
        layout.addWidget(title)
        layout.addSpacing(6)
        self.panel = AiSettingsPanel(self)
        layout.addWidget(self.panel)
        self.panel.saved.connect(self._on_saved)

    def _on_saved(self):
        QMessageBox.information(self, "已保存", "AI 设置已保存，下次对话立即生效。")
        self.accept()
