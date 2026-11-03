"""
系统托盘：显示/隐藏桌宠、停止移动、切换宠物、退出
托盘图标优先与可执行文件相同（项目根 / 打包后的 icon.ico 等，与 main.spec 一致），否则使用当前宠物的 resource/icon.png 或 stand 首帧。
右键菜单使用统一暖色样式。
macOS：菜单栏托盘上左右键常会统一为 Trigger，需监听 activated 再弹出菜单（否则右键无反应）。
"""
import os
import sys
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction, QActionGroup, QInputDialog
from PyQt5.QtGui import QIcon, QCursor

from ..core.pet_manager import RESOURCE_DIR, get_app_exe_icon_path

def _menu_style() -> str:
    """托盘菜单样式：已收敛到 style_kit.menu_qss（保留函数名兼容旧调用点）。"""
    from .style_kit import menu_qss
    return menu_qss()


# ---- 菜单注册表 ----
# 托盘菜单与 macOS Dock 菜单共用这一份结构定义：新增功能只需在 action 创建区
# 加一个 QAction 并在此注册一行，两个入口即同步生效（不会再出现漏 Dock 的情况）。
# 项格式：
#   ("action", 属性名)
#   ("sep",)
#   ("submenu", 显示名, 填充方法名或 None, (托盘属性, Dock属性))
_MENU_SPEC = (
    ("action", "_show_action"),
    ("action", "_hide_action"),
    ("action", "_talk_action"),
    ("sep",),
    ("action", "_comfort_action"),
    ("action", "_weather_action"),
    ("action", "_weather_city_action"),
    ("action", "_destroy_file_action"),
    ("submenu", "模式", None, ("_mode_menu", "_dock_mode_menu")),
    ("submenu", "召唤跟班", "_fill_follower_menu", ("_follower_menu", "_dock_follower_menu")),
    ("submenu", "特效装饰", "_fill_effect_menu", ("_effect_menu", "_dock_effect_menu")),
    ("sep",),
    ("action", "_settings_action"),
    ("sep",),
    ("action", "_exit_action"),
)

# 「模式」子菜单固定项（注册表 submenu 填充器为 None 时使用）
_MODE_MENU_ITEMS = (
    "_auto_mode_action", "_control_mode_action", "_follow_mouse_action", "_clone_mode_action",
)


def _build_menu_from_spec(owner, menu, dock: bool) -> None:
    """按 _MENU_SPEC 构建 menu（托盘与 Dock 同源）。

    dock=False 时子菜单引用写到托盘属性名（如 _effect_menu）；
    dock=True 时写到 Dock 属性名（如 _dock_effect_menu），供 aboutToShow / 主题刷新复用。
    """
    for item in _MENU_SPEC:
        kind = item[0]
        if kind == "sep":
            menu.addSeparator()
        elif kind == "action":
            menu.addAction(getattr(owner, item[1]))
        else:  # submenu
            _, label, filler_name, (tray_attr, dock_attr) = item
            sub = menu.addMenu(label)
            sub.setStyleSheet(_menu_style())
            setattr(owner, dock_attr if dock else tray_attr, sub)
            if filler_name:
                getattr(owner, filler_name)(sub)
            else:  # 模式菜单：固定项 + 分隔 + 敲键盘 + 停止移动
                for act_name in _MODE_MENU_ITEMS:
                    sub.addAction(getattr(owner, act_name))
                sub.addSeparator()
                sub.addAction(owner._bongo_mode_action)
                # 造型子菜单每次现建：QMenu 只能挂一个父菜单，
                # 托盘和 Dock 两套菜单共用同一个对象会只有一边显出来。
                style = sub.addMenu("键盘造型")
                style.setStyleSheet(_menu_style())
                owner._fill_bongo_style_menu(style)
                sub.addSeparator()
                sub.addAction(owner._stop_movement_action)


def _tray_icon_path(registry) -> str:
    """托盘图标：优先 exe 同款图标；否则当前宠物 resource/icon.png，再否则 stand 首帧。"""
    app_icon = get_app_exe_icon_path()
    if app_icon:
        return app_icon
    pet_icon = ""
    if registry:
        pkg = registry.current().pet_package
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
    def __init__(self, app, registry, on_switch_pet=None, clone_pets=None, set_clone_mode=None):
        """
        :param app: QApplication 实例
        :param registry: PetRegistry，current() 为当前宠物；切换宠物由 main 经 set_master 替换
        :param on_switch_pet: 可选，回调 (pet_id: str) -> None，用于切换宠物
        :param clone_pets: 可选，分身模式下的额外宠物列表（由 main 填充），用于显示/隐藏/退出
        :param set_clone_mode: 可选，回调 (on: bool) -> None，进入/退出分身模式
        """
        self.app = app
        self.registry = registry
        self.on_switch_pet = on_switch_pet
        self.clone_pets = clone_pets if clone_pets is not None else []
        self.set_clone_mode = set_clone_mode
        self._follower = None  # 召唤跟班（FollowerPet）
        self._bongo_host = None  # 敲键盘模式（BongoKeyboardMode），首次开启时才建
        icon_path = _tray_icon_path(registry)
        self.tray_icon = QSystemTrayIcon(QIcon(icon_path) if icon_path else QIcon(), self.app)
        self.create_tray_menu()
        # 主题切换总线：settings 广播 theme_changed 后菜单配色自动刷新
        from ..core.bus import bus
        self._on_theme_changed = lambda key: self.refresh_theme()
        bus.subscribe("theme_changed", self._on_theme_changed)

    def update_icon(self):
        """切换宠物后更新托盘图标（优先 exe 同款图标）。"""
        icon_path = _tray_icon_path(self.registry)
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
        self._weather_city_action = QAction("查询城市天气…", self.app)
        self._destroy_file_action = QAction("摧毁文件…", self.app)
        self._settings_action = QAction("设置…", self.app)
        self._exit_action = QAction("退出", self.app)

        self._show_action.triggered.connect(self._on_show_pets)
        self._hide_action.triggered.connect(self._on_hide_pets)
        self._talk_action.triggered.connect(lambda: self.registry.current().show_custom_input_dialog() if self.registry else None)
        self._comfort_action.triggered.connect(self._on_comfort)
        self._weather_action.triggered.connect(self._on_weather)
        self._weather_city_action.triggered.connect(self._on_weather_city)
        self._destroy_file_action.triggered.connect(self._on_destroy_file)
        self._settings_action.triggered.connect(self.open_settings)
        self._exit_action.triggered.connect(self.exit_app)

        # 模式动作（自动/操控/跟随/分身 + 停止移动）
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

        # 敲键盘：独立开关，不和上面几个移动模式互斥（猫在敲键盘时也可以跟随鼠标）
        self._bongo_mode_action = QAction("敲键盘模式", self.app, checkable=True)
        self._bongo_mode_action.triggered.connect(self._on_bongo_mode)

        # 按注册表构建托盘菜单（Dock 菜单同源，见 _install_macos_dock_menu）
        _build_menu_from_spec(self, menu, dock=False)
        self._update_follower_menu()  # 托盘/Dock 跟班菜单按当前跟班状态填充

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
        """Dock 图标菜单：与托盘同源（_MENU_SPEC），仅挂载方式不同。Qt 文档：setAsDockMenu 仅 macOS。"""
        dock = QMenu()
        if not hasattr(dock, "setAsDockMenu"):
            return
        self._dock_menu = dock
        dock.setStyleSheet(_menu_style())
        _build_menu_from_spec(self, dock, dock=True)
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
            if len(clone_pets) > 0 and self.registry:
                all_pets = self.registry.all_pets()
                for p in all_pets:
                    try:
                        p.lower()
                    except Exception:
                        pass
            self._tray_menu.popup(QCursor.pos())

    def _on_tray_menu_about_to_hide_macos(self):
        """macOS 托盘菜单关闭后：恢复宠物窗口置顶层级（分身模式下临时降下的）。"""
        clone_pets = getattr(self, "clone_pets", []) or []
        if len(clone_pets) > 0 and self.registry:
            all_pets = self.registry.all_pets()
            for p in all_pets:
                try:
                    p.raise_()
                except Exception:
                    pass

    def _all_pets(self):
        """当前所有宠物窗口（主宠 + 分身），用于显示/隐藏/退出等。"""
        return self.registry.all_pets()

    def _on_show_pets(self):
        # 敲键盘模式下本体是藏着的（身体由叠加层画），直接 show 会出现两个身子。
        # 语义上「显示桌宠」= 退出那个模式，比默默无视这次点击清楚。
        self._leave_bongo_mode()
        for p in self._all_pets():
            p.show()

    def _on_hide_pets(self):
        for p in self._all_pets():
            p.hide()

    def exit_app(self):
        # 退出主题总线订阅
        try:
            from ..core.bus import bus
            bus.unsubscribe("theme_changed", self._on_theme_changed)
        except Exception:
            pass
        # 先摘键盘钩子：pynput 的监听线程不摘会吊住进程，托盘退了爪子还在按
        self.reset_bongo()
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
        self._leave_bongo_mode()
        for p in self._all_pets():
            p.set_allow_movement(not checked)

    def _show_action_params_dialog(self):
        """打开动作参数面板，居中显示，可拖动。"""
        if not self.registry:
            return
        from .action_params_dialog import ActionParamsDialog
        from PyQt5.QtWidgets import QApplication
        pet = self.registry.current()
        dialog = ActionParamsDialog(pet, pet)
        screen = QApplication.desktop().availableGeometry()
        x = (screen.width() - dialog.width()) // 2 + screen.x()
        y = (screen.height() - dialog.height()) // 2 + screen.y()
        dialog.move(x, y)
        dialog.exec_()

    def _show_plans_web_dialog(self):
        """打开 Web 工作台（内嵌 QWebEngine，实时桥接 plans.json）。"""
        if not self.registry:
            return
        from .plans_web_dialog import open_plans_web
        pet = self.registry.current()
        open_plans_web(pet, pet)

    def _show_plans_web_browser_dialog(self):
        """在系统浏览器中打开 Web 工作台（纯网页版，localStorage 模式）。"""
        if not self.registry:
            return
        from .plans_web_dialog import open_plans_web_browser
        pet = self.registry.current()
        open_plans_web_browser(pet)

    def _on_weather(self):
        """托盘「天气」：气泡播报当前天气（缓存命中则秒回，否则后台取数）。"""
        if not self.registry:
            return
        from .weather_report import report_weather
        report_weather(self.registry.current())

    def _on_weather_city(self):
        """托盘「查询城市天气…」：输入城市名直查（无 AI，wttr.in 支持中英文城市名）。
        输入框样式跟随当前外观主题（style_kit.input_dialog_qss）。"""
        if not self.registry:
            return
        from .style_kit import input_dialog_qss
        last = getattr(self, "_last_weather_city", "")
        dialog = QInputDialog(None)
        dialog.setWindowTitle("查询城市天气")
        dialog.setLabelText("输入城市名（如：宁波 / 上海 / Tokyo）：")
        dialog.setTextValue(last)
        dialog.setInputMode(QInputDialog.TextInput)
        dialog.setStyleSheet(input_dialog_qss())
        ok = dialog.exec_() == QInputDialog.Accepted
        city = (dialog.textValue() or "").strip() if ok else ""
        if not city:
            return
        self._last_weather_city = city  # 记住本次输入，下次作默认值
        from .weather_report import report_weather
        report_weather(self.registry.current(), city)

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
        if not self.registry:
            return
        from .follower import FollowerPet
        self._follower = FollowerPet(master=self.registry.current(), holder=self.registry, scale=scale)
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
        """读取当前特效配置（已收敛到 core.effect_state）。"""
        from ..core import effect_state
        return effect_state.get_current()

    def _save_effect_config(self, name: str) -> None:
        """保存特效配置（已收敛到 core.effect_state）。"""
        from ..core import effect_state
        if not effect_state.set_current(name):
            print(f"[Tray] 保存特效配置失败: {name}")

    def _on_set_effect(self, name: str) -> None:
        """切换特效。"""
        if not self.registry:
            return
        pet = self.registry.current()
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
        if not self.registry:
            return
        self.registry.current().start_comfort_dialog()

    def _on_destroy_file(self):
        """摧毁文件：选文件 → 点屏幕位置 → 宠物跑过去表演摧毁（进回收站）。"""
        if not self.registry:
            return
        from .destroy_show import begin_destroy_flow
        pet = self.registry.current()
        begin_destroy_flow(pet, pet)

    def _show_api_settings_dialog(self):
        """打开 AI 设置对话框，保存后立即生效。"""
        if not self.registry:
            return
        from .api_settings_dialog import ApiSettingsDialog
        from PyQt5.QtWidgets import QApplication
        pet = self.registry.current()
        dialog = ApiSettingsDialog(pet)
        screen = QApplication.desktop().availableGeometry()
        x = (screen.width() - dialog.width()) // 2 + screen.x()
        y = (screen.height() - dialog.height()) // 2 + screen.y()
        dialog.move(x, y)
        dialog.exec_()

    def _on_auto_mode(self):
        self._leave_bongo_mode()
        if self.registry:
            if getattr(self, "set_clone_mode", None) and len(getattr(self, "clone_pets", [])) > 0:
                self.set_clone_mode(False)
            self.registry.current().set_control_mode(False)
            self.registry.current().set_follow_mouse_mode(False)
            self._auto_mode_action.setChecked(True)
            self._control_mode_action.setChecked(False)
            self._follow_mouse_action.setChecked(False)
            self._clone_mode_action.setChecked(False)

    def _on_control_mode(self):
        self._leave_bongo_mode()
        if self.registry:
            if getattr(self, "set_clone_mode", None) and len(getattr(self, "clone_pets", [])) > 0:
                self.set_clone_mode(False)
            self.registry.current().set_control_mode(True)
            self._auto_mode_action.setChecked(False)
            self._control_mode_action.setChecked(True)
            self._follow_mouse_action.setChecked(False)
            self._clone_mode_action.setChecked(False)

    def _on_follow_mouse_mode(self):
        self._leave_bongo_mode()
        if self.registry:
            if getattr(self, "set_clone_mode", None) and len(getattr(self, "clone_pets", [])) > 0:
                self.set_clone_mode(False)
            self.registry.current().set_follow_mouse_mode(True)
            self._auto_mode_action.setChecked(False)
            self._control_mode_action.setChecked(False)
            self._follow_mouse_action.setChecked(True)
            self._clone_mode_action.setChecked(False)

    def _on_clone_mode(self):
        if not self.registry or not self.set_clone_mode:
            return
        self._leave_bongo_mode()
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

    # ---- 敲键盘模式 ----

    def _ensure_bongo_host(self):
        """懒建敲键盘宿主。绑在**当前宠物**身上，切换宠物后要 reset_bongo。"""
        if self._bongo_host is None:
            pet = self.registry.current() if self.registry else None
            if pet is None:
                return None
            from .bongo import BongoKeyboardMode

            self._bongo_host = BongoKeyboardMode(pet)
        return self._bongo_host

    def _fill_bongo_style_menu(self, menu):
        """造型子菜单：注册表里有几款就列几款，新加模式不用改这里。"""
        from ..core import bongo_modes

        group = QActionGroup(menu)
        group.setExclusive(True)
        current = bongo_modes.current_key()
        for mode in bongo_modes.list_modes():
            act = QAction(mode.label, menu, checkable=True)
            act.setChecked(mode.key == current)
            if mode.desc:
                act.setToolTip(mode.desc)
            act.triggered.connect(lambda _checked=False, key=mode.key: self._on_bongo_style(key))
            group.addAction(act)
            menu.addAction(act)
        self._bongo_style_group = group

    def _on_bongo_style(self, key):
        """换造型：先落盘再让宿主重建，下次启动还是这一款。"""
        from ..core import bongo_modes

        if not bongo_modes.set_mode(key):
            return
        if self._bongo_host is not None:
            self._bongo_host.apply_mode(bongo_modes.get_mode(key))

    def _on_bongo_mode(self, checked: bool):
        host = self._ensure_bongo_host()
        if host is None:
            self._bongo_mode_action.setChecked(False)
            return
        if not checked:
            host.stop()
            return
        backend = host.start()
        if not backend:
            # 拿不到全局键盘就退回关闭：光有画面、爪子不动，比直接不开更迷惑
            host.stop()
            self._bongo_mode_action.setChecked(False)
            self._warn("这机器拿不到全局键盘监听（缺 pynput / 辅助功能权限），敲键盘模式开不了。")

    def _leave_bongo_mode(self):
        """切到别的模式前先关掉敲键盘模式。

        不关的话宠物本体还藏着、位置还被钉着，用户点「自动模式」看不到任何
        变化，只会觉得模式切不回去。
        """
        if not hasattr(self, "_bongo_mode_action"):
            return
        if not self._bongo_mode_action.isChecked():
            return
        self._bongo_mode_action.setChecked(False)
        if self._bongo_host is not None:
            self._bongo_host.stop()

    def _warn(self, message: str, duration: int = 9000) -> None:
        pet = self.registry.current() if self.registry else None
        if pet is None:
            return
        try:
            pet.update_bubble(message, duration=duration)
        except Exception:
            print(f"[Peko] {message}")

    def reset_bongo(self):
        """切换宠物后调用：叠加层绑在旧宠物身上，必须关掉重建。"""
        if self._bongo_host is not None:
            try:
                # shutdown 而不是 stop：键鼠造型还挂着 pynput 鼠标监听线程，
                # 只 stop 的话对象删了线程还在，进程退不掉
                self._bongo_host.shutdown()
                self._bongo_host.overlay.deleteLater()
                self._bongo_host.deleteLater()
            except Exception:
                pass
            self._bongo_host = None
        if hasattr(self, "_bongo_mode_action"):
            self._bongo_mode_action.setChecked(False)

    def _update_mode_actions_checked(self):
        """打开托盘菜单时，根据当前模式同步勾选状态。"""
        if self.registry and hasattr(self, "_auto_mode_action"):
            pet = self.registry.current()
            cm = getattr(pet, "control_mode", False)
            fm = getattr(pet, "follow_mouse_mode", False)
            in_clone = len(getattr(self, "clone_pets", [])) > 0
            # 敲键盘模式开着时，上面四个移动模式都不该显示成勾选：
            # 宠物的动作是停着的，勾着「自动模式」等于告诉用户它还在自己走
            bongo_on = getattr(self, "_bongo_mode_action", None) is not None and \
                self._bongo_mode_action.isChecked()
            self._auto_mode_action.setChecked(not cm and not fm and not in_clone and not bongo_on)
            self._control_mode_action.setChecked(cm)
            self._follow_mouse_action.setChecked(fm)
            self._clone_mode_action.setChecked(in_clone)
