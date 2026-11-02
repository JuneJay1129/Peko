"""
聊天模块：与宠物对话（输入框 + AI 回复 + 气泡展示）。
"""
import re
import threading
import time
import traceback
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .pet import DesktopPet

# 宠物回复/错误提示气泡展示时长（毫秒），可在此调整
REPLY_BUBBLE_DURATION_MS = 10000
# 流式增量的合并窗口（毫秒）：模型吐字再快也只是每 80ms 推一次，
# 避免每个 token 都跨线程打一发信号把主线程淹没；真正的显示节奏由气泡打字机控制
STREAM_FLUSH_INTERVAL_MS = 80

# 「忘掉之前聊的」类指令：本地清空对话记忆 + 长期记忆，不走 AI
# 要求动词后面紧跟记忆类名词，避免「清空待办」这类工作台指令被误伤
_FORGET_PATTERN = re.compile(
    r"(?:忘(?:掉|了|记)|清空|清除|删除|重置)[^，。！？,.!?]{0,8}"
    r"(?:记忆|对话|聊天|上下文|聊天记录|聊的)"
)


def is_forget_request(text: str) -> bool:
    """判断是否为「清空记忆」类指令。"""
    return bool(_FORGET_PATTERN.search(text or ""))


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
        text = (text or "").strip()
        if not text:
            return
        # 清空记忆：本地处理，不占用 AI 请求；放在意图识别之前，避免被当成别的指令
        if is_forget_request(text):
            self._forget_memory()
            return
        # C5：先尝试把这句话识别为「工作台写入」意图；命中则本地落盘并直接回复，不走 AI。
        try:
            from ..core import nl_intent
            intent = nl_intent.parse(text)
        except Exception:
            intent = None
        if intent is not None:
            action = intent.get("action")
            # 天气是只读查询 + 需联网，单独走异步播报，不进工作台写入流程
            if action == "ask_weather":
                try:
                    from .weather_report import report_weather
                    report_weather(self.pet)
                except Exception:
                    pass
                return
            # 显式指定城市的一次性查询（「帮我查看xx的天气」），不改默认城市
            if action == "ask_weather_city":
                try:
                    from .weather_report import report_weather
                    report_weather(self.pet, intent.get("city"))
                except Exception:
                    pass
                return
            # 纠正城市（IP 定位不准时）：本地写配置 + 打字机确认，不联网、不进工作台写入
            if action == "set_city":
                try:
                    from ..core.weather import WeatherService
                    svc = WeatherService()
                    msg = svc.set_city_by_user(intent.get("city") or "")
                    self.pet.bubble_stream_ready.emit(msg, REPLY_BUBBLE_DURATION_MS)
                except Exception:
                    self.pet.bubble_text_ready.emit("唔…城市没记住，等会儿再试试～", REPLY_BUBBLE_DURATION_MS)
                return
            # 安慰打气：压力/难过/被指责时的情绪陪伴；配了 AI 走个性化，否则用内置语库
            if action == "comfort":
                try:
                    self._handle_comfort(text)
                except Exception:
                    try:
                        self.pet.comfort()
                    except Exception:
                        pass
                return
            self._handle_workspace_intent(intent)
            return
        # 像命令但没写全（如「记一笔」缺金额）→ 给用法提示，不走 AI
        try:
            hint = nl_intent.suggest_usage(text)
        except Exception:
            hint = None
        if hint:
            self.pet.bubble_text_ready.emit(hint, REPLY_BUBBLE_DURATION_MS)
            return
        threading.Thread(target=self._fetch_response, args=(text,), daemon=True).start()

    def _forget_memory(self) -> None:
        """清空对话历史与长期记忆（两者都是本地文件，失败也不影响继续聊天）。"""
        try:
            from ..core import chat_store, user_memory

            chat_store.ChatStore().clear()
            user_memory.clear()
        except Exception:
            traceback.print_exc()
        self.pet.bubble_stream_ready.emit(
            "好，之前聊的我都忘掉啦，我们重新认识一下～", REPLY_BUBBLE_DURATION_MS
        )

    def _build_chat_messages(self, user_text: str, *, base_prompt: str, mood_context: str = ""):
        """组装本次请求的上下文：人设 + 状态 + 长期记忆 + 工作台摘要 + 最近对话。

        任何一环失败都退化为「无记忆的单轮对话」，不能让增强功能拖垮聊天。
        """
        from ..core import chat_store, context_builder, user_memory

        history = []
        try:
            history = chat_store.ChatStore().load_messages()
        except Exception:
            history = []
        system_prompt = context_builder.build_system_prompt(
            base_prompt,
            mood_context=mood_context,
            workspace_digest=context_builder.digest_workspace(),
            memory_text=user_memory.format_for_prompt(),
        )
        return context_builder.build_messages(user_text, system_prompt, history)

    def _remember_turn(self, user_text: str, reply: str) -> None:
        """把这一轮写进对话记忆，并从用户原话里抽取长期事实；失败不影响聊天。"""
        reply = (reply or "").strip()
        if not reply:
            return
        try:
            from ..core import chat_store, user_memory
        except Exception:
            return
        try:
            chat_store.ChatStore().append_turn(user_text, reply)
        except Exception:
            traceback.print_exc()
        try:
            learned = user_memory.remember_from(user_text)
            if learned:
                print("[Peko 记忆]", learned)
        except Exception:
            traceback.print_exc()

    def _handle_comfort(self, text: str) -> None:
        """安慰打气（对话式）：用桌宠气泡多轮引导倾诉；无 AI 也能用。"""
        self.pet.start_comfort_dialog(initial_hint=text)

    def _handle_workspace_intent(self, intent) -> None:
        """C5：执行自然语言 → 工作台写入；专注类额外用 QTimer 做结束提醒（记录已由 apply 落盘）。"""
        from ..core import nl_intent
        msg = nl_intent.apply(intent)
        if msg:
            self.pet.bubble_text_ready.emit(msg, REPLY_BUBBLE_DURATION_MS)
        if intent.get("action") == "start_focus":
            self._schedule_focus_reminder(int(intent.get("minutes") or 25))

    def _schedule_focus_reminder(self, minutes: int) -> None:
        try:
            from PyQt5.QtCore import QTimer
            ms = max(1, minutes) * 60 * 1000
            QTimer.singleShot(ms, lambda: self.pet.bubble_text_ready.emit(
                f"专注 {minutes} 分钟到啦，去「专注」模块打个卡吧～", REPLY_BUBBLE_DURATION_MS))
        except Exception:
            pass

    def _fetch_response(self, user_input: str) -> None:
        """子线程中调用 AI，结果通过气泡打字机展示；成功才把这一轮写进记忆。"""
        try:
            from ..ai.service import stream_chat, validate_ai_config
            character = self.pet.character
            base_prompt = character.get("systemPrompt") or (
                "你是一个可爱的桌面宠物，用简短、友好的话回复用户。"
            )
            mood_context = ""
            if hasattr(self.pet, "get_chat_context"):
                mood_context = self.pet.get_chat_context()
            if not validate_ai_config():
                self.pet.bubble_text_ready.emit(
                    "AI 闲聊还没开放哦～可以点输入框上方的「记支出 / 记收入 / 待办 / 专注」快捷按钮，"
                    "或直接说「记一笔 支出 午饭 38」这样的指令，我马上帮你记录。",
                    REPLY_BUBBLE_DURATION_MS,
                )
                return
            messages = self._build_chat_messages(
                user_input, base_prompt=base_prompt, mood_context=mood_context
            )
            # 流式增量交给气泡的打字机队列：reset=True 表示这是新一轮回复的开头。
            # 这里只按时间窗口合并增量，显示快慢由 bubbles.CHAT_STREAM_TYPING_MS 决定。
            state = {"first": True, "last_flush": 0.0}
            pending = []
            received = []

            def flush():
                if not pending:
                    return
                delta = "".join(pending)
                pending.clear()
                self.pet.bubble_chat_stream.emit(
                    delta, state["first"], REPLY_BUBBLE_DURATION_MS
                )
                state["first"] = False

            def on_token(token: str):
                received.append(token)
                pending.append(token)
                now = time.monotonic()
                if (now - state["last_flush"]) * 1000 >= STREAM_FLUSH_INTERVAL_MS:
                    state["last_flush"] = now
                    flush()

            stream_chat(messages, on_token=on_token)
            flush()  # 收尾：把最后不足一个窗口的尾巴也推出去
            self._remember_turn(user_input, "".join(received))
        except Exception as e:
            err_msg = str(e)
            self.pet.bubble_text_ready.emit(f"错误: {err_msg}", REPLY_BUBBLE_DURATION_MS)
            print("[Peko API 错误]", err_msg)
            traceback.print_exc()
