"""
系统托盘：显示/隐藏桌宠、停止移动、切换宠物、退出
托盘图标使用当前宠物的 resource/icon.png，每个宠物独立 resource，无公共模块。
"""
import os
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction
from PyQt5.QtGui import QIcon

from ..core.pet_manager import RESOURCE_DIR


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
    def __init__(self, app, pet_holder, on_switch_pet=None):
        """
        :param app: QApplication 实例
        :param pet_holder: 列表 [DesktopPet]，当前宠物为 pet_holder[0]，切换宠物时由 main 替换
        :param on_switch_pet: 可选，回调 (pet_id: str) -> None，用于切换宠物
        """
        self.app = app
        self.pet_holder = pet_holder
        self.on_switch_pet = on_switch_pet
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
        pet = self.pet_holder[0] if self.pet_holder else None

        show_action = QAction("显示桌宠", self.app)
        hide_action = QAction("隐藏桌宠", self.app)
        stop_movement_action = QAction("停止移动", self.app, checkable=True)
        show_action.triggered.connect(lambda: self.pet_holder[0].show() if self.pet_holder else None)
        hide_action.triggered.connect(lambda: self.pet_holder[0].hide() if self.pet_holder else None)
        stop_movement_action.triggered.connect(self.toggle_movement)

        menu.addAction(show_action)
        menu.addAction(hide_action)
        menu.addAction(stop_movement_action)
        menu.addSeparator()

        switch_menu = menu.addMenu("切换宠物")
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
        self.tray_icon.show()

    def exit_app(self):
        if self.pet_holder:
            self.pet_holder[0].close()
        self.tray_icon.hide()
        self.app.quit()

    def toggle_movement(self, checked):
        if self.pet_holder:
            self.pet_holder[0].set_allow_movement(not checked)
