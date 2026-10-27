"""
统一 JSON 配置读写门面（阶段 A 基建）。

此前各功能模块各自维护「get_writable_root + open + json.load/dump + try/except」
样板（effects.json 甚至被 main.py / tray.py 各自实现 3 遍）。新模块涉及持久化时优先走：

- read_json(rel_path, default)  — 读不到/损坏时返回 default，不抛异常
- write_json(rel_path, data)    — 自动建目录 + 临时文件原子替换，失败返回 False

目录语义约定（rel_path 首段）：
- config/  用户设置类：改了影响行为、可手工编辑（appearance / effects / api …）
- data/    运行状态类：程序自管、删了可再生（缓存 / 聊天记录 / 心情 / 台账 …）

纯 Python、不依赖 Qt，便于单元测试。rel_path 一律用 '/' 分隔（内部转 os.sep）。

现状（2026-10）：仅 effect_state.py 已迁入；appearance / mood / plans_store / weather /
config_loader 仍各自实现，迁移按需进行，不强求一次性铺开。
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Optional

from .runtime_paths import get_writable_root


def _abs_path(rel_path: str) -> str:
    return os.path.join(get_writable_root(module_file=__file__), *rel_path.split("/"))


def read_json(rel_path: str, default: Any = None) -> Any:
    """读取可写根目录下的 JSON；文件缺失/损坏/类型异常时返回 default。"""
    path = _abs_path(rel_path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(rel_path: str, data: Any) -> bool:
    """写入 JSON：先写临时文件再原子替换，避免写一半损坏配置。"""
    path = _abs_path(rel_path)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
        return True
    except Exception:
        return False
