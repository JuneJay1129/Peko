"""
天气查询工具 — 使用 wttr.in，无需 API Key。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List
from urllib.parse import quote

from .base import BaseTool, ToolResult

try:
    import requests
except ImportError:
    requests = None


class WeatherTool(BaseTool):
    name = "get_weather"
    description = (
        "查询指定城市的当前天气与未来几天预报。"
        "适合用户问「今天天气怎么样」「北京会下雨吗」等问题。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名称，如「北京」「上海」「深圳」",
            },
            "days": {
                "type": "integer",
                "description": "预报天数，1-3，默认 2",
                "default": 2,
            },
        },
        "required": ["city"],
    }

    _HEADERS = {
        "User-Agent": "Peko-Desktop-Pet/1.0",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    def execute(self, city: str, days: int = 2, **kwargs) -> ToolResult:
        if not requests:
            return ToolResult.fail("requests 库未安装，无法查询天气")
        if not city or not city.strip():
            return ToolResult.fail("城市名称不能为空")

        city = city.strip()
        days = max(1, min(int(days or 2), 3))
        try:
            data = self._fetch(city)
            text = self._format(city, data, days)
            return ToolResult.ok(text, data=data)
        except Exception as e:
            return ToolResult.fail(f"天气查询失败: {e}")

    def _fetch(self, city: str) -> Dict[str, Any]:
        url = f"https://wttr.in/{quote(city)}?format=j1&lang=zh"
        resp = requests.get(url, headers=self._HEADERS, timeout=12)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _format(city: str, data: Dict[str, Any], days: int) -> str:
        current_list = data.get("current_condition") or []
        if not current_list:
            raise ValueError("未获取到天气数据，请检查城市名称")
        cur = current_list[0]

        def _desc(block: Dict[str, Any]) -> str:
            desc = block.get("weatherDesc") or []
            if desc and isinstance(desc[0], dict):
                return str(desc[0].get("value", ""))
            return ""

        lines = [
            f"📍 {city} 天气",
            "",
            "【当前】",
            f"  天气：{_desc(cur)}",
            f"  气温：{cur.get('temp_C', '?')}°C（体感 {cur.get('FeelsLikeC', '?')}°C）",
            f"  湿度：{cur.get('humidity', '?')}%",
            f"  风速：{cur.get('windspeedKmph', '?')} km/h",
        ]

        forecast: List[Dict[str, Any]] = data.get("weather") or []
        if forecast:
            lines.append("")
            lines.append(f"【未来 {days} 天预报】")
            for day in forecast[:days]:
                date = day.get("date", "")
                max_t = day.get("maxtempC", "?")
                min_t = day.get("mintempC", "?")
                hourly = day.get("hourly") or []
                day_desc = _desc(hourly[4]) if len(hourly) > 4 else ""
                if not day_desc and hourly:
                    day_desc = _desc(hourly[0])
                lines.append(f"  {date}：{day_desc}，{min_t}°C ~ {max_t}°C")

        return "\n".join(lines)
