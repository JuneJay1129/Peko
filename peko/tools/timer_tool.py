"""set_timer 工具：设置定时提醒，到时通过宠物气泡通知用户。"""
from __future__ import annotations
import threading
from typing import Callable, Optional
from .base import BaseTool, ToolResult

# 全局回调，由 pet.py 初始化时注入
# 注意：这些回调应该封装为 Qt signal.emit()，从后台线程调用是线程安全的
_notify_callback: Optional[Callable[[str, int], None]] = None
_timer_start_callback: Optional[Callable[[float, str, float], None]] = None
_timer_fire_callback: Optional[Callable[[str], None]] = None
_chat_message_callback: Optional[Callable[[str], None]] = None


def set_notify_callback(callback: Callable[[str, int], None]) -> None:
    global _notify_callback
    _notify_callback = callback


def set_timer_start_callback(callback: Callable[[float, str, float], None]) -> None:
    global _timer_start_callback
    _timer_start_callback = callback


def set_timer_fire_callback(callback: Callable[[str], None]) -> None:
    global _timer_fire_callback
    _timer_fire_callback = callback


def set_chat_message_callback(callback: Optional[Callable[[str], None]]) -> None:
    """注册对话框注入回调：callback(message)，定时器触发时向聊天窗口发一条提醒消息。"""
    global _chat_message_callback
    _chat_message_callback = callback


def _fire(msg: str) -> None:
    """定时器到期，在 threading.Timer 后台线程中调用。
    回调封装的是 Qt signal.emit()，PyQt5 会自动将跨线程 emit 转为 QueuedConnection，
    因此直接调用是安全的，不需要再包一层 QTimer.singleShot。
    """
    for cb, args in [
        (_notify_callback, (msg, 8000)),
        (_timer_fire_callback, (msg,)),
        (_chat_message_callback, (msg,)),
    ]:
        if cb is not None:
            try:
                cb(*args)
            except Exception as e:
                print(f"[timer_tool] callback error: {e}")


class SetTimerTool(BaseTool):
    name = "set_timer"
    description = (
        "设置一个定时提醒。到时间后宠物会弹出气泡通知用户。"
        "支持秒(seconds)、分钟(minutes)两种单位。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "seconds": {
                "type": "integer",
                "description": "定时秒数（和 minutes 二选一）",
            },
            "minutes": {
                "type": "integer",
                "description": "定时分钟数（和 seconds 二选一）",
            },
            "message": {
                "type": "string",
                "description": '提醒内容，例如"喝水时间到啦！"',
            },
        },
        "required": ["message"],
    }

    def execute(self, message: str = "", seconds: int = 0, minutes: int = 0, **kwargs) -> ToolResult:
        delay = int(seconds) + int(minutes) * 60
        if delay <= 0:
            return ToolResult.fail("请指定 seconds 或 minutes，且必须大于 0。")

        if delay > 7200:
            return ToolResult.fail("定时器最长支持 2 小时（120 分钟）。")

        # 人类可读的时间描述
        if delay >= 60:
            m, s = divmod(delay, 60)
            time_desc = f"{m}分{s}秒" if s else f"{m}分钟"
        else:
            time_desc = f"{delay}秒"

        import time as _time
        end_time = _time.time() + delay
        total_minutes = delay / 60.0

        def _do_fire():
            _fire(f"⏰ 提醒：{message}")

        t = threading.Timer(delay, _do_fire)
        t.daemon = True
        t.start()

        # 通知 UI 层定时器已启动（用于宠物倒计时显示）
        if _timer_start_callback:
            _timer_start_callback(end_time, message, total_minutes)

        return ToolResult.ok(f"已设置 {time_desc} 后提醒：「{message}」")
