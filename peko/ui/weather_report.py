"""
天气播报入口：托盘菜单与聊天框共用。

- 缓存新鲜（30 分钟内）→ 同步播报，不联网，秒回。
- 否则先显示「正在查天气…」，再起子线程取数，结果通过 pet.bubble_stream_ready
  信号回主线程，用打字机（假流式）逐字显示——子线程直接改 UI 会崩，必须走信号。
- 首次用 IP 定位的城市，会在文案前先交代「我按网络猜你在 XX（IP 归属地…）」，
  并提示可用「我在宁波」纠正（之后不再重复提示）。
- 播报时顺手切到对应的天气动作（雨 / 雪 / 雷 / 晴 …，见 core.weather_anim），
  动作和气泡同期收起；宠物没有这套素材、或这次是本地估算（没有天气现象）
  时不动动作。
- 全程兜异常：天气拿不到也不会影响桌宠其它功能。
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from ..core.weather import WeatherService
from ..core.weather_anim import action_for_condition

BUBBLE_DURATION_MS = 8000   # 文案变长（4~6 行）+ 打字机耗时，停留久一点
WEATHER_ACTION_MS = 9000    # 天气动作比气泡稍长一点，免得文案还在打字就切回站姿


def _start_weather_action(pet: Any, data: Dict[str, Any]) -> None:
    """按天气现象切宠物动作。走信号，因为取数在子线程、直接改 UI 会崩。"""
    try:
        action = action_for_condition(data.get("cond"))
        if not action:
            return    # 估算/缓存里没有现象，别硬塞一个
        pet.weather_action_ready.emit(action, WEATHER_ACTION_MS)
    except Exception:
        pass


def _emit(pet: Any, svc: Optional[WeatherService], text: str, include_ip_hint: bool = True) -> None:
    """拼上 IP 定位提示（如有）后用打字机播报。include_ip_hint=False 时跳过提示
    （用于显式指定城市的查询：用户本就想看别的城市，没必要再交代默认定位）。"""
    try:
        if include_ip_hint and svc is not None:
            hint = svc.ip_location_line()
            if hint:
                svc.mark_announced()
                text = hint + "\n\n" + text
        pet.bubble_stream_ready.emit(text, BUBBLE_DURATION_MS)
    except Exception:
        try:
            pet.bubble_stream_ready.emit(text, BUBBLE_DURATION_MS)
        except Exception:
            pass


def report_weather(pet: Any, city: Optional[str] = None) -> None:
    """播报天气。

    - city 为 None：用默认（IP 定位/配置）城市；缓存新鲜同步秒回，否则异步取数。
    - city 指定：一次性查该城市，不改动默认城市配置、不写默认缓存、不弹 IP 定位提示。
    """
    try:
        svc = WeatherService()
        if city is None:
            cached = svc.load_cache()
            if svc.is_cache_fresh(cached):
                data = dict(cached or {})
                data["level"] = "cache"
                _start_weather_action(pet, data)
                _emit(pet, svc, svc.report(data), include_ip_hint=True)
                return
            pet.update_bubble("吱吱～正在帮你查天气…", 2500)
            threading.Thread(target=_fetch_and_report, args=(pet, svc, None), daemon=True).start()
        else:
            pet.update_bubble(f"吱吱～正在查{city}的天气…", 2500)
            threading.Thread(target=_fetch_and_report, args=(pet, svc, city), daemon=True).start()
    except Exception:
        try:
            pet.bubble_stream_ready.emit("哎呀，天气没查到，等会儿再试试～吱吱", 3000)
        except Exception:
            pass


def _fetch_and_report(pet: Any, svc: WeatherService, city: Optional[str]) -> None:
    data: Dict[str, Any] = {}
    try:
        data = svc.fetch(city=city, force=(city is not None))
        text = svc.report(data)
    except Exception:
        text = "哎呀，天气没查到，等会儿再试试～吱吱"
    _start_weather_action(pet, data)
    _emit(pet, svc, text, include_ip_hint=(city is None))
