"""
Peko 桌宠入口：加载宠物包、统一 API 配置（config/api.json + config/secrets.json），支持切换宠物
全局快捷键监听使用 pynput 实现跨平台支持（Windows 和 macOS）。
L+Enter 唤起对话。
注意：macOS 上需要授予「辅助功能」权限才能监听全局键盘事件。
"""
import sys
import threading
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QMetaObject, Qt

from .ui.pet import DesktopPet
from .ui.tray import TrayIcon
from .core.pet_manager import get_pet, get_available_pets, get_default_pet_id, discover_pets

# 分身模式下的宠物数量（当前主宠 + 14 个分身 = 15 个）
CLONE_COUNT = 15


def global_hotkey_listener(pet_holder):
    """使用 pynput 监听 L+Enter 快捷键（跨平台）。

    使用 HotKey + Listener.canonical：各平台虚拟键不同（如 Windows 上 L 为 vk 76，
    macOS ANSI L 为 vk 37），手写 vk 判断会在 Mac 上失效。
    """
    try:
        from pynput import keyboard

        def invoke_dialog():
            QMetaObject.invokeMethod(
                pet_holder[0],
                "show_custom_input_dialog",
                Qt.QueuedConnection,
            )

        hotkey = keyboard.HotKey(
            frozenset(keyboard.HotKey.parse("l+<enter>")),
            invoke_dialog,
        )

        listener = keyboard.Listener(
            on_press=lambda k: hotkey.press(listener.canonical(k)),
            on_release=lambda k: hotkey.release(listener.canonical(k)),
        )
        listener.start()
        listener.join()  # 保持线程运行
    except ImportError:
        # pynput 未安装，回退到 keyboard 库（仅 Windows）
        if sys.platform == "win32":
            try:
                import keyboard
                while True:
                    keyboard.wait("l+enter")
                    QMetaObject.invokeMethod(
                        pet_holder[0],
                        "show_custom_input_dialog",
                        Qt.QueuedConnection,
                    )
            except Exception:
                pass
    except Exception as e:
        print(f"[Peko] 快捷键监听启动失败: {e}")
        if sys.platform == "darwin":
            print("[Peko] macOS 提示：请在「系统偏好设置 > 安全性与隐私 > 辅助功能」中授权本应用")


def main():
    discover_pets()
    avail = get_available_pets()
    if not avail:
        print("未找到任何宠物包，请将宠物配置放到 pets/<宠物id>/pet_config.json")
        sys.exit(1)

    app = QApplication(sys.argv)
    default_id = get_default_pet_id()
    pet_package = get_pet(default_id)
    frame_rate = 10
    pet = DesktopPet(pet_package, frame_rate=frame_rate)
    pet_holder = [pet]
    clone_pets = []  # 分身模式下额外 14 个窗口

    def set_clone_mode(on: bool):
        nonlocal clone_pets
        if on:
            pet_holder[0].set_control_mode(False)
            pet_holder[0].set_follow_mouse_mode(False)
            pkg = pet_holder[0].pet_package
            desktop = QApplication.desktop()
            screen = desktop.screenGeometry()
            available = desktop.availableGeometry()
            sw = screen.width()
            pw = pet_holder[0].width()
            ph = pet_holder[0].height()
            # 任务栏上方一行：宠物底边贴住任务栏顶部
            taskbar_top = available.y() + available.height()
            row_y = taskbar_top - ph
            pet_holder[0].clone_mode = True
            pet_holder[0].clone_mode_row_y = row_y
            # 15 只沿任务栏上方水平排开，均匀分布
            margin = 12
            if CLONE_COUNT <= 1:
                pet_holder[0].move(margin, row_y)
            else:
                step = (sw - 2 * margin - pw) / max(1, CLONE_COUNT - 1)
                for i in range(CLONE_COUNT):
                    x = int(margin + i * step)
                    x = max(0, min(x, sw - pw))
                    if i == 0:
                        pet_holder[0].move(x, row_y)
                    else:
                        new_pet = DesktopPet(pkg, frame_rate=frame_rate)
                        new_pet.clone_mode = True
                        new_pet.clone_mode_row_y = row_y
                        new_pet.move(x, row_y)
                        new_pet.set_control_mode(False)
                        new_pet.set_follow_mouse_mode(False)
                        new_pet.show()
                        clone_pets.append(new_pet)
        else:
            for p in clone_pets:
                try:
                    p._cleanup_for_destroy()
                    p.close()
                    p.deleteLater()
                except Exception:
                    pass
            clone_pets.clear()
            pet_holder[0].clone_mode = False
            if hasattr(pet_holder[0], "clone_mode_row_y"):
                del pet_holder[0].clone_mode_row_y

    tray = TrayIcon(app, pet_holder, on_switch_pet=None, clone_pets=clone_pets, set_clone_mode=set_clone_mode)

    def switch_pet(pet_id: str):
        nonlocal clone_pets
        if clone_pets:
            set_clone_mode(False)
        old = pet_holder[0]
        pkg = get_pet(pet_id)
        new_pet = DesktopPet(pkg, frame_rate=frame_rate)
        was_visible = old.isVisible()
        old.close()
        pet_holder[0] = new_pet
        tray.update_icon()
        if was_visible:
            new_pet.show()
        # 欢迎语
        name = pkg.get("name", pet_id)
        welcome_msg = f"Hi！我是 {name}。用 L+Enter 和我对话吧～"
        if sys.platform == "darwin":
            welcome_msg = f"Hi！我是 {name}。用 L+Enter 和我对话吧～（需辅助功能权限）"
        new_pet.show_bubble(
            welcome_msg,
            duration=10000,
            typing_speed=100,
        )

    tray.on_switch_pet = switch_pet
    pet.show()
    welcome = pet_package.get("description") or f"我是 {pet_package.get('name', default_id)}，用 L+Enter 和我对话吧！"
    # macOS 上 pynput 需要辅助功能权限，添加提示
    if sys.platform == "darwin":
        welcome = pet_package.get("description") or f"我是 {pet_package.get('name', default_id)}，用 L+Enter 和我对话吧！（需在系统设置中授予辅助功能权限）"
    pet.show_bubble(
        welcome,
        duration=10000,
        typing_speed=100,
    )

    hotkey_thread = threading.Thread(
        target=global_hotkey_listener, args=(pet_holder,), daemon=True
    )
    hotkey_thread.start()

    sys.exit(app.exec_())
