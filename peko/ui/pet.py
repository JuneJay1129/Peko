"""
桌宠组件：窗口、动画帧、气泡、拖拽；动作与聊天委托给独立模块。
- 动作：actions.auto（自动随机）、actions.control（键盘操控）
- 聊天：chat（输入框 + AI 气泡）
"""
import sys
from typing import Any, Dict

from PyQt5.QtCore import Qt, QTimer, pyqtSlot, pyqtSignal
from PyQt5.QtGui import QPixmap, QFont
from PyQt5.QtWidgets import QLabel, QWidget, QApplication

from .actions import (
    AutoActions,
    ControlActions,
    STANDARD_MOVEMENT_STATES,
    RESERVED_STATES,
)


def _default_bubble_style() -> str:
    return """
        background-color: rgba(255, 255, 255, 0.9);
        border: 2px solid #4CAF50;
        border-radius: 15px;
        padding: 10px;
        font-size: 14px;
        color: black;
    """


def _bubble_style_from_config(bubble_style: Dict[str, Any]) -> str:
    """从宠物包的 bubbleStyle 生成 QSS（可扩展）。"""
    if not bubble_style:
        return _default_bubble_style()
    bg = bubble_style.get("backgroundColor", "rgba(255, 255, 255, 0.9)")
    border = bubble_style.get("border", "2px solid #4CAF50")
    radius = bubble_style.get("borderRadius", "15px")
    padding = bubble_style.get("padding", "10px")
    font_size = bubble_style.get("fontSize", "14px")
    color = bubble_style.get("color", "black")
    return f"""
        background-color: {bg};
        border: {border};
        border-radius: {radius};
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

        self.init_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.next_frame)
        self._apply_state_frame_rate()
        self.timer.start()

        self.state_timer = QTimer(self)
        self._auto_actions = AutoActions(self, self.state_timer)
        self._control_actions = ControlActions(self)
        self._chat = None  # 在 init 末尾创建，避免循环引用

        self._auto_actions.schedule_next()

        self.bubble_timer = QTimer(self)
        self.bubble_timer.timeout.connect(self.hide_bubble)
        self.bubble_text_ready.connect(self._on_bubble_text_ready)
        self.typing_timer = QTimer(self)
        self.typing_timer.timeout.connect(self.type_next_character)

        from .chat import ChatHandler
        self._chat = ChatHandler(self)

    def init_ui(self):
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        first_frame_path = self.animations["stand"][0]
        first_frame = QPixmap(first_frame_path)
        if first_frame.isNull():
            print(f"[Peko] 无法加载首帧: {first_frame_path}")
            first_frame = QPixmap(1, 1)
        if self._display_width is not None and self._display_height is not None:
            self.setFixedSize(self._display_width, self._display_height)
        else:
            self.setFixedSize(first_frame.size())

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
        self.bubble_window.setAttribute(Qt.WA_TranslucentBackground, False)
        self.bubble_label = QLabel(self.bubble_window)
        self.bubble_label.setStyleSheet(_bubble_style_from_config(self.bubble_style_config))
        font = QFont("PingFang SC" if sys.platform == "darwin" else "Microsoft YaHei", 14)
        font.setBold(True)
        self.bubble_label.setFont(font)
        self.bubble_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.bubble_label.setWordWrap(True)
        self.bubble_label.setVisible(True)
        self.bubble_label.resize(200, 100)
        self.bubble_label.move(0, 0)
        self.bubble_window.resize(200, 100)
        self.bubble_window.setVisible(False)

        self.update_frame()
        self.setFocusPolicy(Qt.StrongFocus)

    def set_control_mode(self, on: bool) -> None:
        """切换为操控模式或自动模式。"""
        self.control_mode = on
        self.state_timer.stop()
        if on:
            self._control_actions.enter()
        else:
            self._control_actions.exit()
            self._auto_actions.resume()

    def _get_current_frame_rate(self) -> int:
        return self._state_config.get(self.current_state, {}).get("frameRate") or self.frame_rate

    def _apply_state_frame_rate(self) -> None:
        fps = max(1, self._get_current_frame_rate())
        self.timer.setInterval(max(50, 1000 // fps))

    @pyqtSlot()
    def show_custom_input_dialog(self):
        """委托给聊天模块。"""
        if self._chat:
            self._chat.show_dialog()

    def next_frame(self):
        frames = self.animations.get(self.current_state)
        if not frames:
            return
        self.current_frame_index = (self.current_frame_index + 1) % len(frames)
        self.update_frame()
        if self.current_state in STANDARD_MOVEMENT_STATES:
            self.update_position()

    def update_frame(self):
        frames = self.animations.get(self.current_state)
        if not frames and self.current_state == "dragged":
            frames = self.animations.get("stand")
        if not frames:
            return
        frame_path = frames[self.current_frame_index % len(frames)]
        pixmap = QPixmap(frame_path)
        if pixmap.isNull():
            print(f"[Peko] 无法加载帧: {frame_path}")
            return
        scaled_pixmap = pixmap.scaled(self.width(), self.height())
        self.label.setPixmap(scaled_pixmap)

    def update_position(self):
        x, y = self.x(), self.y()
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
        lines = metrics.boundingRect(0, 0, max_width, 0, Qt.TextWordWrap, text)
        w, h = lines.width() + 20, lines.height() + 50
        self.bubble_label.resize(w, h)
        self.bubble_window.resize(w, h)
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
        lines = metrics.boundingRect(0, 0, max_width, 0, Qt.TextWordWrap, text)
        w, h = lines.width() + 20, lines.height() + 50
        self.bubble_label.resize(w, h)
        self.bubble_window.resize(w, h)
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
            lines = metrics.boundingRect(0, 0, 200, 0, Qt.TextWordWrap, self.current_text)
            w, h = lines.width() + 20, lines.height() + 50
            self.bubble_label.resize(w, h)
            self.bubble_window.resize(w, h)
            self._position_bubble_window()
        else:
            self.typing_timer.stop()

    def hide_bubble(self):
        self.bubble_window.hide()
        self.bubble_timer.stop()

    @pyqtSlot(str, int)
    def _on_bubble_text_ready(self, text: str, duration: int):
        self.update_bubble(text, duration=duration)

    def closeEvent(self, event):
        self.bubble_window.hide()
        super().closeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
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
            self.current_state = self.previous_state
            self.current_frame_index = 0
            self._apply_state_frame_rate()
            QTimer.singleShot(10, self._resume_after_drag)
            event.accept()

    def _resume_after_drag(self) -> None:
        if self.current_state == "dragged":
            self.current_state = "stand"
        if not self.control_mode:
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
            self._auto_actions.resume()
