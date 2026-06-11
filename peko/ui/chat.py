"""
聊天模块：与宠物对话（输入框 + AI 回复 + 气泡展示 + Agent 工具调用）。
"""
import os
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
        self._full_chat_window = None
        self._agent = None  # 懒加载 AgentLoop

    def _get_system_prompt(self) -> str:
        """构建系统提示词（含情绪上下文）。"""
        character = self.pet.character
        system_prompt = character.get("systemPrompt") or (
            "你是一个可爱的桌面宠物，用简短、友好的话回复用户。"
        )
        mood_context = ""
        if hasattr(self.pet, "get_chat_context"):
            mood_context = self.pet.get_chat_context()
        if mood_context:
            system_prompt = f"{system_prompt}\n\n{mood_context}"
        return system_prompt

    def _get_or_create_agent(self):
        """获取或创建 AgentLoop 实例（懒加载）。"""
        if self._agent is None:
            self._agent = self._create_agent()
        else:
            # 更新系统提示词（情绪可能变化）
            self._agent.set_system_prompt(self._get_system_prompt())
        return self._agent

    def _create_agent(self):
        """创建一个新的 AgentLoop 实例。"""
        from ..ai.agent import AgentLoop
        from ..ai.service import validate_ai_config
        if not validate_ai_config():
            return None
        return AgentLoop(
            system_prompt=self._get_system_prompt(),
            on_status=lambda s: self.pet.bubble_text_ready.emit(s, REPLY_BUBBLE_DURATION_MS),
            on_token=lambda t: None,  # token 通过下面的 local closure 传
        )

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

        dialog = InputDialog(self.pet, self._on_submit, on_expand=self._open_full_chat)
        self._input_dialog = dialog
        dialog.finished.connect(self._on_dialog_finished)

        # 自动模式下进入 listen 动作（对话前待机），发送或关闭对话框时由 _on_dialog_finished 调用 exit_listen
        self.pet.enter_listen()

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

    def _open_full_chat(self) -> None:
        """关闭小输入框，打开完整聊天窗口。"""
        if self._input_dialog is not None:
            self._input_dialog.close()
            self._input_dialog = None

        if self._full_chat_window is not None and self._full_chat_window.isVisible():
            self._full_chat_window.activateWindow()
            return

        from .full_chat import FullChatWindow

        pkg = self.pet.pet_package
        pet_dir = pkg.get("_pet_dir", "")
        pet_icon_path = ""
        if pet_dir:
            icon_path = os.path.join(pet_dir, "resource", "icon.png")
            if os.path.isfile(icon_path):
                pet_icon_path = icon_path
            else:
                stand = (pkg.get("animations") or {}).get("stand") or {}
                frames = stand.get("frames") or []
                if frames and os.path.isfile(frames[0]):
                    pet_icon_path = frames[0]

        agent = self._create_agent()
        window = FullChatWindow(
            agent_loop=agent,
            system_prompt=self._get_system_prompt(),
            pet_name=str(pkg.get("name") or pkg.get("id") or "Peko"),
            pet_icon_path=pet_icon_path,
        )
        self._full_chat_window = window
        window.closed.connect(self._on_full_chat_closed)
        window.show()
        window.activateWindow()

    def _on_full_chat_closed(self):
        self._full_chat_window = None

    def _on_dialog_finished(self):
        self._input_dialog = None
        self.pet.exit_listen()
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
        """子线程中调用 AI（含工具调用），结果通过 pet.bubble_text_ready 在主线程更新气泡。"""
        try:
            from ..ai.service import validate_ai_config
            if not validate_ai_config():
                self.pet.bubble_text_ready.emit(
                    "请先在任务栏菜单的 AI 设置里填写 API Key 并选择模型，然后再和我对话哦～",
                    REPLY_BUBBLE_DURATION_MS,
                )
                return

            agent = self._get_or_create_agent()
            if agent is None:
                self.pet.bubble_text_ready.emit("AI 初始化失败，请检查配置。", REPLY_BUBBLE_DURATION_MS)
                return

            accumulated = [""]
            has_streamed = [False]

            def on_token(token: str):
                accumulated[0] += token
                has_streamed[0] = True
                self.pet.bubble_text_ready.emit(accumulated[0], REPLY_BUBBLE_DURATION_MS)

            def on_status(status: str):
                self.pet.bubble_text_ready.emit(status, REPLY_BUBBLE_DURATION_MS)

            agent._on_token = on_token
            agent._on_status = on_status
            result = agent.chat(user_input)
            # 流式模式下 accumulated 已有内容，用 result 兜底非流式情况
            final = accumulated[0] if has_streamed[0] else result
            self.pet.bubble_text_ready.emit(final, REPLY_BUBBLE_DURATION_MS)
        except Exception as e:
            err_msg = str(e)
            self.pet.bubble_text_ready.emit(f"错误: {err_msg}", REPLY_BUBBLE_DURATION_MS)
            print("[Peko API 错误]", err_msg)
            traceback.print_exc()
