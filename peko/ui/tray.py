"""
系统托盘：显示/隐藏桌宠、停止移动、切换宠物、退出
托盘图标优先与可执行文件相同（项目根 / 打包后的 icon.ico 等，与 main.spec 一致），否则使用当前宠物的 resource/icon.png 或 stand 首帧。
右键菜单使用统一暖色样式。
macOS：菜单栏托盘上左右键常会统一为 Trigger，需监听 activated 再弹出菜单（否则右键无反应）。
"""
import os
import sys
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction
from PyQt5.QtGui import QIcon, QCursor

from ..core.pet_manager import RESOURCE_DIR, get_app_exe_icon_path

def _menu_style() -> str:
    """托盘菜单样式：按当前外观主题的 UI 色板生成（暖色圆角）。"""
    try:
        from ..core import appearance as appearance_mod
        ui = appearance_mod.get_ui_style(appearance_mod.get_theme())
    except Exception:
        ui = {"bg": "#faf3e0", "card": "#fffef8", "accent": "#c4a574", "accent_hover": "#b59668",
              "ink": "#4a3f35", "ink_soft": "#a09888", "border": "#e8dcc4"}
    return f"""
    QMenu {{
        background-color: {ui['bg']};
        border: 1px solid {ui['border']};
        border-radius: 10px;
        padding: 6px 0;
        min-width: 160px;
    }}
    QMenu::item {{
        padding: 8px 24px 8px 16px;
        font-size: 13px;
        color: {ui['ink']};
    }}
    QMenu::item:selected {{
        background-color: {ui['border']};
        color: {ui['ink']};
    }}
    QMenu::item:disabled {{
        color: {ui['ink_soft']};
    }}
    QMenu::separator {{
        height: 1px;
        background-color: {ui['border']};
        margin: 4px 12px;
    }}
    QMenu::indicator {{
        width: 14px;
        height: 14px;
        border-radius: 3px;
        border: 1px solid {ui['accent']};
        background-color: {ui['card']};
        margin-left: 8px;
    }}
    QMenu::indicator:checked {{
        background-color: {ui['accent']};
    }}
"""


def _tray_icon_path(pet_holder) -> str:
    """托盘图标：优先 exe 同款图标；否则当前宠物 resource/icon.png，再否则 stand 首帧。"""
    app_icon = get_app_exe_icon_path()
    if app_icon:
        return app_icon
    pet_icon = ""
    if pet_holder:
        pkg = pet_holder[0].pet_package
        pet_dir = pkg.get("_pet_dir", "")
        if pet_dir:
            icon_path = os.path.join(pet_dir, RESOURCE_DIR, "icon.png")
            if os.path.isfile(icon_path):
                pet_icon = icon_path
            else:
                # 回退：使用 stand 首帧（animations.stand 为 { "frames": [...] }）
                stand = (pkg.get("animations") or {}).get("stand") or {}
                frames = stand.get("frames") or []
                if frames and os.path.isfile(frames[0]):
                    pet_icon = frames[0]
    return pet_icon


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
        self._follower = None  # 召唤跟班（FollowerPet）
        icon_path = _tray_icon_path(pet_holder)
        self.tray_icon = QSystemTrayIcon(QIcon(icon_path) if icon_path else QIcon(), self.app)
        self.create_tray_menu()

    def update_icon(self):
        """切换宠物后更新托盘图标（优先 exe 同款图标）。"""
        icon_path = _tray_icon_path(self.pet_holder)
        if icon_path:
            self.tray_icon.setIcon(QIcon(icon_path))

    def refresh_theme(self) -> None:
        """外观主题切换后刷新托盘 / Dock 菜单及其「模式」子菜单配色。"""
        try:
            for attr in ("_tray_menu", "_mode_menu", "_follower_menu", "_effect_menu",
                         "_dock_menu", "_dock_mode_menu", "_dock_effect_menu"):
                m = getattr(self, attr, None)
                if m is not None:
                    m.setStyleSheet(_menu_style())
        except Exception:
            pass

    def create_tray_menu(self):
        """托盘菜单：高频操作 + 常用功能（安慰/摧毁/模式）+ 设置入口。"""
        menu = QMenu()
        menu.setStyleSheet(_menu_style())
        menu.setMinimumWidth(180)

        self._show_action = QAction("显示桌宠", self.app)
        self._hide_action = QAction("隐藏桌宠", self.app)
        self._talk_action = QAction("与宠物对话", self.app)
        self._comfort_action = QAction("安慰我", self.app)
        self._weather_action = QAction("查看天气", self.app)
        self._destroy_file_action = QAction("摧毁文件…", self.app)
        self._settings_action = QAction("设置…", self.app)
        self._exit_action = QAction("退出", self.app)

        self._show_action.triggered.connect(self._on_show_pets)
        self._hide_action.triggered.connect(self._on_hide_pets)
        self._talk_action.triggered.connect(lambda: self.pet_holder[0].show_custom_input_dialog() if self.pet_holder else None)
        self._comfort_action.triggered.connect(self._on_comfort)
        self._weather_action.triggered.connect(self._on_weather)
        self._destroy_file_action.triggered.connect(self._on_destroy_file)
        self._settings_action.triggered.connect(self.open_settings)
        self._exit_action.triggered.connect(self.exit_app)

        menu.addAction(self._show_action)
        menu.addAction(self._hide_action)
        menu.addAction(self._talk_action)
        menu.addSeparator()
        menu.addAction(self._comfort_action)
        menu.addAction(self._weather_action)
        menu.addAction(self._destroy_file_action)

        # 模式子菜单（自动/操控/跟随/分身 + 停止移动）
        self._stop_movement_action = QAction("停止移动", self.app, checkable=True)
        self._stop_movement_action.triggered.connect(self.toggle_movement)
        self._auto_mode_action = QAction("自动模式", self.app, checkable=True)
        self._control_mode_action = QAction("操控模式", self.app, checkable=True)
        self._follow_mouse_action = QAction("跟随鼠标", self.app, checkable=True)
        self._clone_mode_action = QAction("分身模式", self.app, checkable=True)
        self._auto_mode_action.triggered.connect(self._on_auto_mode)
        self._control_mode_action.triggered.connect(self._on_control_mode)
        self._follow_mouse_action.triggered.connect(self._on_follow_mouse_mode)
        self._clone_mode_action.triggered.connect(self._on_clone_mode)
        self._auto_mode_action.setChecked(True)

        mode_menu = menu.addMenu("模式")
        mode_menu.setStyleSheet(_menu_style())
        self._mode_menu = mode_menu
        for act in (self._auto_mode_action, self._control_mode_action,
                    self._follow_mouse_action, self._clone_mode_action):
            mode_menu.addAction(act)
        mode_menu.addSeparator()
        mode_menu.addAction(self._stop_movement_action)

        # 召唤跟班（大/中/小；已有跟班时显示「取消跟班」）
        self._follower_menu = menu.addMenu("召唤跟班")
        self._follower_menu.setStyleSheet(_menu_style())
        self._update_follower_menu()

        # 特效装饰子菜单
        self._effect_menu = menu.addMenu("特效装饰")
        self._effect_menu.setStyleSheet(_menu_style())
        self._fill_effect_menu(self._effect_menu)

        menu.addSeparator()
        menu.addAction(self._settings_action)
        menu.addSeparator()
        menu.addAction(self._exit_action)

        self.tray_icon.setContextMenu(menu)
        self._tray_menu = menu
        menu.aboutToShow.connect(self._on_tray_menu_about_to_show)
        if sys.platform == "darwin":
            menu.aboutToHide.connect(self._on_tray_menu_about_to_hide_macos)
            self.tray_icon.activated.connect(self._on_tray_activated_macos)
            self._install_macos_dock_menu()
        self.tray_icon.show()

    def open_settings(self) -> None:
        """打开「设置」页（托盘 / Dock 入口）。"""
        from .settings_dialog import SettingsDialog
        dialog = SettingsDialog(self)
        dialog.exec_()

    def _on_tray_menu_about_to_show(self) -> None:
        self.refresh_theme()
        self._update_follower_menu()
        self._update_mode_actions_checked()

    def _install_macos_dock_menu(self) -> None:
        """Dock 图标菜单：与托盘一致的精简项。Qt 文档：setAsDockMenu 仅 macOS。"""
        dock = QMenu()
        if not hasattr(dock, "setAsDockMenu"):
            return
        self._dock_menu = dock
        dock.setStyleSheet(_menu_style())
        dock.addAction(self._show_action)
        dock.addAction(self._hide_action)
        dock.addAction(self._talk_action)
        dock.addSeparator()
        dock.addAction(self._comfort_action)
        dock.addAction(self._weather_action)
        dock.addAction(self._destroy_file_action)
        mode_menu = dock.addMenu("模式")
        mode_menu.setStyleSheet(_menu_style())
        self._dock_mode_menu = mode_menu
        for act in (self._auto_mode_action, self._control_mode_action,
                    self._follow_mouse_action, self._clone_mode_action):
            mode_menu.addAction(act)
        mode_menu.addSeparator()
        mode_menu.addAction(self._stop_movement_action)
        self._dock_follower_menu = dock.addMenu("召唤跟班")
        self._dock_follower_menu.setStyleSheet(_menu_style())
        self._fill_follower_menu(self._dock_follower_menu)
        # 特效装饰子菜单（与托盘一致；切换特效后 _on_set_effect 会同步刷新勾选）
        self._dock_effect_menu = dock.addMenu("特效装饰")
        self._dock_effect_menu.setStyleSheet(_menu_style())
        self._fill_effect_menu(self._dock_effect_menu)
        dock.addSeparator()
        dock.addAction(self._settings_action)
        dock.addSeparator()
        dock.addAction(self._exit_action)
        dock.setAsDockMenu()

    def _on_tray_activated_macos(self, reason):
        """macOS 上 Qt 往往不把右键映射为 Context，需在 Trigger 等场景手动弹出菜单。
        分身模式下多窗口置顶会抢焦点，弹出菜单前先把宠物窗口临时降下，确保菜单可见可点。"""
        import sys
        if reason == QSystemTrayIcon.DoubleClick:
            return
        if reason in (
            QSystemTrayIcon.Trigger,
            QSystemTrayIcon.Context,
            QSystemTrayIcon.MiddleClick,
        ):
            # 分身模式下：临时降低所有宠物窗口层级，避免抢托盘菜单焦点
            clone_pets = getattr(self, "clone_pets", []) or []
            if len(clone_pets) > 0 and self.pet_holder:
                all_pets = list(self.pet_holder) + list(clone_pets)
                for p in all_pets:
                    try:
                        p.lower()
                    except Exception:
                        pass
            self._tray_menu.popup(QCursor.pos())

    def _on_tray_menu_about_to_hide_macos(self):
        """macOS 托盘菜单关闭后：恢复宠物窗口置顶层级（分身模式下临时降下的）。"""
        clone_pets = getattr(self, "clone_pets", []) or []
        if len(clone_pets) > 0 and self.pet_holder:
            all_pets = list(self.pet_holder) + list(clone_pets)
            for p in all_pets:
                try:
                    p.raise_()
                except Exception:
                    pass

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
        self._dismiss_follower()
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

    def _show_plans_web_dialog(self):
        """打开 Web 工作台（内嵌 QWebEngine，实时桥接 plans.json）。"""
        if not self.pet_holder:
            return
        from .plans_web_dialog import open_plans_web
        pet = self.pet_holder[0]
        open_plans_web(pet, pet)

    def _show_plans_web_browser_dialog(self):
        """在系统浏览器中打开 Web 工作台（纯网页版，localStorage 模式）。"""
        if not self.pet_holder:
            return
        from .plans_web_dialog import open_plans_web_browser
        pet = self.pet_holder[0]
        open_plans_web_browser(pet)

    def _on_weather(self):
        """托盘「天气」：气泡播报当前天气（缓存命中则秒回，否则后台取数）。"""
        if not self.pet_holder:
            return
        from .weather_report import report_weather
        report_weather(self.pet_holder[0])

    def _fill_follower_menu(self, menu) -> None:
        """填充「召唤跟班」子菜单：有可见跟班 → 取消；否则大/中/小。"""
        menu.clear()
        follower = getattr(self, "_follower", None)
        if follower is not None and follower.isVisible():
            act = QAction("取消跟班", self.app)
            act.triggered.connect(self._dismiss_follower)
            menu.addAction(act)
        else:
            if follower is not None:
                self._follower = None  # 跟班已自动退出
            from .follower import SCALE_OPTIONS
            for label, scale in SCALE_OPTIONS:
                act = QAction(label, self.app)
                act.triggered.connect(lambda _=False, s=scale: self._on_summon_follower(s))
                menu.addAction(act)

    def _update_follower_menu(self) -> None:
        for m in (getattr(self, "_follower_menu", None), getattr(self, "_dock_follower_menu", None)):
            if m is not None:
                self._fill_follower_menu(m)

    def _on_summon_follower(self, scale: float) -> None:
        """召唤一只跟班桌宠（完全跟随主宠动作；当前只允许一只）。"""
        if self._follower is not None:
            self._dismiss_follower()
        if not self.pet_holder:
            return
        from .follower import FollowerPet
        self._follower = FollowerPet(master=self.pet_holder[0], holder=self.pet_holder, scale=scale)
        self._follower.show()

    def _dismiss_follower(self) -> None:
        if self._follower is not None:
            try:
                self._follower.close()
            except Exception:
                pass
            self._follower = None

    def _fill_effect_menu(self, menu) -> None:
        """填充特效装饰子菜单。"""
        menu.clear()
        from .effects import EFFECTS
        current = self._get_effect_config()
        for key, info in EFFECTS.items():
            act = QAction(info["name"], self.app, checkable=True)
            act.setChecked(key == current)
            act.triggered.connect(lambda _=False, k=key: self._on_set_effect(k))
            menu.addAction(act)

    def _get_effect_config(self) -> str:
        """读取当前特效配置。"""
        import json
        import os
        from ..core.runtime_paths import get_writable_root
        cfg_path = os.path.join(get_writable_root(module_file=__file__), "config", "effects.json")
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("current", "none")
            except Exception:
                pass
        return "none"

    def _save_effect_config(self, name: str) -> None:
        """保存特效配置。"""
        import json
        import os
        from ..core.runtime_paths import get_writable_root
        cfg_path = os.path.join(get_writable_root(module_file=__file__), "config", "effects.json")
        try:
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump({"current": name}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Tray] 保存特效配置失败: {e}")

    def _on_set_effect(self, name: str) -> None:
        """切换特效。"""
        if not self.pet_holder:
            return
        pet = self.pet_holder[0]
        ok = pet.set_effect(name)
        if ok:
            self._save_effect_config(name)
        # 刷新所有特效菜单的勾选状态
        for m in (getattr(self, "_effect_menu", None), getattr(self, "_dock_effect_menu", None)):
            if m is not None:
                self._fill_effect_menu(m)

    def _refresh_theme_effect_menu(self) -> None:
        """刷新主题时同步特效菜单样式。"""
        for m in (getattr(self, "_effect_menu", None), getattr(self, "_dock_effect_menu", None)):
            if m is not None:
                m.setStyleSheet(_menu_style())

    def _on_comfort(self):
        """托盘「安慰我」：用桌宠气泡开启引导式安慰对话（多轮，无 AI 也能用）。"""
        if not self.pet_holder:
            return
        self.pet_holder[0].start_comfort_dialog()

    def _on_destroy_file(self):
        """摧毁文件：选文件 → 点屏幕位置 → 宠物跑过去表演摧毁（进回收站）。"""
        if not self.pet_holder:
            return
        from .destroy_show import begin_destroy_flow
        pet = self.pet_holder[0]
        begin_destroy_flow(pet, pet)

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
