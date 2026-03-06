"""
聊天模块：与宠物对话（输入框 + AI 回复 + 气泡展示）。
"""
import threading
import traceback
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .pet import DesktopPet

# 宠物回复/错误提示气泡展示时长（毫秒），可在此调整
REPLY_BUBBLE_DURATION_MS = 10000


class ChatHandler:
    """对话：弹出输入框，调用 AI 服务，结果通过宠物的气泡展示。"""

    def __init__(self, pet: "DesktopPet"):
        self.pet = pet
        self._input_dialog = None

    def show_dialog(self) -> None:
        """显示与宠物对话的输入框；若已打开则关闭。"""
        if self._input_dialog is not None and self._input_dialog.isVisible():
            self._input_dialog.reject()
            self._input_dialog = None
            return
        from .input_dialog import InputDialog
        from PyQt5.QtWidgets import QApplication

        # 操控模式下宠物会 grabKeyboard，导致对话框内的输入框收不到按键；先释放以便 Backspace 等可用
        if getattr(self.pet, "releaseKeyboard", None):
            try:
                self.pet.releaseKeyboard()
            except Exception:
                pass

        dialog = InputDialog(self.pet, self._on_submit)
        self._input_dialog = dialog
        dialog.finished.connect(self._on_dialog_finished)

        pet_x, pet_y = self.pet.x(), self.pet.y()
        pet_width, pet_height = self.pet.width(), self.pet.height()
        dialog_x = pet_x + (pet_width - dialog.width()) // 2
        dialog_y = pet_y - dialog.height() - 15
        screen = QApplication.desktop().screenGeometry()
        if dialog_y < 0:
            dialog_y = pet_y + pet_height + 10
        dialog_x = max(0, min(dialog_x, screen.width() - dialog.width()))
        dialog_y = max(0, min(dialog_y, screen.height() - dialog.height()))
        dialog.move(dialog_x, dialog_y)
        dialog.exec_()

    def _on_dialog_finished(self):
        self._input_dialog = None
        # 若仍在操控模式，重新抓取键盘以便方向键/空格继续生效
        if getattr(self.pet, "control_mode", False) and getattr(self.pet, "grabKeyboard", None):
            try:
                self.pet.grabKeyboard()
            except Exception:
                pass

    def _on_submit(self, dialog, text: str) -> None:
        dialog.close()
        if text.strip():
            threading.Thread(target=self._fetch_response, args=(text.strip(),), daemon=True).start()

    def _fetch_response(self, user_input: str) -> None:
        """子线程中调用 AI，结果通过 pet.bubble_text_ready 在主线程更新气泡。"""
        try:
            from ..ai.service import stream_chat, validate_ai_config
            character = self.pet.character
            system_prompt = character.get("systemPrompt") or (
                "你是一个可爱的桌面宠物，用简短、友好的话回复用户。"
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ]
            if not validate_ai_config():
                self.pet.bubble_text_ready.emit(
                    "请先在 config/secrets.json 中填写 apiKey、config/api.json 中设置 modelId 后再和我对话哦～",
                    REPLY_BUBBLE_DURATION_MS,
                )
                return
            current = [""]

            def on_token(token: str):
                current[0] += token
                self.pet.bubble_text_ready.emit(current[0], REPLY_BUBBLE_DURATION_MS)

            stream_chat(messages, on_token=on_token)
            self.pet.bubble_text_ready.emit(current[0], REPLY_BUBBLE_DURATION_MS)
        except Exception as e:
            err_msg = str(e)
            self.pet.bubble_text_ready.emit(f"错误: {err_msg}", REPLY_BUBBLE_DURATION_MS)
            print("[Peko API 错误]", err_msg)
            traceback.print_exc()
