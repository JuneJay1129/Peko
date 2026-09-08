"""
Peko 设置页：导航式设置窗口。

左侧分类导航（模式 / AI / 天气 / 动作参数 / 计划台 / 宠物），右侧对应面板。
- AI：内嵌 AiSettingsPanel（URL / Key / 模型 + 测试连接 + 保存），不再弹窗。
- 动作参数：内嵌 ActionParamsPanel，右侧直接调各动作参数。
- 计划台：内嵌 PlansWebPanel（懒加载），并提供「在浏览器打开工作台」。
- 托盘菜单只保留高频项 + 设置入口；模式 / 摧毁文件 / 安慰我 留在托盘。

后期新增设置项：加一个分类 + 一个面板即可，不影响托盘。
"""
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QListWidget,
    QListWidgetItem, QStackedWidget, QPushButton, QLineEdit, QMessageBox,
    QButtonGroup,
)


def _font_family() -> str:
    return "PingFang SC" if sys.platform == "darwin" else "Microsoft YaHei UI"


def _build_style(ui: dict) -> str:
    """按外观主题的 UI 色板生成设置页全局样式。"""
    return f"""
    QDialog {{
        background-color: {ui['bg']};
        font-family: '{_font_family()}';
    }}
    QLabel {{ color: {ui['ink']}; font-size: 14px; }}
    QLabel#page_title {{ font-size: 23px; font-weight: 600; color: {ui['ink']}; }}
    QLabel#hint {{ color: {ui['ink_soft']}; font-size: 12px; line-height: 1.5; }}
    QLabel#desc {{ color: {ui['ink_soft']}; font-size: 12px; }}
    QListWidget {{
        background-color: {ui['border']};
        border: none;
        border-radius: 12px;
        padding: 6px;
        outline: 0;
    }}
    QListWidget::item {{
        padding: 12px 18px;
        border-radius: 8px;
        color: {ui['ink']};
        font-size: 14px;
    }}
    QListWidget::item:hover {{ background-color: {ui['bg']}; }}
    QListWidget::item:selected {{
        background-color: {ui['accent']};
        color: {ui['card']};
        font-weight: 600;
    }}
    QWidget#page {{
        background-color: {ui['card']};
        border: 1px solid {ui['border']};
        border-radius: 14px;
    }}
    QPushButton {{
        background-color: {ui['card']};
        border: 1.5px solid {ui['border']};
        border-radius: 10px;
        padding: 10px 24px;
        color: {ui['ink']};
        font-size: 14px;
        font-family: '{_font_family()}';
    }}
    QPushButton:hover {{ background-color: {ui['bg']}; }}
    QPushButton:pressed {{ background-color: {ui['border']}; }}
    QPushButton#primary {{
        background-color: {ui['accent']};
        color: {ui['card']};
        font-weight: 600;
        border: none;
    }}
    QPushButton#primary:hover {{ background-color: {ui['accent_hover']}; }}
    QPushButton:checked {{
        background-color: {ui['accent']};
        color: {ui['card']};
        border-color: {ui['accent']};
        font-weight: 600;
    }}
    QRadioButton {{ color: {ui['ink']}; font-size: 15px; spacing: 8px; }}
    QLineEdit {{
        background-color: {ui['card']};
        border: 1.5px solid {ui['border']};
        border-radius: 8px;
        padding: 9px 12px;
        color: {ui['ink']};
        font-size: 14px;
    }}
    QLineEdit:focus {{ border-color: {ui['accent']}; }}
"""


def _current_style() -> str:
    try:
        from ..core import appearance as ap
        return _build_style(ap.get_ui_style(ap.get_theme()))
    except Exception:
        return _build_style({"bg": "#faf3e0", "card": "#fffef9", "accent": "#c4a574",
                             "accent_hover": "#b59668", "ink": "#4a3f35",
                             "ink_soft": "#9a8f7f", "border": "#e8dcc4"})

NAV_ITEMS = ("AI", "天气", "动作参数", "计划台", "宠物", "外观")
PLANS_INDEX = NAV_ITEMS.index("计划台")


class SettingsDialog(QDialog):
    """设置主页面：左侧分类导航 + 右侧面板。传入 TrayIcon 实例。"""

    def __init__(self, tray, parent=None):
        super().__init__(parent)
        self.tray = tray
        self.setWindowTitle("Peko 设置")
        self.resize(920, 620)
        self.setMinimumSize(840, 560)
        self.setStyleSheet(_current_style())
        self._plans_ready = False
        self._build_pages()
        self.setup_ui()

    # ---------- 工具 ----------
    def _pet(self):
        try:
            return self.tray.pet_holder[0]
        except Exception:
            return None

    def _label(self, text, obj="desc", wrap=True):
        label = QLabel(text, self)
        label.setObjectName(obj)
        label.setWordWrap(wrap)
        return label

    def _page(self):
        page = QWidget(self)
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        return page, layout

    # ---------- 构建 ----------
    def _build_pages(self):
        self._pages = {
            "ai": self._build_ai_page(),
            "weather": self._build_weather_page(),
            "params": self._build_params_page(),
            "plans": self._build_plans_page(),
            "pet": self._build_pet_page(),
            "appearance": self._build_appearance_page(),
        }

    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 20)
        root.setSpacing(16)

        title = QLabel("Peko 设置", self)
        title.setObjectName("page_title")
        root.addWidget(title)

        body = QHBoxLayout()
        body.setSpacing(16)

        self.nav = QListWidget(self)
        self.nav.setFixedWidth(180)
        self.nav.setFocusPolicy(Qt.NoFocus)
        self.nav.currentRowChanged.connect(self._on_nav_changed)
        for label in NAV_ITEMS:
            QListWidgetItem(label, self.nav)
        body.addWidget(self.nav)

        self.stack = QStackedWidget(self)
        for page in self._pages.values():
            self.stack.addWidget(page)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)

        self.nav.setCurrentRow(0)
        self._refresh_all()

    def _on_nav_changed(self, row: int):
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)
            if row == PLANS_INDEX:
                self._ensure_plans()

    def _refresh_all(self):
        self._refresh_weather()
        self._refresh_pet()
        self._refresh_appearance()

    # ---------- 面板：AI ----------
    def _build_ai_page(self):
        page, layout = self._page()
        layout.addWidget(self._label("AI 聊天", "page_title"))
        layout.addWidget(self._label("填好 URL / Key / 模型名，桌宠就能陪你聊天、安慰你。"))
        layout.addSpacing(4)
        from .api_settings_dialog import AiSettingsPanel
        self.ai_panel = AiSettingsPanel(page)
        layout.addWidget(self.ai_panel, 1)
        layout.addStretch(0)
        return page

    # ---------- 面板：天气 ----------
    def _build_weather_page(self):
        page, layout = self._page()
        layout.addWidget(self._label("天气", "page_title"))
        layout.addWidget(self._label("播报当前城市天气；也可指定常用城市。"))

        btn_weather = QPushButton("查看天气", self)
        btn_weather.setObjectName("primary")
        btn_weather.clicked.connect(self._show_weather)
        layout.addWidget(btn_weather, 0, Qt.AlignLeft)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.city_edit = QLineEdit(self)
        self.city_edit.setPlaceholderText("输入城市名，如 杭州")
        row.addWidget(self.city_edit, 1)
        btn_city = QPushButton("记住这个城市", self)
        btn_city.clicked.connect(self._remember_city)
        row.addWidget(btn_city)
        layout.addLayout(row)
        layout.addWidget(self._label(
            "IP 自动定位可能不准，手动指定后会以你填的城市为准（一次到位）。", "hint"))
        layout.addStretch(1)
        return page

    def _show_weather(self):
        from .weather_report import report_weather
        pet = self._pet()
        if pet:
            report_weather(pet)

    def _remember_city(self):
        city = self.city_edit.text().strip()
        if not city:
            QMessageBox.warning(self, "提示", "请先输入城市名。")
            return
        try:
            from ..core.weather import WeatherService
            svc = WeatherService()
            msg = svc.set_city_by_user(city)
            QMessageBox.information(self, "已记住", msg)
        except Exception as e:
            QMessageBox.warning(self, "提示", f"设置失败：{e}")

    def _refresh_weather(self):
        try:
            from ..core.weather import WeatherService
            svc = WeatherService()
            city = svc.get_city()
            if city:
                self.city_edit.setText(city)
        except Exception:
            pass

    # ---------- 面板：动作参数 ----------
    def _build_params_page(self):
        page, layout = self._page()
        layout.addWidget(self._label("动作参数", "page_title"))
        layout.addWidget(self._label("用滑动条实时调整帧率、切换间隔、移动速度与大小（可针对单个动作）。"))
        layout.addSpacing(4)
        from .action_params_dialog import ActionParamsPanel
        self.params_panel = ActionParamsPanel(parent=page, pet=self._pet())
        layout.addWidget(self.params_panel, 1)
        return page

    # ---------- 面板：计划台 ----------
    def _build_plans_page(self):
        page, layout = self._page()
        layout.addWidget(self._label("计划台", "page_title"))
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        btn_browser = QPushButton("在浏览器打开工作台")
        btn_browser.clicked.connect(self._open_plans_browser)
        toolbar.addWidget(btn_browser)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        layout.addWidget(self._label(
            "内嵌工作台：记账、待办、专注、习惯，与桌面数据实时同步。", "hint"))

        self._plans_container = QWidget(self)
        self._plans_container_layout = QVBoxLayout(self._plans_container)
        self._plans_container_layout.setContentsMargins(0, 0, 0, 0)
        loading = QLabel("点击左侧「计划台」后在此加载…")
        loading.setObjectName("hint")
        self._plans_container_layout.addWidget(loading)
        layout.addWidget(self._plans_container, 1)
        self._plans_ready = False
        return page

    def _ensure_plans(self):
        """懒加载：首次切到计划台分类时才创建 WebEngine 面板，避免打开设置页就加载网页。"""
        if self._plans_ready:
            return
        self._plans_ready = True
        try:
            from .plans_web_dialog import PlansWebPanel
            panel = PlansWebPanel(pet=self._pet(), parent=self._plans_container)
            self._replace_container(panel)
        except ImportError as e:
            print(f"[Peko] 计划台：PyQtWebEngine 导入失败（{e}）")
            self._replace_container(self._build_plans_error(
                "未安装 PyQtWebEngine，无法内嵌工作台。\n可改用「在浏览器打开工作台」，或运行 pip install PyQtWebEngine 后重试。"))
        except Exception as e:
            print(f"[Peko] 计划台加载失败：{type(e).__name__}: {e}")
            self._replace_container(self._build_plans_error(
                f"工作台加载失败：{type(e).__name__}: {e}\n可先用「在浏览器打开工作台」。"))

    def _build_plans_error(self, message: str) -> QWidget:
        box = QWidget(self._plans_container)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(12)
        label = QLabel(message, box)
        label.setObjectName("hint")
        label.setWordWrap(True)
        layout.addWidget(label)
        row = QHBoxLayout()
        btn = QPushButton("在浏览器打开工作台", box)
        btn.clicked.connect(self._open_plans_browser)
        row.addWidget(btn)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)
        return box

    def _replace_container(self, widget: QWidget):
        while self._plans_container_layout.count():
            item = self._plans_container_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._plans_container_layout.addWidget(widget)

    def _open_plans_browser(self):
        try:
            self.tray._show_plans_web_browser_dialog()
        except Exception:
            pass

    # ---------- 面板：宠物 ----------
    def _build_pet_page(self):
        page, layout = self._page()
        layout.addWidget(self._label("宠物", "page_title"))
        layout.addWidget(self._label("切换当前宠物："))

        self.pet_current = self._label("", "desc")
        layout.addWidget(self.pet_current)

        self.pet_buttons = QVBoxLayout()
        self.pet_buttons.setSpacing(8)
        layout.addLayout(self.pet_buttons)
        layout.addStretch(1)
        return page

    def _refresh_pet(self):
        try:
            from ..core.pet_manager import get_available_pets, get_pet
            pids = get_available_pets()
        except Exception:
            pids = []
        pet = self._pet()
        current_id = ""
        try:
            current_id = pet.pet_package.get("id", "")
        except Exception:
            pass
        self.pet_current.setText(f"当前宠物：{current_id or '未知'}")

        while self.pet_buttons.count():
            item = self.pet_buttons.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        for pid in pids:
            try:
                pkg = get_pet(pid)
                name = pkg.get("name", pid)
            except Exception:
                name = pid
            btn = QPushButton(name, self)
            btn.setEnabled(pid != current_id)
            btn.clicked.connect(lambda _=False, id=pid: self._switch_pet(id))
            self.pet_buttons.addWidget(btn)

    def _switch_pet(self, pet_id: str):
        if self.tray.on_switch_pet:
            try:
                self.tray.on_switch_pet(pet_id)
            except Exception:
                pass
        self._refresh_pet()

    # ---------- 面板：外观 ----------
    def _build_appearance_page(self):
        page, layout = self._page()
        layout.addWidget(self._label("外观", "page_title"))
        layout.addWidget(self._label("切换全局主题：气泡、设置页、对话框、托盘菜单一起换色。"))

        layout.addSpacing(6)
        layout.addWidget(self._label("主题：", "desc"))
        self.bubble_group = QButtonGroup(self)
        self.bubble_group.setExclusive(True)
        theme_row = QHBoxLayout()
        theme_row.setSpacing(8)
        try:
            from ..core import appearance as appearance_mod
            themes = appearance_mod.list_themes()
        except Exception:
            themes = [("pet", "跟随宠物")]
        for key, label in themes:
            btn = QPushButton(label, page)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, k=key: self._apply_theme(k))
            self.bubble_group.addButton(btn)
            theme_row.addWidget(btn)
        theme_row.addStretch(1)
        layout.addLayout(theme_row)
        layout.addWidget(self._label("选择后立即生效并保持；重启后继续使用该主题。", "hint"))

        layout.addStretch(1)
        return page

    def _apply_theme(self, key: str):
        """切换全局主题：持久化 + 刷新设置页自身 + 宠物气泡 + 托盘菜单。"""
        try:
            from ..core import appearance as appearance_mod
            appearance_mod.save_appearance(theme=key)
        except Exception:
            pass
        # 刷新设置页自身配色
        self.setStyleSheet(_current_style())
        # 内嵌面板（AI 表单 / 动作参数）
        for panel in (getattr(self, "ai_panel", None), getattr(self, "params_panel", None)):
            if panel is not None and hasattr(panel, "apply_theme"):
                try:
                    panel.apply_theme()
                except Exception:
                    pass
        # 宠物气泡 + 侧面操作面板
        pet = self._pet()
        if pet is not None and hasattr(pet, "refresh_theme"):
            try:
                pet.refresh_theme(key)
            except Exception:
                pass
        # 托盘菜单
        try:
            self.tray.refresh_theme()
        except Exception:
            pass

    def _refresh_appearance(self):
        try:
            from ..core import appearance as appearance_mod
            theme = appearance_mod.get_theme()
            themes = appearance_mod.list_themes()
            for i, btn in enumerate(self.bubble_group.buttons()):
                key = themes[i][0] if i < len(themes) else ""
                if key == theme:
                    btn.blockSignals(True)
                    btn.setChecked(True)
                    btn.blockSignals(False)
                    break
        except Exception:
            pass

