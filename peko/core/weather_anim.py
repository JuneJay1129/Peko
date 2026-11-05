"""天气动作：中文天气现象 → 桌宠的天气动作，以及素材帧的发现。

为什么单独一层：`WeatherService` 只负责取数和文案（纯 Python、不依赖 Qt，
单测才好写），"播天气时该放哪套动作"属于表现层的事，放进去会把 Qt/宠物目录
一起拖进来。映射本身是纯函数，素材发现只碰文件系统，两边都能单测。

素材约定（每个宠物各自一份）：

    resource/weather/<action>/1.png, 2.png, ...

没有 weather 目录的宠物 = 不支持天气动作，播报时静默跳过，不影响其它功能。
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

# 播放中的临时动作名。以双下划线开头，和素材里配置的动作名错开，
# 同时要进 actions.constants.RESERVED_STATES，否则会被自动模式当成
# 普通动作随机抽到（播完就恢复，池子里不该留它）。
WEATHER_STATE = "__weather__"

# 六类动作，顺序即素材目录的优先级说明，和 pets/BB/resource/weather 一致
ACTIONS = ("clear", "cloudy", "rain", "heavy_rain", "snow", "thunder")

# 天气帧的播放节奏。素材是为"背景里持续下雨/下雪"画的循环，10fps 足够顺，
# 雪 15 帧 / 雷 6 帧也不会显出跳帧。
FRAME_RATE = 10

ACTION_LABELS: Dict[str, str] = {
    "clear": "晴",
    "cloudy": "阴",
    "rain": "雨",
    "heavy_rain": "大雨",
    "snow": "雪",
    "thunder": "雷",
}

# 关键词 → 动作。**顺序敏感**，和 WeatherService._advice 的判定顺序保持一致：
# 特殊现象先判定（雷 → 雪 → 冰雹 → 暴雨 → 雨），最后才是晴/阴。
# 单纯按"包含雨"先判的话，"雷阵雨"会被播成下雨，"雨夹雪"会丢雪。
_RULES = (
    ("雷", "thunder"),
    ("暴风雨", "thunder"),
    ("storm", "thunder"),
    ("雪", "snow"),
    ("sleet", "snow"),          # _cond_to_zh 已转成「雨夹雪」，这里兜英文原文
    ("冰雹", "heavy_rain"),
    ("hail", "heavy_rain"),
    ("暴雨", "heavy_rain"),
    ("大雨", "heavy_rain"),
    ("torrential", "heavy_rain"),
    ("雨", "rain"),
    ("rain", "rain"),
    ("drizzle", "rain"),
    ("shower", "rain"),
    ("晴", "clear"),
    ("clear", "clear"),
    ("sunny", "clear"),
    ("阴", "cloudy"),
    ("多云", "cloudy"),
    ("雾", "cloudy"),
    ("霾", "cloudy"),
    ("overcast", "cloudy"),
    ("cloudy", "cloudy"),
    ("fog", "cloudy"),
    ("haze", "cloudy"),
    ("mist", "cloudy"),
)


def action_for_condition(cond: Optional[str]) -> Optional[str]:
    """把天气现象转成动作名；认不出来（或降级估算没有现象）返回 None。

    返回 None 表示"这次不切动作"——本地估算（level=guess）本来就没有现象，
    硬塞一个「晴」上去会播报错的东西。
    """
    text = str(cond or "").strip().lower()
    if not text:
        return None
    for key, action in _RULES:
        if key in text:
            return action
    return None


def action_dir(pet_dir: Optional[str], action: Optional[str]) -> Optional[str]:
    """动作对应的素材目录；参数不全返回 None。"""
    if not pet_dir or not action:
        return None
    return os.path.join(str(pet_dir), "resource", "weather", str(action))


def frames_for(pet_dir: Optional[str], action: Optional[str]) -> List[str]:
    """按文件名里的数字顺序取帧（1.png, 2.png, … 10.png 不能按字典序排）。

    目录不存在、没有 png、参数不全都返回空列表，调用方据此跳过动作。
    """
    folder = action_dir(pet_dir, action)
    if not folder or not os.path.isdir(folder):
        return []

    def _num(name: str) -> int:
        stem = os.path.splitext(name)[0]
        return int(stem) if stem.isdigit() else 0

    names = [n for n in os.listdir(folder) if n.lower().endswith(".png")]
    names.sort(key=_num)
    return [os.path.join(folder, n) for n in names]
