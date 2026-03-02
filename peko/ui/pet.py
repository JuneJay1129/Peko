"""
桌宠组件：支持宠物包（pet package）与公共/独立插槽
- 每个宠物像 SimuEngine 的 topic 一样独立配置
- 对话使用统一 AI 服务（api_config_loader + ai_service），需在 config/secrets.json 填写 apiKey、config/api.json 设置 modelId
"""
import random
import time
import threading
import traceback
from typing import Any, Dict, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QPixmap, QFont
from PyQt5.QtWidgets import QLabel, QWidget, QApplication

from .input_dialog import InputDialog

# 公共动作：会触发位移
STANDARD_MOVEMENT_STATES = ["walk_left", "walk_right", "walk_up", "walk_down"]
# 系统保留：不参与随机切换
RESERVED_STATES = ["stand", "dragged"]


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
    桌宠窗口。
    pet_package: 宠物包（来自 pet_manager.get_pet），含 animations、character、bubbleStyle、slots 等。
    scale_factor / frame_rate: 显示与动画参数。
    """

    def __init__(
        self,
        pet_package: Dict[str, Any],
        scale_factor: int = 2,
        frame_rate: int = 10,
    ):
        super().__init__()
        self.pet_package = pet_package
        self.animations = pet_package["animations"]
        self.character = pet_package.get("character") or {}
        self.bubble_style_config = pet_package.get("bubbleStyle") or {}
        self.slots = pet_package.get("slots") or {}
        action_cfg = pet_package.get("actionConfig") or {}

        self.scale_factor = scale_factor
        self.frame_rate = action_cfg.get("frameRate") or frame_rate
        self.current_state = "stand"
        self.previous_state = "stand"
        self.current_frame_index = 0
        self.move_speed = action_cfg.get("moveSpeed", 5)
        self.state_switch_interval = action_cfg.get("stateSwitchInterval", 3000)
        self.allow_movement = True
        self._input_dialog = None  # 对话输入框，L+Enter 再次按下时关闭

        self.init_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.next_frame)
        self.timer.start(max(50, 1000 // self.frame_rate))

        self.state_timer = QTimer(self)
        self.state_timer.timeout.connect(self.change_state)
        self.state_timer.start(max(500, self.state_switch_interval))

        self.bubble_timer = QTimer(self)
        self.bubble_timer.timeout.connect(self.hide_bubble)

        self.typing_timer = QTimer(self)
        self.typing_timer.timeout.connect(self.type_next_character)

    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint
            | Qt.FramelessWindowHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        first_frame_path = self.animations["stand"][0]
        first_frame = QPixmap(first_frame_path)
        if first_frame.isNull():
            print(f"[Peko] 无法加载首帧: {first_frame_path}")
            first_frame = QPixmap(1, 1)  # 占位，避免后续 scaled 报错
        scaled_size = first_frame.size() * self.scale_factor
        self.setFixedSize(scaled_size)

        self.label = QLabel(self)
        self.label.setFixedSize(self.size())
        self.label.setScaledContents(False)

        screen_geometry = QApplication.desktop().screenGeometry()
        screen_width, screen_height = screen_geometry.width(), screen_geometry.height()
        pet_width, pet_height = self.width(), self.height()
        offset_x, offset_y = 20, 50
        initial_x = screen_width - pet_width - offset_x
        initial_y = screen_height - pet_height - offset_y
        self.move(initial_x, initial_y)

        # 气泡用独立窗口，避免被宠物窗口裁剪（宠物缩小后仍能完整显示）
        self.bubble_window = QWidget(self)
        self.bubble_window.setWindowFlags(
            Qt.Window | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool
        )
        self.bubble_window.setAttribute(Qt.WA_TranslucentBackground, False)
        self.bubble_label = QLabel(self.bubble_window)
        self.bubble_label.setStyleSheet(
            _bubble_style_from_config(self.bubble_style_config)
        )
        font = QFont("Microsoft YaHei", 14)
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

    @pyqtSlot()
    def show_custom_input_dialog(self):
        # 若对话框已打开，再次 L+Enter 关闭
        if self._input_dialog is not None and self._input_dialog.isVisible():
            self._input_dialog.reject()
            self._input_dialog = None
            return
        input_dialog = InputDialog(self, self.handle_input)
        self._input_dialog = input_dialog
        input_dialog.finished.connect(lambda: setattr(self, "_input_dialog", None))
        pet_x, pet_y = self.x(), self.y()
        pet_width, pet_height = self.width(), self.height()
        # 放在宠物上方，避免遮挡
        dialog_x = pet_x + (pet_width - input_dialog.width()) // 2
        dialog_y = pet_y - input_dialog.height() - 15
        screen = QApplication.desktop().screenGeometry()
        if dialog_y < 0:
            dialog_y = pet_y + pet_height + 10  # 若上方空间不足，则放下方
        dialog_x = max(0, min(dialog_x, screen.width() - input_dialog.width()))
        dialog_y = max(0, min(dialog_y, screen.height() - input_dialog.height()))
        input_dialog.move(dialog_x, dialog_y)
        input_dialog.exec_()

    def handle_input(self, dialog, text):
        dialog.close()
        if text.strip():
            threading.Thread(
                target=self.fetch_response, args=(text,), daemon=True
            ).start()

    def fetch_response(self, user_input: str) -> None:
        """使用统一 AI 服务（config/secrets.json + api.json 配置 apiKey + modelId）生成回复并流式更新气泡。"""
        try:
            from ..ai.service import stream_chat, validate_ai_config
            system_prompt = self.character.get("systemPrompt") or (
                "你是一个可爱的桌面宠物，用简短、友好的话回复用户。"
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ]
            if not validate_ai_config():
                self.update_bubble("请先在 config/secrets.json 中填写 apiKey、config/api.json 中设置 modelId 后再和我对话哦～")
                return
            current = [""]

            def on_token(token: str):
                current[0] += token
                self.update_bubble(current[0], duration=5000)

            stream_chat(messages, on_token=on_token)
            time.sleep(2)
            self.hide_bubble()
        except Exception as e:
            err_msg = str(e)
            self.update_bubble(f"错误: {err_msg}")
            print("[Peko API 错误]", err_msg)
            traceback.print_exc()

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

    def change_state(self):
        if self.current_state == "dragged" or not self.allow_movement:
            return
        # 公共动作：行走（会位移）
        walk_states = [s for s in STANDARD_MOVEMENT_STATES if s in self.animations]
        # 自定义动作：animations 中除 stand/dragged/walk_* 外的所有 key
        custom_states = [
            k for k in self.animations.keys()
            if k not in RESERVED_STATES and k not in STANDARD_MOVEMENT_STATES
        ]
        # 可选池：stand + 行走 + 自定义，pet.py 只负责随机选择
        pool = []
        if "stand" in self.animations:
            pool.append("stand")
        pool.extend(walk_states)
        pool.extend(custom_states)
        if not pool:
            return
        self.current_state = random.choice(pool)
        self.current_frame_index = 0

    def update_position(self):
        x, y = self.x(), self.y()
        if self.current_state not in STANDARD_MOVEMENT_STATES:
            return
        if self.current_state == "walk_left":
            x -= self.move_speed
        elif self.current_state == "walk_right":
            x += self.move_speed
        elif self.current_state == "walk_up":
            y -= self.move_speed
        elif self.current_state == "walk_down":
            y += self.move_speed
        screen_geometry = QApplication.desktop().screenGeometry()
        x = max(0, min(x, screen_geometry.width() - self.width()))
        y = max(0, min(y, screen_geometry.height() - self.height()))
        self.move(x, y)
        self._position_bubble_window()

    def _position_bubble_window(self) -> None:
        """把气泡窗口放在宠物上方（屏幕坐标），不受宠物窗口大小裁剪。"""
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
            # 打字时随内容更新气泡窗口大小并重定位
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

    def closeEvent(self, event):
        self.bubble_window.hide()
        super().closeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.previous_state = self.current_state
            self.current_state = "dragged"
            self.current_frame_index = 0
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
            event.accept()

    def set_allow_movement(self, allow: bool) -> None:
        self.allow_movement = allow
        if not allow:
            self.current_state = "stand"
            self.current_frame_index = 0
