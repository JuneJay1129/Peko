"""set_timer 工具：设置定时提醒，到时通过宠物气泡通知用户。"""
from __future__ import annotations
import threading
from typing import Callable, Optional
from .base import BaseTool, ToolResult

# 全局通知回调，由 pet.py 初始化时注入
_notify_callback: Optional[Callable[[str, int], None]] = None
_timer_start_callback: Optional[Callable[[float, str, float], None]] = None
_timer_fire_callback: Optional[Callable[[str], None]] = None


def set_notify_callback(callback: Callable[[str, int], None]) -> None:
    """注册通知回调：callback(message, duration_ms)。"""
    global _notify_callback
    _notify_callback = callback


def set_timer_start_callback(callback: Callable[[float, str, float], None]) -> None:
    """注册定时器启动回调：callback(end_time, message, total_minutes)。"""
    global _timer_start_callback
    _timer_start_callback = callback


def set_timer_fire_callback(callback: Callable[[str], None]) -> None:
    """注册定时器触发回调：callback(message)。"""
    global _timer_fire_callback
    _timer_fire_callback = callback


def _fire(msg: str) -> None:
    """定时器到期时在后台线程调用。
    PyQt5 的 QTimer.singleShot 静态方法会将 callable 投递到主线程事件循环，
    因此从后台线程调用是安全的。
    """
    cb_notify = _notify_callback
    cb_fire = _timer_fire_callback
    try:
        from PyQt5.QtCore import QCoreApplication, QTimer
        if QCoreApplication.instance() is not None:
            if cb_notify is not None:
                QTimer.singleShot(0, lambda m=msg: cb_notify(m, 8000))
            if cb_fire is not None:
                QTimer.singleShot(0, lambda m=msg: cb_fire(m))
        else:
            # 无 Qt 事件循环（测试环境），直接同步调用
            if cb_notify is not None:
                cb_notify(msg, 8000)
            if cb_fire is not None:
                cb_fire(msg)
    except Exception:
        pass


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
