"""
Peko 桌宠入口：加载宠物包、统一 API 配置（config/api.json），支持切换宠物
"""
import sys
import threading
import keyboard
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QMetaObject, Qt

from pet import DesktopPet
from tray import TrayIcon
from pet_manager import get_pet, get_available_pets, get_default_pet_id, discover_pets


def global_hotkey_listener(pet_holder):
    """全局快捷键 L+Enter 唤起对话。"""
    while True:
        keyboard.wait("l+enter")
        QMetaObject.invokeMethod(
            pet_holder[0],
            "show_custom_input_dialog",
            Qt.QueuedConnection,
        )


def main():
    discover_pets()
    avail = get_available_pets()
    if not avail:
        print("未找到任何宠物包，请将宠物配置放到 pets/<宠物id>/pet_config.json")
        sys.exit(1)

    app = QApplication(sys.argv)
    default_id = get_default_pet_id()
    pet_package = get_pet(default_id)
    pet = DesktopPet(pet_package, scale_factor=5, frame_rate=2)
    pet_holder = [pet]

    def switch_pet(pet_id: str):
        old = pet_holder[0]
        pkg = get_pet(pet_id)
        new_pet = DesktopPet(pkg, scale_factor=5, frame_rate=2)
        was_visible = old.isVisible()
        old.close()
        pet_holder[0] = new_pet
        if was_visible:
            new_pet.show()
        # 欢迎语
        name = pkg.get("name", pet_id)
        new_pet.show_bubble(
            f"Hi！我是 {name}。用 L+Enter 和我对话吧～\n请在 config/api.json 中填写 apiKey 并设置 modelId。",
            duration=10000,
            typing_speed=100,
        )

    tray = TrayIcon(app, pet_holder, on_switch_pet=switch_pet)
    pet.show()
    welcome = pet_package.get("description") or f"我是 {pet_package.get('name', default_id)}，用 L+Enter 和我对话吧！"
    pet.show_bubble(
        welcome ,
        duration=10000,
        typing_speed=100,
    )

    hotkey_thread = threading.Thread(
        target=global_hotkey_listener, args=(pet_holder,), daemon=True
    )
    hotkey_thread.start()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
