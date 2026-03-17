"""
桌宠组件：窗口、动画帧、气泡、拖拽；动作与聊天委托给独立模块。
- 动作：actions.auto（自动随机）、actions.control（键盘操控）
- 聊天：chat（输入框 + AI 气泡）
- 随机文案：配置 randomSayings 后偶尔用气泡弹出句子（复用气泡样式）
"""
import random
import sys
from typing import Any, Dict, Optional, Tuple

from PyQt5.QtCore import Qt, QTimer, pyqtSlot, pyqtSignal, QDateTime, QRect, QPropertyAnimation, QParallelAnimationGroup, QEasingCurve
from PyQt5.QtGui import QPixmap, QFont
from PyQt5.QtWidgets import QLabel, QWidget, QApplication

from .actions import (
    AutoActions,
    ControlActions,
    FollowMouseActions,
    STANDARD_MOVEMENT_STATES,
    RESERVED_STATES,
)

# 动作「控制窗口」：走向屏幕四角后对前台窗口最小化/最大化（仅 Windows）
WINDOW_CONTROL_STATE = "window_control"
WINDOW_CONTROL_REACH_THRESHOLD = 25


def _default_bubble_style() -> str:
    return """
        background-color: rgba(255, 255, 255, 0.72);
        border: 2px solid rgba(76, 175, 80, 0.85);
        border-radius: 15px;
        border-top-left-radius: 15px;
        border-top-right-radius: 15px;
        border-bottom-left-radius: 15px;
        border-bottom-right-radius: 15px;
        padding: 10px;
        font-size: 14px;
        color: black;
    """


def _bubble_style_from_config(bubble_style: Dict[str, Any]) -> str:
    """从宠物包的 bubbleStyle 生成 QSS（可扩展）。"""
    if not bubble_style:
        return _default_bubble_style()
    bg = bubble_style.get("backgroundColor", "rgba(255, 255, 255, 0.72)")
    border = bubble_style.get("border", "2px solid rgba(76, 175, 80, 0.85)")
    radius = bubble_style.get("borderRadius", "15px")
    padding = bubble_style.get("padding", "10px")
    font_size = bubble_style.get("fontSize", "14px")
    color = bubble_style.get("color", "black")
    return f"""
        background-color: {bg};
        border: {border};
        border-radius: {radius};
        border-top-left-radius: {radius};
        border-top-right-radius: {radius};
        border-bottom-left-radius: {radius};
        border-bottom-right-radius: {radius};
        padding: {padding};
        font-size: {font_size};
        color: {color};
    """


class DesktopPet(QWidget):
    """
    桌宠窗口。动作与聊天委托给 actions 与 chat 模块。
    """
    bubble_text_ready = pyqtSignal(str, int)  # text, duration；供 chat 模块 emit 后主线程更新气泡

    def __init__(self, pet_package: Dict[str, Any], frame_rate: int = 10):
        super().__init__()
        self.pet_package = pet_package
        raw_animations = pet_package["animations"]
        self.character = pet_package.get("character") or {}
        self.bubble_style_config = pet_package.get("bubbleStyle") or {}
        self.slots = pet_package.get("slots") or {}
        action_cfg = pet_package.get("actionConfig") or {}

        display = pet_package.get("displaySize")
        if isinstance(display, (list, tuple)) and len(display) >= 2:
            self._display_width, self._display_height = int(display[0]), int(display[1])
        elif isinstance(pet_package.get("frameWidth"), (int, float)) and isinstance(pet_package.get("frameHeight"), (int, float)):
            self._display_width = int(pet_package["frameWidth"])
            self._display_height = int(pet_package["frameHeight"])
        else:
            self._display_width = self._display_height = None
        self._display_scale = 1.0

        default_frame_rate = action_cfg.get("frameRate") or frame_rate
        default_switch_interval = action_cfg.get("stateSwitchInterval", 3000)
        default_move_speed = action_cfg.get("moveSpeed", 5)

        self.animations = {}
        self._state_config = {}
        for state_name, state_value in raw_animations.items():
            frames = state_value.get("frames") or []
            self.animations[state_name] = frames
            self._state_config[state_name] = {
                "frameRate": state_value.get("frameRate") if "frameRate" in state_value else default_frame_rate,
                "stateSwitchInterval": state_value.get("stateSwitchInterval") if "stateSwitchInterval" in state_value else default_switch_interval,
                "moveSpeed": state_value.get("moveSpeed") if "moveSpeed" in state_value else default_move_speed,
            }

        self.frame_rate = default_frame_rate
        self.state_switch_interval = default_switch_interval
        self.move_speed = default_move_speed
        self.current_state = "stand"
        self.previous_state = "stand"
        self.current_frame_index = 0
        self.allow_movement = True
        self.control_mode = False
        self.follow_mouse_mode = False

        self.init_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.next_frame)
        self._apply_state_frame_rate()
        self.timer.start()

        self.state_timer = QTimer(self)
        self._auto_actions = AutoActions(self, self.state_timer)
        self._control_actions = ControlActions(self)
        self._follow_mouse_actions = FollowMouseActions(self)
        self._chat = None  # 在 init 末尾创建，避免循环引用

        self._auto_actions.schedule_next()

        self.bubble_timer = QTimer(self)
        self.bubble_timer.timeout.connect(self.hide_bubble)
        self.bubble_text_ready.connect(self._on_bubble_text_ready)
        self.typing_timer = QTimer(self)
        self.typing_timer.timeout.connect(self.type_next_character)

        from .chat import ChatHandler
        self._chat = ChatHandler(self)

        # 随机文案：从 randomSayings.phrases 随机取一句，用现有气泡弹出（复用气泡样式）
        sayings_cfg = pet_package.get("randomSayings") or {}
        self._sayings_phrases = sayings_cfg.get("phrases") or []
        self._sayings_enabled = sayings_cfg.get("enabled", True) if self._sayings_phrases else False
        self._sayings_interval_min = max(30000, int(sayings_cfg.get("intervalMinMs", 60000)))
        self._sayings_interval_max = max(
            self._sayings_interval_min,
            int(sayings_cfg.get("intervalMaxMs", 180000)),
        )
        self._sayings_duration = max(2000, int(sayings_cfg.get("durationMs", 5000)))
        self._sayings_timer = QTimer(self)
        self._sayings_timer.setSingleShot(True)
        self._sayings_timer.timeout.connect(self._on_sayings_tick)
        if self._sayings_enabled:
            self._schedule_next_saying(initial_delay=True)

        # 快速点击计数：用于“连续 3 次及以上点击触发 fight”
        self._click_count = 0
        self._last_click_time_ms = 0
        self._press_global_pos = None
        self._triple_click_window_ms = 500  # 在此时间内的点击算作连续

    def init_ui(self):
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        first_frame_path = self.animations["stand"][0]
        first_frame = QPixmap(first_frame_path)
        if first_frame.isNull():
            print(f"[Peko] 无法加载首帧: {first_frame_path}")
            first_frame = QPixmap(1, 1)
        if self._display_width is not None and self._display_height is not None:
            self._base_display_width = self._display_width
            self._base_display_height = self._display_height
        else:
            self._base_display_width = first_frame.width()
            self._base_display_height = first_frame.height()
        w = max(1, int(self._base_display_width * self._display_scale))
        h = max(1, int(self._base_display_height * self._display_scale))
        self.setFixedSize(w, h)

        self.label = QLabel(self)
        self.label.setFixedSize(self.size())
        self.label.setScaledContents(False)

        screen_geometry = QApplication.desktop().screenGeometry()
        screen_width, screen_height = screen_geometry.width(), screen_geometry.height()
        pet_width, pet_height = self.width(), self.height()
        initial_x = screen_width - pet_width - 20
        initial_y = screen_height - pet_height - 50
        self.move(initial_x, initial_y)

        self.bubble_window = QWidget(self)
        self.bubble_window.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.bubble_window.setAttribute(Qt.WA_TranslucentBackground, True)
        self.bubble_label = QLabel(self.bubble_window)
        self.bubble_label.setStyleSheet(_bubble_style_from_config(self.bubble_style_config))
        font = QFont("PingFang SC" if sys.platform == "darwin" else "Microsoft YaHei", 14)
        font.setBold(True)
        self.bubble_label.setFont(font)
        self.bubble_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.bubble_label.setWordWrap(True)
        self.bubble_label.setContentsMargins(12, 12, 12, 12)
        self.bubble_label.setVisible(True)
        self.bubble_label.resize(200, 100)
        self.bubble_label.move(0, 0)
        self.bubble_window.resize(200, 100)
        self.bubble_window.setVisible(False)

        self.update_frame()
        self.setFocusPolicy(Qt.StrongFocus)

    def set_control_mode(self, on: bool) -> None:
        """切换为操控模式或自动/跟随模式。"""
        self.control_mode = on
        if on:
            self.set_follow_mouse_mode(False)
        self.state_timer.stop()
        if on:
            self._control_actions.enter()
        else:
            self._control_actions.exit()
            if not self.follow_mouse_mode:
                self._auto_actions.resume()

    def set_follow_mouse_mode(self, on: bool) -> None:
        """切换为跟随鼠标模式；与操控模式互斥。"""
        self.follow_mouse_mode = on
        if on:
            self.control_mode = False
            self._control_actions.exit()
            self.state_timer.stop()
            self._follow_mouse_actions.enter()
        else:
            self._follow_mouse_actions.exit()
            self.state_timer.stop()
            if not self.control_mode:
                self._auto_actions.resume()

    def _get_current_frame_rate(self) -> int:
        if self.follow_mouse_mode and getattr(self, "_follow_mouse_frame_rate", None) is not None:
            return max(1, min(60, self._follow_mouse_frame_rate))
        return self._state_config.get(self.current_state, {}).get("frameRate") or self.frame_rate

    def _apply_state_frame_rate(self) -> None:
        fps = max(1, self._get_current_frame_rate())
        self.timer.setInterval(max(50, 1000 // fps))

    def get_action_params(self) -> Dict[str, Any]:
        """供参数面板读取：当前动作相关参数。"""
        return {
            "frameRate": self.frame_rate,
            "stateSwitchInterval": self.state_switch_interval,
            "moveSpeed": self.move_speed,
        }

    def get_action_params_for_state(self, state_name: Optional[str]) -> Dict[str, Any]:
        """获取指定动作的参数；state_name 为 None 或空时返回全局默认。"""
        if not state_name or state_name == "__all__":
            return self.get_action_params()
        cfg = self._state_config.get(state_name, {})
        return {
            "frameRate": cfg.get("frameRate") or self.frame_rate,
            "stateSwitchInterval": cfg.get("stateSwitchInterval") or self.state_switch_interval,
            "moveSpeed": cfg.get("moveSpeed") or self.move_speed,
        }

    def set_action_params_for_state(
        self,
        state_name: Optional[str],
        frame_rate: Optional[int] = None,
        state_switch_interval: Optional[int] = None,
        move_speed: Optional[int] = None,
    ) -> None:
        """仅更新指定动作的参数；state_name 为 None 或 '__all__' 时更新全局并应用到所有动作。"""
        if not state_name or state_name == "__all__":
            self.set_action_params(
                frame_rate=frame_rate,
                state_switch_interval=state_switch_interval,
                move_speed=move_speed,
                apply_to_all_states=True,
            )
            return
        if state_name not in self._state_config:
            return
        cfg = self._state_config[state_name]
        if frame_rate is not None:
            cfg["frameRate"] = max(1, min(60, frame_rate))
        if state_switch_interval is not None:
            cfg["stateSwitchInterval"] = max(500, min(120000, state_switch_interval))
        if move_speed is not None:
            cfg["moveSpeed"] = max(1, min(50, move_speed))
        self._apply_state_frame_rate()
        if not self.control_mode and not self.follow_mouse_mode and hasattr(self, "_auto_actions"):
            self._auto_actions.schedule_next()

    def get_display_scale(self) -> float:
        """当前宠物显示缩放比例，1.0 为配置的原始大小。"""
        return getattr(self, "_display_scale", 1.0)

    def set_display_scale(self, scale: float) -> None:
        """设置宠物显示缩放比例（如 0.5～2.0），立即生效。"""
        scale = max(0.5, min(2.0, float(scale)))
        self._display_scale = scale
        if not hasattr(self, "_base_display_width"):
            return
        w = max(1, int(self._base_display_width * scale))
        h = max(1, int(self._base_display_height * scale))
        self.setFixedSize(w, h)
        if hasattr(self, "label"):
            self.label.setFixedSize(self.size())
        self.update_frame()
        self._position_bubble_window()

    def set_action_params(
        self,
        frame_rate: Optional[int] = None,
        state_switch_interval: Optional[int] = None,
        move_speed: Optional[int] = None,
        apply_to_all_states: bool = True,
    ) -> None:
        """
        实时更新动作参数并生效。
        apply_to_all_states 为 True 时同时更新各状态覆盖值；会立即刷新帧率与状态切换定时器。
        """
        if frame_rate is not None:
            self.frame_rate = max(1, min(60, frame_rate))
            if apply_to_all_states:
                for cfg in self._state_config.values():
                    cfg["frameRate"] = self.frame_rate
        if state_switch_interval is not None:
            self.state_switch_interval = max(500, min(120000, state_switch_interval))
            if apply_to_all_states:
                for cfg in self._state_config.values():
                    cfg["stateSwitchInterval"] = self.state_switch_interval
        if move_speed is not None:
            self.move_speed = max(1, min(50, move_speed))
            if apply_to_all_states:
                for cfg in self._state_config.values():
                    cfg["moveSpeed"] = self.move_speed
        self._apply_state_frame_rate()
        if not self.control_mode and not self.follow_mouse_mode and hasattr(self, "_auto_actions"):
            self._auto_actions.schedule_next()

    @pyqtSlot()
    def show_custom_input_dialog(self):
        """委托给聊天模块。"""
        if self._chat:
            self._chat.show_dialog()

    def next_frame(self):
        if self.follow_mouse_mode:
            self._follow_mouse_actions.update_direction_to_cursor()
        frames = self.animations.get(self.current_state)
        if not frames and self.current_state != "dragged":
            self.current_state = "stand"
            self.current_frame_index = 0
            frames = self.animations.get("stand")
        if not frames:
            return
        self.current_frame_index = (self.current_frame_index + 1) % len(frames)
        self.update_frame()
        if self.current_state in STANDARD_MOVEMENT_STATES and not self.follow_mouse_mode:
            self.update_position()
        elif self.current_state == WINDOW_CONTROL_STATE and not getattr(self, "clone_mode", False):
            self._update_window_control_position()

    def update_frame(self):
        frames = self.animations.get(self.current_state)
        if not frames and self.current_state == "dragged":
            frames = self.animations.get("stand")
        if not frames and self.current_state != "dragged":
            frames = self.animations.get("stand")
            if frames:
                self.current_state = "stand"
                self.current_frame_index = 0
        if not frames:
            return
        frame_path = frames[self.current_frame_index % len(frames)]
        pixmap = QPixmap(frame_path)
        if pixmap.isNull():
            print(f"[Peko] 无法加载帧: {frame_path}")
            stand_frames = self.animations.get("stand") or []
            if stand_frames:
                fallback_path = stand_frames[0]
                fallback_pixmap = QPixmap(fallback_path)
                if not fallback_pixmap.isNull():
                    self.label.setPixmap(fallback_pixmap.scaled(self.width(), self.height()))
            return
        scaled_pixmap = pixmap.scaled(self.width(), self.height())
        self.label.setPixmap(scaled_pixmap)

    def update_position(self):
        if getattr(self, "_exit_animating", False):
            return
        x, y = self.x(), self.y()
        # 分身模式：固定在任务栏上一行，只做水平位移
        clone_mode = getattr(self, "clone_mode", False)
        row_y = getattr(self, "clone_mode_row_y", None)
        if clone_mode and row_y is not None:
            y = row_y
            if self.current_state == "walk_left":
                cfg = self._state_config.get(self.current_state, {})
                speed = cfg.get("moveSpeed", self.move_speed)
                x -= speed
            elif self.current_state == "walk_right":
                cfg = self._state_config.get(self.current_state, {})
                speed = cfg.get("moveSpeed", self.move_speed)
                x += speed
            screen_geometry = QApplication.desktop().screenGeometry()
            x = max(0, min(x, screen_geometry.width() - self.width()))
            self.move(x, y)
            self._position_bubble_window()
            return
        if self.current_state not in STANDARD_MOVEMENT_STATES:
            return
        cfg = self._state_config.get(self.current_state, {})
        speed = cfg.get("moveSpeed") if "moveSpeed" in cfg else self.move_speed
        if self.current_state == "walk_left":
            x -= speed
        elif self.current_state == "walk_right":
            x += speed
        elif self.current_state == "walk_up":
            y -= speed
        elif self.current_state == "walk_down":
            y += speed
        screen_geometry = QApplication.desktop().screenGeometry()
        x = max(0, min(x, screen_geometry.width() - self.width()))
        y = max(0, min(y, screen_geometry.height() - self.height()))
        self.move(x, y)
        self._position_bubble_window()

    def _get_window_control_target(self) -> Optional[Tuple[int, int]]:
        """随机选一个屏幕四角坐标（宠物左上角目标），仅 Windows 有效。"""
        screen = QApplication.desktop().screenGeometry()
        sw = screen.width()
        sh = screen.height()
        pw = self.width()
        ph = self.height()
        corners = [
            (0, 0),
            (sw - pw, 0),
            (0, sh - ph),
            (sw - pw, sh - ph),
        ]
        return random.choice(corners)

    def _update_window_control_position(self) -> None:
        """window_control 动作：朝目标角移动，到达后对前台窗口最小化/最大化并切回 stand。"""
        target = getattr(self, "_window_control_target", None)
        if target is None:
            self._window_control_target = self._get_window_control_target()
            target = self._window_control_target
        tx, ty = target
        x, y = self.x(), self.y()
        cfg = self._state_config.get(WINDOW_CONTROL_STATE, {})
        speed = cfg.get("moveSpeed", self.move_speed)
        dx = tx - x
        dy = ty - y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist <= WINDOW_CONTROL_REACH_THRESHOLD:
            self._do_window_control_action()
            self._window_control_target = None
            self.current_state = "stand"
            self.current_frame_index = 0
            self._apply_state_frame_rate()
            self.update_frame()
            if not self.control_mode and not self.follow_mouse_mode and hasattr(self, "_auto_actions"):
                self._auto_actions.schedule_next()
            return
        if dist > 0:
            step = min(speed, dist)
            x = int(x + (dx / dist) * step)
            y = int(y + (dy / dist) * step)
        screen = QApplication.desktop().screenGeometry()
        x = max(0, min(x, screen.width() - self.width()))
        y = max(0, min(y, screen.height() - self.height()))
        self.move(x, y)
        self._position_bubble_window()

    def _do_window_control_action(self) -> None:
        """对当前前台窗口执行：最小化、最大化、或缩放（变大/变小）（仅 Windows）。"""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            SW_MINIMIZE = 6
            SW_MAXIMIZE = 3
            SW_RESTORE = 9
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return
            action = random.choice(["minimize", "maximize", "resize_larger", "resize_smaller"])
            if action == "minimize":
                user32.ShowWindow(hwnd, SW_MINIMIZE)
            elif action == "maximize":
                user32.ShowWindow(hwnd, SW_RESTORE)
                user32.ShowWindow(hwnd, SW_MAXIMIZE)
            else:
                # 变大或变小：先还原再按当前尺寸缩放
                if user32.IsZoomed(hwnd):
                    user32.ShowWindow(hwnd, SW_RESTORE)
                class RECT(ctypes.Structure):
                    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
                rect = RECT()
                if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    return
                w = rect.right - rect.left
                h = rect.bottom - rect.top
                screen = QApplication.desktop().screenGeometry()
                max_w = screen.width()
                max_h = screen.height()
                min_w, min_h = 200, 150
                if action == "resize_larger":
                    new_w = min(int(w * 1.2), max_w)
                    new_h = min(int(h * 1.2), max_h)
                    if new_w <= w and new_h <= h:
                        new_w = min(w + 80, max_w)
                        new_h = min(h + 60, max_h)
                else:
                    new_w = max(int(w * 0.8), min_w)
                    new_h = max(int(h * 0.8), min_h)
                    if new_w >= w and new_h >= h:
                        new_w = max(w - 80, min_w)
                        new_h = max(h - 60, min_h)
                user32.MoveWindow(hwnd, rect.left, rect.top, new_w, new_h, 1)
        except Exception:
            pass

    def _position_bubble_window(self) -> None:
        if not self.bubble_window.isVisible():
            return
        pet_global = self.mapToGlobal(self.rect().topLeft())
        bw, bh = self.bubble_window.width(), self.bubble_window.height()
        bx = pet_global.x() + (self.width() - bw) // 2
        by = pet_global.y() - bh - 8
        screen = QApplication.desktop().screenGeometry()
        by = max(0, min(by, screen.height() - bh))
        bx = max(0, min(bx, screen.width() - bw))
        self.bubble_window.move(bx, by)

    def update_bubble(self, text: str, duration: int = 3000) -> None:
        self.bubble_label.setVisible(True)
        self.bubble_label.setText(text)
        max_width = 200
        self.bubble_label.setWordWrap(True)
        self.bubble_label.setFixedWidth(max_width)
        metrics = self.bubble_label.fontMetrics()
        # 用足够大的高度计算换行后的真实尺寸；加 descent 避免汉字下半被裁切
        br = metrics.boundingRect(0, 0, max_width, 2000, Qt.TextWordWrap, text)
        w = min(max(br.width() + 24 + 12, 120), 400)  # 左右 contentsMargins 12*2 + 余量
        h = br.height() + metrics.descent() + 24  # 上下各 12px 留白，descent 防裁切
        self.bubble_window.resize(w, h)
        self.bubble_label.setFixedSize(w, h)
        self.bubble_label.move(0, 0)
        self.bubble_window.setVisible(True)
        self._position_bubble_window()
        self.bubble_timer.stop()
        self.bubble_timer.start(duration)

    def show_bubble(self, text: str, duration: int = 3000, typing_speed: int = 50) -> None:
        self.bubble_label.setText("")
        self.bubble_label.setVisible(True)
        max_width = 200
        self.bubble_label.setWordWrap(True)
        self.bubble_label.setFixedWidth(max_width)
        metrics = self.bubble_label.fontMetrics()
        br = metrics.boundingRect(0, 0, max_width, 2000, Qt.TextWordWrap, text)
        w = min(max(br.width() + 24 + 12, 120), 400)
        h = br.height() + metrics.descent() + 24
        self.bubble_window.resize(w, h)
        self.bubble_label.setFixedSize(w, h)
        self.bubble_label.move(0, 0)
        self.bubble_window.setVisible(True)
        self._position_bubble_window()
        self.full_text = text
        self.current_text = ""
        self.typing_index = 0
        self.typing_timer.start(typing_speed)
        self.bubble_timer.start(duration)

    def type_next_character(self):
        if self.typing_index < len(self.full_text):
            self.current_text += self.full_text[self.typing_index]
            self.bubble_label.setText(self.current_text)
            self.typing_index += 1
            metrics = self.bubble_label.fontMetrics()
            br = metrics.boundingRect(0, 0, 200, 2000, Qt.TextWordWrap, self.current_text)
            w = min(max(br.width() + 24 + 12, 120), 400)
            h = br.height() + metrics.descent() + 24
            self.bubble_window.resize(w, h)
            self.bubble_label.setFixedSize(w, h)
            self.bubble_label.move(0, 0)
            self._position_bubble_window()
        else:
            self.typing_timer.stop()

    def hide_bubble(self):
        self.bubble_window.hide()
        self.bubble_timer.stop()

    def _stop_bubble_timers(self):
        """停止所有与气泡相关的定时器并隐藏气泡，用于关闭窗口前清理，避免关闭后定时器再次弹出气泡。"""
        self.bubble_timer.stop()
        self.typing_timer.stop()
        if hasattr(self, "_sayings_timer") and self._sayings_timer:
            self._sayings_timer.stop()
        self.bubble_window.hide()

    def _cleanup_for_destroy(self) -> None:
        """彻底清理：停止所有定时器并关闭气泡窗口，用于分身模式退出时，避免气泡残留和卡顿。"""
        self.timer.stop()
        self.state_timer.stop()
        self._stop_bubble_timers()
        self.bubble_window.close()

    def play_exit_animation(self, duration_ms: int = 2000) -> None:
        """退场动画：使用 walk_up 向上移动并逐渐透明，渐行渐远。"""
        self._exit_animating = True
        self._stop_bubble_timers()
        self.state_timer.stop()
        if "walk_up" in self.animations and (self.animations.get("walk_up") or []):
            self.current_state = "walk_up"
        else:
            self.current_state = "stand"
        self.current_frame_index = 0
        self._apply_state_frame_rate()
        self.update_frame()

        start_rect = QRect(self.x(), self.y(), self.width(), self.height())
        end_y = -self.height() - 100
        end_rect = QRect(self.x(), end_y, self.width(), self.height())

        anim_geom = QPropertyAnimation(self, b"geometry")
        anim_geom.setDuration(duration_ms)
        anim_geom.setStartValue(start_rect)
        anim_geom.setEndValue(end_rect)
        anim_geom.setEasingCurve(QEasingCurve.OutCubic)

        anim_opacity = QPropertyAnimation(self, b"windowOpacity")
        anim_opacity.setDuration(duration_ms)
        anim_opacity.setStartValue(1.0)
        anim_opacity.setEndValue(0.0)
        anim_opacity.setEasingCurve(QEasingCurve.InQuad)

        self._exit_animation_group = QParallelAnimationGroup(self)
        self._exit_animation_group.addAnimation(anim_geom)
        self._exit_animation_group.addAnimation(anim_opacity)
        self._exit_animation_group.start()

    def showEvent(self, event):
        super().showEvent(event)
        self.update_frame()
        self.update()

    def closeEvent(self, event):
        self._stop_bubble_timers()
        super().closeEvent(event)

    def _schedule_next_saying(self, initial_delay: bool = False) -> None:
        """安排下一次随机文案弹出（单次定时器，随机间隔）。"""
        if not self._sayings_enabled or not self._sayings_phrases:
            return
        low, high = self._sayings_interval_min, self._sayings_interval_max
        delay = random.randint(10000, 30000) if initial_delay else (random.randint(low, high) if low <= high else low)
        self._sayings_timer.stop()
        self._sayings_timer.setInterval(delay)
        self._sayings_timer.start()

    def _on_sayings_tick(self) -> None:
        """定时到：若当前无气泡则随机选一句用气泡显示，然后安排下一次。"""
        if not self._sayings_enabled or not self._sayings_phrases:
            return
        if self.bubble_window.isVisible():
            self._schedule_next_saying()
            return
        text = random.choice(self._sayings_phrases)
        if text and isinstance(text, str):
            self.update_bubble(text.strip(), duration=self._sayings_duration)
        self._schedule_next_saying()

    def try_show_action_bubble(self, state_name: str) -> None:
        """若当前无气泡且该动作配置了专属气泡，则显示。用于随机/分身模式切换动作时，不与 randomSayings 冲突。"""
        if self.bubble_window.isVisible():
            return
        animations = self.pet_package.get("animations") or {}
        bubble_cfg = animations.get(state_name) or {}
        raw = bubble_cfg.get("bubbles") if "bubbles" in bubble_cfg else bubble_cfg.get("bubble")
        if isinstance(raw, list):
            text = (random.choice(raw).strip() if raw else "")
        else:
            text = (raw or "").strip() if isinstance(raw, str) else ""
        if not text:
            return
        self.update_bubble(text, duration=self._sayings_duration)

    @pyqtSlot(str, int)
    def _on_bubble_text_ready(self, text: str, duration: int):
        self.update_bubble(text, duration=duration)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_global_pos = event.globalPos()
            self.previous_state = self.current_state
            self.current_state = "dragged"
            self.current_frame_index = 0
            self.state_timer.stop()
            self._apply_state_frame_rate()
            self.mouse_drag_position = event.globalPos() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.mouse_drag_position)
            self._position_bubble_window()
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 快速三击检测（仅自动模式且该宠物有 fight 动作时）：位移小于阈值视为一次“点击”
            triggered_fight = False
            if (
                self._press_global_pos is not None
                and "fight" in self.animations
                and not self.control_mode
                and not getattr(self, "follow_mouse_mode", False)
                and self.current_state != "fight"
            ):
                release_pos = event.globalPos()
                dx = release_pos.x() - self._press_global_pos.x()
                dy = release_pos.y() - self._press_global_pos.y()
                if dx * dx + dy * dy <= 225:  # 约 15px 内视为点击
                    now = QDateTime.currentMSecsSinceEpoch()
                    if now - self._last_click_time_ms > self._triple_click_window_ms:
                        self._click_count = 0
                    self._click_count += 1
                    self._last_click_time_ms = now
                    if self._click_count >= 3:
                        self._click_count = 0
                        self.current_state = "fight"
                        self.current_frame_index = 0
                        self._apply_state_frame_rate()
                        self.update_frame()
                        cfg = self._state_config.get("fight", {})
                        interval = cfg.get("stateSwitchInterval") or self.state_switch_interval
                        interval = max(500, int(interval) if isinstance(interval, (int, float)) else self.state_switch_interval)
                        self.state_timer.setInterval(interval)
                        self.state_timer.start()
                        triggered_fight = True
            self._press_global_pos = None

            if not triggered_fight:
                # 分身模式下松手后把 y 贴回任务栏一行，保持在同一排
                if getattr(self, "clone_mode", False):
                    row_y = getattr(self, "clone_mode_row_y", None)
                    if row_y is not None:
                        screen = QApplication.desktop().screenGeometry()
                        x = max(0, min(self.x(), screen.width() - self.width()))
                        self.move(x, row_y)
                        self._position_bubble_window()
                self.current_state = self.previous_state
                self.current_frame_index = 0
                self._apply_state_frame_rate()
                QTimer.singleShot(10, self._resume_after_drag)
            event.accept()

    def _resume_after_drag(self) -> None:
        if self.current_state == "dragged":
            self.current_state = "stand"
        if not self.control_mode and not self.follow_mouse_mode:
            self._auto_actions.resume()

    def enter_listen(self) -> None:
        """进入 listen 动作（对话前待机）。仅自动模式且配置了 listen 时生效；会暂停 state_timer，直到 exit_listen。"""
        if self.control_mode or getattr(self, "follow_mouse_mode", False) or "listen" not in self.animations:
            return
        self.state_timer.stop()
        self._state_before_listen = self.current_state
        self.current_state = "listen"
        self.current_frame_index = 0
        self._apply_state_frame_rate()
        self.update_frame()

    def exit_listen(self) -> None:
        """结束 listen 动作（用户发送消息或关闭对话框后调用），恢复此前状态并继续自动切换。"""
        if self.current_state != "listen":
            return
        self.current_state = getattr(self, "_state_before_listen", "stand")
        self.current_frame_index = 0
        self._apply_state_frame_rate()
        self.update_frame()
        if not self.control_mode and not getattr(self, "follow_mouse_mode", False):
            self._auto_actions.resume()

    def keyPressEvent(self, event):
        if self.control_mode and self._control_actions.handle_key_press(event):
            event.accept()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if self.control_mode and self._control_actions.handle_key_release(event):
            event.accept()
        else:
            super().keyReleaseEvent(event)

    def set_allow_movement(self, allow: bool) -> None:
        self.allow_movement = allow
        if not allow:
            self.current_state = "stand"
            self.current_frame_index = 0
            self._apply_state_frame_rate()
        elif not self.control_mode and not getattr(self, "follow_mouse_mode", False) and self.current_state != "listen":
            self._auto_actions.resume()
