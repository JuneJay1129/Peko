"""
特效装饰当前选择的持久化（config/effects.json）。

此前 tray.py 与 main.py 各自实现了这份读写（共 3 遍）；收敛为唯一入口，
今后新功能涉及持久化时直接走 config_store / 本模块模式。
"""
from __future__ import annotations

from .config_store import read_json, write_json

_PATH = "config/effects.json"


def get_current() -> str:
    """当前特效 key（'none' 表示关闭）；配置缺失/损坏时回退 'none'。"""
    data = read_json(_PATH) or {}
    current = data.get("current") if isinstance(data, dict) else None
    return current if isinstance(current, str) and current else "none"


def set_current(name: str) -> bool:
    """保存当前特效 key，返回是否写成功。"""
    return write_json(_PATH, {"current": name})
