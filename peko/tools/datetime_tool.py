"""get_datetime 工具：返回当前日期和时间。"""
from __future__ import annotations
from datetime import datetime
from .base import BaseTool, ToolResult


class GetDatetimeTool(BaseTool):
    name = "get_datetime"
    description = "获取当前日期和时间，返回本地时间的年月日、星期几、时分秒。"
    parameters = {}

    def execute(self, **kwargs) -> ToolResult:
        now = datetime.now()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        wd = weekdays[now.weekday()]
        text = (
            f"当前时间：{now.strftime('%Y年%m月%d日')} {wd} "
            f"{now.strftime('%H:%M:%S')}"
        )
        return ToolResult.ok(text)
