"""
桌宠组件：支持宠物包（pet package）与公共/独立插槽
- 每个宠物像 SimuEngine 的 topic 一样独立配置
- 对话使用统一 AI 服务（api_config_loader + ai_service），需在 config/api.json 中填写 apiKey 与 modelId
"""
import random
import time
from typing import Any, Dict, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QPixmap, QFont
from PyQt5.QtWidgets import QLabel, QWidget, QApplication

from input_dialog import InputDialog
import threading
import traceback


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

        self.scale_factor = scale_factor
        self.frame_rate = frame_rate
        self.current_state = "stand"
        self.previous_state = "stand"
        self.current_frame_index = 0
        self.move_speed = 5
        self.allow_movement = True

        self.init_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.next_frame)
        self.timer.start(1000 // self.frame_rate)

        self.state_timer = QTimer(self)
        self.state_timer.timeout.connect(self.change_state)
        self.state_timer.start(3000)  # 每 3 秒切换一次状态（站/走），便于看到自主移动

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

        first_frame = QPixmap(self.animations["stand"][0])
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

        self.bubble_label = QLabel(self)
        self.bubble_label.setStyleSheet(
            _bubble_style_from_config(self.bubble_style_config)
        )
        font = QFont("Microsoft YaHei", 14)
        font.setBold(True)
        self.bubble_label.setFont(font)
        self.bubble_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.bubble_label.setWordWrap(True)
        self.bubble_label.setVisible(False)
        self.bubble_label.resize(200, 100)

        self.update_frame()

    @pyqtSlot()
    def show_custom_input_dialog(self):
        input_dialog = InputDialog(self, self.handle_input)
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
        """使用统一 AI 服务（config/api.json 配置 apiKey + modelId）生成回复并流式更新气泡。"""
        try:
            from ai_service import stream_chat, validate_ai_config
            system_prompt = self.character.get("systemPrompt") or (
                "你是一个可爱的桌面宠物，用简短、友好的话回复用户。"
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ]
            if not validate_ai_config():
                self.update_bubble("请先在 config/api.json 中填写 apiKey 并设置 modelId 后再和我对话哦～")
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
        frames = self.animations[self.current_state]
        self.current_frame_index = (self.current_frame_index + 1) % len(frames)
        self.update_frame()
        if self.current_state in ["walk_left", "walk_right", "walk_up", "walk_down"]:
            self.update_position()

    def update_frame(self):
        frame_path = self.animations[self.current_state][self.current_frame_index]
        pixmap = QPixmap(frame_path)
        scaled_pixmap = pixmap.scaled(self.width(), self.height())
        self.label.setPixmap(scaled_pixmap)

    def change_state(self):
        if self.current_state == "dragged" or not self.allow_movement:
            return
        # 约 50% 站立、50% 随机方向行走，让自主移动更明显
        walk_states = ["walk_left", "walk_right", "walk_up", "walk_down"]
        walk_states = [s for s in walk_states if s in self.animations]
        if not walk_states:
            return
        if random.random() < 0.5:
            self.current_state = random.choice(walk_states)
        else:
            self.current_state = "stand"
        self.current_frame_index = 0

    def update_position(self):
        x, y = self.x(), self.y()
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

    def update_bubble(self, text: str, duration: int = 3000) -> None:
        self.bubble_label.setVisible(True)
        self.bubble_label.setText(text)
        max_width = 200
        self.bubble_label.setWordWrap(True)
        self.bubble_label.setFixedWidth(max_width)
        metrics = self.bubble_label.fontMetrics()
        lines = metrics.boundingRect(0, 0, max_width, 0, Qt.TextWordWrap, text)
        self.bubble_label.resize(lines.width() + 20, lines.height() + 50)
        self.bubble_label.move(
            self.width() // 2 - self.bubble_label.width() // 2,
            0,
        )

    def show_bubble(self, text: str, duration: int = 3000, typing_speed: int = 50) -> None:
        self.bubble_label.setText("")
        self.bubble_label.setVisible(True)
        max_width = 200
        self.bubble_label.setWordWrap(True)
        self.bubble_label.setFixedWidth(max_width)
        metrics = self.bubble_label.fontMetrics()
        lines = metrics.boundingRect(0, 0, max_width, 0, Qt.TextWordWrap, text)
        self.bubble_label.resize(lines.width() + 20, lines.height() + 50)
        self.bubble_label.move(
            self.width() // 2 - self.bubble_label.width() // 2,
            0,
        )
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
        else:
            self.typing_timer.stop()

    def hide_bubble(self):
        self.bubble_label.setVisible(False)
        self.bubble_timer.stop()

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
