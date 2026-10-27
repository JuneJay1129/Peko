"""
Peko 桌宠入口：加载宠物包、统一 API 配置（config/api.json + config/secrets.json），支持切换宠物
全局快捷键监听使用 pynput 实现跨平台支持（Windows 和 macOS）。
L+Enter 唤起对话。
注意：macOS 上需要授予「辅助功能」权限才能监听全局键盘事件。
"""
import sys
import threading
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon
from PyQt5.QtCore import QMetaObject, Qt, QTimer

from .ui.pet import DesktopPet
from .ui.tray import TrayIcon
from .core.pet_manager import get_pet, get_available_pets, get_default_pet_id, discover_pets
from .core.pet_registry import PetRegistry

# 分身模式下的宠物数量（当前主宠 + 14 个分身 = 15 个）
CLONE_COUNT = 15


def _schedule_pet_warning(registry, message: str, duration: int = 9000) -> None:
    pet = registry.current() if registry else None
    if pet is None:
        return

    def _show_warning():
        try:
            pet.update_bubble(message, duration=duration)
        except Exception:
            pass

    QTimer.singleShot(0, _show_warning)



def _tray_is_available() -> bool:
    try:
        return bool(QSystemTrayIcon.isSystemTrayAvailable())
    except Exception:
        return False



def _create_tray_icon(app, registry, on_switch_pet=None, clone_pets=None, set_clone_mode=None):
    if not _tray_is_available():
        return None
    return TrayIcon(app, registry, on_switch_pet=on_switch_pet, clone_pets=clone_pets, set_clone_mode=set_clone_mode)



def global_hotkey_listener(registry):
    """使用 pynput 监听 L+Enter 快捷键（跨平台）。

    使用 HotKey + Listener.canonical：各平台虚拟键不同（如 Windows 上 L 为 vk 76，
    macOS ANSI L 为 vk 37），手写 vk 判断会在 Mac 上失效。
    """
    try:
        from pynput import keyboard

        def invoke_dialog():
            pet = registry.current()
            if pet is None:
                return
            QMetaObject.invokeMethod(
                pet,
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
                    pet = registry.current()
                    if pet is None:
                        continue
                    QMetaObject.invokeMethod(
                        pet,
                        "show_custom_input_dialog",
                        Qt.QueuedConnection,
                    )
            except Exception:
                pass
        elif sys.platform == "darwin":
            _schedule_pet_warning(
                registry,
                "快捷键监听组件未安装，先用托盘里的“与宠物对话”吧。",
            )
    except Exception as e:
        print(f"[Peko] 快捷键监听启动失败: {e}")
        if sys.platform == "darwin":
            print("[Peko] macOS 提示：请在「系统偏好设置 > 安全性与隐私 > 辅助功能」中授权本应用")
            _schedule_pet_warning(
                registry,
                "L+Enter 需要辅助功能权限；你也可以先用托盘里的“与宠物对话”。",
            )


def main():
    discover_pets()
    avail = get_available_pets()
    if not avail:
        print("未找到任何宠物包，请将宠物配置放到 pets/<宠物id>/pet_config.json")
        sys.exit(1)

    app = QApplication(sys.argv)
    # 允许随后懒导入 PyQt5.QtWebEngineWidgets（Web 工作台宿主窗用到），
    # 否则会报 "QtWebEngineWidgets must be imported ... before a QCoreApplication instance is created"
    app.setAttribute(Qt.AA_ShareOpenGLContexts)
    app.setQuitOnLastWindowClosed(False)
    default_id = get_default_pet_id()
    pet_package = get_pet(default_id)
    frame_rate = 10
    pet = DesktopPet(pet_package, frame_rate=frame_rate)
    registry = PetRegistry()
    registry.set_master(pet)
    clone_pets = []  # 分身模式下额外 14 个窗口
    registry.set_clones(clone_pets)  # 引用同一列表：原地增删自动同步

    def set_clone_mode(on: bool):
        nonlocal clone_pets
        if on:
            pet = registry.current()
            pet.set_control_mode(False)
            pet.set_follow_mouse_mode(False)
            pkg = pet.pet_package
            desktop = QApplication.desktop()
            screen = desktop.screenGeometry()
            available = desktop.availableGeometry()
            sw = screen.width()
            pw = pet.width()
            ph = pet.height()
            # 任务栏上方一行：宠物底边贴住任务栏顶部
            taskbar_top = available.y() + available.height()
            row_y = taskbar_top - ph
            pet.clone_mode = True
            pet.clone_mode_row_y = row_y
            # 15 只沿任务栏上方水平排开，均匀分布
            margin = 12
            if CLONE_COUNT <= 1:
                pet.move(margin, row_y)
            else:
                step = (sw - 2 * margin - pw) / max(1, CLONE_COUNT - 1)
                for i in range(CLONE_COUNT):
                    x = int(margin + i * step)
                    x = max(0, min(x, sw - pw))
                    if i == 0:
                        pet.move(x, row_y)
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
            pet = registry.current()
            pet.clone_mode = False
            if hasattr(pet, "clone_mode_row_y"):
                del pet.clone_mode_row_y

    tray = _create_tray_icon(app, registry, on_switch_pet=None, clone_pets=clone_pets, set_clone_mode=set_clone_mode)
    if tray is None:
        _schedule_pet_warning(
            registry,
            "当前系统托盘不可用；桌宠会继续运行，但请不要关闭主窗口。",
            duration=12000,
        )

    def switch_pet(pet_id: str):
        nonlocal clone_pets
        if clone_pets:
            set_clone_mode(False)
        old = registry.current()
        pkg = get_pet(pet_id)
        new_pet = DesktopPet(pkg, frame_rate=frame_rate)
        was_visible = old.isVisible()
        old.close()
        registry.set_master(new_pet)
        if tray is not None:
            tray.update_icon()
        if was_visible:
            new_pet.show()
        # 恢复特效
        _load_effect(new_pet)
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

    # 加载保存的特效（已收敛到 core.effect_state，托盘与启动共用唯一入口）
    def _load_effect(pet_widget):
        try:
            from .core import effect_state
            effect_name = effect_state.get_current()
            if effect_name and effect_name != "none":
                pet_widget.set_effect(effect_name)
        except Exception as e:
            print(f"[Main] 加载特效配置失败: {e}")

    _load_effect(pet)
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
        target=global_hotkey_listener, args=(registry,), daemon=True
    )
    hotkey_thread.start()

    sys.exit(app.exec_())
