"""
系统托盘：显示/隐藏桌宠、停止移动、切换宠物、退出
托盘图标使用当前宠物的 resource/icon.png，每个宠物独立 resource，无公共模块。
右键菜单使用统一暖色样式。
"""
import os
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction
from PyQt5.QtGui import QIcon

from ..core.pet_manager import RESOURCE_DIR

# 托盘右键菜单样式：暖色圆角，与桌宠面板风格一致
TRAY_MENU_STYLE = """
    QMenu {
        background-color: #faf3e0;
        border: 1px solid #e8dcc4;
        border-radius: 10px;
        padding: 6px 0;
        min-width: 160px;
    }
    QMenu::item {
        padding: 8px 24px 8px 16px;
        font-size: 13px;
        color: #4a3f35;
    }
    QMenu::item:selected {
        background-color: #e8dcc4;
        color: #3d3329;
    }
    QMenu::item:disabled {
        color: #a09888;
    }
    QMenu::separator {
        height: 1px;
        background-color: #e8dcc4;
        margin: 4px 12px;
    }
    QMenu::indicator {
        width: 14px;
        height: 14px;
        border-radius: 3px;
        border: 1px solid #c4a574;
        background-color: #fffef8;
        margin-left: 8px;
    }
    QMenu::indicator:checked {
        background-color: #c4a574;
    }
"""


def _icon_path_for_pet(pet_holder) -> str:
    """从当前宠物的 resource/icon.png 获取托盘图标路径；若无则尝试 stand 首帧。"""
    if not pet_holder:
        return ""
    pkg = pet_holder[0].pet_package
    pet_dir = pkg.get("_pet_dir", "")
    if pet_dir:
        icon_path = os.path.join(pet_dir, RESOURCE_DIR, "icon.png")
        if os.path.isfile(icon_path):
            return icon_path
        # 回退：使用 stand 首帧（animations.stand 为 { "frames": [...] }）
        stand = (pkg.get("animations") or {}).get("stand") or {}
        frames = stand.get("frames") or []
        if frames and os.path.isfile(frames[0]):
            return frames[0]
    return ""


class TrayIcon:
    def __init__(self, app, pet_holder, on_switch_pet=None, clone_pets=None, set_clone_mode=None):
        """
        :param app: QApplication 实例
        :param pet_holder: 列表 [DesktopPet]，当前宠物为 pet_holder[0]，切换宠物时由 main 替换
        :param on_switch_pet: 可选，回调 (pet_id: str) -> None，用于切换宠物
        :param clone_pets: 可选，分身模式下的额外宠物列表（由 main 填充），用于显示/隐藏/退出
        :param set_clone_mode: 可选，回调 (on: bool) -> None，进入/退出分身模式
        """
        self.app = app
        self.pet_holder = pet_holder
        self.on_switch_pet = on_switch_pet
        self.clone_pets = clone_pets if clone_pets is not None else []
        self.set_clone_mode = set_clone_mode
        icon_path = _icon_path_for_pet(pet_holder)
        self.tray_icon = QSystemTrayIcon(QIcon(icon_path) if icon_path else QIcon(), self.app)
        self.create_tray_menu()

    def update_icon(self):
        """切换宠物后更新托盘图标为当前宠物的 resource/icon.png"""
        icon_path = _icon_path_for_pet(self.pet_holder)
        if icon_path:
            self.tray_icon.setIcon(QIcon(icon_path))

    def create_tray_menu(self):
        menu = QMenu()
        menu.setStyleSheet(TRAY_MENU_STYLE)
        menu.setMinimumWidth(180)
        pet = self.pet_holder[0] if self.pet_holder else None

        show_action = QAction("显示桌宠", self.app)
        hide_action = QAction("隐藏桌宠", self.app)
        stop_movement_action = QAction("停止移动", self.app, checkable=True)
        talk_action = QAction("与宠物对话", self.app)
        api_settings_action = QAction("AI 设置", self.app)
        params_action = QAction("动作参数", self.app)
        self._auto_mode_action = QAction("自动模式", self.app, checkable=True)
        self._control_mode_action = QAction("操控模式", self.app, checkable=True)
        self._follow_mouse_action = QAction("跟随鼠标", self.app, checkable=True)
        self._clone_mode_action = QAction("分身模式", self.app, checkable=True)
        show_action.triggered.connect(self._on_show_pets)
        hide_action.triggered.connect(self._on_hide_pets)
        stop_movement_action.triggered.connect(self.toggle_movement)
        talk_action.triggered.connect(lambda: self.pet_holder[0].show_custom_input_dialog() if self.pet_holder else None)
        api_settings_action.triggered.connect(self._show_api_settings_dialog)
        params_action.triggered.connect(self._show_action_params_dialog)
        self._auto_mode_action.triggered.connect(self._on_auto_mode)
        self._control_mode_action.triggered.connect(self._on_control_mode)
        self._follow_mouse_action.triggered.connect(self._on_follow_mouse_mode)
        self._clone_mode_action.triggered.connect(self._on_clone_mode)

        # 默认自动模式
        self._auto_mode_action.setChecked(True)
        self._control_mode_action.setChecked(False)
        self._follow_mouse_action.setChecked(False)
        self._clone_mode_action.setChecked(False)

        menu.addAction(show_action)
        menu.addAction(hide_action)
        menu.addAction(stop_movement_action)
        menu.addAction(talk_action)
        menu.addAction(api_settings_action)
        menu.addAction(params_action)
        menu.addSeparator()
        menu.addAction(self._auto_mode_action)
        menu.addAction(self._control_mode_action)
        menu.addAction(self._follow_mouse_action)
        menu.addAction(self._clone_mode_action)
        menu.addSeparator()

        switch_menu = menu.addMenu("切换宠物")
        switch_menu.setStyleSheet(TRAY_MENU_STYLE)
        switch_menu.setMinimumWidth(180)
        try:
            from ..core.pet_manager import get_available_pets, get_pet
            for pid in get_available_pets():
                pkg = get_pet(pid)
                name = pkg.get("name", pid)
                act = QAction(name, self.app)
                act.triggered.connect(lambda checked, id=pid: self.on_switch_pet(id) if self.on_switch_pet else None)
                switch_menu.addAction(act)
        except Exception:
            pass

        menu.addSeparator()

        exit_action = QAction("退出", self.app)
        exit_action.triggered.connect(self.exit_app)
        menu.addAction(exit_action)

        self.tray_icon.setContextMenu(menu)
        self._tray_menu = menu
        menu.aboutToShow.connect(self._update_mode_actions_checked)
        self.tray_icon.show()

    def _all_pets(self):
        """当前所有宠物窗口（主宠 + 分身），用于显示/隐藏/退出等。"""
        return list(self.pet_holder) + list(getattr(self, "clone_pets", []))

    def _on_show_pets(self):
        for p in self._all_pets():
            p.show()

    def _on_hide_pets(self):
        for p in self._all_pets():
            p.hide()

    def exit_app(self):
        pets = self._all_pets()
        if not pets:
            self.tray_icon.hide()
            self.app.quit()
            return
        for p in pets:
            try:
                p.play_exit_animation(duration_ms=2000)
            except Exception:
                try:
                    p.close()
                except Exception:
                    pass
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(2500, self._do_quit_after_exit)

    def _do_quit_after_exit(self):
        for p in self._all_pets():
            try:
                p.close()
            except Exception:
                pass
        self.tray_icon.hide()
        self.app.quit()

    def toggle_movement(self, checked):
        for p in self._all_pets():
            p.set_allow_movement(not checked)

    def _show_action_params_dialog(self):
        """打开动作参数面板，居中显示，可拖动。"""
        if not self.pet_holder:
            return
        from .action_params_dialog import ActionParamsDialog
        from PyQt5.QtWidgets import QApplication
        pet = self.pet_holder[0]
        dialog = ActionParamsDialog(pet, pet)
        screen = QApplication.desktop().availableGeometry()
        x = (screen.width() - dialog.width()) // 2 + screen.x()
        y = (screen.height() - dialog.height()) // 2 + screen.y()
        dialog.move(x, y)
        dialog.exec_()

    def _show_api_settings_dialog(self):
        """打开 AI 设置对话框，保存后立即生效。"""
        if not self.pet_holder:
            return
        from .api_settings_dialog import ApiSettingsDialog
        from PyQt5.QtWidgets import QApplication
        pet = self.pet_holder[0]
        dialog = ApiSettingsDialog(pet)
        screen = QApplication.desktop().availableGeometry()
        x = (screen.width() - dialog.width()) // 2 + screen.x()
        y = (screen.height() - dialog.height()) // 2 + screen.y()
        dialog.move(x, y)
        dialog.exec_()

    def _on_auto_mode(self):
        if self.pet_holder:
            if getattr(self, "set_clone_mode", None) and len(getattr(self, "clone_pets", [])) > 0:
                self.set_clone_mode(False)
            self.pet_holder[0].set_control_mode(False)
            self.pet_holder[0].set_follow_mouse_mode(False)
            self._auto_mode_action.setChecked(True)
            self._control_mode_action.setChecked(False)
            self._follow_mouse_action.setChecked(False)
            self._clone_mode_action.setChecked(False)

    def _on_control_mode(self):
        if self.pet_holder:
            if getattr(self, "set_clone_mode", None) and len(getattr(self, "clone_pets", [])) > 0:
                self.set_clone_mode(False)
            self.pet_holder[0].set_control_mode(True)
            self._auto_mode_action.setChecked(False)
            self._control_mode_action.setChecked(True)
            self._follow_mouse_action.setChecked(False)
            self._clone_mode_action.setChecked(False)

    def _on_follow_mouse_mode(self):
        if self.pet_holder:
            if getattr(self, "set_clone_mode", None) and len(getattr(self, "clone_pets", [])) > 0:
                self.set_clone_mode(False)
            self.pet_holder[0].set_follow_mouse_mode(True)
            self._auto_mode_action.setChecked(False)
            self._control_mode_action.setChecked(False)
            self._follow_mouse_action.setChecked(True)
            self._clone_mode_action.setChecked(False)

    def _on_clone_mode(self):
        if not self.pet_holder or not self.set_clone_mode:
            return
        in_clone = len(getattr(self, "clone_pets", [])) > 0
        self.set_clone_mode(not in_clone)
        if not in_clone:
            self._auto_mode_action.setChecked(False)
            self._control_mode_action.setChecked(False)
            self._follow_mouse_action.setChecked(False)
            self._clone_mode_action.setChecked(True)
        else:
            self._auto_mode_action.setChecked(True)
            self._control_mode_action.setChecked(False)
            self._follow_mouse_action.setChecked(False)
            self._clone_mode_action.setChecked(False)

    def _update_mode_actions_checked(self):
        """打开托盘菜单时，根据当前模式同步勾选状态。"""
        if self.pet_holder and hasattr(self, "_auto_mode_action"):
            pet = self.pet_holder[0]
            cm = getattr(pet, "control_mode", False)
            fm = getattr(pet, "follow_mouse_mode", False)
            in_clone = len(getattr(self, "clone_pets", [])) > 0
            self._auto_mode_action.setChecked(not cm and not fm and not in_clone)
            self._control_mode_action.setChecked(cm)
            self._follow_mouse_action.setChecked(fm)
            self._clone_mode_action.setChecked(in_clone)
