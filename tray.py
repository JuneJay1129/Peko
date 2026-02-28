"""
系统托盘：显示/隐藏桌宠、停止移动、切换宠物、退出
"""
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction
from PyQt5.QtGui import QIcon


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
        self.tray_icon = QSystemTrayIcon(QIcon("resources/icon.png"), self.app)
        self.create_tray_menu()

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

        if self.on_switch_pet:
            switch_menu = menu.addMenu("切换宠物")
            try:
                from pet_manager import get_available_pets, get_pet
                for pid in get_available_pets():
                    pkg = get_pet(pid)
                    name = pkg.get("name", pid)
                    act = QAction(name, self.app)
                    act.triggered.connect(lambda checked, id=pid: self.on_switch_pet(id))
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
